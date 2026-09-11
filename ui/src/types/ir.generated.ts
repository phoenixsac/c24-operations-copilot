/**
 * GENERATED — do not edit.
 * Source: api/app/core/ir.py.  Regenerate: python api/scripts_gen_types.py
 *
 * The IR is declared once, in Pydantic. These types are derived from it, so
 * the console and the API cannot disagree about the contract.
 */

export type QueryShape =
  | 'lookup'
  | 'diagnosis'
  | 'aggregate'
  | 'cohort'
  | 'policy'
  | 'action'
  | 'concept'
  | 'unsupported'

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

export type FilterOp =
  | 'eq'
  | 'neq'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'in'
  | 'contains'

export type OrderState =
  | 'CREATED'
  | 'TOKEN_PAID'
  | 'FULL_PAID'
  | 'REFURB_DONE'
  | 'RC_DONE'
  | 'DISPATCH_SCHEDULED'
  | 'OUT_FOR_DELIVERY'
  | 'DELIVERED'
  | 'RETURN_WINDOW_OPEN'
  | 'CLOSED'
  | 'RETURN_REQUESTED'
  | 'REFUNDED'
  | 'SELLER_PAYOUT_PENDING'
  | 'SELLER_PAYOUT_DONE'

export type ActionId =
  | 'replay_webhook'
  | 'escalate_rto'
  | 'notify_customer_delay'
  | 'schedule_delivery'
  | 'call_customer'
  | 'freeze_and_review'
  | 'route_to_sellside'
  | 'cancel_later_order'
  | 'supervisor_exception'
  | 'reconcile'
  | 'assign_now'
  | 'reopen_for_audit'
  | 'escalate_supervisor'
  | 'request_identifier'
  | 'auto_followup'
  | 'refund'

export type RuleId =
  | 'payment_capture_lag'
  | 'rc_transfer_stall'
  | 'refurb_overrun'
  | 'delivery_slot_missing'
  | 'delivery_attempts_exhausted'
  | 'refund_duplication'
  | 'seller_payout_hold'
  | 'inventory_double_allocation'
  | 'return_window_boundary'
  | 'state_ledger_mismatch'
  | 'ticket_first_response_breach'
  | 'ticket_resolved_without_cause'
  | 'ticket_reopen_loop'
  | 'ticket_orphaned'
  | 'ticket_stale_blocked'

