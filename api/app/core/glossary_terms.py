"""
The content half of the glossary. Kept apart from `glossary.py` so the lookup
logic and the domain text can be reviewed independently — this file is prose,
that one is code.

Everything below is derived from docs/DOMAIN_v2.md (§1 entities, §2 order
state machine, §3 ticket lifecycle, §4 invariants → rules) and the live
thresholds in `app/core/rules.py::Config`. Nothing here is invented: where the
sources are silent on detail (NOC, for instance), the definition stays short
rather than guessing at specifics no source states.

`test_glossary_covers_enums` fails if `OrderState`, `RuleId`, or `EntityType`
gain a value with no matching entry here — this file is expected to grow with
the schema, not the other way round.
"""

from __future__ import annotations

from app.core.glossary import Term

TERMS: dict[str, Term] = {}
ALIASES: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Order states — docs/DOMAIN_v2.md §2
#
# CREATED → TOKEN_PAID → FULL_PAID → REFURB_DONE → RC_DONE
#         → DISPATCH_SCHEDULED → OUT_FOR_DELIVERY → DELIVERED
#         → RETURN_WINDOW_OPEN → CLOSED
#                             ↘ RETURN_REQUESTED → REFUNDED
#
# Plus the stubbed sell-side pair, SELLER_PAYOUT_PENDING/DONE, which exists so
# a cross-seam blocker (seller_payout_hold) can be modelled without building
# out a full sell funnel.
# ---------------------------------------------------------------------------

TERMS["created"] = Term(
    term="CREATED",
    definition=(
        "The order exists but the customer has not paid anything yet. "
        "It moves forward once the token payment is captured."
    ),
    kind="state",
    see_also=("token_paid",),
)

TERMS["token_paid"] = Term(
    term="TOKEN_PAID",
    definition=(
        "The customer has paid a token — a partial, booking amount — to hold the "
        "vehicle, but the remaining purchase price has not been paid. The order "
        "advances to full_paid once the balance is captured."
    ),
    kind="state",
    see_also=("created", "full_paid"),
)

TERMS["full_paid"] = Term(
    term="FULL_PAID",
    definition=(
        "The customer has paid the full purchase price, not just the token. "
        "With the money in, reconditioning and the RC ownership transfer can "
        "proceed; the order advances to refurb_done once reconditioning finishes."
    ),
    kind="state",
    see_also=("token_paid", "refurb_done", "refurb_job"),
)

TERMS["refurb_done"] = Term(
    term="REFURB_DONE",
    definition=(
        "Reconditioning of the vehicle is complete. The order advances to "
        "rc_done once the RC ownership transfer also completes."
    ),
    kind="state",
    see_also=("full_paid", "rc_done", "refurb_job"),
)

TERMS["rc_done"] = Term(
    term="RC_DONE",
    definition=(
        "The RC ownership transfer has completed. Dispatch was gated on this, "
        "so a delivery can now be scheduled."
    ),
    kind="state",
    see_also=("refurb_done", "dispatch_scheduled", "rc_case"),
)

TERMS["dispatch_scheduled"] = Term(
    term="DISPATCH_SCHEDULED",
    definition=(
        "A delivery slot has been scheduled for the order. The order advances "
        "to out_for_delivery once the vehicle is actually on its way."
    ),
    kind="state",
    see_also=("rc_done", "out_for_delivery", "delivery"),
)

TERMS["out_for_delivery"] = Term(
    term="OUT_FOR_DELIVERY",
    definition=(
        "The vehicle is on its way to the customer. The order advances to "
        "delivered once the handover succeeds."
    ),
    kind="state",
    see_also=("dispatch_scheduled", "delivered", "delivery"),
)

TERMS["delivered"] = Term(
    term="DELIVERED",
    definition=(
        "The vehicle has been handed over to the customer. This opens the "
        "return window during which the customer can still request a return."
    ),
    kind="state",
    see_also=("out_for_delivery", "return_window_open"),
)

TERMS["return_window_open"] = Term(
    term="RETURN_WINDOW_OPEN",
    definition=(
        "The order is inside the post-delivery return window — the customer "
        "may still ask to return the vehicle. It ends in closed if no return is "
        "requested, or in return_requested if one is."
    ),
    kind="state",
    see_also=("delivered", "closed", "return_requested"),
)

TERMS["closed"] = Term(
    term="CLOSED",
    definition="The order finished normally: delivered, and no return was requested within the window. Terminal state.",
    kind="state",
    see_also=("return_window_open",),
)

