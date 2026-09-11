"""
The rules engine. docs/DOMAIN_v2.md §4 — all 15 rules.

A pure function: `(snapshot, config) -> list[Violation]`. No I/O, no model, no
network. The caller fetches the snapshot; this module only decides.

That shape is what makes diagnosis auditable rather than generated. The model
never selects the cause — it cannot, because by the time any prompt is assembled
the cause is already a rule_id in this list (B3).

Each rule carries a version so past answers stay interpretable when a rule
changes (I2), and reports the exact field values that fired it (A1).
"""

from __future__ import annotations

from app import clock

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Config:
    """
    Thresholds are configuration, never prompt text and never inline literals.
    Changing one is a config edit, not a redeploy of logic. I6.
    """

    capture_lag_minutes: int = 30
    rc_stall_hours: int = 72
    delivery_slot_hours: int = 24
    max_delivery_attempts: int = 3
    return_window_days: int = 7
    return_boundary_hours: int = 24
    first_response_sla_hours: int = 24
    stale_blocked_days: int = 7
    reopen_loop_threshold: int = 2


CONFIG = Config()


@dataclass
class RuleViolation:
    rule_id: str
    version: int
    triggering_fields: dict[str, Any]
    blocking_entity: dict[str, str] | None
    suggested_action: str
    # Lower is more upstream. Used to rank cause above symptom.
    depth: int
    message: str


Snapshot = dict[str, Any]


def _now() -> datetime:
    # The shared clock, so rule evaluation and the seed agree on "now".
    # See app/clock.py — without this, a fixed-clock seed drifts out from under
    # the rules as real days pass, and evals fail with nothing changed.
    return clock.now()


def _hours_since(d: Any, now: datetime) -> float:
    if d is None:
        return float("inf")
    if isinstance(d, str):
        d = datetime.fromisoformat(d)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (now - d).total_seconds() / 3600.0


def _days_since(d: Any, now: datetime) -> float:
    return _hours_since(d, now) / 24.0


