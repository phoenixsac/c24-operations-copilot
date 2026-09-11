"""
CORE-6 — the policy engine. docs/INVARIANTS.md I6.

**Policy is data, and the answer has to show its work.**

That is the whole reason this is a separate component rather than another rule.
A rule answers "is something wrong". A policy question asks "is this
*permitted*", and the answer depends on configured thresholds the records do
not contain — a seven-day return window lives in `CONFIG`, not in a column. An
answer that says "no, they're outside the window" without naming the clock
start, the threshold and today's position is asking to be believed. Eval P-01
requires the clock start and the odometer delta to be *shown*, not asserted.

The second reason it is separate: a policy question is usually **hypothetical**.
"Customer wants to return it — are they eligible?" describes something that has
not happened. No rule has fired, and no rule will, because the return has not
been requested. `evaluate()` reports what *is* wrong; this reports what *would*
be allowed. Waiting for a violation would answer every such question with
silence.

What it never does: assert a threshold from memory. Every number here is read
from `CONFIG` and reported alongside the verdict, so a changed threshold changes
the answer *and* the explanation together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.rules import CONFIG, Config, _days_since, _now
from app.data.queries import _aware


@dataclass
class Factor:
    """
    One input to the decision, with its source named.

    `source` is either a record (`order_event/DELIVERED`) or a config key
    (`CONFIG.return_window_days`). An operator reading this can check every line
    without asking anyone.
    """

    label: str
    value: str
    source: str


@dataclass
class PolicyDecision:
    verdict: str                    # eligible | ineligible | requires_supervisor | not_applicable
    policy_id: str                  # the rule id that governs, even if it did not fire
    summary: str
    factors: list[Factor] = field(default_factory=list)
    # Named explicitly rather than omitted. "Not recorded" and "zero" are
    # different answers, and a policy decision that silently treats a missing
    # input as absent is the failure B5 describes one layer up.
    unrecorded: list[str] = field(default_factory=list)
    requires_role: str | None = None


# What kind of permission is being asked about. Closed list: a policy answer
# quotes a threshold, so an unrecognised question must fall through to a
# refusal rather than be answered against the nearest-looking rule.
_RETURN = re.compile(r"\b(return|send it back|give it back|take it back)\b", re.I)
_REFUND = re.compile(r"\b(refund|money back|reimburse)\b", re.I)
_EXCEPTION = re.compile(r"\b(exception|override|waive|bend|special case)\b", re.I)


def applies(query: str) -> bool:
    return bool(_RETURN.search(query) or _REFUND.search(query) or _EXCEPTION.search(query))


def decide(query: str, snap: dict, session, cfg: Config = CONFIG,
           now: datetime | None = None) -> PolicyDecision:
    now = now or _now()

    if _EXCEPTION.search(query):
        return _exception(session, cfg)
    if _RETURN.search(query) or _REFUND.search(query):
        return _return_window(snap, session, cfg, now)

    return PolicyDecision(
        verdict="not_applicable",
        policy_id="—",
        summary="No configured policy covers that question.",
    )


def _return_window(snap: dict, session, cfg: Config, now: datetime) -> PolicyDecision:
    """
    Return eligibility, computed from the ledger and the configured window.

    The clock starts at the DELIVERED event, not at the order date and not at
    `updated_at` — a return window runs from when the customer got the car.
    Reading it from the ledger rather than the state column matters for the same
    reason `state_ledger_mismatch` exists: the column is a materialised
    convenience and can be wrong.
    """
    order = snap.get("order") or {}
    events = snap.get("events") or []
    delivered = next((e for e in events if e["to_state"] == "DELIVERED"), None)

    factors = [
        Factor("Return window", f"{cfg.return_window_days} days",
               "CONFIG.return_window_days"),
        Factor("Order state", str(order.get("state", "—")), "orders.state"),
    ]

    # The odometer at handover is not modelled — `vehicle.km` is a single
    # current figure with no delivery-time snapshot, so the delta a return
    # policy would need cannot be computed. Named, not omitted: an operator
    # must know this was not checked rather than assume it passed.
    unrecorded = ["odometer_delta — no odometer reading is captured at delivery"]

    if delivered is None:
        factors.append(
            Factor("Clock start", "not started — no DELIVERED event in the ledger",
                   "order_event")
        )
        return PolicyDecision(
            verdict="ineligible",
            policy_id="return_window_boundary",
            summary=(
                f"The return window has not started. Order {order.get('id', '—')} has "
                f"no DELIVERED event in its ledger, and the {cfg.return_window_days}-day "
                "clock starts at handover. A return cannot be assessed before then."
            ),
            factors=factors,
            unrecorded=unrecorded,
        )

    days = _days_since(delivered["at"], now)
    remaining = cfg.return_window_days - days
    factors.insert(0, Factor(
        "Clock start", f"{_aware(delivered['at']):%Y-%m-%d %H:%M} (DELIVERED)",
        "order_event/DELIVERED",
    ))
    factors.append(Factor("Elapsed", f"{days:.1f} days", "computed"))

    if remaining < 0:
        verdict, summary = "ineligible", (
            f"Outside the window. Delivery was {days:.1f} days ago and the window is "
            f"{cfg.return_window_days} days, so it closed "
            f"{abs(remaining):.1f} days ago."
        )
    elif abs(remaining) * 24 <= cfg.return_boundary_hours:
        verdict, summary = "requires_supervisor", (
            f"On the boundary. Delivery was {days:.1f} days ago against a "
            f"{cfg.return_window_days}-day window — within "
            f"{cfg.return_boundary_hours}h of expiry, so a supervisor decides."
        )
    else:
        verdict, summary = "eligible", (
            f"Inside the window. Delivery was {days:.1f} days ago and "
            f"{remaining:.1f} days remain of the {cfg.return_window_days}-day window."
        )

    return PolicyDecision(
        verdict=verdict,
        policy_id="return_window_boundary",
        summary=summary,
        factors=factors,
        unrecorded=unrecorded,
        requires_role="supervisor" if verdict == "requires_supervisor" else None,
    )


def _exception(session, cfg: Config) -> PolicyDecision:
    """
    An exception is not a policy question — it is a request to ignore one.

    Always routed to a supervisor regardless of what the records say, because
    the whole point of an exception is that the rule said no. D3.
    """
    return PolicyDecision(
        verdict="requires_supervisor",
        policy_id="return_window_boundary",
        summary=(
            "An exception overrides the configured policy, so it is a supervisor "
            "decision rather than a lookup. Raise it with the reason and the "
            "record; the policy itself is unchanged."
        ),
        factors=[
            Factor("Your role", session.role.value, "app_actor.role"),
            Factor("Required role", "supervisor", "ROLE_GRANTS"),
        ],
        requires_role="supervisor",
    )
