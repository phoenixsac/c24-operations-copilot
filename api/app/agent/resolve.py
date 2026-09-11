"""
AGT-4 — entity resolution.

Turns the IR's entity refs into a snapshot the rules engine can run over.

Everything here goes through `with_session`'s scoped connection, so resolution
is bounded by RLS: an order in another city does not resolve, and the caller
cannot tell whether it does not exist or is merely invisible. That ambiguity is
the point (ADR-001) — a message distinguishing the two would confirm the
existence of records the operator may not see.

Which is also why `NotFound` carries no detail about *why*. Eval L-03 asks for
order 9999, which does not exist; the honest answer and the safe answer are the
same sentence.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.ir import IR, EntityType
from app.data.queries import snapshot, snapshot_for_order
from app.db import Sql


@dataclass
class Resolved:
    snap: dict
    order_id: int | None
    ticket_id: str | None
    # Free text pulled for the planner's context. Untrusted, unscrubbed at this
    # point — `wrap_untrusted` handles it at prompt assembly, which is the only
    # boundary that survives being read back from storage later (eval X-02d).
    context: str | None


class NotFound(Exception):
    """Named neither 'missing' nor 'forbidden'. Both, on purpose."""


class Ambiguous(Exception):
    """
    More than one order fits, and picking one would be a guess.

    Carries the candidates so the refusal can list them and the operator can
    choose. Eval T-04: a customer writes "my Swift hasn't arrived" on a ticket
    with no order linked, and the right answer is a question, not an order id.
    """

    def __init__(self, candidates: list[dict], what: str) -> None:
        super().__init__(f"{len(candidates)} orders match {what}")
        self.candidates = candidates
        self.what = what


async def resolve(sql: Sql, ir: IR, ticket_id: str | None) -> Resolved:
    """
    Resolution order: an explicit ticket in the IR, then the ticket the operator
    has open, then an order id. A question naming an order resolves against the
    order even when a ticket is open, because "payment status 4521" means 4521.
    """
    want_ticket = next(
        (str(e.id) for e in ir.entities if e.type is EntityType.TICKET), None
    )
    want_order = next(
        (int(e.id) for e in ir.entities
         if e.type is EntityType.ORDER and str(e.id).isdigit()), None
    )
    want_reg = next(
        (str(e.id) for e in ir.entities
         if e.type is EntityType.VEHICLE and not str(e.id).startswith("v_")
         and e.id != "*"), None
    )

    # A registration resolves to a vehicle, and a vehicle can carry more than
    # one live order — which is the whole point of `inventory_double_allocation`.
    # The oldest is taken as the subject because it is the one that was
    # allocated first and therefore the one with the claim; the rules engine
    # sees all of them through `vehicle_live_orders` regardless.
    if want_reg is not None:
        rows = await sql.all(
            """
            SELECT o.id FROM orders o
            JOIN vehicle v ON v.id = o.vehicle_id
            WHERE upper(replace(replace(v.reg_no, ' ', ''), '-', '')) = $1
            ORDER BY o.created_at ASC, o.id ASC
            """,
            want_reg,
        )
        if not rows:
            raise NotFound(f"vehicle {want_reg}")
        want_order = rows[0]["id"]

    if want_order is not None:
        snap = await snapshot_for_order(sql, want_order)
        if not snap.get("order"):
            raise NotFound(f"order {want_order}")
        return Resolved(snap, want_order, (snap.get("ticket") or {}).get("id"),
                        _context(snap))

    tid = want_ticket or ticket_id
    if tid:
        snap = await snapshot(sql, tid)
        if not snap.get("ticket"):
            raise NotFound(f"ticket {tid}")

        # A ticket with no order linked is not a dead end — the customer is
        # known, and their orders are reachable. `ticket_orphaned` exists as a
        # rule precisely because this happens. Eval T-04.
        if not snap.get("order"):
            resolved = await _via_customer(sql, snap["ticket"]["id"])
            if resolved is not None:
                return resolved

        order = snap.get("order") or {}
        return Resolved(snap, order.get("id"), tid, _context(snap))

    raise NotFound("no entity")


async def _via_customer(sql: Sql, ticket_id: str) -> Resolved | None:
    """
    ticket → customer → their orders.

    Exactly one live order: resolve it, and say so in the answer rather than
    silently. More than one: raise `Ambiguous` and let the caller ask. None:
    return None and let the ticket stand on its own.

    The temptation is to pick the most recent when there are several. That is a
    guess wearing a heuristic's clothes, and an ops agent acting on the wrong
    order is a worse outcome than one extra question.
    """
    rows = await sql.all(
        """
        SELECT o.id, o.state, v.make, v.model, o.created_at
        FROM ticket t
        JOIN orders o ON o.customer_id = t.customer_id
        JOIN vehicle v ON v.id = o.vehicle_id
        WHERE t.id = $1 AND o.state NOT IN ('CLOSED', 'REFUNDED')
        ORDER BY o.created_at DESC, o.id DESC
        """,
        ticket_id,
    )
    if not rows:
        return None
    if len(rows) > 1:
        raise Ambiguous(
            [{"order_id": r["id"], "vehicle": f"{r['make']} {r['model']}",
              "state": r["state"]} for r in rows],
            "this customer",
        )

    snap = await snapshot_for_order(sql, rows[0]["id"])
    t = await sql.one(
        "SELECT id, state, subject, body, resolution_evidence, reopen_count, "
        "resolved_by, resolved_at, order_id, created_at, first_response_at, "
        "resolution_code FROM ticket WHERE id = $1",
        ticket_id,
    )
    if t:
        snap["ticket"] = t
    return Resolved(snap, rows[0]["id"], ticket_id, _context(snap))


def _context(snap: dict) -> str | None:
    """
    The untrusted free text a planner may see, assembled in one place so there
    is exactly one list to audit.

    `rc_case.blocked_reason` is here because it arrives from an external RTO
    feed — a third-party system field is untrusted too (eval X-02c), which is
    easy to forget when only customer messages feel like an attack surface.
    Same for `resolution_evidence`, which is our own text but was written by a
    previous turn and may carry something scrubbed at ingest and stored anyway.
    """
    parts: list[str] = []
    t = snap.get("ticket") or {}
    if t.get("subject"):
        parts.append(f"subject: {t['subject']}")
    if t.get("body"):
        parts.append(f"message: {t['body']}")
    if t.get("resolution_evidence"):
        parts.append(f"prior resolution evidence: {t['resolution_evidence']}")
    rc = snap.get("rc_case") or {}
    if rc.get("blocked_reason"):
        parts.append(f"rc blocked reason: {rc['blocked_reason']}")
    refurb = snap.get("refurb") or {}
    if refurb.get("blocked_reason"):
        parts.append(f"refurb blocked reason: {refurb['blocked_reason']}")
    for m in snap.get("messages") or []:
        if m.get("body"):
            parts.append(f"{m.get('direction', 'in')}: {m['body']}")
    return "\n".join(parts) if parts else None
