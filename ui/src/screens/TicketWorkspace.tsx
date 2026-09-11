import { useEffect, useState } from 'react'
import { TopBar } from '@/components/TopBar'
import { TicketContextPane } from '@/components/TicketContextPane'
import { CopilotThread, type Turn } from '@/components/CopilotThread'
import { SessionRail } from '@/components/SessionRail'
import { EvidencePane, type PaneTab } from '@/components/EvidencePane'
import { RecordsModal } from '@/components/RecordsModal'
import { ApprovalModal } from '@/components/ApprovalModal'
import {
  ApiError,
  ask,
  deleteConversation,
  getConversation,
  getRecords,
  getSession,
  getTicket,
  listConversations,
  newConversation,
  resolveTicket,
} from '@/api/client'
import type {
  AskResponse,
  ConversationResponse,
  ConversationSummary,
  EvidenceRecord,
  RecordsGraph,
  Session,
  TicketDetail,
} from '@/types/api'

let turnSeq = 0
const nextId = () => `turn_${++turnSeq}`

// Persisted globally, not per ticket — collapsing the rail on one ticket
// should not make it pop back open on the next. Default collapsed: the three
// ticket panes are the primary content here, unlike the console screen.
const RAIL_COLLAPSED_KEY = 'copilot.ticketWorkspace.sessionRailCollapsed'

