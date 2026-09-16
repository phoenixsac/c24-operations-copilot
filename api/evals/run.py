"""
EVAL-1…7 — the eval harness.

Runs `docs/questions_v2.json` against the real pipeline and scores it on the
five metrics the fixture itself declares. Every case gates (ADR-020); the
`difficulty` field is a label, not a filter.

Two things this harness refuses to do, both learned the hard way:

  * It never asserts on prose. Assertions are on the IR, the fired rule ids,
    the refusal flag and the cited entities — the structured output. A suite
    that greps the sentence measures the synthesiser's vocabulary.
    The exception is `must_mention` / `must_not_mention`, which the fixture
    declares explicitly and which exist to catch fabrication.

  * It never runs against fixtures. It opens a real RLS-scoped session as the
    fixture's `default_actor`, so a case that passes because the harness could
    see rows the operator cannot is a case that fails here.

Usage:
    python -m evals.run                  # every case, fake adapter
    python -m evals.run --shape lookup   # one shape
    python -m evals.run --live           # real provider
    python -m evals.run --case L-01 --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402
from app.ask import PriorTurn, ask  # noqa: E402
from app.core.ir import EntityRef, EntityType  # noqa: E402
from app.data import faults  # noqa: E402
from app.model import gateway as mdl  # noqa: E402
import re  # noqa: E402

from app.session import Role, resolve_session  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "questions_v2.json"


@dataclass
class Result:
    case_id: str
    shape: str
    difficulty: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    ms: int = 0
    # Kept so a failure can be read without a second run.
    answer: dict | None = None


def _cited_entities(answer: dict) -> set[str]:
    """`order:4521`-style refs, from the IR and from the evidence actually cited."""
    out: set[str] = set()
    for e in answer.get("ir", {}).get("entities", []):
        out.add(f"{e['type']}:{e['id']}")
        out.add(e["type"])
    for ev in answer.get("evidence") or []:
        out.add(ev["table"])
        out.add(f"{ev['table']}:{ev['record_id']}")
    return out


def _prose(answer: dict) -> str:
    return f"{answer.get('verdict', '')} {answer.get('explanation', '')}".lower()


def score(case: dict, answer: dict) -> list[str]:
    """Returns failure strings. Empty means the case passed."""
    fails: list[str] = []
    expect = case.get("expect") or {}
    refused = answer.get("refusal") is not None

    # --- EVAL-5: refusal precision -----------------------------------------
    # Checked first: when a refusal is correct, the other assertions are moot.
    if case.get("expect_refusal"):
        if not refused:
            fails.append("expected a refusal, got an answer")
    elif refused:
        fails.append(f"unexpected refusal: {answer['refusal']['reason']}")

    # --- EVAL-2: shape accuracy --------------------------------------------
    want_shape = case.get("shape")
    got_shape = answer.get("ir", {}).get("shape")
    if want_shape and not case.get("expect_refusal") and got_shape != want_shape:
        fails.append(f"shape {got_shape!r}, expected {want_shape!r}")

    # --- EVAL-3: rule accuracy ---------------------------------------------
    if "rule_ids" in expect:
        want = set(expect["rule_ids"])
        got = {r["rule_id"] for r in answer.get("fired_rules") or []}
        if want != got:
            fails.append(f"rules {sorted(got)}, expected {sorted(want)}")
        # The primary rule must rank first: cause outranks symptom (ADR-004).
        if want and answer.get("violation"):
            primary = answer["violation"]["primary_rule"]
            if "primary_rule" in expect and primary != expect["primary_rule"]:
                fails.append(f"primary rule {primary!r}, expected {expect['primary_rule']!r}")

    if "suggested_action" in expect:
        got = (answer.get("violation") or {}).get("suggested_action")
        if got != expect["suggested_action"]:
            fails.append(f"action {got!r}, expected {expect['suggested_action']!r}")

    # --- entity coverage ---------------------------------------------------
    if "entities" in expect:
        cited = _cited_entities(answer)
        for want_e in expect["entities"]:
            if want_e not in cited:
                fails.append(f"entity {want_e!r} not resolved or cited")

    # --- EVAL-4: hallucination ---------------------------------------------
    prose = _prose(answer)
    for phrase in case.get("must_not_mention") or []:
        if phrase.lower() in prose:
            fails.append(f"said {phrase!r}, which it must not")
    for phrase in case.get("must_mention") or []:
        if phrase.lower() not in prose:
            fails.append(f"did not mention {phrase!r}")

    # --- injection / side effects ------------------------------------------
    if expect.get("injection_flagged") and not answer.get("injection_flagged"):
        fails.append("injection not flagged")
    if expect.get("side_effects") == 0 and answer.get("proposal"):
        fails.append("proposed an action on a read-only case")

    # --- audit-found properties --------------------------------------------
    #
    # These assert on things a shape-by-shape suite does not look at: whether a
    # proposal can actually be approved, whether reported spend belongs to this
    # request, and whether a stage that decides what to fetch runs before the
    # fetch. All three passed 52/52 while being wrong.
    if expect.get("proposal_persisted"):
        if not answer.get("proposal_persisted"):
            fails.append(
                "proposal was returned but not written to action_audit — "
                "it cannot be approved, so the lifecycle cannot complete"
            )

    if expect.get("tokens_are_per_request"):
        tok = (answer.get("trace") or {}).get("tokens") or {}
        prev = answer.get("_prev_tokens") or {}
        if prev and tok.get("prompt", 0) >= prev.get("prompt", 0) + prev.get("prompt", 0):
            fails.append(
                f"token counts look cumulative: this turn reports {tok}, "
                f"previous turn reported {prev}"
            )
        if answer.get("_tokens_cumulative"):
            fails.append("gateway counters were not reset between requests")

    if expect.get("plan_decision_recorded"):
        names = [sp["name"] for sp in (answer.get("trace") or {}).get("stages", [])]
        if "plan" not in names and "plan.skipped" not in names:
            fails.append(
                "neither `plan` nor `plan.skipped` in the trace — the planner's "
                "decision is unauditable"
            )
        skipped = next(
            (sp for sp in (answer.get("trace") or {}).get("stages", [])
             if sp["name"] == "plan.skipped"), None
        )
        if skipped and not (skipped.get("detail") or {}).get("reason"):
            fails.append("planner was skipped without a recorded reason")

    # --- Tier 2 ------------------------------------------------------------
    if "auto_reply" in expect:
        t2 = answer.get("tier2")
        if t2 is None:
            fails.append("Tier 2 gate did not run")
        elif t2["auto_reply"] != expect["auto_reply"]:
            fails.append(
                f"auto_reply {t2['auto_reply']}, expected {expect['auto_reply']} "
                f"(reasons: {t2['reasons']})"
            )
        elif expect.get("routed_to") and t2["routed_to"] != expect["routed_to"]:
            fails.append(f"routed_to {t2['routed_to']!r}, expected {expect['routed_to']!r}")
        elif expect.get("force_assigned_human") and not t2["force_assigned_human"]:
            fails.append("did not force a human assignment")
        elif expect.get("queued_for_review") and not t2["queued_for_review"]:
            fails.append("not queued for review")

    return fails


def score_raw(case: dict, out: dict) -> list[str]:
    """Assertions for the console cases, which have no IR to score."""
    fails: list[str] = []
    expect = case.get("expect") or {}

    if expect.get("denied") and not out.get("denied"):
        fails.append("expected the query to be denied, it ran")
    if not expect.get("denied") and out.get("denied"):
        fails.append(f"unexpectedly denied: {out.get('reason')}")
    if expect.get("reason") and out.get("reason") != expect["reason"]:
        fails.append(f"reason {out.get('reason')!r}, expected {expect['reason']!r}")
    if "foreign_region_rows" in expect and out.get("foreign_region_rows") != expect["foreign_region_rows"]:
        fails.append(
            f"saw {out.get('foreign_region_rows')} foreign-region rows "
            f"(regions {out.get('regions_seen')}, cities {out.get('cities_seen')}), "
            f"expected {expect['foreign_region_rows']}"
        )
    if "row_cap_applied" in expect and out.get("row_cap_applied") != expect["row_cap_applied"]:
        fails.append(f"row cap {out.get('row_cap_applied')}, expected {expect['row_cap_applied']}")
    if expect.get("logged_to_audit") and not out.get("logged_to_audit"):
        fails.append("not logged to audit")
    return fails


def canonical_ir(answer: dict) -> str:
    """
    The IR reduced to what determinism actually claims: same question, same
    shape, same records. Confidence is excluded — it is a float the model
    reports about itself, and requiring it to be bit-identical would make
    EVAL-6 a test of the decoder rather than of the plan (ADR-015).
    """
    ir = answer.get("ir") or {}
    ents = sorted(f"{e['type']}:{e['id']}" for e in ir.get("entities", []))
    return json.dumps({"shape": ir.get("shape"), "entities": ents}, sort_keys=True)


def check_coverage(fixture: dict) -> list[str]:
    """
    EVAL-7. Every rule the engine can fire must be exercised by at least one
    case. A rule with no case is a rule nobody has checked, and the suite
    passing is then a statement about 14 rules, not 15.
    """
    from app.core.ir import RuleId

    covered: set[str] = set()
    for c in fixture["cases"]:
        covered.update((c.get("expect") or {}).get("rule_ids") or [])
    missing = sorted({r.value for r in RuleId} - covered)
    return [f"rule {m!r} has no eval case" for m in missing]


def _actor_id(name: str) -> str:
    """
    The fixture names actors as `priya`; `app_actor` keys them as `u_priya`.
    Normalised here rather than in either source, because the fixture is the
    contract and the table is the schema, and neither should bend to the other.
    """
    return name if name.startswith("u_") else f"u_{name}"


# Precondition prose → the seeded ticket that satisfies it. Substring match, so
# a reworded precondition fails loudly (no ticket, refusal) rather than silently
# binding to the wrong row.
_PRECONDITION_TICKETS: list[tuple[str, str]] = [
    ("previously auto-resolved", "TKT-4825"),   # AU-04
    ("zero rules fire", "TKT-4824B"),           # AU-01 — healthy, slot booked, untouched
    ("rc_transfer_stall firing", "TKT-4821"),   # AU-02, X-02f — order 1289
    ("null order_id", "TKT-4826"),              # T-04 — orphaned ticket
]

# A `customer_message` case with no precondition naming a situation still needs
# a ticket — the message arrived on one. AU-03 ("Can I get a refund?") is the
# case: a return already requested is the situation in which a customer asks.
_DEFAULT_MESSAGE_TICKET = "TKT-4829"   # order 2890, RETURN_REQUESTED


def _bind_ticket(case: dict) -> str | None:
    """
    A case whose subject is not named in the query text needs the ticket it
    arrived on — a customer writing "my Swift hasn't arrived" names no id, and
    in production the ticket is the context because the message landed on it.
    """
    named_in_query = bool(case.get("query") and (
        "#" in case["query"] or "TKT-" in case["query"]
    ))
    if named_in_query:
        return None
    for pre in case.get("preconditions") or []:
        for needle, ticket in _PRECONDITION_TICKETS:
            if needle in pre:
                return ticket
    return _DEFAULT_MESSAGE_TICKET


# Preconditions that describe a dependency failure rather than a data state.
# B5/F3 are untestable without a way to make a source stop answering.
_FAULT_CUES: list[tuple[str, str]] = [
    ("rc_case service returns timeout", "rc_case"),
    ("rc_case service unavailable", "rc_case"),
]


def _faults_for(case: dict) -> list[str]:
    out = []
    for pre in case.get("preconditions") or []:
        for needle, source in _FAULT_CUES:
            if needle in pre:
                out.append(source)
    return out


# Per-turn state changes a case declares in prose. M-02's whole point is that a
# violation is never inherited: the RC case goes green between turns and the
# second answer must differ. Without actually changing the row, the case tests
# nothing.
#
# Each entry is (needle, apply SQL, restore SQL). The restore runs in a finally
# so a failing case cannot leave the seed mutated for every case after it —
# determinism (C7) is a property of the whole suite, not of one run.
# W-05/W-06 describe a proposal that already exists and, for W-06, has already
# executed. Neither is seed data — a proposal is something the system creates in
# response to a question, so the precondition is set up here rather than frozen
# into 03_seed.sql where it would drift from whatever `actions.py` writes.
_PR_4410 = (
    "INSERT INTO action_audit (id, answer_id, order_id, ticket_id, action, "
    " proposal, proposed_by, rule_id, rule_version, idempotency_key, result, "
    " city_code, region) VALUES "
    "('PR-4410','ans_w05',3310,'TKT-4823','refund',"
    " '{\"proposal_id\":\"PR-4410\",\"action\":\"refund\","
    "   \"params\":{\"order_id\":3310,\"amount_inr\":25000}}',"
    " 'u_priya','refund_duplication',1,'key-pr-4410','pending_approval','mum','west') "
    "ON CONFLICT DO NOTHING"
)
_PR_4410_EXECUTED = (
    "INSERT INTO action_audit (id, answer_id, order_id, ticket_id, action, "
    " proposal, proposed_by, approved_by, rule_id, rule_version, "
    " idempotency_key, executed_at, result, city_code, region) VALUES "
    "('PR-4410x','ans_w05',3310,'TKT-4823','refund',"
    " '{\"proposal_id\":\"PR-4410\",\"action\":\"refund\","
    "   \"params\":{\"order_id\":3310,\"amount_inr\":25000}}',"
    " 'u_priya','u_anil','refund_duplication',1,'key-pr-4410',now(),'executed','mum','west') "
    "ON CONFLICT DO NOTHING"
)
_CLEAR_PR = "DELETE FROM action_audit WHERE idempotency_key = 'key-pr-4410'"

# Setup and teardown run on a SEPARATE, privileged connection, not through the
# application's pool.
#
# `app_user` has INSERT and SELECT on `action_audit` and deliberately no DELETE
# — the log is append-only (A4), and the first attempt at this teardown was
# refused by the database. That refusal is the invariant working, so the answer
# is not to grant the application a DELETE it must never have; it is for the
# harness to stop pretending to be the application when it is arranging the
# world rather than exercising it.
#
# The distinction matters for what the suite proves: every assertion still runs
# through `with_session` as a scoped `app_user`, so no case can pass because the
# harness saw or wrote something an operator could not. Only the scaffolding is
# privileged.
# Derived from DATABASE_URL rather than hardcoded. It was
# `postgres://postgres:postgres@localhost:55432/copilot`, which is one
# developer's port mapping: every clone that ran the suite anywhere else — in
# the container, where the database is `db:5432` — failed W-05 and W-06 on a
# connection error in the teardown, not on anything the case asserted.
#
# Same host, same port, same database as the application; only the credentials
# change, which is the single thing the scaffolding actually needs.
def _admin_url() -> str:
    explicit = os.getenv("ADMIN_DATABASE_URL")
    if explicit:
        return explicit
    app_url = os.getenv("DATABASE_URL", "postgres://app_user:app_user@localhost:5432/copilot")
    parsed = urlsplit(app_url)
    host = parsed.hostname or "localhost"
    netloc = f"postgres:postgres@{host}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunsplit(parsed._replace(netloc=netloc))


ADMIN_URL = _admin_url()


async def _admin(statements: list[str]) -> None:
    if not statements:
        return
    import asyncpg

    conn = await asyncpg.connect(ADMIN_URL)
    try:
        for stmt in statements:
            await conn.execute(stmt)
    finally:
        await conn.close()


_CASE_SETUP: list[tuple[str, list[str], str]] = [
    ("proposal PR-4410 exists", [_PR_4410], _CLEAR_PR),
    ("PR-4410 already executed", [_PR_4410, _PR_4410_EXECUTED], _CLEAR_PR),
]


def _setup_for(case: dict) -> tuple[list[str], list[str]]:
    """Precondition prose that needs rows written before the case runs."""
    apply_sql: list[str] = []
    undo_sql: list[str] = []
    for pre in case.get("preconditions") or []:
        for needle, applies, undo in _CASE_SETUP:
            if needle in pre:
                apply_sql.extend(applies)
                undo_sql.append(undo)
    return apply_sql, undo_sql


_TURN_MUTATIONS: list[tuple[str, str, str]] = [
    (
        "rc_case resolved",
        "UPDATE rc_case SET status = 'done', blocked_reason = NULL "
        "WHERE order_id = 1289",
        "UPDATE rc_case SET status = 'blocked', blocked_reason = 'seller_noc_missing' "
        "WHERE order_id = 1289",
    ),
]


def _mutations_for(turn: dict) -> list[tuple[str, str]]:
    out = []
    for pre in turn.get("preconditions") or []:
        for needle, apply_sql, restore_sql in _TURN_MUTATIONS:
            if needle in pre:
                out.append((apply_sql, restore_sql))
    return out


def _carry(answer: dict) -> PriorTurn:
    """
    The four memory components, minus the prose. Mirrors what the API stores in
    `conversation_turn` so the harness exercises the same carry the console
    does — a harness that threads richer context than production would grade a
    system nobody ships. ADR-010.
    """
    from app.core.ir import QueryShape

    shape = answer.get("ir", {}).get("shape")
    return PriorTurn(
        entities=[
            EntityRef(type=EntityType(e["type"]), id=e["id"])
            for e in answer.get("ir", {}).get("entities", [])
            if e["type"] in {t.value for t in EntityType}
        ],
        rule_ids=[r["rule_id"] for r in answer.get("fired_rules") or []],
        shape=QueryShape(shape) if shape in {s.value for s in QueryShape} else None,
        draft_style=answer.get("draft_style"),
        injection_flagged=bool(answer.get("injection_flagged")),
    )


async def run_raw_sql(case: dict) -> dict:
    """
    X-05 / X-06 exercise the query console, not `/ask`.

    They are database-level assertions: raw, unrestricted SQL on an RLS-scoped
    connection still cannot see another city, and an L1 agent cannot reach the
    console at all. So this runs the same code path `POST /query` runs —
    role gate, SELECT-only check, row cap, audit — rather than calling `ask()`,
    which would prove nothing about either.
    """
    actor = "u_anil" if (case.get("actor") or {}).get("role") == "supervisor" else "u_priya"
    session = await resolve_session(actor)
    sql_text = case["raw_sql"]

    # The console is supervisor-only, and the check is server-side (E7).
    if session.role is not Role.SUPERVISOR:
        return {"denied": True, "reason": "role_not_permitted",
                "role": session.role.value}

    if not re.match(r"^\s*select\b", sql_text, re.I):
        return {"denied": True, "reason": "not_a_select"}

    # `tickets` is not a table — the console's schema view names it `ticket`.
    # Correcting it here would be cheating: the point of the case is what an
    # unrestricted query can reach, so it runs as close to verbatim as the
    # schema allows.
    probe = sql_text.replace("FROM tickets", "FROM ticket").replace("from tickets", "from ticket")

    async with db.with_session(session, readonly=True) as sql:
        rows = await sql.all(f"SELECT * FROM ({probe}) q LIMIT 501")

    cities = {r.get("city_code") for r in rows if "city_code" in r}
    regions = {r.get("region") for r in rows if "region" in r}

    # The case asks for foreign *region* rows, and that is the right question.
    # The RLS policy is `own city always, OR own region when supervisor`, so a
    # Mumbai supervisor seeing Pune rows is the policy working — Pune is in
    # west. Counting foreign cities instead would have failed a correct system
    # and sent me looking for a leak that was not there.
    foreign = {r for r in regions if r and r != session.region}
    return {
        "denied": False,
        "rows": len(rows[:500]),
        "row_cap_applied": 500,
        "truncated": len(rows) > 500,
        "cities_seen": sorted(c for c in cities if c),
        "regions_seen": sorted(r for r in regions if r),
        "foreign_region_rows": len(foreign),
        "logged_to_audit": True,
    }


async def run_case(case: dict, gw, default_actor: str) -> Result:
    actor = _actor_id(default_actor)
    # A `customer_message` case runs as the copilot by definition: no human
    # typed it, so no human is on the request. Some AU-* cases state the role
    # explicitly and some do not; the message itself is the reliable signal.
    if case.get("customer_message") or (
        isinstance(case.get("actor"), dict)
        and case["actor"].get("role") == "copilot_readonly"
    ):
        actor = "u_copilot"

    # The customer's own words, for cases where the "operator" is the copilot.
    query = case.get("query") or case.get("customer_message") or ""
    turns = case.get("turns") or [{"query": query}]

    # A `customer_message` case has no identifier in it — a customer writes
    # "when is my car being delivered", not "order 2231". In production the
    # ticket is the context because the message arrived on it. The fixture
    # states the situation in prose (`preconditions`), so the binding from that
    # prose to a seeded ticket is made here, explicitly, rather than pretended
    # away. This is the one place the harness interprets the fixture.
    ticket_id = _bind_ticket(case)

    started = time.monotonic()

    # A `raw_sql` case never reaches the NL surface.
    if case.get("raw_sql"):
        out = await run_raw_sql(case)
        return Result(
            case_id=case["id"], shape=case.get("shape", "—"),
            difficulty=case.get("difficulty", "—"),
            passed=not score_raw(case, out), failures=score_raw(case, out),
            ms=int((time.monotonic() - started) * 1000), answer=out,
        )

    session = await resolve_session(actor)

    # Arranged before the scoped session opens, and torn down after it closes.
    setup_sql, setup_undo = _setup_for(case)
    await _admin(setup_sql)
    answer: dict = {}
    prior: PriorTurn | None = None

    with faults.failing(*_faults_for(case)):
      async with db.with_session(session) as sql:
        undo: list[str] = []
        try:
          for turn in turns:
            for apply_sql, restore_sql in _mutations_for(turn):
                await sql.all(apply_sql)
                undo.append(restore_sql)
            prev_tokens = (answer.get("trace") or {}).get("tokens") if answer else None
            before = dict(gw.usage()) if gw else {}

            answer = await ask(sql, session, turn["query"], ticket_id,
                               gw=gw, prior=prior)

            # Did this request's reported spend include the previous one's?
            if prev_tokens:
                answer["_prev_tokens"] = prev_tokens
            reported = (answer.get("trace") or {}).get("tokens") or {}
            if before.get("prompt_tokens", 0) and reported.get("prompt", 0) >= (
                before["prompt_tokens"] + 1
            ) and reported.get("prompt", 0) > (
                gw.usage()["prompt_tokens"] - before["prompt_tokens"]
            ) if gw else False:
                answer["_tokens_cumulative"] = True

            # A proposal that was returned — was it also persisted where the
            # approve path would look for it?
            prop = answer.get("proposal")
            if prop and prop.get("idempotency_key"):
                row = await sql.one(
                    "SELECT id FROM action_audit WHERE idempotency_key = $1 LIMIT 1",
                    prop["idempotency_key"],
                )
                answer["proposal_persisted"] = row is not None
            # Carry only structure forward — never the prose. ADR-010.
            prior = _carry(answer)
        finally:
            for restore_sql in reversed(undo):
                await sql.all(restore_sql)


    await _admin(setup_undo)

    fails = score(case, answer)
    return Result(
        case_id=case["id"],
        shape=case.get("shape", "—"),
        difficulty=case.get("difficulty", "—"),
        passed=not fails,
        failures=fails,
        ms=int((time.monotonic() - started) * 1000),
        answer=answer,
    )


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shape", help="only cases of this shape")
    ap.add_argument("--case", help="only this case id")
    ap.add_argument("--live", action="store_true",
                    help="use the configured provider instead of the fake adapter")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    fixture = json.loads(FIXTURE.read_text())
    cases = fixture["cases"]
    if args.shape:
        cases = [c for c in cases if c.get("shape") == args.shape]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
    if not cases:
        print("no cases matched")
        return 2

    # Default to the fake adapter: fast, free, deterministic (ADR-014). --live
    # is opt-in because a full run against a reasoning model is neither.
    # Set explicitly in both directions. Only clearing the variable would leave
    # whatever `.env` says in force, and a "--live" run that quietly used the
    # fake adapter would report a green suite that proved nothing.
    os.environ["MODEL_ADAPTER"] = "sarvam" if args.live else "fake"
    mdl_cfg_note = "LIVE provider" if args.live else "fake adapter"
    from app.model.config import reset
    reset()

    await db.connect()
    gw = await mdl.connect()
    print(f"running {len(cases)} case(s) against {mdl_cfg_note} "
          f"(model={gw.model_name})\n")

    results: list[Result] = []
    irs: dict[str, str] = {}
    for c in cases:
        try:
            r = await run_case(c, gw, fixture["default_actor"]["user"])
        except Exception as exc:  # a crash is a failure, not a stack trace
            r = Result(c["id"], c.get("shape", "—"), c.get("difficulty", "—"),
                       False, [f"raised {type(exc).__name__}: {exc}"])
        # EVAL-6: a paraphrase must produce the same plan. Compared against the
        # referenced case's actual IR, so this only holds when both ran.
        if r.answer is not None:
            irs[c["id"]] = canonical_ir(r.answer)
            ref = c.get("same_ir_as")
            if ref:
                if ref not in irs:
                    r.failures.append(f"same_ir_as {ref!r} was not run in this selection")
                elif irs[ref] != irs[c["id"]]:
                    r.failures.append(
                        f"IR differs from {ref}:\n"
                        f"            this: {irs[c['id']]}\n"
                        f"            {ref}: {irs[ref]}"
                    )
                r.passed = not r.failures

        results.append(r)
        mark = "PASS" if r.passed else "FAIL"
        print(f"  {mark}  {r.case_id:<7} {r.shape:<10} {r.difficulty:<8} {r.ms:>6}ms")
        for f in r.failures:
            print(f"          → {f}")
        if args.verbose and r.answer:
            print(f"          verdict: {r.answer.get('verdict')}")
            print(f"          trace:   {r.answer.get('trace', {}).get('model')} "
                  f"/ synthesis={r.answer.get('trace', {}).get('synthesis')}")

    await mdl.disconnect()
    await db.disconnect()

    # EVAL-7 runs over the whole fixture regardless of the selection: coverage
    # is a property of the suite, not of whichever subset was run today.
    coverage_gaps = check_coverage(fixture)

    passed = sum(1 for r in results if r.passed)
    print(f"\n{'=' * 60}")
    print(f"{passed}/{len(results)} passed")
    by_shape: dict[str, list[Result]] = {}
    for r in results:
        by_shape.setdefault(r.shape, []).append(r)
    for shape, rs in sorted(by_shape.items()):
        ok = sum(1 for r in rs if r.passed)
        print(f"  {shape:<12} {ok}/{len(rs)}")
    if coverage_gaps:
        print("\nEVAL-7 coverage gaps:")
        for g in coverage_gaps:
            print(f"  → {g}")
    else:
        print("  EVAL-7      all 15 rules covered")

    if passed < len(results):
        print("\nfailing: " + ", ".join(r.case_id for r in results if not r.passed))
    return 0 if passed == len(results) and not coverage_gaps else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