TERMS["return_requested"] = Term(
    term="RETURN_REQUESTED",
    definition=(
        "The customer has asked to return the vehicle inside the return "
        "window. The order moves to refunded once that return is processed."
    ),
    kind="state",
    see_also=("return_window_open", "refunded", "return_window_boundary"),
)

TERMS["refunded"] = Term(
    term="REFUNDED",
    definition="The refund for a returned order has been completed. Terminal state.",
    kind="state",
    see_also=("return_requested", "refund"),
)

TERMS["seller_payout_pending"] = Term(
    term="SELLER_PAYOUT_PENDING",
    definition=(
        "Sell-side stub state: the payout owed to the seller on the linked "
        "sell-side order has not completed yet. While pending, it can hold up "
        "a connected buy-side order."
    ),
    kind="state",
    see_also=("seller_payout_done", "payout", "seller_payout_hold"),
)

TERMS["seller_payout_done"] = Term(
    term="SELLER_PAYOUT_DONE",
    definition="Sell-side stub state: the payout owed to the seller has completed. Terminal for this stubbed funnel.",
    kind="state",
    see_also=("seller_payout_pending", "payout"),
)

# ---------------------------------------------------------------------------
# Entities — docs/DOMAIN_v2.md §1
# ---------------------------------------------------------------------------

TERMS["order"] = Term(
    term="Order",
    definition=(
        "One purchase transaction linking a customer to a vehicle, tracked "
        "through the order state machine from creation to closure or refund."
    ),
    kind="entity",
    see_also=("order_event", "ticket"),
)

TERMS["customer"] = Term(
    term="Customer",
    definition="The person buying (or selling) a vehicle through Cars24. Orders and tickets are linked to a customer.",
    kind="entity",
    see_also=("order", "ticket"),
)

TERMS["vehicle"] = Term(
    term="Vehicle",
    definition=(
        "A specific car, identified by its registration number, with a life "
        "that spans many orders over time — bought, refurbished, sold, "
        "returned, relisted."
    ),
    kind="entity",
    see_also=("order", "refurb_job", "rc_case"),
)

TERMS["payment"] = Term(
    term="Payment",
    definition="A money-in record against an order — a token payment, the full payment, or a seller payout — with a captured status and time.",
    kind="entity",
    see_also=("order", "refund", "payment_capture_lag"),
)

TERMS["refund"] = Term(
    term="Refund",
    definition=(
        "A money-out record against a specific payment, protected by an "
        "idempotency key so a retried refund request cannot silently pay out twice."
    ),
    kind="entity",
    see_also=("payment", "idempotency_key", "refund_duplication"),
)

TERMS["rc_case"] = Term(
    term="RC case",
    definition=(
        "The record tracking transfer of the vehicle's RC — its registration "
        "certificate, the legal proof of ownership — into the customer's name. "
        "The order cannot be dispatched until this is done."
    ),
    kind="entity",
    see_also=("rc_transfer_stall", "rto", "rc_done"),
)

TERMS["refurb_job"] = Term(
    term="Refurb job",
    definition="The reconditioning work done on a vehicle before it can be delivered, tracked against a promised completion date.",
    kind="entity",
    see_also=("refurb_overrun", "vehicle", "refurb_done"),
)

TERMS["delivery"] = Term(
    term="Delivery",
    definition="The scheduled handover of the vehicle to the customer, tracked by slot time, status, and number of attempts made.",
    kind="entity",
    see_also=("delivery_slot_missing", "delivery_attempts_exhausted", "dispatch_scheduled"),
)

TERMS["ticket"] = Term(
    term="Ticket",
    definition=(
        "The unit of customer-facing work — a support conversation, optionally "
        "linked to an order, tracked through its own lifecycle separate from "
        "the order's state machine."
    ),
    kind="entity",
    see_also=("order", "ticket_first_response_breach"),
)

TERMS["order_event"] = Term(
    term="Order event",
    definition=(
        "The append-only log of every order state transition. It is the "
        "source of truth — when the order's own state disagrees with the "
        "latest event, the event log is right and the state column is the defect."
    ),
    kind="entity",
    see_also=("state_ledger_mismatch", "order"),
)

# ---------------------------------------------------------------------------
# Rules — docs/DOMAIN_v2.md §4, thresholds from rules.py::Config
# ---------------------------------------------------------------------------

