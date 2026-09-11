/**
 * The API surface, one function per endpoint in docs/README_v3.md §API.
 *
 * Every value the console renders comes from here, and everything here comes
 * from Postgres. There are no fixtures: the mock adapter and its dataset were
 * deleted once the API landed, so there is no path by which a stale invented
 * record can reach the screen.
 *
 * The one thing this module sends is `X-Actor-Id` — *who* is asking. It never
 * sends a city, a region or a role, because scope is resolved server-side from
 * the actor row and enforced by RLS. A client cannot widen what it can see.
 * docs/INVARIANTS.md E3 / D4.
 */
import type {
  AskRequest,
  AskResponse,
  AuditEntry,
  Cohort,
  ConsoleTable,
  ConversationResponse,
  ConversationSummary,
  NewConversationResponse,
  QueryResult,
  RecordsGraph,
  Session,
  TicketCohort,
  TicketDetail,
  TicketQueue,
} from '@/types/api'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

/**
 * Demo affordance only. In the real system the actor comes from an
 * authenticated session and this header does not exist. It is here so the
 * supervisor-gated paths can be shown without a second login (docs/SCOPE.md §3
 * stubs auth to a header-supplied actor). Note what it does NOT do: naming a
 * different actor cannot grant a scope that actor does not have, because the
 * server looks the scope up rather than believing the request.
 */
let actorId: string | null = null
export function setActor(id: string | null) {
  actorId = id
}
export function getActor() {
  return actorId
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(actorId ? { 'X-Actor-Id': actorId } : {}),
      ...init?.headers,
    },
  })
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json()
      // Most endpoints send `error`; /ask's 429 sends `detail` (contract in
      // docs/README_v3.md §API). Accept either rather than falling back to
      // the generic status text and losing the turn-cap message.
      message = body.error ?? body.detail ?? message
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Reads
// ---------------------------------------------------------------------------

/** Derived server-side from the authenticated actor. Never built client-side. */
export const getSession = () => req<Session>('/session')

/** RLS-scoped in the database. The client cannot widen the scope. */
export const getQueue = () => req<TicketQueue>('/tickets')

export const getTicket = (id: string) => req<TicketDetail>(`/tickets/${id}`)

/** The fallback view. No model is involved in producing it. F4. */
export const getRecords = (ticketId: string) => req<RecordsGraph>(`/tickets/${ticketId}/records`)

/** Each cohort is a rule evaluated across the scope, not a saved filter. */
export const getCohorts = () => req<Cohort[]>('/cohorts')

/** The five ticket rules. Members are tickets, not orders. */
export const getTicketCohorts = () => req<TicketCohort[]>('/cohorts/tickets')

export const getAuditLog = () => req<AuditEntry[]>('/audit')

export const getConsoleSchema = () => req<ConsoleTable[]>('/query/schema')

export const getSavedQueries = () => req<Array<{ name: string; sql: string }>>('/query/saved')

// ---------------------------------------------------------------------------
// Ask
// ---------------------------------------------------------------------------

/** The only natural-language surface. Everything else is typed. */
export const ask = (body: AskRequest) =>
  req<AskResponse>('/ask', { method: 'POST', body: JSON.stringify(body) })

/**
 * Omit both to get the actor's current open thread for the console-level
 * conversation. Pass `conversationId` to fetch a specific thread — including
 * a closed one, for reopening it from the history list — which takes
 * precedence over `ticketId` when both are given.
 */
export const getConversation = (opts?: { ticketId?: string; conversationId?: string }) => {
  const params = new URLSearchParams()
  if (opts?.conversationId) params.set('conversation_id', opts.conversationId)
  else if (opts?.ticketId) params.set('ticket_id', opts.ticketId)
  const qs = params.toString()
  return req<ConversationResponse>(`/conversations${qs ? `?${qs}` : ''}`)
}

/** Closes the current thread server-side and opens a fresh one. */
export const newConversation = (ticketId?: string | null) =>
  req<NewConversationResponse>('/conversations/new', {
    method: 'POST',
    body: JSON.stringify({ ticket_id: ticketId ?? null }),
  })

/** Every thread the actor has for this scope, newest first. Omit `ticketId`
 *  for the console-level threads. Used to render the history rail/dropdown —
 *  the backend keeps every thread; this is how the UI reaches past ones. */
export const listConversations = (ticketId?: string) =>
  req<ConversationSummary[]>(
    `/conversations/list${ticketId ? `?ticket_id=${encodeURIComponent(ticketId)}` : ''}`,
  )

/** Permanent, cascades the turns. 404s if the conversation isn't the actor's —
 *  same "not yours" shape as every other scoped read. */
export const deleteConversation = (conversationId: string) =>
  req<{ deleted: string }>(`/conversations/${conversationId}`, { method: 'DELETE' })

// ---------------------------------------------------------------------------
// Writes — proposed, approved, idempotent. All three, always.
// ---------------------------------------------------------------------------

export const assignTicket = (ticketId: string) =>
  req<{ assignee: string }>(`/tickets/${ticketId}/assign`, { method: 'POST' })

/** Both fields are required server-side; a close with no cause is a defect. */
export const resolveTicket = (ticketId: string, body: { resolution_code: string; answer_id: string }) =>
  req<{ state: 'RESOLVED' }>(`/tickets/${ticketId}/resolve`, {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const reopenTicket = (ticketId: string) =>
  req<{ state: 'REOPENED' }>(`/tickets/${ticketId}/reopen`, { method: 'POST' })

/**
 * The idempotency key is minted server-side at proposal time. The client echoes
 * it back and never invents one; replaying the same key executes once. D2.
 */
export const approveAction = (proposalId: string, idempotencyKey: string) =>
  req<{ executed: boolean; result: string }>(`/actions/${proposalId}/approve`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  })

/** Supervisor only, SELECT-only role, 5s timeout, 500-row cap, logged. E7. */
export const runQuery = (sql: string) =>
  req<QueryResult>('/query', { method: 'POST', body: JSON.stringify({ sql }) })
