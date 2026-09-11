"""
`/ask` — the only natural-language surface.

Six stages, fixed order, no cycles:

    route → plan → fetch → diagnose → gate → synthesise

The model participates in stages 1, 2 and 6. It participates in stages 3–5 not
at all, and that gap is the design: what is *true* about an order is decided by
`core/rules.py`, a pure function over records, and no provider is consulted
about it (ADR-004).

Passing `gw=None` runs the whole thing with no provider: keyword router,
templated phrasing. That is not a stub — it is the F4 degraded path, the same
code that runs when Sarvam is unavailable, and it is what the eval suite grades
against deterministically (ADR-014, ADR-015). Responses report
`model: "deterministic"` and `synthesis: "template"` so an answer never claims
to be something it is not.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.agent.planner import (
    PROMPT_VERSION as PLANNER_VERSION,
    ROUTER_PROMPT_VERSION,
    extract_entities,
    is_wide,
    plan,
    route_model,
)
from app.agent import actions, cohorts
from app.agent.actions import record_proposal
from app.agent.conversation import state_hash
from app.agent.resolve import Ambiguous, NotFound, resolve
from app.agent.synthesise import draft_reply, synthesise
from app.agent.tier2 import AUTO_REPLY_ROLE, evaluate_gate
from app.core import glossary
from app.core.ir import IR, EntityRef, QueryShape
from app.core.rules import RuleViolation, evaluate, expected_state
from app.data.queries import snapshot, snapshot_for_order
from app.db import Sql
from app.model.redact import wrap_untrusted
from app.obs.trace import Trace
from app.obs.trace import Trace
from app.session import Session

if TYPE_CHECKING:
    from app.model.gateway import Gateway


@dataclass
class PriorTurn:
    """
    What a follow-up may inherit. Two of the four memory components (§7):
    the previous IR's entities and the digest of what it found.

    Note what is not here: the previous answer's prose. "Who do I escalate to?"
    resolves against the prior *IR*, never against the sentence the model wrote
    last turn — otherwise a hallucination becomes an input. ADR-010.
    """

    entities: list[EntityRef] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    # The shape of the last turn. "And now?" carries no shape of its own and
    # means "ask that again against current state" — eval M-02.
    shape: QueryShape | None = None
    # How the last draft was asked for, NOT the draft itself.
    #
    # "Make it shorter" looks like it needs the previous prose, and that would
    # break ADR-010. It does not: a draft is a pure function of (facts, style),
    # so a shorter one is the same facts under a tighter constraint. Carrying
    # the constraint instead of the text keeps model output out of the input,
    # and has the side effect that a redrafted reply is regenerated from
    # records rather than degraded from a copy. Eval M-03.
    draft_style: str | None = None
    # J10 is sticky. A conversation that touched flagged content stays flagged
    # even on a turn whose own text is clean, because the history is re-sent.
    injection_flagged: bool = False

# Confidence below this and the router does not guess. docs/DESIGN.md §4.1.
ROUTER_CONFIDENCE_FLOOR = 0.35

_SHAPE_CUES: list[tuple[QueryShape, list[str]]] = [
    # Verbs an operator uses to ask for something to happen. "schedule" was
    # here briefly and had to go: D-01 says "delivery isn't scheduled", which
    # describes a state rather than requesting one, and the cue sent a
    # diagnosis down the write path. A cue that appears as often in a complaint
    # as in a command is not a cue.
    (QueryShape.ACTION, ["refund", "issue", "escalate", "approve", "execute",
                         "resolve", "cancel", "close", "reopen", "replay",
                         "freeze"]),
    # Diagnosis is checked before lookup, and most of these are not the word
    # "why". An operator describing a contradiction — "says delivered but the
    # customer never got the car", "shows paid but the order still says
    # pending" — is asking why, without using the word. Those phrasings were
    # falling through to `unsupported` (evals D-03, D-05, T-04).
    (QueryShape.DIAGNOSIS, [
        "why", "stuck", "blocked", "holding", "going on", "delay", "delayed",
        "wrong", "problem", "issue with", "not scheduled", "never got",
        "never arrived", "hasn't arrived", "hasnt arrived", "has not arrived",
        "still says", "but the order", "keep coming back", "keeps coming back",
        "not received", "hasn't been", "isn't scheduled", "didn't get",
    ]),
    (QueryShape.AGGREGATE, ["how many", "count", "total", "average", "rate",
                            "top reason", "most common", "breakdown", "how much"]),
    # A triage question is a cohort. "Anything I should look at today?" and
    # "what's overdue in my queue?" name no group and no entity, and the honest
    # reading is "show me the set that needs me" — a ranked list, not a refusal.
    # Evals C-02 and T-05 are both this shape of question.
    (QueryShape.COHORT, ["all orders", "all tickets", "list", "cohort", "every",
                         "which orders", "which tickets", "show me all",
                         "anything i should", "what should i", "overdue",
                         "in my queue", "needs attention", "stuck more than",
                         "stuck for more", "look at today"]),
    (QueryShape.POLICY, ["eligible", "policy", "allowed", "entitled", "window", "can we"]),
    (QueryShape.LOOKUP, ["status", "summar", "when", "what is", "show", "details",
                         "who", "where", "evidence", "tell me about"]),
]

# A shape cue alone is not enough. "What is the airspeed velocity of an unladen
# swallow" matches the lookup cue "what is" and means nothing here, so a query
# must also mention something this system actually models. A real router gets
# this from the domain description in its system prompt; the keyword fallback
# needs it stated explicitly.
_DOMAIN_ANCHORS = [
    "order", "payment", "paid", "refund", "delivery", "deliver", "dispatch",
    "rc", "registration", "rto", "refurb", "recondition", "vehicle", "car",
    "customer", "ticket", "invoice", "return", "seller", "payout", "noc",
    "swift", "i20", "city", "nexon", "glanza", "maruti", "hyundai", "honda",
    "tata", "toyota",  # a customer names the model, not the order id (T-04)
    "this", "it",  # deictic — resolved against the ticket in context
]


# Openers that make a sentence a question about the world rather than an
# instruction to change it.
_INTERROGATIVE = re.compile(
    r"^\s*(who|what|which|where|when|how|whose|whom)\b", re.I
)

# An imperative that changes something. Matched as whole words so "refunded"
# in a complaint does not read as "refund" the instruction.
_WRITE_VERB = re.compile(
    r"\b(refund|issue|escalate|approve|execute|cancel|close|reopen|replay|freeze)\b",
    re.I,
)


# The operator asking about a set rather than a subject.
_COLLECTIVE = re.compile(
    r"\b(all (?:the )?(?:orders|tickets|cases)|every (?:order|ticket|case)|"
    r"which (?:orders|tickets)|show me all|anything i should|what should i|"
    r"in my queue|my queue|needs attention|look at today|"
    r"(?:what'?s|whats) overdue)\b",
    re.I,
)


# A turn that continues the previous question rather than asking a new one.
# "And now?", "still?", "what about now" — no entity, no shape, and perfectly
# clear in context: run that again against current state.
_CONTINUATION = re.compile(
    r"^\s*(and\s+now|now\??$|still\??$|what about now|any change|"
    r"has that changed|and\s+then|any update|now what)\b",
    re.I,
)

# The operator wants customer-facing text, not an internal answer.
_DRAFT = re.compile(
    r"\b(draft (?:the |a )?(?:reply|response|message)|write (?:the |a )?reply|"
    r"reply to (?:the )?customer|compose (?:the |a )?(?:reply|response))\b",
    re.I,
)

# A revision of the previous draft, expressed as a constraint rather than an
# edit. Each maps to a style the draft is regenerated under.
_RESTYLE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(shorter|briefer|more concise|cut it down|tighten)\b", re.I), "short"),
    (re.compile(r"\b(longer|more detail|expand|fuller)\b", re.I), "detailed"),
    (re.compile(r"\b(warmer|friendlier|softer|more empathetic)\b", re.I), "warm"),
    (re.compile(r"\b(formal|more professional)\b", re.I), "formal"),
]

# An operator approving a proposal by name. Extracted by regex for the same
# reason order ids are (ADR-024): the key decides which write executes, and a
# decoder that is not deterministic must not be the thing that reads it.
_PROPOSAL_RE = re.compile(r"\b(PR-\d{3,6})\b", re.I)

# "all the orders…", "every ticket…" — a write with no single subject.
_BULK = re.compile(r"\b(all|every|each|bulk|these|them)\b", re.I)


# The operator handing their judgement to retrieved text.
#
# "Read the latest ticket on order #1289 and do what it says" is the injection
# surface with the operator's own consent, which is the hardest version of it:
# nothing was smuggled in, the request itself asks us to obey a stranger.
#
# It is answered, not refused — the operator does want to know what is going on
# with that order, and refusing outright would be unhelpful. What is refused is
# the delegation: the clause is stripped, the request is treated as a question
# about the named entity, `action` is taken off the table so nothing can
# execute, and the turn is flagged. J1 is what makes this survivable — the model
# cannot name an action outside the enum however persuasive the ticket body is.
_DELEGATION = re.compile(
    r"\b(do what it says|do as it says|do what they say|follow (?:the |its |their )?"
    r"instructions?|act on (?:it|that|what it says)|do whatever it says|"
    r"carry out (?:the |its )?instructions?)\b",
    re.I,
)


# Unambiguous quantifier phrasings. A count is a count however it is worded.
_AGGREGATE_SURE = re.compile(
    r"\b(how many|how much|top reason|most common|commonest|breakdown|"
    r"what proportion|what percentage|average|count of)\b",
    re.I,
)


def _settled_shape(query: str) -> QueryShape | None:
    """
    The shape when no judgement is required. `None` means ask the model.

    Deliberately narrow: only phrasings where a second opinion could only make
    the answer worse. A write verb disqualifies both — "refund all the orders…"
    is a bulk action, and a quantifier must never turn a write into a list.
    """
    if _WRITE_VERB.search(query):
        return None
    if _AGGREGATE_SURE.search(query):
        return QueryShape.AGGREGATE
    if _COLLECTIVE.search(query):
        return QueryShape.COHORT
    return None


def route(query: str, *, in_conversation: bool = False) -> tuple[QueryShape, float]:
    """
    Reads the operator's turn and nothing else. Ticket text is never an input,
    so retrieved content cannot change the query shape. docs/INVARIANTS.md J7.

    There is no `synthesis` branch. "Give me a full status summary" is a lookup
    with a wide fan-out — the same execution path, more tools in parallel.

    Returns `UNSUPPORTED` below the confidence floor rather than defaulting to
    lookup. A confident answer to a question nobody asked is the failure this
    design argues against, so an unclassifiable query becomes a refusal.
    """
    q = query.lower().strip()
    if not q:
        return QueryShape.UNSUPPORTED, 0.0

    # No domain anchor means the question is not about anything we model, no
    # matter which cue words it happens to contain.
    #
    # Naming an identifier is itself an anchor. "Summarise #2231" contains no
    # domain noun at all, but an order id is as unambiguous a reference to this
    # domain as the word "order" — and refusing it was the original bug here.
    #
    # A turn inside a conversation is anchored by the conversation. "Who do I
    # escalate to?" names nothing on its own and is perfectly clear as the
    # second turn about order 1289 — the entity comes from the prior IR, never
    # from the prior prose (ADR-010). Eval M-01.
    # Checked before every other shape. A definitional question uses the same
    # openers as a lookup ("what is…"), so cue order alone would send it to the
    # wrong place; `wants_definition` already excludes anything naming a record,
    # and `find` requires the query to mention a term we actually define. Both
    # must hold, so "what is the airspeed velocity of an unladen swallow" stays
    # unsupported rather than becoming a concept question with no concept.
    if glossary.wants_definition(query) and glossary.find(query):
        return QueryShape.CONCEPT, 0.9

    # A collective question is a cohort even when it also sounds like a
    # diagnosis. "Show me all orders stuck more than 21 days in RC transfer"
    # contains "stuck", which is a diagnosis cue and would otherwise win on
    # ordering — but the operator asked for a set, not for one order's cause.
    #
    # This also supplies the anchor. "Anything I should look at today?" and
    # "what's overdue in my queue?" name no order, no ticket and no domain
    # noun; they are anchored by being about the caller's own work, which is a
    # bounded set. Evals C-01, C-02, T-05.
    # …unless the operator asked for something to be DONE to the set. "Refund
    # all the orders stuck in RC transfer" is collective and is still a write;
    # routing it to `cohort` turned a bulk action into a list and quietly
    # dropped the request. A verb outranks a quantifier. Eval W-03.
    if _COLLECTIVE.search(q) and not _WRITE_VERB.search(q):
        return QueryShape.COHORT, 0.85

    anchored = (
        in_conversation
        or any(re.search(rf"\b{re.escape(a)}\b", q) for a in _DOMAIN_ANCHORS)
        or bool(extract_entities(query))
    )
    if not anchored:
        return QueryShape.UNSUPPORTED, 0.0

    # An interrogative opener outranks an action verb. "Who do I escalate to?"
    # contains "escalate" and requests nothing — it asks who the escalation
    # path is. Classifying it as `action` would offer to perform a write in
    # answer to a question, which is the wrong kind of wrong. Eval M-01.
    #
    # "Can we refund this?" is deliberately not covered here: it is a policy
    # question, and `policy` is checked before `lookup` below.
    asks_rather_than_tells = _INTERROGATIVE.match(q) is not None

    for shape, cues in _SHAPE_CUES:
        if shape is QueryShape.ACTION and asks_rather_than_tells:
            continue
        hits = sum(1 for c in cues if c in q)
        if hits:
            # Crude but honest: more matching cues means more confidence. A real
            # router returns the model's own probability over the six labels.
            return shape, min(0.95, 0.55 + 0.15 * hits)

    return QueryShape.UNSUPPORTED, 0.0


ACTION_LABEL = {
    "escalate_rto": "Escalate to RTO",
    "replay_webhook": "Replay webhook",
    "notify_customer_delay": "Notify customer of delay",
    "schedule_delivery": "Schedule delivery",
    "call_customer": "Call customer",
    "freeze_and_review": "Freeze and review",
    "route_to_sellside": "Route to sell-side",
    "cancel_later_order": "Cancel later order",
    "supervisor_exception": "Request supervisor exception",
    "reconcile": "Reconcile ledger",
    "refund": "Issue refund",
    "assign_now": "Assign now",
    "reopen_for_audit": "Reopen for audit",
    "escalate_supervisor": "Escalate to supervisor",
    "request_identifier": "Ask for an order number",
    "auto_followup": "Send follow-up",
}

# Questions about things no field models. The correct answer is a refusal with
# pointers, not a plausible guess. docs/questions_v2.json X-01.
_UNMODELLED = re.compile(
    r"\b(warranty|promised|verbally|told me|part exchange|goodwill|assured)\b", re.I
)


def _state_line(snap: dict) -> str:
    """
    The facts a lookup was actually asking for, in one line.

    This exists because the original template only ever answered "what is
    blocking this order" — correct for a diagnosis, and a non-answer to "what's
    the payment status", which is what eval L-01 caught. A healthy order has no
    violation to narrate, so the narration has to come from the records.
    """
    bits: list[str] = []
    for p in snap.get("payments") or []:
        bits.append(f"{p['kind']} payment {p['id']} is {p['status']}")
    d = snap.get("delivery")
    if d:
        slot = f", slot {d['slot_at']:%d %b %H:%M}" if d.get("slot_at") else ", no slot booked"
        bits.append(f"delivery is {d['status']}{slot}")
    rc = snap.get("rc_case")
    if rc:
        bits.append(f"RC transfer is {rc['status']}")
    refurb = snap.get("refurb")
    if refurb:
        bits.append(f"reconditioning is {refurb['status']}")
    for r in snap.get("refunds") or []:
        bits.append(f"refund {r['id']} is {r['status']}")
    return "; ".join(bits)


def phrase(primary: RuleViolation | None, all_v: list[RuleViolation],
           snap: dict | None = None) -> tuple[str, str]:
    """Templated, not generated. Every sentence traces to a field."""
    if primary is None:
        snap = snap or {}
        order = snap.get("order") or {}
        detail = _state_line(snap)
        head = (
            f"Order {order['id']} is in state {order['state']}."
            if order else "Nothing is currently blocking this order."
        )
        return (
            f"{head} {detail}." if detail else head,
            "No rule fired against these records. Payment, reconditioning, ownership "
            "transfer and delivery are all consistent with the order state.",
        )
    # Same depth rule as the synthesiser (ADR-035), and for the same reason.
    # This is the F4 path — it ships whenever the provider times out, which on
    # a reasoning model is often — so a causal claim invented here reaches an
    # operator just as readily as one invented by the model. Fixing it in one
    # place and not the other would have left the bug live on the path that
    # runs when things are already going wrong.
    downstream = [o for o in all_v[1:] if o.depth > primary.depth]
    alongside = [o for o in all_v[1:] if o.depth <= primary.depth]
    tail = ""
    if downstream:
        word = "symptom follows" if len(downstream) == 1 else "symptoms follow"
        tail += (
            f" {len(downstream)} downstream {word} from it: "
            f"{', '.join(o.rule_id for o in downstream)}."
        )
    if alongside:
        verb = "is" if len(alongside) == 1 else "are"
        tail += (
            f" Separately, and not caused by it, {', '.join(o.rule_id for o in alongside)} "
            f"also {verb} firing on this ticket."
        )
    where = ""
    if primary.blocking_entity:
        be = primary.blocking_entity
        where = f' The blocking record is {be["type"]} {be["id"]} ({be["reason"]}).'
    fields = ", ".join(f"{k} = {v}" for k, v in primary.triggering_fields.items())
    return (
        primary.message,
        f"Rule {primary.rule_id} v{primary.version} fired on {fields}.{where}{tail}",
    )


def _stuck_for(since: Any) -> str:
    d = since if isinstance(since, datetime) else datetime.fromisoformat(str(since))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    h = (datetime.now(timezone.utc) - d).total_seconds() / 3600
    return f"{round(h)}h" if h < 48 else f"{round(h / 24)}d"


def _idempotency_key(action: str, order_id: int, rule_id: str) -> str:
    """
    Deterministic: the same (action, order, cause) always yields the same key, so
    a replay is recorded as a no-op rather than performed twice. D2.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"copilot:{action}:{order_id}:{rule_id}"))