export function TicketWorkspace({
  ticketId = 'TKT-4821',
  onBack,
  onSearchCustomer,
}: {
  ticketId?: string
  onBack?: () => void
  onSearchCustomer?: (name: string) => void
}) {
  const [session, setSession] = useState<Session | null>(null)
  const [ticket, setTicket] = useState<TicketDetail | null>(null)
  const [records, setRecords] = useState<RecordsGraph | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [pending, setPending] = useState(false)
  const [showRecords, setShowRecords] = useState(false)
  const [approving, setApproving] = useState<AskResponse | null>(null)
  const [tab, setTab] = useState<PaneTab>('evidence')
  const [focused, setFocused] = useState<string | null>(null)
  const [resolveErr, setResolveErr] = useState<string | null>(null)
  const [turnCount, setTurnCount] = useState<number | null>(null)
  const [maxTurns, setMaxTurns] = useState<number | null>(null)
  const [capNotice, setCapNotice] = useState<string | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [railCollapsed, setRailCollapsed] = useState(() => {
    try {
      const stored = localStorage.getItem(RAIL_COLLAPSED_KEY)
      return stored === null ? true : stored === 'true'
    } catch {
      return true
    }
  })

  function toggleRailCollapsed() {
    setRailCollapsed((collapsed) => {
      const next = !collapsed
      try {
        localStorage.setItem(RAIL_COLLAPSED_KEY, String(next))
      } catch {
        /* private-browsing or storage disabled — collapse state just won't persist */
      }
      return next
    })
  }

  function refreshConversationList() {
    listConversations(ticketId)
      .then(setConversations)
      .catch(() => setConversations([]))
  }

  /** Hydrates local thread state from a server conversation payload — shared
   *  by the initial load, selecting a past thread from the rail, and
   *  recovering after the active thread is deleted. */
  function applyConversation(c: ConversationResponse) {
    const hydrated: Turn[] = c.turns.flatMap((t) => {
      const out: Turn[] = [{ id: nextId(), role: 'agent', text: t.operator_text }]
      if (t.answer) out.push({ id: nextId(), role: 'copilot', answer: t.answer })
      return out
    })
    setTurns(hydrated)
    setTurnCount(c.turn_count)
    setMaxTurns(c.max_turns)
    setConversationId(c.conversation_id)
  }

  useEffect(() => {
    getSession().then(setSession)
    getTicket(ticketId).then(setTicket)
    getRecords(ticketId).then(setRecords)
    refreshConversationList()

    // Hydrate from what the server remembers — a refresh must not present the
    // operator's next question as turn 1 when it is actually turn 6.
    setCapNotice(null)
    getConversation({ ticketId })
      .then(applyConversation)
      .catch(() => {
        // Endpoint not live yet, or no prior thread — start with an empty one.
        setTurns([])
        setTurnCount(null)
        setMaxTurns(null)
        setConversationId(null)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId])

  const answers = turns.filter((t) => t.role === 'copilot').map((t) => t.answer!)
  const latest = answers.at(-1) ?? null

  /**
   * Every turn re-runs against live state — turn 3 does not reuse turn 1's
   * violations. Serving a stale diagnosis is the failure this design exists to
   * prevent. docs/DESIGN.md §5 "Recompute, never inherit".
   *
   * Returns whether the turn was accepted. The agent bubble is only appended
   * on success — a 429 must not make it look like a question was asked and
   * silently dropped; the text stays in the input instead (CopilotThread).
   */
  async function handleAsk(query: string): Promise<boolean> {
    // The question goes into the thread before the request is made, so the
    // typing indicator appears under it rather than beside an empty pane.
    // Rolled back below if the ask never ran.
    const askId = nextId()
    setTurns((t) => [...t, { id: askId, role: 'agent', text: query }])
    setPending(true)
    setTab('evidence')
    try {
      const answer = await ask({ query, ticket_id: ticketId, conversation_id: conversationId ?? undefined })
      setTurns((t) => [...t, { id: nextId(), role: 'copilot', answer }])
      if (answer.turn_index != null) setTurnCount(answer.turn_index)
      setCapNotice(null)
      // A resumed closed thread reopens server-side on this ask — refresh so
      // the popover's `closed` marker and turn count reflect that.
      refreshConversationList()
      return true
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        // Nothing ran, so the optimistic question is withdrawn.
        setTurns((t) => t.filter((x) => x.id !== askId))
        setCapNotice(e.message || 'This conversation has reached its turn limit.')
        return false
      }
      setTurns((t) => t.filter((x) => x.id !== askId))
      throw e
    } finally {
      setPending(false)
    }
  }

  /** Closes the current thread server-side (if the endpoint is live) and
   * always resets the local view — a fresh session must not be blocked by a
   * backend that hasn't landed yet. */
  async function handleNewSession() {
    try {
      const { conversation_id } = await newConversation(ticketId)
      setConversationId(conversation_id)
    } catch {
      /* endpoint may 404 while the backend lands; still start a fresh local thread */
      setConversationId(null)
    }
    setTurns([])
    setCapNotice(null)
    setTurnCount(0)
    refreshConversationList()
  }

  /** Loads a past thread from the history popover and makes it the active one
   *  — every subsequent ask from this screen passes its conversation_id. */
  async function handleSelectConversation(id: string) {
    setCapNotice(null)
    const c = await getConversation({ conversationId: id })
    applyConversation(c)
  }

  /** Permanent and cascades server-side. If the deleted thread was the active
   *  one, the pane must not keep showing turns from a conversation that no
   *  longer exists — reload this ticket's current thread instead. */
  async function handleDeleteConversation(id: string) {
    await deleteConversation(id)
    if (id === conversationId) {
      setCapNotice(null)
      try {
        applyConversation(await getConversation({ ticketId }))
      } catch {
        setTurns([])
        setTurnCount(null)
        setMaxTurns(null)
        setConversationId(null)
      }
    }
    refreshConversationList()
  }

  /**
   * Resolution requires a code AND evidence. An agent resolution inherits the
   * copilot's rule_id and evidence automatically, so every close is auditable —
   * and closing with neither is itself a detectable defect
   * (ticket_resolved_without_cause). So the button refuses without an answer.
   */
  async function handleResolve() {
    if (!latest) {
      setResolveErr('Ask the copilot first — a resolution needs a rule_id and evidence attached.')
      setTimeout(() => setResolveErr(null), 4000)
      return
    }
    const rule = latest.fired_rules[0]?.rule_id ?? 'no_rule'
    await resolveTicket(ticketId, { resolution_code: rule, answer_id: latest.answer_id })
    setTicket((t) =>
      t
        ? {
            ...t,
            state: 'RESOLVED',
            resolution: { resolution_code: rule, resolved_by: 'agent', rule_id: rule },
          }
        : t,
    )
  }

  function handleSelectEvidence(r: EvidenceRecord) {
    setTab('evidence')
    setFocused(`${r.table}-${r.record_id}`)
  }

  if (!ticket) {
    return <div className="h-full flex items-center justify-center text-slate-400 text-xs">Loading ticket…</div>
  }

  return (
    <div className="h-full w-full bg-slate-100 text-slate-800 flex flex-col overflow-hidden antialiased">
      <TopBar
        ticket={ticket}
        session={session}
        onResolve={handleResolve}
        onBack={onBack}
        resolveError={resolveErr}
      />

      {/* Left to right: what the customer said and who they are, then which
          conversation you are in, then the conversation, then the evidence
          behind its answers. The rail sits beside the thread it controls
          rather than at the screen edge, so the ticket context stays first —
          that is what an agent reads before typing anything. */}
      <main className="flex-1 flex overflow-hidden">
        <TicketContextPane ticket={ticket} onSearchCustomer={onSearchCustomer} />
        {/* Collapsed by default — the ticket panes are the primary content
            here, unlike the console screen where the rail gets full width. */}
        <SessionRail
          conversations={conversations}
          activeId={conversationId}
          onSelect={handleSelectConversation}
          onNew={handleNewSession}
          onDelete={handleDeleteConversation}
          collapsed={railCollapsed}
          onToggleCollapsed={toggleRailCollapsed}
        />
        <CopilotThread
          turns={turns}
          pending={pending}
          latestTrace={latest?.trace ?? null}
          turnCount={turnCount}
          maxTurns={maxTurns}
          capNotice={capNotice}
          onNewSession={handleNewSession}
          onAsk={handleAsk}
          onSelectEvidence={handleSelectEvidence}
          onShowTrace={() => setTab('trace')}
          // Opens the approval modal. It does NOT execute — no code path runs
          // from /ask to a mutation. docs/INVARIANTS.md J2.
          onPropose={setApproving}
        />
        <EvidencePane
          answer={latest}
          records={records}
          tab={tab}
          onTabChange={setTab}
          focusedRecord={focused}
          onExpandRecords={() => setShowRecords(true)}
        />
      </main>

      {showRecords && records && (
        <RecordsModal records={records} ticketId={ticketId} onClose={() => setShowRecords(false)} />
      )}

      {approving?.proposal && (
        <ApprovalModal
          proposal={approving.proposal}
          session={session}
          evidence={approving.evidence}
          onClose={() => setApproving(null)}
        />
      )}
    </div>
  )
}