TERMS["payment_capture_lag"] = Term(
    term="payment_capture_lag",
    definition=(
        "Fires when a payment has captured but the order hasn't advanced "
        "within 30 minutes — usually a payment webhook that never landed. "
        "Suggested fix: replay the webhook."
    ),
    kind="rule",
    see_also=("payment", "created"),
)

TERMS["rc_transfer_stall"] = Term(
    term="rc_transfer_stall",
    definition=(
        "Fires when an order has been fully paid for more than 72 hours and "
        "the RC ownership transfer still isn't done — the block holding up "
        "dispatch. Suggested fix: escalate to the RTO."
    ),
    kind="rule",
    see_also=("rc_case", "rto", "full_paid"),
)

TERMS["refurb_overrun"] = Term(
    term="refurb_overrun",
    definition=(
        "Fires when a vehicle's reconditioning has passed its promised "
        "completion date and still isn't marked done. Suggested fix: notify "
        "the customer of the delay."
    ),
    kind="rule",
    see_also=("refurb_job",),
)

TERMS["delivery_slot_missing"] = Term(
    term="delivery_slot_missing",
    definition=(
        "Fires when an order has sat in rc_done or refurb_done for more than "
        "24 hours with no delivery scheduled at all. Suggested fix: schedule the delivery."
    ),
    kind="rule",
    see_also=("delivery", "rc_done"),
)

TERMS["delivery_attempts_exhausted"] = Term(
    term="delivery_attempts_exhausted",
    definition=(
        "Fires once a delivery has failed 3 or more attempts — it needs a "
        "human to call the customer rather than another automatic retry."
    ),
    kind="rule",
    see_also=("delivery",),
)

TERMS["refund_duplication"] = Term(
    term="refund_duplication",
    definition=(
        "Fires when more than one refund exists against the same payment — a "
        "serious money-out defect. Suggested fix: freeze the case and review "
        "before anything else happens."
    ),
    kind="rule",
    see_also=("refund", "idempotency_key"),
)

TERMS["seller_payout_hold"] = Term(
    term="seller_payout_hold",
    definition=(
        "Fires when the sell-side order linked to this transaction is stuck "
        "— typically on seller KYC — which in turn holds up the connected "
        "buy-side order. The only rule that crosses from the sell funnel into "
        "the buy funnel. Suggested fix: route to the sell-side team."
    ),
    kind="rule",
    see_also=("seller_payout_pending", "payout"),
)

TERMS["inventory_double_allocation"] = Term(
    term="inventory_double_allocation",
    definition="Fires when the same vehicle is allocated to more than one live order at once. Suggested fix: cancel the later order.",
    kind="rule",
    see_also=("vehicle",),
)

TERMS["return_window_boundary"] = Term(
    term="return_window_boundary",
    definition=(
        "Fires when a return is requested within 24 hours of the return "
        "window's expiry — close enough to the edge that it needs a "
        "supervisor's judgment call rather than an automatic decision."
    ),
    kind="rule",
    see_also=("return_window", "return_requested"),
)

TERMS["state_ledger_mismatch"] = Term(
    term="state_ledger_mismatch",
    definition=(
        "Fires when the order's own state disagrees with the last recorded "
        "event in its ledger. The ledger is always treated as correct, so "
        "this means the state column itself is the defect. Suggested fix: reconcile."
    ),
    kind="rule",
    see_also=("order_event", "order"),
)

TERMS["ticket_first_response_breach"] = Term(
    term="ticket_first_response_breach",
    definition=(
        "Fires when a ticket is still open with no first reply after 24 "
        "hours, breaching the first-response SLA. Suggested fix: assign it now."
    ),
    kind="rule",
    see_also=("ticket", "sla"),
)

TERMS["ticket_resolved_without_cause"] = Term(
    term="ticket_resolved_without_cause",
    definition=(
        "Fires when a ticket is marked resolved or closed with no supporting "
        "evidence on record — a resolution with no documented reason. "
        "Suggested fix: reopen it for audit."
    ),
    kind="rule",
    see_also=("ticket",),
)

TERMS["ticket_reopen_loop"] = Term(
    term="ticket_reopen_loop",
    definition=(
        "Fires when a ticket has been reopened 2 or more times, meaning "
        "whatever caused it was never actually fixed. Suggested fix: escalate "
        "to a supervisor."
    ),
    kind="rule",
    see_also=("ticket",),
)