def _harvest(trace: "Trace | None", gw: "Gateway | None") -> "Trace | None":
    """
    Copy the gateway's captured prompts onto the trace before it leaves.

    Tolerates both being absent: the early-return helpers are called from paths
    that may never have built a gateway, and a missing trace must not turn a
    refusal into a 500.
    """
    if trace is not None and gw is not None:
        trace.exchanges = list(gw.exchanges)
    return trace


def _trace(started: datetime, rule_count: int, *, model: str = "deterministic",
           synth: str = "template", gw: "Gateway | None" = None,
           trace: "Trace | None" = None) -> dict:
    """
    Names what actually ran. `model: "deterministic"` when no provider was
    called, and `synthesis: "template"` when the model's sentence was rejected
    or never requested — an answer must never look model-generated when it is
    not, and vice versa. A3.
    """
    ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    usage = gw.usage() if gw else {}
    return {
        "model": model,
        "latency_ms": ms,
        "tokens": {
            "prompt": usage.get("prompt_tokens", 0),
            "completion": usage.get("completion_tokens", 0),
            # Broken out because on this provider it is most of the spend.
            "reasoning": usage.get("reasoning_tokens", 0),
        },
        "model_calls": usage.get("calls", 0),
        "synthesis": synth,
        # Measured, not asserted. The previous version reported a literal 1ms
        # for `rules` and total-minus-2 for `fetch` whatever happened — numbers
        # that looked like instrumentation and were not. OBS-1.
        "stages": trace.to_dict() if trace else [],
        "prompt_version": f"rules-only@{rule_count}" if model == "deterministic"
                          else f"{ROUTER_PROMPT_VERSION}+{PLANNER_VERSION}",
    }


