/**
 * The IR — the contract between the model and everything else.
 * Mirrors docs/DESIGN.md §4. Every field is enum or typed; there is no field
 * where arbitrary text can travel. If you find yourself widening a type here to
 * `string`, that is the injection surface reopening. Don't.
 */

/**
 * docs/README_v3.md §Query shapes. Closed enum, one execution path each.
 *
 * The canonical declaration lives in `api/app/core/ir.py` as a Pydantic model.
 * `ir.generated.ts` is derived from it — see the re-export below. This array
 * stays because the UI iterates the shapes; it is checked against the generated
 * union at compile time, so the two cannot drift silently.
 *
 * `lookup` covers both a single field and a multi-tool fan-out narrated as one
 * answer. Those were separate shapes (`lookup` and `synthesis`) until it became
 * clear the only difference was breadth, not execution path.
 *
 * `unsupported` is not a shape the planner may return — the router emits it
 * when it cannot classify, and the request becomes a refusal rather than a guess.
 */
import type { QueryShape as GeneratedQueryShape } from './ir.generated'

export const QUERY_SHAPES = [
  'lookup',
  'diagnosis',
  'aggregate',
  'cohort',
  'policy',
  'action',
  // Answered from the curated glossary, touching no records at all — the only
  // shape with no scope, because there is no row to leak. ADR-036.
  'concept',
  'unsupported',
] as const satisfies readonly GeneratedQueryShape[]

export type QueryShape = GeneratedQueryShape

export type EntityType =
  | 'order'
  | 'customer'
  | 'vehicle'
  | 'payment'
  | 'refund'
  | 'rc_case'
  | 'refurb_job'
  | 'delivery'
  | 'ticket'
  | 'order_event'

export interface EntityRef {
  type: EntityType
  id: string | number
}

/** Filters are AST nodes, never SQL. docs/INVARIANTS.md J6. */
export type FilterOp = 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'contains'

export interface Filter {
  field: string
  op: FilterOp
  value: string | number | boolean | Array<string | number>
}

export interface TimeWindow {
  from: string
  to: string
}

/**
 * Actions the rules engine can suggest. The model SELECTS from this enum —
 * it never authors an action name or parameters. docs/INVARIANTS.md J1.
 */
export const ACTIONS = [
  'replay_webhook',
  'escalate_rto',
  'notify_customer_delay',
  'schedule_delivery',
  'call_customer',
  'freeze_and_review',
  'route_to_sellside',
  'cancel_later_order',
  'supervisor_exception',
  'reconcile',
  'assign_now',
  'reopen_for_audit',
  'escalate_supervisor',
  'request_identifier',
  'auto_followup',
  'refund',
] as const
export type ActionId = (typeof ACTIONS)[number]

export interface IR {
  shape: QueryShape
  entities: EntityRef[]
  filters: Filter[]
  time_window: TimeWindow | null
  /** Drawn from the rules engine's output, nullable. Never free text. */
  requested_action: ActionId | null
  ambiguities: string[]
  confidence: number
}

/** docs/README_v3.md §Rules. Versioned so past answers stay interpretable (I2). */
export const RULE_IDS = [
  'payment_capture_lag',
  'rc_transfer_stall',
  'refurb_overrun',
  'delivery_slot_missing',
  'delivery_attempts_exhausted',
  'refund_duplication',
  'seller_payout_hold',
  'inventory_double_allocation',
  'return_window_boundary',
  'state_ledger_mismatch',
  'ticket_first_response_breach',
  'ticket_resolved_without_cause',
  'ticket_reopen_loop',
  'ticket_orphaned',
  'ticket_stale_blocked',
] as const
export type RuleId = (typeof RULE_IDS)[number]

export interface FiredRule {
  rule_id: RuleId
  version: number
  /** The exact field values that fired it. docs/INVARIANTS.md A1. */
  triggering_fields: Record<string, string | number>
}

export const ORDER_STATES = [
  'CREATED',
  'TOKEN_PAID',
  'FULL_PAID',
  'REFURB_DONE',
  'RC_DONE',
  'DISPATCH_SCHEDULED',
  'OUT_FOR_DELIVERY',
  'DELIVERED',
  'RETURN_WINDOW_OPEN',
  'CLOSED',
  'RETURN_REQUESTED',
  'REFUNDED',
] as const
export type OrderState = (typeof ORDER_STATES)[number]

/** Diagnosis is a diff, not a narration. docs/README_v3.md §Diagnosis. */
export interface Violation {
  /**
   * Null for the five ticket-level rules. `ticket_orphaned` is a finding about
   * a ticket with no order attached, so requiring an order here would make the
   * one rule whose subject is a missing order unreportable.
   */
  order_id: number | null
  expected_state: OrderState
  observed_state: OrderState
  stuck_for: string
  primary_rule: RuleId
  blocking_entity: { type: EntityType; id: string; reason: string } | null
  suggested_action: ActionId
}
