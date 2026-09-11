/**
 * Wire types for the endpoints in docs/README_v3.md §API.
 * `/ask` is the only natural-language surface. Everything else is typed.
 * Session context is derived server-side and never sent from the client —
 * so no actor field appears in any request body here. That absence is deliberate.
 */
import type { ActionId, FiredRule, IR, OrderState, RuleId, Violation } from './ir'

/** One record the copilot cited. The evidence pane renders these verbatim. */
export interface EvidenceRecord {
  table: string
  record_id: string
  fields: Array<{
    label: string
    value: string | number
    /** True for the field that triggered the rule — rendered amber. */
    triggered?: boolean
  }>
  rule_id?: string
  /** Record's own status, derived from its columns — not from the model. */
  status?: { label: string; tone: 'ok' | 'warn' | 'bad' | 'neutral' }
}

export interface ProposedAction {
  proposal_id: string
  action: ActionId
  label: string
  params: Record<string, string | number>
  /** Always true before execution. docs/INVARIANTS.md D1. */
  requires_confirmation: boolean
  /** docs/INVARIANTS.md D2 — deterministic key, surfaced in the approval modal. */
  idempotency_key: string
  motivating_rule: string
  /** Set when the action exceeds the caller's limit. docs/INVARIANTS.md D3. */
  approval_gate?: {
    reason: string
    limit_inr: number
    routes_to: { name: string; role: string }
  }
  /** docs/INVARIANTS.md D6 — bulk actions disclose scope before execution. */
  bulk?: { count: number; sample: string[] }
}

/**
 * Refusal is a supported outcome, not an error path. docs/INVARIANTS.md B2.
 * It carries pointers rather than an answer.
 */
export interface Refusal {
  reason: string
  evidence_pointers: EvidenceRecord[]
}

/** An unavailable source is named, never silently treated as empty. B5 / F3. */
export interface DegradedInfo {
  unavailable: string[]
  note: string
}

export interface TraceSummary {
  model: string
  latency_ms: number
  tokens: { prompt: number; completion: number }
  stages: Array<{ name: string; ms: number }>
  prompt_version: string
}

export interface AskRequest {
  query: string
  ticket_id?: string
  /** Continues a specific thread. Omit to use the actor's current open thread. */
  conversation_id?: string
}

export interface AskResponse {
  answer_id: string
  ir: IR
  /** One-line verdict, then the explanation. Phrasing only — no cause picked here. */
  verdict: string
  explanation: string
  violation: Violation | null
  fired_rules: FiredRule[]
  evidence: EvidenceRecord[]
  confidence: number
  proposal: ProposedAction | null
  refusal: Refusal | null
  degraded: DegradedInfo | null
  /** Flagged, counted, surfaced — never silently stripped. J10. */
  injection_flagged: boolean
  trace: TraceSummary
  /** Position of this answer's turn in the conversation. Absent on older payloads. */
  turn_index?: number
  /** Exact field-level line the verdict traces back to. Rendered verbatim, never prettified. */
  provenance?: string | null
  /** A reply drafted for the operator to review. There is no send path — it is never executed. */
  draft?: { text: string; style: string; source: 'model' | 'template'; sent: false } | null
  /** Tier-2 auto-reply routing verdict, separate from the diagnosis itself. */
  tier2?: {
    auto_reply: boolean
    reasons: string[]
    routed_to: string | null
    force_assigned_human: boolean
    queued_for_review: boolean
  } | null
}

// ---------------------------------------------------------------------------
// Conversations — persisted turn history. A page refresh must show what the
// server remembers, not an empty thread that silently drops earlier turns.
// ---------------------------------------------------------------------------

export interface ConversationTurnRecord {
  turn_index: number
  operator_text: string
  answer: AskResponse | null
}

export interface ConversationResponse {
  conversation_id: string
  ticket_id: string | null
  turn_count: number
  max_turns: number
  turns: ConversationTurnRecord[]
}

export interface NewConversationResponse {
  conversation_id: string
}

/** One row of `/conversations/list` — enough to render a history rail without
 *  fetching every thread's full turn payload. Newest first. */
export interface ConversationSummary {
  id: string
  /** First thing the operator typed, <=60 chars. */
  title: string
  turn_count: number
  started_at: string
  last_at: string
  closed: boolean
}

// ---------------------------------------------------------------------------
// Tickets
// ---------------------------------------------------------------------------

export type TicketState =
  | 'OPEN'
  | 'ASSIGNED'
  | 'IN_PROGRESS'
  | 'AWAITING_CUSTOMER'
  | 'AWAITING_INTERNAL'
  | 'RESOLVED'
  | 'CLOSED'
  | 'REOPENED'

export interface TicketSummary {
  id: string
  subject: string
  customer_name: string
  city_code: string
  order_id: number | null
  state: TicketState
  priority: 'low' | 'normal' | 'high' | 'urgent'
  age: string
  assignee: string | null
  flags: {
    sla_breach: boolean
    reopen_count: number
    auto_replied: boolean
    /** Shield icon in the queue. J10. */
    flagged_content: boolean
  }
}