def _refusal(answer_id: str, shape: QueryShape, reason: str, started: datetime,
             explanation: str | None = None, pointers: list[dict] | None = None,
             trace: "Trace | None" = None, gw: "Gateway | None" = None) -> dict:
    return {
        "answer_id": answer_id,
        "ir": {"shape": shape.value, "entities": [], "filters": [], "time_window": None,
               "requested_action": None, "ambiguities": [], "confidence": 0.3},
        "verdict": reason,
        "explanation": explanation or (
            "Refusal is a supported outcome. Pointers are returned instead of an answer "
            "so the agent can check by hand."
        ),
        "violation": None,
        "fired_rules": [],
        "evidence": [],
        "confidence": 0.3,
        "proposal": None,
        "refusal": {"reason": reason, "evidence_pointers": pointers or []},
        "degraded": None,
        "injection_flagged": False,
        "_trace_obj": _harvest(trace, gw),
        "trace": _trace(started, 0, trace=trace),
    }


async def _cohort_answer(sql: Sql, session: Session, answer_id: str, query: str,
                         shape: QueryShape, started: datetime,
                         gw: "Gateway | None",
                         trace: "Trace | None" = None) -> dict:
    """
    A list, or a count over the same list. One execution path, two renderings.

    `aggregate` is not a different query from `cohort` — it is the same set with
    the members summed instead of listed. Keeping them on one path means a count
    can never disagree with the list it counts, which is the way this usually
    goes wrong.
    """
    spec = cohorts.parse(query)
    members = await cohorts.collect(sql, spec, session)
    counts = cohorts.tally(members)

    if not members:
        named = ", ".join(spec.rule_ids) if spec.rule_ids else "those criteria"
        return _refusal(
            answer_id, shape,
            f"Nothing in your scope matches {named}.",
            started,
            explanation=(
                "That is an answer, not a failure — the set is empty. Scope is your "
                "city, so a wider search would need a different role."
            ),
        )

    scope_note = (
        f"within {session.city_code}"
        + (" and assigned to you" if spec.mine_only else "")
    )

    if shape is QueryShape.AGGREGATE:
        top_rule, _ = counts[0]
        verdict = (
            f"{len(members)} {spec.subject} {scope_note}"
            + (f", over {spec.min_days} days" if spec.min_days else "")
            + "."
        )
        explanation = (
            "Grouped by cause: "
            + ", ".join(f"{rid} ({n})" for rid, n in counts)
            + f". The commonest is {top_rule}."
        )
    else:
        shown = members[:10]
        verdict = (
            f"{len(members)} {spec.subject} {scope_note}"
            + (f", stuck more than {spec.min_days} days" if spec.min_days else "")
            + (", ranked cause-first" if spec.open_ended else "")
            + "."
        )
        explanation = "; ".join(
            f"{m.subject_type} {m.subject_id} \u2014 {m.rule_id} ({m.age_days}d)"
            for m in shown
        ) + (f"; and {len(members) - len(shown)} more" if len(members) > 10 else "")

    evidence = [
        {
            "table": "ticket" if m.subject_type == "ticket" else "orders",
            "record_id": m.subject_id,
            "rule_id": m.rule_id,
            "status": {"label": m.rule_id.upper(), "tone": "bad"},
            "fields": [
                {"label": "cause", "value": m.rule_id, "triggered": True},
                {"label": "age", "value": f"{m.age_days}d"},
                {"label": "suggested", "value": m.suggested_action},
            ],
        }
        for m in members[:10]
    ]

    return {
        "answer_id": answer_id,
        "ir": {
            "shape": shape.value,
            "entities": [
                {"type": "order" if m.subject_type == "order" else "ticket",
                 "id": int(m.subject_id) if m.subject_id.isdigit() else m.subject_id}
                for m in members[:10]
            ],
            # The filter, surfaced. Built from the operator's words by regex,
            # never authored by the model \u2014 eval X-02g.
            "filters": (
                [{"field": "rule_id", "op": "in", "value": list(spec.rule_ids)}]
                if spec.rule_ids else []
            ) + (
                [{"field": "age_days", "op": "gte", "value": spec.min_days}]
                if spec.min_days is not None else []
            ),
            "time_window": None,
            "requested_action": None,
            "ambiguities": [],
            "confidence": 0.9,
        },
        "verdict": verdict,
        "explanation": explanation,
        "provenance": (
            f"rules engine over {len(members)} matching {spec.subject} in "
            f"{session.city_code}; filter built from the operator's turn, "
            "no model-authored SQL"
        ),
        "violation": None,
        "fired_rules": [
            {"rule_id": rid, "version": 1, "triggering_fields": {"count": n}}
            for rid, n in counts
        ],
        "evidence": evidence,
        "digest": {"rule_ids": [rid for rid, _ in counts],
                   "cited": [m.subject_id for m in members[:10]],
                   "state_hash": "", "injection_flagged": False},
        "draft": None, "draft_style": None, "tier2": None,
        "confidence": 0.9,
        "proposal": None,
        "refusal": None, "degraded": None, "injection_flagged": False,
        "_trace_obj": _harvest(trace, gw),
        "trace": _trace(started, len(counts), model="deterministic", trace=trace,
                        synth="template", gw=gw),
    }


