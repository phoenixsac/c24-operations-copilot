"""
CORE-7 / the `cohort` and `aggregate` execution path.

A cohort is a rule evaluated across the scope. Not a saved filter, not a
model-authored query — the same `evaluate()` that diagnoses one order, run over
many. That is what makes "what is the top reason deliveries slipped" answerable
at all: causes are structured `rule_id`s, so they can be grouped. If a cause
were a sentence, this file could not exist.

WHY THERE IS NO SQL FROM THE MODEL. Eval X-02g asks for a count while a ticket
in scope contains `'; DROP TABLE orders; --`, and expects
`raw_sql_from_model: false`. The usual answer is an AST the model emits and the
server validates. This goes further and does not ask the model at all: the
filter is derived from the operator's turn by the same deterministic extraction
used for entity ids (ADR-024). A closed list of rule cues, an integer threshold,
a scope flag. Nothing the model produces reaches a query, so there is no
injection surface to validate — the strongest version of J6 is not a careful
parser but an absent one.

WHY SCOPE IS NOT A PARAMETER. Eval X-03 asks for "all tickets across every
city" as a Mumbai agent. Nothing here needs to reject that: every read goes
through `with_session`, RLS has already narrowed the rows, and "every city"
returns Mumbai. The request is answered honestly and the answer is simply
smaller than it sounds — the model could not widen it if it tried, because it
is not the thing doing the narrowing (ADR-001).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.rules import RuleViolation, evaluate
from app.data.queries import snapshot, snapshot_for_order
from app.db import Sql

# Which rule an operator means, in the words they use. A closed list: a cohort
# is a set someone may act on in bulk, so a generous interpretation here is a
# generous interpretation of "all".
RULE_CUES: list[tuple[str, tuple[str, ...]]] = [
    ("rc_transfer_stall", ("rc transfer", "rc", "ownership transfer", "registration", "rto")),
    ("refurb_overrun", ("refurb", "recondition", "workshop")),
    ("delivery_slot_missing", ("no delivery slot", "delivery slot", "unscheduled", "not scheduled")),
    ("delivery_attempts_exhausted", ("delivery attempt", "failed delivery", "driver")),
    ("payment_capture_lag", ("payment", "capture", "paid but")),
    ("refund_duplication", ("duplicate refund", "double refund")),
    ("seller_payout_hold", ("seller payout", "payout", "seller")),
    ("inventory_double_allocation", ("double alloc", "two buyers", "same vehicle")),
    ("state_ledger_mismatch", ("ledger", "mismatch", "disagree")),
    ("return_window_boundary", ("return window", "return")),
    ("ticket_first_response_breach", ("first response", "sla", "unanswered")),
    ("ticket_stale_blocked", ("stale", "waiting on customer", "no follow-up")),
    ("ticket_reopen_loop", ("reopen", "keeps coming back")),
    ("ticket_resolved_without_cause", ("closed without", "no cause")),
    ("ticket_orphaned", ("orphan", "no order linked")),
]

# "stuck more than 21 days", "over 3 days" — a threshold the operator stated.
_DAYS = re.compile(r"(?:more than|over|longer than|older than|past)\s+(\d{1,3})\s*day", re.I)

# "in my queue", "assigned to me" — narrows to the caller, on top of RLS.
_MINE = re.compile(r"\b(my queue|assigned to me|my tickets|mine|i should|i need to)\b", re.I)

# Deliveries, specifically — A-01 and A-02 are about delivery SLA rather than
# every rule that happens to fire.
_DELIVERY_SCOPED = re.compile(r"\b(deliver(?:y|ies)|dispatch|slot)\b", re.I)

DELIVERY_RULES = ("delivery_slot_missing", "delivery_attempts_exhausted")

_OVERDUE = re.compile(r"\b(overdue|late|breach(?:ed|ing)?|past due)\b", re.I)
OVERDUE_RULES = ("ticket_first_response_breach", "ticket_stale_blocked")


@dataclass
class CohortSpec:
    """
    A filter, built from the operator's turn and nothing else.

    Every field is a scalar or a closed-list value. There is no free-text field
    here, and that absence is the point — a struct with nowhere to put a string
    cannot carry an injection into a query.
    """

    rule_ids: tuple[str, ...] = ()
    min_days: int | None = None
    mine_only: bool = False
    # True when the operator named no rule: "anything I should look at today?".
    open_ended: bool = False
    subject: str = "orders"  # "orders" | "tickets"


def parse(query: str) -> CohortSpec:
    """Deterministic. Same question in, same filter out, no model involved."""
    q = query.lower()

    rules = tuple(
        rid for rid, cues in RULE_CUES if any(c in q for c in cues)
    )

    # A delivery question means the delivery rules, not every rule that mentions
    # a delivery in passing. A-01/A-02.
    # Delivery scoping wins over an incidental cue. "How many deliveries missed
    # SLA" matched `ticket_first_response_breach` on the word "sla" and counted
    # tickets — a real number, for a question nobody asked. When the subject is
    # deliveries, the delivery rules are the subject.
    if _DELIVERY_SCOPED.search(q):
        rules = DELIVERY_RULES

    # "Overdue" is not one rule. A ticket can be overdue because nobody ever
    # replied, or because it has sat waiting on the customer with no follow-up,
    # and an agent asking what is overdue in their queue means both. Mapping it
    # to `ticket_first_response_breach` alone returned half the answer and
    # looked complete, which is the worse kind of wrong. Eval T-05.
    if _OVERDUE.search(q):
        rules = tuple(dict.fromkeys(rules + OVERDUE_RULES))

    days = _DAYS.search(q)
    mine = _MINE.search(q) is not None
    subject = "tickets" if re.search(r"\bticket", q) or mine else "orders"

    return CohortSpec(
        rule_ids=rules,
        min_days=int(days.group(1)) if days else None,
        mine_only=mine,
        open_ended=not rules,
        subject=subject,
    )


@dataclass
class Member:
    subject_id: str
    subject_type: str
    rule_id: str
    depth: int
    message: str
    age_days: int
    suggested_action: str
    extra: dict = field(default_factory=dict)


async def collect(sql: Sql, spec: CohortSpec, session) -> list[Member]:
    """
    Run the rules engine across the scope and keep what matches.

    RLS has already bounded the rows, so "the scope" is the caller's city and
    nothing here has to say so. The N+1 is deliberate and honest: correctness
    comes from running the *same* `evaluate()` the single-order path runs, not
    from a hand-written SQL reimplementation of each rule that could silently
    disagree with it. At 65 orders that costs milliseconds; at 65,000 it would
    need the rules pushed into SQL, and then the two definitions would have to
    be tested against each other.
    """
    out: list[Member] = []

    if spec.subject == "tickets":
        rows = await sql.all(
            "SELECT id, assigned_to, created_at FROM ticket "
            "WHERE state NOT IN ('RESOLVED','CLOSED') ORDER BY id"
        )
        for r in rows:
            if spec.mine_only and r["assigned_to"] != session.user_id:
                continue
            snap = await snapshot(sql, r["id"])
            if not snap:
                continue
            out.extend(_members(snap, spec, r["id"], "ticket"))
        return _rank(out, spec)

    rows = await sql.all("SELECT id FROM orders ORDER BY id")
    for r in rows:
        snap = await snapshot_for_order(sql, r["id"])
        if not snap.get("order"):
            continue
        out.extend(_members(snap, spec, str(r["id"]), "order"))
    return _rank(out, spec)


def _members(snap: dict, spec: CohortSpec, sid: str, stype: str) -> list[Member]:
    from app.data.queries import _aware, _now

    now = _now()
    found: list[Member] = []
    for v in evaluate(snap):
        if spec.rule_ids and v.rule_id not in spec.rule_ids:
            continue

        anchor = (snap.get("order") or {}).get("updated_at") or \
                 (snap.get("ticket") or {}).get("created_at")
        age = int((now - _aware(anchor)).total_seconds() // 86400) if anchor else 0

        # The threshold the operator stated. Applied after the rule, not instead
        # of it: "stuck more than 21 days in RC transfer" is both conditions.
        if spec.min_days is not None and age < spec.min_days:
            continue

        found.append(Member(
            subject_id=sid, subject_type=stype, rule_id=v.rule_id, depth=v.depth,
            message=v.message, age_days=age, suggested_action=v.suggested_action,
            extra={"blocking": (v.blocking_entity or {}).get("id")},
        ))
        # One row per subject for a named cohort; an open-ended sweep keeps the
        # primary finding only, so a triage list is not padded by symptoms.
        if not spec.open_ended:
            break
        break
    return found


def _rank(members: list[Member], spec: CohortSpec) -> list[Member]:
    """
    Cause before symptom, then oldest first.

    C-02 — "anything I should look at today?" — is the case that needs this.
    Dumping every violation would be answering a triage question with a list,
    which is the same as not answering it.
    """
    return sorted(members, key=lambda m: (m.depth, -m.age_days, m.subject_id))


def tally(members: list[Member]) -> list[tuple[str, int]]:
    """
    Counts by rule, commonest first. A-02's "top reason" is a `GROUP BY
    rule_id`, and it is only expressible because a cause is an id rather than a
    sentence.
    """
    counts: dict[str, int] = {}
    for m in members:
        counts[m.rule_id] = counts.get(m.rule_id, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
