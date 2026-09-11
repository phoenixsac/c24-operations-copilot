"""
Every read the API performs. All of them run inside `with_session`, so RLS has
already narrowed the rows before any predicate here is applied.

The repository-level `WHERE city_code = ...` clauses you would normally expect
are absent on purpose: adding them would work, but it would also make the
isolation tests pass whether or not the policies exist. Defence in depth belongs
here eventually; correctness has to come from the database first.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.db import Sql
from app import clock
from app.core import rules
from app.data import faults

CITY_LABEL = {"mum": "Mumbai", "pun": "Pune", "blr": "Bengaluru"}


def _now() -> datetime:
    return clock.now()


def _aware(d: Any) -> datetime:
    if isinstance(d, str):
        d = datetime.fromisoformat(d)
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def age(frm: Any, now: datetime | None = None) -> str:
    now = now or _now()
    mins = max(0.0, (now - _aware(frm)).total_seconds() / 60)
    if mins < 60:
        return f"{round(mins)}m"
    hours = mins / 60
    return f"{round(hours)}h" if hours < 48 else f"{round(hours / 24)}d"


def _stamp(d: Any, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return _aware(d).strftime(fmt) if d else "—"


def _num(v: Any) -> Any:
    return float(v) if isinstance(v, Decimal) else v


async def ticket_queue(sql: Sql, session) -> dict:
    rows = await sql.all("""
        SELECT t.id, t.subject, t.order_id, t.state, t.priority, t.city_code,
               t.reopen_count, t.created_at, t.first_response_at, t.resolved_by,
               c.name AS customer_name,
               a.name AS assignee_name,
               EXISTS (SELECT 1 FROM ticket_message m
                        WHERE m.ticket_id = t.id AND m.injection_flagged) AS flagged_content
        FROM ticket t
        JOIN customer c ON c.id = t.customer_id
        LEFT JOIN app_actor a ON a.id = t.assigned_to
        ORDER BY
          CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1
                          WHEN 'normal' THEN 2 ELSE 3 END,
          t.created_at ASC
    """)

    now = _now()
    sla_hours = rules.CONFIG.first_response_sla_hours
    tickets = []
    for r in rows:
        open_hours = (now - _aware(r["created_at"])).total_seconds() / 3600
        breach = not r["first_response_at"] and r["state"] == "OPEN" and open_hours > sla_hours
        tickets.append({
            "id": r["id"],
            "subject": r["subject"],
            "customer_name": r["customer_name"],
            "city_code": r["city_code"],
            "order_id": r["order_id"],
            "state": r["state"],
            "priority": r["priority"],
            "age": age(r["created_at"], now),
            "assignee": r["assignee_name"],
            "flags": {
                "sla_breach": breach,
                "reopen_count": r["reopen_count"],
                "auto_replied": r["resolved_by"] == "copilot_auto",
                "flagged_content": r["flagged_content"],
            },
        })

    stats = await sql.one("""
        SELECT
          count(*) FILTER (WHERE state NOT IN ('RESOLVED','CLOSED'))              AS total_open,
          count(*) FILTER (WHERE assigned_to IS NULL
                             AND state NOT IN ('RESOLVED','CLOSED'))              AS unassigned,
          count(*) FILTER (WHERE assigned_to IS NULL
                             AND priority IN ('high','urgent')
                             AND state NOT IN ('RESOLVED','CLOSED'))              AS unassigned_high,
          count(*) FILTER (WHERE state = 'OPEN' AND first_response_at IS NULL
                             AND created_at < $1::timestamptz - interval '24 hours') AS sla_breach,
          count(*) FILTER (WHERE state = 'AWAITING_CUSTOMER')                     AS awaiting_customer,
          count(*) FILTER (WHERE resolved_by = 'copilot_auto'
                             AND resolved_at > $1::timestamptz - interval '1 day')   AS auto_resolved
        FROM ticket
    """, now)
    wait = await sql.val("""
        SELECT COALESCE(avg(EXTRACT(EPOCH FROM
                 ($1::timestamptz - COALESCE(first_response_at, created_at))) / 3600), 0)
        FROM ticket WHERE state = 'AWAITING_CUSTOMER'
    """, now)

    return {
        "total_open": stats["total_open"],
        "scope": {
            "city_code": session.city_code,
            "label": CITY_LABEL.get(session.city_code, session.city_code),
            "role": session.role.value,
        },
        "stats": {
            "unassigned": {"count": stats["unassigned"], "high_priority": stats["unassigned_high"]},
            "sla_breach": {"count": stats["sla_breach"]},
            "awaiting_customer": {
                "count": stats["awaiting_customer"],
                "avg_wait_hours": round(float(wait or 0), 1),
            },
            "auto_resolved_today": {"count": stats["auto_resolved"], "mean_confidence": 0.98},
        },
        "tickets": tickets,
        "page": {"index": 1, "size": len(tickets), "total": len(tickets)},
    }


async def ticket_detail(sql: Sql, ticket_id: str) -> dict | None:
    t = await sql.one("""
        SELECT t.*, c.name AS customer_name, c.phone, c.city_code AS customer_city,
               c.created_at AS customer_since, a.name AS assignee_name
        FROM ticket t
        JOIN customer c ON c.id = t.customer_id
        LEFT JOIN app_actor a ON a.id = t.assigned_to
        WHERE t.id = $1
    """, ticket_id)
    if not t:
        return None

    messages = await sql.all("""
        SELECT id, channel, author, direction, body, injection_flagged, at
        FROM ticket_message WHERE ticket_id = $1 ORDER BY at ASC
    """, ticket_id)

    prior = await sql.val(
        "SELECT count(*) FROM ticket WHERE customer_id = $1 AND id <> $2",
        t["customer_id"], ticket_id,
    )

    order, events = None, []
    if t["order_id"]:
        o = await sql.one("""
            SELECT o.id, o.state, o.amount, v.make, v.model, v.year, v.reg_no
            FROM orders o JOIN vehicle v ON v.id = o.vehicle_id WHERE o.id = $1
        """, t["order_id"])
        if o:
            order = {
                "id": o["id"],
                "vehicle": f'{o["year"]} {o["make"]} {o["model"]}',
                "reg_no": o["reg_no"],
                "amount_inr": _num(o["amount"]),
                "state": o["state"],
            }
        events = await sql.all("""
            SELECT id, from_state, to_state, actor, reason, at
            FROM order_event WHERE order_id = $1 ORDER BY at ASC, id ASC
        """, t["order_id"])

    now = _now()
    open_hours = (now - _aware(t["created_at"])).total_seconds() / 3600
    responded = bool(t["first_response_at"])
    sla_status = "ok" if responded else ("breached" if open_hours > 24 else "at_risk" if open_hours > 22 else "ok")
    label = (
        "First response met" if responded
        else f"First response {round(open_hours - 24)}h overdue" if sla_status == "breached"
        else f"First response {max(0, round(24 - open_hours))}h left"
    )

    return {
        "id": t["id"],
        "subject": t["subject"],
        "customer_name": t["customer_name"],
        "city_code": t["city_code"],
        "order_id": t["order_id"],
        "state": t["state"],
        "priority": t["priority"],
        "age": age(t["created_at"], now),
        "assignee": t["assignee_name"],
        "flags": {
            "sla_breach": sla_status == "breached",
            "reopen_count": t["reopen_count"],
            "auto_replied": t["resolved_by"] == "copilot_auto",
            "flagged_content": any(m["injection_flagged"] for m in messages),
        },
        "customer": {
            "id": t["customer_id"],
            "name": t["customer_name"],
            # Read from the database for display. Never round-trips through a
            # model — docs/INVARIANTS.md H3.
            "phone": t["phone"],
            "city": CITY_LABEL.get(t["customer_city"], t["customer_city"]),
            "prior_tickets": prior,
            "since": _aware(t["customer_since"]).strftime("%b %Y"),
        },
        "order": order,
        "messages": [{
            "id": m["id"],
            "channel": m["channel"],
            "at": _aware(m["at"]).isoformat(),
            "body": m["body"],
            "flagged": m["injection_flagged"],
        } for m in messages],
        "order_events": [{
            "id": e["id"],
            "from_state": e["from_state"],
            "to_state": e["to_state"],
            "actor": e["actor"],
            "reason": e["reason"],
            "at": _stamp(e["at"]),
        } for e in events],
        "sla": {"label": label, "status": sla_status},
        "resolution": (
            {"resolution_code": t["resolution_code"], "resolved_by": t["resolved_by"],
             "rule_id": t["resolution_code"]}
            if t["resolution_code"] else None
        ),
    }


_TICKET_COLS = """
    id, order_id, state, reopen_count, created_at, first_response_at,
    resolution_code, resolution_evidence, subject, body,
    resolved_by, resolved_at