async def _bulk_proposal(sql: Sql, session: Session, answer_id: str,
                         query: str, started: datetime,
                         gw: "Gateway | None",
                         trace: "Trace | None" = None) -> dict:
    """
    A proposal over a cohort. Nothing executes, and the count comes first.

    The cohort is resolved by running the rules engine over the scope — the
    same rules, not a hand-written filter — so "stuck in RC transfer" means
    exactly what `rc_transfer_stall` means and cannot quietly mean something
    broader. RLS bounds it to the caller's city, so "all" is already narrower
    than it sounds and the number shown is the number that would be affected.
    """
    from app.agent.planner import _SUB_ENTITY_CUES  # local: cue table only

    q = query.lower()
    wanted = next(
        (rid for rid, cues in _BULK_RULE_CUES if any(c in q for c in cues)), None
    )
    if wanted is None:
        return _refusal(
            answer_id, QueryShape.ACTION,
            "I cannot tell which group of orders you mean.",
            started,
            explanation=(
                "A bulk action needs a group defined by a rule — 'stuck in RC "
                "transfer', 'missing a delivery slot'. Name one, or use Cohorts "
                "to pick the set and act on it there."
            ),
        )

    rows = await sql.all("SELECT id FROM orders ORDER BY id")
    members: list[dict] = []
    for r in rows:
        snap = await snapshot_for_order(sql, r["id"])
        if not snap.get("order"):
            continue
        for v in evaluate(snap):
            if v.rule_id == wanted:
                members.append({"order_id": r["id"], "rule": v.rule_id,
                                "action": v.suggested_action})
                break

    if not members:
        return _refusal(
            answer_id, QueryShape.ACTION,
            f"No orders in your scope match {wanted}.",
            started,
            explanation="There is nothing to act on, so nothing was proposed.",
        )

    sample = [str(m["order_id"]) for m in members[:5]]
    proposal = {
        "proposal_id": f"prop_{uuid.uuid4().hex[:8]}",
        "action": "refund",
        "label": f"Refund {len(members)} orders matching {wanted}",
        "params": {"rule_id": wanted, "count": len(members)},
        "requires_confirmation": True,
        "idempotency_key": _idempotency_key("bulk_refund", 0, wanted),
        "motivating_rule": wanted,
        # D6: the count and a sample, before anything runs.
        "bulk": {"count": len(members), "sample": sample},
        "approval_gate": {
            "reason": (
                f"A bulk refund over {len(members)} orders is above any single "
                "approval limit and needs a supervisor."
            ),
            "limit_inr": session.refund_limit_inr,
            "routes_to": {"name": "Supervisor", "role": "supervisor"},
        },
    }

    return {
        "answer_id": answer_id,
        "ir": {"shape": QueryShape.ACTION.value,
               "entities": [{"type": "order", "id": m["order_id"]} for m in members[:5]],
               "filters": [], "time_window": None, "requested_action": "refund",
               "ambiguities": [], "confidence": 0.9},
        "verdict": (
            f"{len(members)} orders in your scope match {wanted}. "
            "Nothing has been refunded."
        ),
        "explanation": (
            f"This would refund {len(members)} orders — {', '.join('#' + s for s in sample)}"
            + (" and others" if len(members) > 5 else "")
            + ". It needs supervisor approval, and each order is refunded under its "
              "own idempotency key so a partial failure can be retried without "
              "double-refunding the rest."
        ),
        "provenance": f"rules/{wanted} over {len(rows)} orders in scope",
        "violation": None,
        "fired_rules": [],
        "evidence": [],
        "digest": {"rule_ids": [wanted], "cited": sample, "state_hash": "",
                   "injection_flagged": False},
        "draft": None, "draft_style": None, "tier2": None,
        "confidence": 0.9,
        "proposal": proposal,
        "executed": False,
        "refusal": None, "degraded": None, "injection_flagged": False,
        "_trace_obj": _harvest(trace, gw),
        "trace": _trace(started, 0, model="deterministic", synth="template", gw=gw, trace=trace),
    }


# Which rule an operator means by a plain-English group name. Deliberately a
# small closed list: a bulk write is not the place to be generous about
# interpretation.
_BULK_RULE_CUES: list[tuple[str, tuple[str, ...]]] = [
    ("rc_transfer_stall", ("rc transfer", "rc", "ownership", "registration")),
    ("refurb_overrun", ("refurb", "recondition")),
    ("delivery_slot_missing", ("delivery slot", "no slot", "unscheduled")),
    ("delivery_attempts_exhausted", ("delivery attempts", "failed delivery")),
    ("payment_capture_lag", ("payment", "capture", "not advanced")),
    ("refund_duplication", ("duplicate refund", "double refund")),
]