export interface QueueStats {
  unassigned: { count: number; high_priority: number }
  sla_breach: { count: number }
  awaiting_customer: { count: number; avg_wait_hours: number }
  auto_resolved_today: { count: number; mean_confidence: number }
}

export interface TicketQueue {
  total_open: number
  /**
   * The scope the rows were fetched under. Rendered in the UI so the RLS
   * boundary is visible rather than implied — an agent should be able to see
   * that they are looking at one city, not the whole book. docs/DOMAIN_v2.md §6.
   */
  scope: { city_code: string; label: string; role: Session['role'] }
  stats: QueueStats
  tickets: TicketSummary[]
  page: { index: number; size: number; total: number }
}

export interface CustomerMessage {
  id: string
  channel: 'whatsapp' | 'email' | 'call'
  at: string
  /** UNTRUSTED. Render escaped, never interpolate into a prompt client-side. J12. */
  body: string
  flagged: boolean
}

export interface TicketDetail extends TicketSummary {
  customer: {
    id: string
    name: string
    phone: string
    city: string
    prior_tickets: number
    since: string
  }
  order: {
    id: number
    vehicle: string
    reg_no: string
    amount_inr: number
    state: string
  } | null
  messages: CustomerMessage[]
  /** The append-only ledger for the linked order. Source of truth for state. */
  order_events: OrderEvent[]
  sla: { label: string; status: 'ok' | 'at_risk' | 'breached' }
  resolution: {
    resolution_code: string
    resolved_by: 'agent' | 'copilot_auto'
    rule_id: string | null
  } | null
}

/** The fallback view. Must be good enough to work a ticket by hand. F4. */
export interface RecordsGraph {
  ticket_id: string
  nodes: Array<{
    entity: string
    label: string
    count: number
    rule_fired: boolean
    records: Array<{ id: string; fields: Array<{ label: string; value: string | number; triggered?: boolean; rule_id?: string }> }>
  }>
  timeline: Array<{ state: string; at: string | null; status: 'done' | 'current' | 'blocked' | 'pending' }>
  timeline_caption: string
}

// ---------------------------------------------------------------------------
// Cohorts — the `cohort` query shape: SQL + per-item rules.
// docs/README_v3.md §Query shapes
// ---------------------------------------------------------------------------

export interface CohortMember {
  order_id: number
  state: OrderState
  stuck_for: string
  blocking_reason: string | null
  ticket_id: string | null
  city_code: string
}

export interface TicketCohortMember {
  ticket_id: string
  subject: string
  state: TicketState
  waiting_for: string
  order_id: number | null
  city_code: string
}

/**
 * The five ticket rules. Separate from `Cohort` because a member here is a
 * ticket rather than an order — `ticket_orphaned` has no order by definition.
 */
export interface TicketCohort {
  id: string
  label: string
  rule_id: RuleId
  description: string
  members: TicketCohortMember[]
}

export interface Cohort {
  id: string
  label: string
  /** Every cohort is defined by a rule, not by a hand-written filter. */
  rule_id: RuleId
  description: string
  members: CohortMember[]
}

// ---------------------------------------------------------------------------
// Audit log — the `action_audit` table. Append-only; no update or delete path
// exists, which is why nothing here is editable. docs/INVARIANTS.md A4.
// ---------------------------------------------------------------------------

export interface AuditEntry {
  id: string
  answer_id: string
  action: ActionId
  proposal: string
  proposed_by: string
  approved_by: string | null
  rule_id: RuleId
  idempotency_key: string
  executed_at: string | null
  result: 'executed' | 'pending_approval' | 'rejected' | 'replayed_noop'
  order_id: number | null
}

/** One row of `order_event`. The ledger, not the materialised state column. */
export interface OrderEvent {
  id: number
  from_state: OrderState | null
  to_state: OrderState
  actor: string
  reason: string | null
  at: string
}

// ---------------------------------------------------------------------------
// Query console (supervisor only — docs/INVARIANTS.md E7)
// ---------------------------------------------------------------------------

export interface ConsoleTable {
  name: string
  columns: Array<{ name: string; type: string; pk?: boolean }>
}

export interface QueryResult {
  columns: string[]
  rows: Array<Record<string, string | number>>
  /** Rows returned *within the caller's scope*. There is no global count: the
   *  connection cannot see outside its city, so reporting one would leak the
   *  size of the out-of-scope set. */
  row_count: number
  ms: number
  /** True when the 500-row cap clipped the result. docs/DOMAIN_v2.md §6. */
  truncated: boolean
  audit_id: string
}

export interface Session {
  user_id: string
  name: string
  role: 'l1_agent' | 'supervisor'
  city_code: string
  region: string
  permitted_actions: ActionId[]
  refund_limit_inr: number
}