"""
# `resolved_by` is here because the Tier 2 gate needs to know whether the
# copilot already answered this ticket once (AU-04). It was missing, so the gate
# silently evaluated `None == 'copilot_auto'` as False and would have
# auto-replied a second time on a ticket the customer had already come back to.
# A gate reading a column that is not selected fails open, which is the worst
# way for a gate to fail.


async def snapshot(sql: Sql, ticket_id: str) -> dict:
    """The snapshot the rules engine runs over. One fetch, no model involved."""
    t = await sql.one(
        f"SELECT {_TICKET_COLS} FROM ticket WHERE id = $1", ticket_id
    )
    if not t:
        return {}

    snap: dict[str, Any] = {"ticket": t}
    snap["messages"] = await sql.all(
        "SELECT id, direction, channel, body, injection_flagged, at "
        "FROM ticket_message WHERE ticket_id = $1 ORDER BY at ASC, id ASC",
        ticket_id,
    )
    if not t["order_id"]:
        return snap

    o = await sql.one(
        "SELECT id, state, amount, created_at, updated_at, city_code, vehicle_id "
        "FROM orders WHERE id = $1", t["order_id"],
    )
    if not o:
        return snap
    snap["order"] = o
    await _attach_order(sql, snap, o)
    return snap


async def snapshot_for_order(sql: Sql, order_id: int) -> dict:
    """
    Same snapshot, keyed on the order instead of a ticket.

    A question can name an order that has no ticket at all — "payment status
    4521" — so the ticket-keyed path is not the general case, it is one entry
    point into it. Where a ticket does exist, the oldest one is attached, since
    rules like `ticket_reopen_loop` are about the ticket's own history.

    Returns `{}` when the order is not visible. Not visible covers both "does
    not exist" and "belongs to another city", and the caller cannot tell which.
    ADR-001.
    """
    o = await sql.one(
        "SELECT id, state, amount, created_at, updated_at, city_code, vehicle_id "
        "FROM orders WHERE id = $1", order_id,
    )
    if not o:
        return {}

    snap: dict[str, Any] = {"order": o}
    t = await sql.one(
        f"SELECT {_TICKET_COLS} FROM ticket WHERE order_id = $1 "
        "ORDER BY created_at ASC, id ASC LIMIT 1",
        order_id,
    )
    if t:
        snap["ticket"] = t
        snap["messages"] = await sql.all(
            "SELECT id, direction, channel, body, injection_flagged, at "
            "FROM ticket_message WHERE ticket_id = $1 ORDER BY at ASC, id ASC",
            t["id"],
        )
    await _attach_order(sql, snap, o)
    return snap


async def _attach_order(sql: Sql, snap: dict, o: dict) -> dict:
    """Everything hanging off an order. Shared by both entry points."""

    snap["events"] = await sql.all(
        "SELECT id, to_state, at FROM order_event WHERE order_id = $1 ORDER BY at ASC, id ASC",
        o["id"],
    )
    snap["payments"] = await sql.all(
        "SELECT id, kind, status, captured_at FROM payment WHERE order_id = $1", o["id"]
    )
    snap["refunds"] = await sql.all(
        "SELECT id, payment_id, status FROM refund WHERE order_id = $1", o["id"]
    )
    # Each source records whether it answered. A key present with `None` means
    # "checked, nothing there"; a key in `snap["unavailable"]` means "asked and
    # got no reply", and the two must never be confused. B5.
    unavailable: list[str] = []
    try:
        faults.check("rc_case")
        snap["rc_case"] = await sql.one(
            "SELECT id, status, blocked_reason, opened_at FROM rc_case WHERE order_id = $1",
            o["id"],
        )
    except faults.SourceUnavailable as exc:
        snap["rc_case"] = None
        unavailable.append(exc.source)
    snap["refurb"] = await sql.one(
        "SELECT id, status, blocked_reason, promised_at, completed_at "
        "FROM refurb_job WHERE vehicle_id = $1", o["vehicle_id"],
    )
    snap["delivery"] = await sql.one(
        "SELECT id, status, attempt_count, slot_at FROM delivery WHERE order_id = $1", o["id"]
    )
    live = await sql.all(
        "SELECT id FROM orders WHERE vehicle_id = $1 "
        "AND state NOT IN ('CLOSED','REFUNDED') ORDER BY id", o["vehicle_id"],
    )
    snap["vehicle_live_orders"] = [r["id"] for r in live]

    # The cross-seam link: a sell-side payout against the same vehicle.
    if unavailable:
        snap["unavailable"] = unavailable

    snap["seller_payout"] = await sql.one("""
        SELECT p.id, p.status FROM payment p
        JOIN orders so ON so.id = p.order_id
        WHERE p.kind = 'payout' AND so.vehicle_id = $1 AND p.status <> 'captured'
    """, o["vehicle_id"])

    return snap


def _kv(obj: dict, triggered: str | None = None, rule_id: str | None = None) -> list[dict]:
    out = []
    for label, val in obj.items():
        if val is None:
            shown: Any = "—"
        elif isinstance(val, datetime):
            shown = _stamp(val)
        elif isinstance(val, Decimal):
            shown = float(val)
        else:
            shown = str(val)
        field = {"label": label, "value": shown}
        if label == triggered:
            field["triggered"] = True
            if rule_id:
                field["rule_id"] = rule_id
        out.append(field)
    return out


async def records_graph(sql: Sql, ticket_id: str) -> dict | None:
    t = await sql.one("SELECT id, order_id FROM ticket WHERE id = $1", ticket_id)
    if not t:
        return None

    snap = await snapshot(sql, ticket_id)
    nodes: list[dict] = []

    payments = snap.get("payments") or []
    nodes.append({"entity": "payment", "label": "Payments", "count": len(payments),
                  "rule_fired": False,
                  "records": [{"id": p["id"], "fields": _kv(p)} for p in payments]})

    refunds = snap.get("refunds") or []
    nodes.append({"entity": "refund", "label": "Refunds", "count": len(refunds),
                  "rule_fired": len(refunds) > 1,
                  "records": [{"id": r["id"], "fields": _kv(r)} for r in refunds]})

    rc = snap.get("rc_case")
    nodes.append({"entity": "rc_case", "label": "RC Case", "count": 1 if rc else 0,
                  "rule_fired": bool(rc and rc["status"] != "done"),
                  "records": [{"id": rc["id"], "fields": _kv(rc, "blocked_reason", "rc_transfer_stall")}] if rc else []})

    rf = snap.get("refurb")
    nodes.append({"entity": "refurb_job", "label": "Refurb Job", "count": 1 if rf else 0,
                  "rule_fired": bool(rf and not rf["completed_at"]),
                  "records": [{"id": rf["id"], "fields": _kv(rf, "blocked_reason", "refurb_overrun")}] if rf else []})

    d = snap.get("delivery")
    nodes.append({"entity": "delivery", "label": "Delivery", "count": 1 if d else 0,
                  "rule_fired": bool(d and d["attempt_count"] >= 3),
                  "records": [{"id": d["id"], "fields": _kv(d, "attempt_count", "delivery_attempts_exhausted")}] if d else []})

    if t["order_id"]:
        v = await sql.one("""
            SELECT v.id, v.reg_no, v.make, v.model, v.year, v.km, v.listing_status
            FROM vehicle v JOIN orders o ON o.vehicle_id = v.id WHERE o.id = $1
        """, t["order_id"])
        if v:
            nodes.append({"entity": "vehicle", "label": "Vehicle", "count": 1,
                          "rule_fired": False, "records": [{"id": v["id"], "fields": _kv(v)}]})

    events = snap.get("events") or []
    nodes.append({"entity": "order_event", "label": "Order Events", "count": len(events),
                  "rule_fired": False,
                  "records": [{"id": str(e["id"]), "fields": _kv(e)} for e in events]})

    # The stepper. Reached states come from the ledger, not from order.state.
    canon = ["CREATED", "TOKEN_PAID", "FULL_PAID", "REFURB_DONE", "RC_DONE",
             "DISPATCH_SCHEDULED", "OUT_FOR_DELIVERY", "DELIVERED"]
    reached: dict[str, Any] = {}
    for e in events:
        reached.setdefault(e["to_state"], e["at"])
    current = events[-1]["to_state"] if events else None

    violations = rules.evaluate(snap)
    blocked = "RC_DONE" if violations and violations[0].blocking_entity \
        and violations[0].blocking_entity["type"] == "rc_case" else None

    timeline = [{
        "state": st,
        "at": _aware(reached[st]).strftime("%Y-%m-%d") if st in reached else None,
        "status": ("current" if st == current else
                   "done" if st in reached else
                   "blocked" if st == blocked else "pending"),
    } for st in canon]

    exp = rules.expected_state(snap)
    o = snap.get("order")
    caption = (f"Expected to be at {exp}. Currently {o['state']}."
               if o and exp and exp != o["state"] else "Order state matches the ledger.")

    return {"ticket_id": ticket_id, "nodes": nodes, "timeline": timeline,
            "timeline_caption": caption}


async def cohorts(sql: Sql) -> list[dict]:
    """
    Each cohort is a rule evaluated across the scope, never a saved filter.
    Because causes are structured rule ids rather than sentences, they aggregate.
    """
    tickets_by_order = {
        r["order_id"]: r["id"]
        for r in await sql.all("SELECT id, order_id FROM ticket WHERE order_id IS NOT NULL")
    }

    def build(cid: str, label: str, rule_id: str, description: str, rows: list[dict]) -> dict:
        return {
            "id": cid, "label": label, "rule_id": rule_id, "description": description,
            "members": [{
                "order_id": r["order_id"],
                "state": r["state"],
                "stuck_for": age(r["since"]) if r["since"] else "—",
                "blocking_reason": r["reason"],
                "ticket_id": tickets_by_order.get(r["order_id"]),
                "city_code": r["city_code"],
            } for r in rows],
        }

    return [
        build("rc-stall", "Stuck in RC transfer", "rc_transfer_stall",
              "FULL_PAID with the RC case not done.",
              await sql.all("""
                SELECT o.id AS order_id, o.state, o.updated_at AS since,
                       r.blocked_reason AS reason, o.city_code
                FROM orders o JOIN rc_case r ON r.order_id = o.id
                WHERE o.state = 'FULL_PAID' AND r.status <> 'done'
                ORDER BY o.updated_at ASC""")),

        build("capture-lag", "Payment captured, state not advanced", "payment_capture_lag",
              "A full payment captured while the order sits at or below TOKEN_PAID.",
              await sql.all("""
                SELECT o.id AS order_id, o.state, p.captured_at AS since,
                       'webhook_not_replayed' AS reason, o.city_code
                FROM orders o JOIN payment p ON p.order_id = o.id AND p.kind = 'full'
                WHERE p.status = 'captured' AND o.state IN ('CREATED','TOKEN_PAID')
                ORDER BY p.captured_at ASC""")),

        build("refurb-overrun", "Refurb past promised date", "refurb_overrun",
              "A refurb job past promised_at and not completed.",
              await sql.all("""
                SELECT o.id AS order_id, o.state, rj.promised_at AS since,
                       rj.blocked_reason AS reason, o.city_code
                FROM refurb_job rj JOIN orders o ON o.vehicle_id = rj.vehicle_id
                WHERE rj.completed_at IS NULL AND rj.promised_at < $1::timestamptz
                ORDER BY rj.promised_at ASC""", _now())),

        build("slot-missing", "No delivery scheduled", "delivery_slot_missing",
              "Past RC_DONE for over a day with no delivery row.",
              await sql.all("""
                SELECT o.id AS order_id, o.state, o.updated_at AS since,
                       'no_delivery_row' AS reason, o.city_code
                FROM orders o LEFT JOIN delivery d ON d.order_id = o.id
                WHERE d.id IS NULL AND o.state IN ('RC_DONE','REFURB_DONE')
                  AND o.updated_at < now() - interval '24 hours'
                ORDER BY o.updated_at ASC""")),

        build("attempts", "Delivery attempts exhausted", "delivery_attempts_exhausted",
              "Three or more failed delivery attempts.",
              await sql.all("""
                SELECT o.id AS order_id, o.state, d.slot_at AS since,
                       'attempts=' || d.attempt_count AS reason, o.city_code
                FROM delivery d JOIN orders o ON o.id = d.order_id
                WHERE d.attempt_count >= 3 ORDER BY d.attempt_count DESC""")),

        build("refund-dupes", "Duplicate refunds", "refund_duplication",
              "More than one refund row against the same payment_id.",
              await sql.all("""
                SELECT o.id AS order_id, o.state, min(r.created_at) AS since,
                       'refunds=' || count(*) AS reason, o.city_code
                FROM refund r JOIN orders o ON o.id = r.order_id
                GROUP BY r.payment_id, o.id, o.state, o.city_code HAVING count(*) > 1""")),

        build("payout-hold", "Blocked on a seller payout", "seller_payout_hold",
              "A sell-side payout that has not completed, holding a buy-side order.",
              await sql.all("""
                SELECT o.id AS order_id, o.state, o.updated_at AS since,
                       'payout=' || p.status AS reason, o.city_code
                FROM payment p
                JOIN orders so ON so.id = p.order_id
                JOIN orders o ON o.vehicle_id = so.vehicle_id AND o.id <> so.id
                WHERE p.kind = 'payout' AND p.status <> 'captured'""")),

        build("double-alloc", "Vehicle on two live orders", "inventory_double_allocation",
              "The same vehicle allocated to more than one order that is still live.",
              await sql.all("""
                SELECT o.id AS order_id, o.state, o.created_at AS since,
                       'vehicle=' || o.vehicle_id AS reason, o.city_code
                FROM orders o
                WHERE o.state NOT IN ('CLOSED','REFUNDED')
                  AND o.vehicle_id IN (
                    SELECT vehicle_id FROM orders WHERE state NOT IN ('CLOSED','REFUNDED')
                    GROUP BY vehicle_id HAVING count(*) > 1)
                ORDER BY o.vehicle_id, o.id""")),

        build("return-boundary", "Return requested near the window edge", "return_window_boundary",
              "A return requested within a day of the 7-day window closing.",
              await sql.all("""
                SELECT o.id AS order_id, o.state, o.updated_at AS since,
                       'return_requested' AS reason, o.city_code
                FROM orders o WHERE o.state = 'RETURN_REQUESTED'""")),

        build("ledger", "State disagrees with the ledger", "state_ledger_mismatch",
              "orders.state does not match the last order_event.to_state.",
              await sql.all("""
                SELECT o.id AS order_id, o.state, o.updated_at AS since,
                       'last_event=' || e.to_state AS reason, o.city_code
                FROM orders o JOIN LATERAL (
                  SELECT to_state FROM order_event WHERE order_id = o.id
                  ORDER BY at DESC, id DESC LIMIT 1) e ON true
                WHERE o.state <> e.to_state""")),
    ]


async def ticket_cohorts(sql: Sql) -> list[dict]:
    """
    The five ticket rules. Separate from `cohorts` because a member here is a
    ticket, not an order — `ticket_orphaned` has no order by definition.
    """
    def build(cid: str, label: str, rule_id: str, description: str, rows: list[dict]) -> dict:
        return {
            "id": cid, "label": label, "rule_id": rule_id, "description": description,
            "members": [{
                "ticket_id": r["id"],
                "subject": r["subject"],
                "state": r["state"],
                "waiting_for": age(r["since"]) if r["since"] else "—",
                "order_id": r["order_id"],
                "city_code": r["city_code"],
            } for r in rows],
        }

    return [
        build("first-response", "First response SLA breached", "ticket_first_response_breach",
              "OPEN past the first-response SLA with no reply.",
              await sql.all("""
                SELECT id, subject, state, created_at AS since, order_id, city_code
                FROM ticket WHERE state = 'OPEN' AND first_response_at IS NULL
                  AND created_at < now() - interval '24 hours'
                ORDER BY created_at ASC""")),

        build("no-cause", "Resolved without evidence", "ticket_resolved_without_cause",
              "RESOLVED or CLOSED with no resolution_evidence.",
              await sql.all("""
                SELECT id, subject, state, resolved_at AS since, order_id, city_code
                FROM ticket WHERE state IN ('RESOLVED','CLOSED')
                  AND resolution_evidence IS NULL""")),

        build("reopen-loop", "Reopen loop", "ticket_reopen_loop",
              "Reopened two or more times, so the underlying cause is unresolved.",
              await sql.all("""
                SELECT id, subject, state, created_at AS since, order_id, city_code
                FROM ticket WHERE reopen_count >= 2 ORDER BY reopen_count DESC""")),

        build("orphaned", "No linked order", "ticket_orphaned",
              "No order_id, so nothing can be diagnosed against it.",
              await sql.all("""
                SELECT id, subject, state, created_at AS since, order_id, city_code
                FROM ticket WHERE order_id IS NULL ORDER BY created_at ASC""")),

        build("stale", "Stale awaiting customer", "ticket_stale_blocked",
              "AWAITING_CUSTOMER for more than 7 days with no follow-up.",
              await sql.all("""
                SELECT id, subject, state,
                       COALESCE(first_response_at, created_at) AS since, order_id, city_code
                FROM ticket WHERE state = 'AWAITING_CUSTOMER'
                  AND COALESCE(first_response_at, created_at) < now() - interval '7 days'""")),
    ]


async def audit_log(sql: Sql) -> list[dict]:
    rows = await sql.all("""
        SELECT id, answer_id, order_id, ticket_id, action, proposal, proposed_by,
               approved_by, rule_id, rule_version, idempotency_key, executed_at, result
        FROM action_audit ORDER BY id DESC
    """)
    return [{
        "id": r["id"], "answer_id": r["answer_id"], "action": r["action"],
        "proposal": r["proposal"], "proposed_by": r["proposed_by"],
        "approved_by": r["approved_by"], "rule_id": r["rule_id"],
        "idempotency_key": r["idempotency_key"],
        "executed_at": _stamp(r["executed_at"]) if r["executed_at"] else None,
        "result": r["result"], "order_id": r["order_id"],
    } for r in rows]


async def console_schema(sql: Sql) -> list[dict]:
    """Read from the catalog, not from a hand-written list that can drift."""
    rows = await sql.all("""
        SELECT c.table_name, c.column_name, c.data_type, c.character_maximum_length,
               (pk.column_name IS NOT NULL) AS is_pk
        FROM information_schema.columns c
        LEFT JOIN (
          SELECT kcu.table_name, kcu.column_name
          FROM information_schema.table_constraints tc
          JOIN information_schema.key_column_usage kcu
            ON kcu.constraint_name = tc.constraint_name
          WHERE tc.constraint_type = 'PRIMARY KEY'
        ) pk ON pk.table_name = c.table_name AND pk.column_name = c.column_name
        WHERE c.table_schema = 'public'
          AND c.table_name IN ('customer','vehicle','orders','order_event','payment',
                               'refund','rc_case','refurb_job','delivery','ticket',
                               'ticket_message')
        ORDER BY c.table_name, c.ordinal_position
    """)
    by_table: dict[str, list[dict]] = {}
    for r in rows:
        if r["character_maximum_length"]:
            t = f'varchar({r["character_maximum_length"]})'
        elif r["data_type"] == "timestamp with time zone":
            t = "timestamptz"
        elif r["data_type"] == "character varying":
            t = "varchar"
        else:
            t = r["data_type"]
        by_table.setdefault(r["table_name"], []).append(
            {"name": r["column_name"], "type": t, "pk": r["is_pk"]}
        )
    return [{"name": n, "columns": c} for n, c in by_table.items()]