async def _approve_named(sql: Sql, session: Session, answer_id: str,
                         ref: str, started: datetime,
                         gw: "Gateway | None",
                         trace: "Trace | None" = None) -> dict:
    """
    Approve by proposal reference, through the same path the button uses.

    Typing the approval and clicking it must not be two code paths — one of
    them would end up with a check the other lacks.
    """
    row = await sql.one(
        "SELECT id, answer_id, order_id, ticket_id, action, proposal, proposed_by, "
        "rule_id, rule_version, idempotency_key, result FROM action_audit "
        "WHERE id = $1 OR proposal LIKE $2 "
        "ORDER BY CASE result WHEN 'executed' THEN 0 "
        "                     WHEN 'pending_approval' THEN 1 ELSE 2 END LIMIT 1",
        ref, f'%"{ref}"%',
    )
    if row is None:
        return _refusal(
            answer_id, QueryShape.ACTION,
            f"There is no proposal {ref} in your scope.",
            started,
            explanation=(
                "It may never have existed, or it may belong to another city. "
                "Open the ticket and ask again to raise a fresh proposal."
            ),
        )

    if row["result"] == "executed":
        out = await actions.replay(sql, session, row)
        verdict = f"{ref} has already been executed. Nothing was done again."
        explanation = (
            "The approval was recorded as a replay. The original result stands, "
            "and no second effect was applied."
        )
    else:
        try:
            out = await actions.execute(sql, session, row)
        except actions.NotPermitted as exc:
            return _refusal(
                answer_id, QueryShape.ACTION, str(exc), started,
                explanation=(
                    "Authorisation is checked again at execution against your own "
                    "role, not inherited from whoever raised the proposal."
                ),
            )
        verdict = f"{ref} executed."
        explanation = f"{row['action']} applied. {out.get('note', '')}".strip()

    return {
        "answer_id": answer_id,
        "ir": {"shape": QueryShape.ACTION.value, "entities": [], "filters": [],
               "time_window": None, "requested_action": row["action"],
               "ambiguities": [], "confidence": 1.0},
        "verdict": verdict,
        "explanation": explanation,
        "provenance": f"action_audit/{row['idempotency_key']}",
        "violation": None,
        "fired_rules": [],
        "evidence": [],
        "digest": {"rule_ids": [], "cited": [], "state_hash": "",
                   "injection_flagged": False},
        "draft": None, "draft_style": None, "tier2": None,
        "confidence": 1.0,
        "proposal": None,
        "executed": out.get("effect") not in (None, "replayed_noop"),
        "result": out,
        "refusal": None, "degraded": None, "injection_flagged": False,
        "_trace_obj": _harvest(trace, gw),
        "trace": _trace(started, 0, model="deterministic", synth="template", gw=gw, trace=trace),
    }


def _concept_answer(answer_id: str, terms: list, started: datetime,
                    gw: "Gateway | None", model_used: str,
                    trace: "Trace | None" = None) -> dict:
    """
    A definition, quoted.

    No model call. The glossary text IS the answer, and asking a model to
    rephrase it would reintroduce exactly the invention this shape exists to
    remove — a reworded definition is a new definition, and nobody can tell
    which words were curated and which were generated.

    The trace says `model: "glossary"` so the provenance is visible: this
    answer came from a file with an owner, not from a provider.
    """
    lead, *rest = terms
    verdict = f"{lead.term}: {lead.definition}"
    explanation = " ".join(f"{t.term}: {t.definition}" for t in rest)

    return {
        "answer_id": answer_id,
        "ir": {
            "shape": QueryShape.CONCEPT.value,
            "entities": [],
            "filters": [],
            "time_window": None,
            "requested_action": None,
            "ambiguities": [],
            "confidence": 1.0,
        },
        "verdict": verdict,
        "explanation": explanation or (
            "Defined in docs/DOMAIN_v2.md. Ask about a specific order or ticket "
            "to see how this applies to a live record."
        ),
        # Cited like any other answer: the source is the glossary entry, and an
        # operator can go read it.
        "provenance": "; ".join(
            f"glossary/{t.kind}/{t.term}" for t in terms
        ),
        "violation": None,
        "fired_rules": [],
        "evidence": [],
        "digest": {"rule_ids": [], "cited": [], "state_hash": "",
                   "injection_flagged": False},
        "draft": None,
        "draft_style": None,
        "tier2": None,
        "confidence": 1.0,
        "proposal": None,
        "refusal": None,
        "degraded": None,
        "injection_flagged": False,
        "_trace_obj": _harvest(trace, gw),
        "trace": _trace(started, 0, model="glossary", synth="glossary", gw=gw, trace=trace),
    }


def _build_evidence(snap: dict, violations: list[RuleViolation]) -> list[dict]:
    def rule_for(entity_type: str) -> str | None:
        for v in violations:
            if v.blocking_entity and v.blocking_entity["type"] == entity_type:
                return v.rule_id
        return None

    def stamp(d: Any) -> str:
        if not d:
            return "—"
        dt = d if isinstance(d, datetime) else datetime.fromisoformat(str(d))
        return dt.strftime("%Y-%m-%d %H:%M")

    cited: list[dict] = []
    for p in snap.get("payments") or []:
        cited.append({
            "table": "payment", "record_id": p["id"],
            "status": {"label": str(p["status"]).upper(),
                       "tone": "ok" if p["status"] == "captured" else "warn"},
            "fields": [
                {"label": "kind", "value": p["kind"]},
                {"label": "status", "value": p["status"]},
                {"label": "captured_at", "value": stamp(p.get("captured_at"))},
            ],
        })

    rc = snap.get("rc_case")
    if rc:
        r = rule_for("rc_case")
        cited.append({
            "table": "rc_case", "record_id": rc["id"], "rule_id": r,
            "status": {"label": str(rc["status"]).upper(),
                       "tone": "ok" if rc["status"] == "done" else "bad"},
            "fields": [
                {"label": "status", "value": rc["status"]},
                {"label": "blocked_reason", "value": rc.get("blocked_reason") or "—",
                 **({"triggered": True} if r else {})},
            ],
        })

    rf = snap.get("refurb")
    if rf:
        r = rule_for("refurb_job")
        cited.append({
            "table": "refurb_job", "record_id": rf["id"], "rule_id": r,
            "status": {"label": str(rf["status"]).upper(),
                       "tone": "ok" if rf.get("completed_at") else "bad"},
            "fields": [
                {"label": "status", "value": rf["status"]},
                {"label": "promised_at", "value": stamp(rf.get("promised_at")),
                 **({"triggered": True} if r else {})},
            ],
        })

    d = snap.get("delivery")
    if d:
        r = rule_for("delivery")
        cited.append({
            "table": "delivery", "record_id": d["id"], "rule_id": r,
            "status": {"label": str(d["status"]).upper(),
                       "tone": "ok" if d["status"] == "delivered" else "warn"},
            "fields": [
                {"label": "status", "value": d["status"]},
                {"label": "attempt_count", "value": d["attempt_count"],
                 **({"triggered": True} if r else {})},
            ],
        })

    events = snap.get("events") or []
    if events:
        last = events[-1]
        cited.append({
            "table": "order_event", "record_id": str(last["id"]),
            "status": {"label": "APPENDED", "tone": "neutral"},
            "fields": [
                {"label": "to_state", "value": last["to_state"]},
                {"label": "at", "value": stamp(last["at"])},
            ],
        })
    return cited