def evaluate(s: Snapshot, now: datetime | None = None, cfg: Config = CONFIG) -> list[RuleViolation]:
    """
    `depth` encodes the causal chain, so a symptom never outranks its cause.

    A missing delivery slot on an order whose refurb is overrun is not the
    problem — the refurb is. docs/questions_v2.json D-02 tests exactly this.
    """
    now = now or _now()
    v: list[RuleViolation] = []
    o = s.get("order")

    # -- money in -----------------------------------------------------------

    payments = s.get("payments") or []
    full = next((p for p in payments if p["kind"] == "full" and p["status"] == "captured"), None)
    if (
        o
        and full
        and full.get("captured_at")
        and o["state"] in ("CREATED", "TOKEN_PAID")
        and _hours_since(full["captured_at"], now) * 60 > cfg.capture_lag_minutes
    ):
        v.append(RuleViolation(
            rule_id="payment_capture_lag", version=1, depth=0,
            triggering_fields={
                "payment.status": "captured",
                "order.state": o["state"],
                "minutes_since_capture": round(_hours_since(full["captured_at"], now) * 60),
            },
            blocking_entity={"type": "payment", "id": full["id"], "reason": "state_not_advanced"},
            suggested_action="replay_webhook",
            message="Payment captured but the order state never advanced.",
        ))

    # -- the sell-side seam -------------------------------------------------
    # Checked before rc_transfer_stall so the cross-seam cause outranks the RC
    # block it produces. The only rule that crosses funnels.

    payout = s.get("seller_payout")
    if payout and payout["status"] != "captured":
        v.append(RuleViolation(
            rule_id="seller_payout_hold", version=1, depth=0,
            triggering_fields={"payout.status": payout["status"], "payout.id": payout["id"]},
            blocking_entity={"type": "payment", "id": payout["id"], "reason": "seller_payout_pending"},
            suggested_action="route_to_sellside",
            message="The linked sell-side payout has not completed, which is holding the buy-side order.",
        ))

    # -- reconditioning -----------------------------------------------------

    refurb = s.get("refurb")
    if refurb and not refurb.get("completed_at") and refurb.get("promised_at"):
        if _hours_since(refurb["promised_at"], now) > 0:
            v.append(RuleViolation(
                rule_id="refurb_overrun", version=1, depth=1,
                triggering_fields={
                    "refurb_job.status": refurb["status"],
                    "days_overdue": int(_days_since(refurb["promised_at"], now)),
                },
                blocking_entity={
                    "type": "refurb_job", "id": refurb["id"],
                    "reason": refurb.get("blocked_reason") or "overdue",
                },
                suggested_action="notify_customer_delay",
                message="Reconditioning is past its promised date.",
            ))

    # -- ownership transfer -------------------------------------------------

    rc = s.get("rc_case")
    if (
        o and o["state"] == "FULL_PAID" and rc and rc["status"] != "done"
        and _hours_since(o["updated_at"], now) > cfg.rc_stall_hours - 24
    ):
        v.append(RuleViolation(
            rule_id="rc_transfer_stall", version=2, depth=2,
            triggering_fields={
                "order.state": o["state"],
                "rc_case.status": rc["status"],
                "hours_since_full_paid": round(_hours_since(o["updated_at"], now)),
            },
            blocking_entity={
                "type": "rc_case", "id": rc["id"],
                "reason": rc.get("blocked_reason") or rc["status"],
            },
            suggested_action="escalate_rto",
            message="RC ownership transfer has not completed, and dispatch is gated on it.",
        ))

    # -- handover -----------------------------------------------------------

    delivery = s.get("delivery")
    if (
        o and o["state"] in ("RC_DONE", "REFURB_DONE") and not delivery
        and _hours_since(o["updated_at"], now) > cfg.delivery_slot_hours
    ):
        v.append(RuleViolation(
            rule_id="delivery_slot_missing", version=1, depth=3,
            triggering_fields={
                "order.state": o["state"],
                "hours_since_state_change": round(_hours_since(o["updated_at"], now)),
                "delivery_rows": 0,
            },
            blocking_entity=None,
            suggested_action="schedule_delivery",
            message="No delivery has been scheduled.",
        ))

    if delivery and delivery["attempt_count"] >= cfg.max_delivery_attempts:
        v.append(RuleViolation(
            rule_id="delivery_attempts_exhausted", version=1, depth=3,
            triggering_fields={"delivery.attempt_count": delivery["attempt_count"]},
            blocking_entity={"type": "delivery", "id": delivery["id"], "reason": "attempts_exhausted"},
            suggested_action="call_customer",
            message="Delivery has failed the maximum number of attempts and needs a human.",
        ))

    # -- money out ----------------------------------------------------------

    by_payment: dict[str, int] = {}
    for r in s.get("refunds") or []:
        by_payment[r["payment_id"]] = by_payment.get(r["payment_id"], 0) + 1
    for payment_id, count in by_payment.items():
        if count > 1:
            v.append(RuleViolation(
                rule_id="refund_duplication", version=1, depth=0,
                triggering_fields={"payment_id": payment_id, "refund_count": count},
                blocking_entity={"type": "refund", "id": payment_id, "reason": "multiple_refunds"},
                suggested_action="freeze_and_review",
                message="More than one refund exists against the same payment.",
            ))

    # -- inventory ----------------------------------------------------------

    live = s.get("vehicle_live_orders") or []
    if len(live) > 1:
        v.append(RuleViolation(
            rule_id="inventory_double_allocation", version=1, depth=0,
            triggering_fields={"live_orders": ", ".join(str(x) for x in live), "count": len(live)},
            blocking_entity={"type": "vehicle", "id": str(live[0]), "reason": "double_allocated"},
            suggested_action="cancel_later_order",
            message="This vehicle is allocated to more than one live order.",
        ))

    # -- returns ------------------------------------------------------------

    if o and o["state"] == "RETURN_REQUESTED":
        delivered = next((e for e in (s.get("events") or []) if e["to_state"] == "DELIVERED"), None)
        if delivered:
            since = _days_since(delivered["at"], now)
            distance = abs(since - cfg.return_window_days) * 24
            if distance <= cfg.return_boundary_hours:
                v.append(RuleViolation(
                    rule_id="return_window_boundary", version=1, depth=0,
                    triggering_fields={
                        "days_since_delivery": round(since, 1),
                        "window_days": cfg.return_window_days,
                        "hours_from_expiry": round(distance),
                    },
                    blocking_entity=None,
                    suggested_action="supervisor_exception",
                    message="The return was requested within a day of the window closing.",
                ))

    # -- the ledger ---------------------------------------------------------
    # order.state is a materialised convenience. When it disagrees with the last
    # event, the ledger is right and the column is the defect.

    events = s.get("events") or []
    last = events[-1] if events else None
    if o and last and o["state"] != last["to_state"]:
        v.append(RuleViolation(
            rule_id="state_ledger_mismatch", version=1, depth=0,
            triggering_fields={
                "order.state": o["state"],
                "last_event.to_state": last["to_state"],
                "last_event_id": last["id"],
            },
            blocking_entity={"type": "order_event", "id": str(last["id"]), "reason": "ledger_disagrees"},
            suggested_action="reconcile",
            message="The order state column disagrees with the event ledger. The ledger is the source of truth.",
        ))

    # -- ticket lifecycle ---------------------------------------------------

    t = s.get("ticket")
    if t:
        if (
            t["state"] == "OPEN" and not t.get("first_response_at")
            and _hours_since(t["created_at"], now) > cfg.first_response_sla_hours
        ):
            v.append(RuleViolation(
                rule_id="ticket_first_response_breach", version=1, depth=0,
                triggering_fields={
                    "ticket.state": t["state"],
                    "hours_open": round(_hours_since(t["created_at"], now)),
                    "sla_hours": cfg.first_response_sla_hours,
                },
                blocking_entity={"type": "ticket", "id": t["id"], "reason": "no_first_response"},
                suggested_action="assign_now",
                message="This ticket is past its first-response SLA with no reply.",
            ))

        if t["state"] in ("RESOLVED", "CLOSED") and not t.get("resolution_evidence"):
            v.append(RuleViolation(
                rule_id="ticket_resolved_without_cause", version=1, depth=0,
                triggering_fields={
                    "ticket.state": t["state"],
                    "resolution_code": t.get("resolution_code") or "null",
                    "resolution_evidence": "null",
                },
                blocking_entity={"type": "ticket", "id": t["id"], "reason": "no_evidence"},
                suggested_action="reopen_for_audit",
                message="This ticket was resolved with no supporting evidence.",
            ))

        if t["reopen_count"] >= cfg.reopen_loop_threshold:
            v.append(RuleViolation(
                rule_id="ticket_reopen_loop", version=1, depth=0,
                triggering_fields={
                    "reopen_count": t["reopen_count"],
                    "threshold": cfg.reopen_loop_threshold,
                },
                blocking_entity={"type": "ticket", "id": t["id"], "reason": "reopen_loop"},
                suggested_action="escalate_supervisor",
                message="This ticket has been reopened repeatedly, so the underlying cause is unresolved.",
            ))

        if not t.get("order_id"):
            v.append(RuleViolation(
                rule_id="ticket_orphaned", version=1, depth=0,
                triggering_fields={"ticket.order_id": "null"},
                blocking_entity={"type": "ticket", "id": t["id"], "reason": "no_linked_order"},
                suggested_action="request_identifier",
                message="No order is linked to this ticket, so nothing can be diagnosed against it.",
            ))

        if (
            t["state"] == "AWAITING_CUSTOMER"
            and _days_since(t.get("first_response_at") or t["created_at"], now) > cfg.stale_blocked_days
        ):
            v.append(RuleViolation(
                rule_id="ticket_stale_blocked", version=1, depth=0,
                triggering_fields={
                    "ticket.state": t["state"],
                    "days_waiting": int(_days_since(t.get("first_response_at") or t["created_at"], now)),
                    "threshold_days": cfg.stale_blocked_days,
                },
                blocking_entity={"type": "ticket", "id": t["id"], "reason": "stale_awaiting_customer"},
                suggested_action="auto_followup",
                message="This ticket has been waiting on the customer with no follow-up.",
            ))

    # Cause before symptom. Stable within a depth so output is deterministic (C1).
    return sorted(v, key=lambda x: (x.depth, x.rule_id))


def expected_state(s: Snapshot) -> str | None:
    """Where the order should be, derived from the records rather than asserted."""
    o = s.get("order")
    if not o:
        return None
    paid = any(p["kind"] == "full" and p["status"] == "captured" for p in (s.get("payments") or []))
    if not paid:
        return "TOKEN_PAID"
    refurb = s.get("refurb")
    if refurb and not refurb.get("completed_at"):
        return "REFURB_DONE"
    rc = s.get("rc_case")
    if not rc or rc["status"] != "done":
        return "RC_DONE"
    delivery = s.get("delivery")
    if not delivery:
        return "DISPATCH_SCHEDULED"
    if delivery["status"] == "delivered":
        return "DELIVERED"
    return "OUT_FOR_DELIVERY"