TERMS["ticket_orphaned"] = Term(
    term="ticket_orphaned",
    definition=(
        "Fires when a ticket has no order linked to it but a resolution was "
        "attempted anyway — there's nothing concrete to diagnose against. "
        "Suggested fix: ask the customer for an identifier."
    ),
    kind="rule",
    see_also=("ticket",),
)

TERMS["ticket_stale_blocked"] = Term(
    term="ticket_stale_blocked",
    definition=(
        "Fires when a ticket has been waiting on the customer for more than "
        "7 days with no follow-up sent. Suggested fix: send an automatic follow-up."
    ),
    kind="rule",
    see_also=("ticket",),
)

# ---------------------------------------------------------------------------
# Concepts an agent uses that no single table names
# ---------------------------------------------------------------------------

TERMS["rto"] = Term(
    term="RTO",
    definition=(
        "The Regional Transport Office — the government authority that "
        "processes RC ownership transfers. rc_transfer_stall escalates to the "
        "RTO once a transfer has stalled past the threshold."
    ),
    kind="concept",
    see_also=("rc_case", "rc_transfer_stall"),
)

TERMS["noc"] = Term(
    term="NOC",
    definition=(
        "No Objection Certificate — a clearance that can be a blocking "
        "requirement during RC ownership transfer. Not detailed further in "
        "this system's records."
    ),
    kind="concept",
    see_also=("rc_case",),
)

TERMS["sla"] = Term(
    term="SLA",
    definition=(
        "Service level agreement — the target time a ticket must be handled "
        "within. The only SLA this system enforces is first response: 24 "
        "hours from a ticket opening, per ticket_first_response_breach."
    ),
    kind="concept",
    see_also=("ticket_first_response_breach", "ticket"),
)

TERMS["payout"] = Term(
    term="Payout",
    definition=(
        "Money paid to a seller on the sell-side of a linked transaction, "
        "recorded as a payment of kind payout. A stalled payout holds up the "
        "connected buy-side order (seller_payout_hold)."
    ),
    kind="concept",
    see_also=("seller_payout_hold", "seller_payout_pending"),
)

TERMS["return_window"] = Term(
    term="Return window",
    definition=(
        "The 7-day period after delivery during which a customer may request "
        "a return. Requests made within 24 hours of it closing are treated as "
        "a boundary case needing supervisor judgment."
    ),
    kind="concept",
    see_also=("return_window_open", "return_window_boundary"),
)

TERMS["idempotency_key"] = Term(
    term="Idempotency key",
    definition=(
        "A unique token attached to a refund so that retrying the same "
        "refund request cannot create a duplicate payout. When a duplicate "
        "shows up anyway, refund_duplication catches it."
    ),
    kind="concept",
    see_also=("refund", "refund_duplication"),
)

# ---------------------------------------------------------------------------
# Roles — docs/DOMAIN_v2.md §5, scoping model
# ---------------------------------------------------------------------------

TERMS["l1_agent"] = Term(
    term="l1_agent",
    definition=(
        "Sees only their own city's data. Can read, ask, propose actions, "
        "resolve tickets, and issue refunds up to ₹25,000 without escalation."
    ),
    kind="role",
    see_also=("supervisor", "copilot_readonly"),
)

TERMS["supervisor"] = Term(
    term="supervisor",
    definition=(
        "Sees their whole region, not just one city. Can do everything an "
        "l1_agent can, plus approve refunds and actions above ₹25,000, grant "
        "policy exceptions, and use the query console."
    ),
    kind="role",
    see_also=("l1_agent",),
)

TERMS["copilot_readonly"] = Term(
    term="copilot_readonly",
    definition=(
        "Scoped to whatever ticket is currently in context. Lookup only — no "
        "writes — the role Tier 2 auto-resolution runs under."
    ),
    kind="role",
    see_also=("l1_agent",),
)

# ---------------------------------------------------------------------------
# Aliases — the surface forms people actually type
# ---------------------------------------------------------------------------

ALIASES.update({
    "token_payment": "token_paid",
    "full_payment": "full_paid",
    "rc": "rc_case",
    "registration_certificate": "rc_case",
    "ownership_transfer": "rc_case",
    "refurbishment": "refurb_job",
    "reconditioning": "refurb_job",
    "seller_payout": "payout",
    "ledger": "order_event",
    "source_of_truth": "order_event",
    "registration_certificate_case": "rc_case",
})