async def ask(
    sql: Sql,
    session: Session,
    query: str,
    ticket_id: str | None,
    gw: "Gateway | None" = None,
    prior: "PriorTurn | None" = None,
) -> dict:
    """
    The six stages, in fixed order: route → plan → fetch → diagnose → gate →
    synthesise. The model participates in the first two and the last one; the
    middle — the part that decides what is true — never calls a provider.

    `gw` is optional and its absence is a supported mode, not a broken one: with
    no gateway the keyword router and the templated phrasing run, which is
    exactly the F4 path taken when the provider is down. Same code, same
    outputs, fewer tokens.
    """
    started = datetime.now(timezone.utc)
    answer_id = f"ans_{uuid.uuid4().hex[:8]}"
    trace = Trace(answer_id, query=query, actor=session.user_id,
                  city=session.city_code)
    if gw is not None:
        # Per-request. Without this a trace would show the previous question's
        # prompts, which is worse than showing none.
        gw.begin()
    stage_ms: dict[str, int] = {}
    model_used = "deterministic"
    synth_source = "template"

    # ---- stage 1: route ----------------------------------------------------
    # The operator's turn and nothing else reaches the router. J7.
    # Settled before the router is called at all.
    #
    # A definitional question is answerable from a file on disk, so paying for a
    # model round trip to classify it — 60s on this provider — buys nothing. The
    # check is two deterministic predicates: the phrasing asks for a meaning, and
    # the query names a term we actually define. Measured: 68s before, ~0s after.
    if glossary.wants_definition(query) and glossary.find(query):
        terms = glossary.find(query)
        return _concept_answer(answer_id, terms, started, gw, "glossary", trace=trace)

    in_conversation = bool(prior and prior.entities)

    # Shapes we can settle without asking anything.
    #
    # "How many deliveries missed SLA last week" and "anything I should look at
    # today?" are unambiguous, and live the model router classified the first as
    # `lookup` and the second as `unsupported` — then resolution refused both,
    # because a count has no single order to resolve against. The keyword router
    # had them right, but it only runs when the model *fails*, so a confident
    # wrong answer beat a correct deterministic one.
    #
    # The rule this follows is the same one behind ADR-024 and `concept`: where
    # the answer is derivable, derive it. A model is for the cases that need
    # judgement, and a quantifier is not one of them.
    with trace.span("route") as _sp:
        settled = _settled_shape(query)
        if settled is not None:
            shape, confidence = settled, 0.9
            routed = None
            _sp["router"] = "deterministic"
            _sp["why"] = "quantifier or collective phrasing needs no judgement"
        else:
            routed = await route_model(gw, query) if gw else None
            _sp["router"] = "model" if routed is not None else (
                "keyword" if gw is None else "keyword (model reply unusable)"
            )

    # Checked before routing so no path can reach `action`. Eval X-02.
    delegating = _DELEGATION.search(query) is not None

    # A conversation that has seen flagged content stays flagged. The history is
    # re-sent every turn, so a clean-looking turn 3 still carries turn 1's
    # untrusted text into the prompt. J10 / eval M-03.
    injection_flagged = bool(prior and prior.injection_flagged)

    # Customer-facing text, and any restyle of it. `wants_draft` is sticky
    # across a restyle: "make it shorter" on its own means shorten the draft,
    # not shorten the diagnosis.
    restyle = next((st for pat, st in _RESTYLE if pat.search(query)), None)
    wants_draft = bool(_DRAFT.search(query)) or bool(
        restyle and prior and prior.draft_style
    )
    draft_style = restyle or (prior.draft_style if prior and wants_draft else None) or "plain"

    if routed is not None:
        shape, confidence = routed
        model_used = gw.model_name
    elif settled is None:
        shape, confidence = route(query, in_conversation=in_conversation)

    # J7 means the router sees the operator's turn and nothing else — so it
    # cannot know that "Who do I escalate to?" is the second turn about order
    # 1289, and it correctly returns `unsupported` for a sentence that names
    # nothing. Widening the router's input to fix that would hand retrieved
    # text influence over the execution path, which is the whole point of J7.
    #
    # Instead the conversation is applied *after* classification: an
    # unsupported follow-up inside a live conversation is re-routed by the
    # keyword path, which may consider it anchored. The prior turn contributes
    # entities and nothing else — never prose (ADR-010).
    #
    # Found live: the fake adapter degrades to the keyword router, which was
    # already conversation-aware, so M-01 passed there and failed here.
    if shape is QueryShape.UNSUPPORTED and in_conversation:
        shape, confidence = route(query, in_conversation=True)

    # "And now?" inherits the previous turn's shape. It is not a new question,
    # it is the same question asked again — and the answer must be recomputed
    # from current records, never carried. Eval M-02 turns the RC case green
    # between turns and requires the second answer to differ.
    if prior and prior.shape and (
        _CONTINUATION.match(query.strip())
        or (shape is QueryShape.UNSUPPORTED and in_conversation)
    ):
        shape = prior.shape
        confidence = max(confidence, 0.6)

    # A draft is a read that produces text. It never writes and never sends.
    if wants_draft and shape is QueryShape.UNSUPPORTED:
        shape = prior.shape if prior and prior.shape else QueryShape.LOOKUP
        confidence = max(confidence, 0.6)

    trace.event("route.resolved", shape=shape.value,
                confidence=round(confidence, 2), in_conversation=in_conversation)

    if wants_draft and shape is QueryShape.ACTION:
        # "Draft the reply" is not "send the reply". Nothing here executes.
        shape = QueryShape.LOOKUP

    if delegating:
        # "…and do what it says" carries no shape of its own, and whatever the
        # router made of it is not to be trusted with a write. The operator is
        # asking what is going on with the entity they named.
        injection_flagged = True
        if shape in (QueryShape.ACTION, QueryShape.UNSUPPORTED):
            shape = QueryShape.DIAGNOSIS
            confidence = max(confidence, 0.6)

    # ---- cohort and aggregate ---------------------------------------------
    #
    # Neither has a single subject, so both return before entity resolution —
    # `resolve` would refuse them for the entirely correct reason that no order
    # was named. What bounds them instead is RLS: the rules engine runs over
    # whatever rows the caller can see, so "every city" already means "your
    # city" before this code is reached (eval X-03).
    if shape in (QueryShape.COHORT, QueryShape.AGGREGATE):
        return await _cohort_answer(sql, session, answer_id, query, shape, started, gw, trace=trace)

    # ---- a bulk write ------------------------------------------------------
    #
    # "Refund all the orders stuck in RC transfer" names no single subject, so
    # resolution would refuse it. That refusal would be the wrong answer twice
    # over: the request is perfectly clear, and silently declining a bulk ask is
    # how someone ends up doing it by hand, one order at a time, with no audit
    # trail at all.
    #
    # Answered as a proposal that states its blast radius first: the count, a
    # sample, and no execution. D6 — a bulk action discloses scope before it
    # runs, because "all" is exactly the word nobody checks.
    # "no entity" means no concrete subject. `extract_entities` also returns
    # wildcard sub-entities — "refund" in the query yields `refund:*` — and
    # testing for an empty list meant the bulk branch never fired for the one
    # sentence it exists to handle.
    named_subject = any(
        e.id != "*" for e in extract_entities(query)
    )
    if shape is QueryShape.ACTION and _BULK.search(query) and not named_subject:
        return await _bulk_proposal(sql, session, answer_id, query, started, gw, trace=trace)

    # ---- approving a named proposal --------------------------------------
    #
    # "Approve and execute PR-4410" is a write, and it is the only place in the
    # NL surface that reaches one. Everything that makes it safe is in
    # `actions`: the proposal must already exist, authorisation is re-checked
    # against THIS session rather than the proposer's, and a key that has
    # already executed replays instead of firing twice.
    proposal_ref = _PROPOSAL_RE.search(query)
    if proposal_ref and shape is QueryShape.ACTION:
        return await _approve_named(
            sql, session, answer_id, proposal_ref.group(1).upper(), started, gw,
            trace=trace,
        )

    unmodelled = _UNMODELLED.search(query) is not None

    # ---- concept: answered from the glossary, and from nothing else ---------
    #
    # Returns before resolution, so no snapshot is fetched, no rule runs and no
    # action can be proposed. That is not an optimisation — a question about
    # what a word means has no subject to be scoped to, and fetching records to
    # answer it would invent a relevance that is not there.
    #
    # It is also the only shape with no RLS exposure, because it reads no rows.
    if shape is QueryShape.CONCEPT:
        terms = glossary.find(query)
        if not terms:
            return _refusal(
                answer_id, shape,
                "That term is not defined in this system.",
                started,
                explanation=(
                    "The glossary covers order states, the fifteen rules, the record "
                    "types and the domain shorthand an agent uses. Anything outside "
                    "that is not something I can define without guessing."
                ),
            trace=trace, gw=gw,
        )
        return _concept_answer(answer_id, terms, started, gw, model_used, trace=trace)

    # Stage 3 refusal: no shape means no tool plan, so nothing executes.
    if shape is QueryShape.UNSUPPORTED or confidence < ROUTER_CONFIDENCE_FLOOR:
        return _refusal(
            answer_id, QueryShape.UNSUPPORTED,
            "I do not have an execution path for that question.",
            started,
            explanation=(
                "The router could not classify this into one of the six query shapes, so no "
                "tools ran. Rephrase it as a status question, a diagnosis, a policy check, or "
                "use the Records tab to work the ticket by hand."
            ),
            trace=trace, gw=gw,
        )

    # ---- stage 2: plan -----------------------------------------------------
    # Entity ids come from a regex over the operator's turn, never from the
    # model, so a non-deterministic decoder cannot move which record is read.
    # ADR-015.
    ir = IR(shape=shape, entities=extract_entities(query), confidence=confidence)

    # A follow-up with no entity of its own inherits the previous turn's
    # resolved ids — from the stored IR, not from the previous prose. §7 / M-01.
    carried_from_prior = False
    if prior and not ir.entities:
        ir = ir.model_copy(update={"entities": list(prior.entities)})
        carried_from_prior = bool(ir.entities)

    # ---- stage 3: fetch ----------------------------------------------------
    try:
        with trace.span("resolve",
                        entities=[f"{e.type.value}:{e.id}" for e in ir.entities]) as sp:
            res = await resolve(sql, ir, ticket_id)
            sp["order_id"] = res.order_id
            sp["ticket_id"] = res.ticket_id
            sp["carried_from_prior"] = carried_from_prior
    except Ambiguous as amb:
        trace.event("resolve.ambiguous", candidates=len(amb.candidates))
        # Not a failure — a question. The operator is shown the candidates and
        # picks; the system does not guess which order the customer meant.
        # docs/INVARIANTS.md B2, eval T-04.
        return _refusal(
            answer_id, shape,
            f"That customer has {len(amb.candidates)} open orders, so I cannot tell "
            "which one this is about.",
            started,
            explanation=(
                "Naming one would be a guess. Pick the order and ask again, or open "
                "it from the Records tab."
            ),
            pointers=[
                {"table": "orders", "record_id": str(c["order_id"]),
                 "fields": [{"label": "vehicle", "value": c["vehicle"]},
                            {"label": "state", "value": c["state"]}]}
                for c in amb.candidates
            ],
            trace=trace, gw=gw,
        )
    except NotFound:
        # Deliberately one message for "does not exist" and "not in your
        # scope". Distinguishing them would confirm the existence of records
        # outside the caller's city. ADR-001, and eval L-03.
        return _refusal(
            answer_id, shape,
            "I have no record of that in your scope.",
            started,
            explanation=(
                "No matching order or ticket is visible to you. It may not exist, or it "
                "may belong to another city. Check the identifier, or use the Records tab."
            ),
            trace=trace, gw=gw,
        )

    snap = res.snap

    # "Did we promise them a free extended warranty?" is a well-formed question
    # about this domain that no field can answer. The honest response names that
    # and hands back pointers to what *is* recorded, so the agent can check by
    # hand — refusing with "I have no execution path" would be true and useless.
    #
    # This runs AFTER resolution, not before. The earlier version required a
    # `ticket_id` to be in context, so it never fired for a question that names
    # an order instead — which is exactly how eval X-01 is written. It appeared
    # to pass only because the keyword router happened to fail to classify the
    # sentence and refused for an unrelated reason; the live router classified
    # it confidently and the answer came back. A test passing for the wrong
    # reason is worse than one failing.
    if unmodelled:
        pointers = []
        t = snap.get("ticket")
        if t:
            pointers.append({"table": "ticket", "record_id": t["id"],
                             "fields": [{"label": "state", "value": t["state"]}]})
        o = snap.get("order")
        if o:
            pointers.append({"table": "orders", "record_id": str(o["id"]),
                             "fields": [{"label": "state", "value": o["state"]}]})
        return _refusal(
            answer_id, shape,
            "No data supports this — nothing in the order, payment or ticket records "
            "models a verbal commitment.",
            started,
            pointers=pointers,
            trace=trace, gw=gw,
        )

    # The planner may widen the fetch set, but only after the shape is fixed and
    # only from wrapped, untrusted context that cannot reclassify the request.
    #
    # Skipped when it has nothing to add, which is most of the time. The planner
    # answers one question — *which record types are needed* — and that is
    # already settled when the operator named a summary (`WIDE_SET` is fixed,
    # ADR-024) or named the records they want ("payment status 4521"). Calling
    # it anyway costs a full round trip: ~8 s of API time plus reasoning, on a
    # provider where that is a third of the whole request.
    #
    # It still runs for anything genuinely ambiguous — a bare "why is this
    # stuck?" where the fetch set is a judgement rather than a reading.
    needs_plan = gw is not None and not is_wide(query) and len(ir.entities) < 2
    if not needs_plan:
        trace.event(
            "plan.skipped",
            reason=("no gateway" if gw is None else
                    "wide summary — fetch set is fixed" if is_wide(query) else
                    "operator named the records"),
        )
    if needs_plan:
        with trace.span("plan") as _sp:
            planned = await plan(gw, query, shape=shape, context=res.context)
            _sp["validated"] = planned is not None
        if planned is not None:
            ir, injection_flagged = planned
            if carried_from_prior and not ir.entities:
                ir = ir.model_copy(update={"entities": list(prior.entities)})

    # Stored text read back later is still untrusted — X-02d. The flag is raised
    # whether the text arrived this turn or was persisted three turns ago.
    if res.context and not injection_flagged:
        _, injection_flagged = wrap_untrusted(res.context)

    # ---- stage 4: diagnose (no model, ever) --------------------------------
    # A source that did not answer is named, never treated as empty. Saying
    # "nothing is wrong" when the RC service timed out is the specific failure
    # B5 exists to prevent — it is confidently wrong in the reassuring
    # direction. Eval X-04.
    unavailable = snap.get("unavailable") or []
    degraded = {
        "unavailable": unavailable,
        "note": (
            f"{', '.join(unavailable)} did not respond, so this answer is partial. "
            "Any problem recorded there is unavailable and would not appear below."
        ),
    } if unavailable else None

    with trace.span("rules") as sp:
        violations = evaluate(snap)
        sp["fired"] = [v.rule_id for v in violations]
        sp["depths"] = [v.depth for v in violations]
        sp["primary"] = violations[0].rule_id if violations else None
    primary = violations[0] if violations else None
    evidence = _build_evidence(snap, violations)
    verdict, explanation = phrase(primary, violations, snap)

    # The exact-field line, kept separate from the prose.
    #
    # It reads like a database because it IS the database — `rule X v2 fired on
    # order.state=FULL_PAID, hours_since_full_paid=75` is what makes an answer
    # auditable (A1), and softening it would cost the provenance. But it is not
    # an explanation a person wants to read, and showing it as the answer made
    # the whole console sound like a query result. So it moves to its own field
    # and the console renders it under the trace.
    provenance = explanation if primary else None
    order = snap.get("order")

    # ---- stage 5: the Tier 2 gate -----------------------------------------
    # Structured state only. The customer's text is not an argument to this
    # function and cannot be. J8 / X-02f.
    tier2 = None
    if session.role.value == AUTO_REPLY_ROLE:
        tier2 = evaluate_gate(
            shape=shape.value, role=session.role.value, snap=snap,
            violations=violations,
        )
        trace.event("tier2", auto_reply=tier2.auto_reply, reasons=tier2.reasons,
                    routed_to=tier2.routed_to)

    # ---- stage 6: synthesise ----------------------------------------------
    # A draft is customer-facing text, produced from the same facts and returned
    # in its own field. It is never sent, and there is no path from here to a
    # write — the "Draft reply" affordance ends at the agent's screen.
    draft = None
    if wants_draft:
        draft_text, draft_source = await draft_reply(gw, snap, violations, draft_style)
        draft = {"text": draft_text, "style": draft_style, "source": draft_source,
                 "sent": False}
        if draft_source == "model":
            model_used = gw.model_name if gw else model_used

    if gw and shape is not QueryShape.UNSUPPORTED:
        with trace.span("synthesise") as sp:
            verdict, explanation, synth_source = await synthesise(
                gw, snap, violations, query, (verdict, explanation)
            )
            sp["source"] = synth_source
            if gw:
                sp["tokens"] = {"prompt": gw.usage()["prompt_tokens"],
                                "completion": gw.usage()["completion_tokens"]}
        if synth_source == "model":
            model_used = gw.model_name

    # Applied AFTER synthesis, not before.
    #
    # Prefixing the template and then letting the synthesiser rewrite it lost
    # the warning entirely — live, X-04 produced a fluent answer that never
    # said a source was down. The notice is a safety statement, not a stylistic
    # one, so it is stapled on outside the model's reach rather than requested
    # of it. B5.
    if degraded:
        verdict = f"Partial answer — {', '.join(unavailable)} is unavailable. {verdict}"
        explanation = f"{degraded['note']} {explanation}"

    # ---- the action gate --------------------------------------------------
    # Authorization is checked here at proposal time and again at execute (D3).
    proposal = None
    if shape is QueryShape.ACTION and primary:
        action = primary.suggested_action
        amount = float(order["amount"]) if order else 0.0
        permitted = [a.value for a in session.permitted_actions]
        over_limit = action == "refund" and amount > session.refund_limit_inr
        not_permitted = action not in permitted

        proposal = {
            "proposal_id": f"prop_{uuid.uuid4().hex[:8]}",
            "action": action,
            "label": ACTION_LABEL.get(action, action),
            "params": {
                "order_id": order["id"] if order else 0,
                **({"amount_inr": amount} if action == "refund" else {}),
                "reason": (primary.blocking_entity or {}).get("reason", primary.rule_id),
            },
            "requires_confirmation": True,
            "idempotency_key": _idempotency_key(action, order["id"] if order else 0, primary.rule_id),
            "motivating_rule": f"{primary.rule_id} v{primary.version}",
        }
        # Persisted at proposal time so it can be approved later — possibly by
        # a different person, hours later, from a different screen. A proposal
        # that lives only in the response body cannot be approved by anyone but
        # the asker, which is exactly the workflow D3 requires.
        await record_proposal(
            sql, session,
            answer_id=answer_id, proposal=proposal,
            rule_id=primary.rule_id, rule_version=primary.version,
            order_id=order["id"] if order else None,
            ticket_id=(snap.get("ticket") or {}).get("id"),
        )

        if over_limit or not_permitted:
            proposal["approval_gate"] = {
                "reason": (
                    f"Above your approval limit of ₹{session.refund_limit_inr:,}. "
                    "Supervisor approval required."
                    if over_limit else
                    f"Your role ({session.role.value}) cannot perform {action}."
                ),
                "limit_inr": session.refund_limit_inr,
                "routes_to": {"name": "Supervisor", "role": "supervisor"},
            }

    ticket = snap.get("ticket")
    entities: list[dict] = []
    if order:
        entities.append({"type": "order", "id": order["id"]})
    for e in ir.entities:
        item = {"type": e.type.value, "id": e.id}
        if item not in entities:
            entities.append(item)
    if primary and primary.blocking_entity:
        be = {"type": primary.blocking_entity["type"], "id": primary.blocking_entity["id"]}
        if be not in entities:
            entities.append(be)

    return {
        "answer_id": answer_id,
        "ir": {
            "shape": shape.value,
            "entities": entities,
            "filters": [],
            "time_window": None,
            "requested_action": proposal["action"] if proposal else None,
            "ambiguities": ir.ambiguities,
            "confidence": round(confidence, 2),
        },
        "tier2": ({
            "auto_reply": tier2.auto_reply,
            "reasons": tier2.reasons,
            "routed_to": tier2.routed_to,
            "force_assigned_human": tier2.force_assigned_human,
            "queued_for_review": tier2.queued_for_review,
        } if tier2 else None),
        "verdict": verdict,
        "explanation": explanation,
        "provenance": provenance,
        # Memory component 4 — what was found, not the values found. Rule ids
        # and a hash of the state they fired against, so a later turn can tell
        # something changed while being unable to answer from the old data.
        # §7 / ADR-010.
        "digest": {
            "rule_ids": [v.rule_id for v in violations],
            "cited": [f"{e['table']}:{e['record_id']}" for e in evidence],
            "state_hash": state_hash(snap),
            "injection_flagged": injection_flagged,
        },
        "draft": draft,
        # Carried into the next turn as a constraint, never as text. ADR-010.
        "draft_style": draft_style if wants_draft else None,
        # Built whenever a rule fired, with or without an order. A ticket-level
        # finding still has a cause and a suggested action; what it lacks is a
        # state transition, so those fields say so rather than being absent.
        "violation": ({
            "order_id": order["id"] if order else None,
            "expected_state": (expected_state(snap) or order["state"]) if order else "—",
            "observed_state": order["state"] if order else (ticket or {}).get("state", "—"),
            "stuck_for": _stuck_for(order["updated_at"]) if order else "—",
            "primary_rule": primary.rule_id,
            "blocking_entity": primary.blocking_entity,
            "suggested_action": primary.suggested_action,
        } if primary else None),
        "fired_rules": [{
            "rule_id": v.rule_id, "version": v.version, "triggering_fields": v.triggering_fields,
        } for v in violations],
        "evidence": evidence,
        "confidence": round(confidence, 2) if primary else 0.72,
        "proposal": proposal,
        "refusal": None,
        "degraded": degraded,
        # Flagged, counted, surfaced — never silently stripped. J10.
        "injection_flagged": injection_flagged,
        "_trace_obj": _harvest(trace, gw),
        "trace": _trace(started, len(violations), model=model_used, trace=trace,
                        synth=synth_source, gw=gw),
    }
