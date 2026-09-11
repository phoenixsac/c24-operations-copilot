"""
The IR — the contract between the model and everything else.

This module is the reason the backend is Python. The IR is the central contract
of the design, and Pydantic collapses three things into one declaration:

  1. runtime validation of whatever the planner returns,
  2. the JSON Schema handed to the model as a tool/output schema,
  3. the type the rest of the code reads.

In TypeScript those are three artifacts that can silently disagree.

Every field is an enum or a typed scalar. There is no field where arbitrary
text can travel — if you find yourself widening one to `str`, that is the
injection surface reopening. docs/INVARIANTS.md J1, J6.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class QueryShape(str, Enum):
    """
    Closed enum, one execution path each. docs/README_v3.md §Query shapes.

    `LOOKUP` covers both a single field and a multi-tool fan-out narrated as one
    answer. Those were separate shapes until it became clear the only difference
    was breadth, not execution path.

    `CONCEPT` is the only shape that touches no records at all. It reads the
    curated glossary and nothing else, which is why it is also the only shape
    that needs no scope: there is no row to leak.

    `UNSUPPORTED` is not a shape the planner may return. The router emits it
    when it cannot classify with confidence, and the request becomes a refusal
    rather than a guess.
    """

    LOOKUP = "lookup"
    DIAGNOSIS = "diagnosis"
    AGGREGATE = "aggregate"
    COHORT = "cohort"
    POLICY = "policy"
    ACTION = "action"
    # Answers from the glossary, not from records. "What does TOKEN_PAID mean"
    # is a question about the schema rather than about a row, and the six
    # record shapes could not express it — so it was refused when asked plainly
    # and improvised when phrasing dragged it into `diagnosis`. The second is
    # the worse failure: an invented definition is indistinguishable from a
    # real one to the person reading it. ADR-036.
    CONCEPT = "concept"
    UNSUPPORTED = "unsupported"


class EntityType(str, Enum):
    ORDER = "order"
    CUSTOMER = "customer"
    VEHICLE = "vehicle"
    PAYMENT = "payment"
    REFUND = "refund"
    RC_CASE = "rc_case"
    REFURB_JOB = "refurb_job"
    DELIVERY = "delivery"
    TICKET = "ticket"
    ORDER_EVENT = "order_event"


class FilterOp(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    CONTAINS = "contains"


class OrderState(str, Enum):
    CREATED = "CREATED"
    TOKEN_PAID = "TOKEN_PAID"
    FULL_PAID = "FULL_PAID"
    REFURB_DONE = "REFURB_DONE"
    RC_DONE = "RC_DONE"
    DISPATCH_SCHEDULED = "DISPATCH_SCHEDULED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    RETURN_WINDOW_OPEN = "RETURN_WINDOW_OPEN"
    CLOSED = "CLOSED"
    RETURN_REQUESTED = "RETURN_REQUESTED"
    REFUNDED = "REFUNDED"
    SELLER_PAYOUT_PENDING = "SELLER_PAYOUT_PENDING"
    SELLER_PAYOUT_DONE = "SELLER_PAYOUT_DONE"


class ActionId(str, Enum):
    """
    The actions the rules engine can suggest.

    The model SELECTS from this enum; it never authors an action name or its
    parameters. Injected text cannot name an action that is not here, which is
    why a missed injection detection is survivable. docs/INVARIANTS.md J1.
    """

    REPLAY_WEBHOOK = "replay_webhook"
    ESCALATE_RTO = "escalate_rto"
    NOTIFY_CUSTOMER_DELAY = "notify_customer_delay"
    SCHEDULE_DELIVERY = "schedule_delivery"
    CALL_CUSTOMER = "call_customer"
    FREEZE_AND_REVIEW = "freeze_and_review"
    ROUTE_TO_SELLSIDE = "route_to_sellside"
    CANCEL_LATER_ORDER = "cancel_later_order"
    SUPERVISOR_EXCEPTION = "supervisor_exception"
    RECONCILE = "reconcile"
    ASSIGN_NOW = "assign_now"
    REOPEN_FOR_AUDIT = "reopen_for_audit"
    ESCALATE_SUPERVISOR = "escalate_supervisor"
    REQUEST_IDENTIFIER = "request_identifier"
    AUTO_FOLLOWUP = "auto_followup"
    REFUND = "refund"


class RuleId(str, Enum):
    """All 15. docs/DOMAIN_v2.md §4."""

    PAYMENT_CAPTURE_LAG = "payment_capture_lag"
    RC_TRANSFER_STALL = "rc_transfer_stall"
    REFURB_OVERRUN = "refurb_overrun"
    DELIVERY_SLOT_MISSING = "delivery_slot_missing"
    DELIVERY_ATTEMPTS_EXHAUSTED = "delivery_attempts_exhausted"
    REFUND_DUPLICATION = "refund_duplication"
    SELLER_PAYOUT_HOLD = "seller_payout_hold"
    INVENTORY_DOUBLE_ALLOCATION = "inventory_double_allocation"
    RETURN_WINDOW_BOUNDARY = "return_window_boundary"
    STATE_LEDGER_MISMATCH = "state_ledger_mismatch"
    TICKET_FIRST_RESPONSE_BREACH = "ticket_first_response_breach"
    TICKET_RESOLVED_WITHOUT_CAUSE = "ticket_resolved_without_cause"
    TICKET_REOPEN_LOOP = "ticket_reopen_loop"
    TICKET_ORPHANED = "ticket_orphaned"
    TICKET_STALE_BLOCKED = "ticket_stale_blocked"


class EntityRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: EntityType
    id: str | int


class Filter(BaseModel):
    """AST nodes, never SQL. The data layer compiles these. J6."""

    model_config = ConfigDict(extra="forbid")
    field: str
    op: FilterOp
    value: str | int | float | bool | list[str | int]


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: str = Field(alias="from")
    to: str


class IR(BaseModel):
    """
    What the planner returns and everything downstream consumes.

    `extra="forbid"` is load-bearing: a model that invents a field gets a
    validation error rather than having it silently ignored.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    shape: QueryShape
    entities: list[EntityRef] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    time_window: TimeWindow | None = None
    # Drawn from the rules engine's own output, never authored by the model.
    requested_action: ActionId | None = None
    ambiguities: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class FiredRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: RuleId
    version: int
    # The exact field values that fired it. docs/INVARIANTS.md A1.
    triggering_fields: dict[str, str | int | float]


class BlockingEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    id: str
    reason: str


class Violation(BaseModel):
    """Diagnosis is a diff, not a narration."""

    model_config = ConfigDict(extra="forbid")
    # Optional because five of the fifteen rules are about the ticket, not the
    # order, and `ticket_orphaned` is the case that proves it: a ticket with no
    # order linked is precisely what that rule detects. Requiring an order id
    # here meant those rules produced no violation at all — no expected state,
    # no suggested action, nothing for the console to show — so the one rule
    # whose entire subject is a missing order could not be reported.
    order_id: int | None = None
    expected_state: str
    observed_state: str
    stuck_for: str
    primary_rule: RuleId
    blocking_entity: BlockingEntity | None = None
    suggested_action: ActionId
