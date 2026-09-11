/**
 * The console-level thread — questions about the whole book rather than one
 * ticket ("how many deliveries missed SLA last week", "show me all orders
 * stuck in RC transfer"). Same CopilotThread component as the ticket
 * workspace, but every call omits ticket_id: /ask, /conversations and
 * /conversations/new all resolve to the actor's console-level conversation,
 * not any particular ticket's.
 *
 * There is no per-ticket EvidencePane here — a console answer can cite
 * records across many tickets, so "show trace" and "select evidence" render
 * inline instead of opening a pane built for one ticket's records.
 */
import { useEffect, useState } from 'react'
import { Sidebar, type Dest } from '@/components/Sidebar'
import { CopilotThread, type Turn } from '@/components/CopilotThread'
import { SessionRail } from '@/components/SessionRail'
import { ApprovalModal } from '@/components/ApprovalModal'
import { Link } from '@/components/Icon'
import {
  ApiError,
  ask,
  deleteConversation,
  getConversation,
  listConversations,
  newConversation,
} from '@/api/client'
import type { AskResponse, ConversationResponse, ConversationSummary, EvidenceRecord, Session } from '@/types/api'

let turnSeq = 0
const nextId = () => `console_turn_${++turnSeq}`

export function ConsoleChat({
  session,
  onNavigate,
}: {
  session: Session | null
  onNavigate: (d: Dest) => void
}) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [pending, setPending] = useState(false)
  const [turnCount, setTurnCount] = useState<number | null>(null)
  const [maxTurns, setMaxTurns] = useState<number | null>(null)
  const [capNotice, setCapNotice] = useState<string | null>(null)
  const [approving, setApproving] = useState<AskResponse | null>(null)
  const [showTrace, setShowTrace] = useState(false)
  const [focusedEvidence, setFocusedEvidence] = useState<EvidenceRecord | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])

  function refreshConversationList() {
    listConversations()
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
    refreshConversationList()
    getConversation()
      .then(applyConversation)
      .catch(() => {
        // Endpoint not live yet, or no prior thread — start with an empty one.
        setTurns([])
        setTurnCount(null)
        setMaxTurns(null)
        setConversationId(null)
      })
  }, [])

  /** Mirrors TicketWorkspace.handleAsk, minus ticket_id. */
  async function handleAsk(query: string): Promise<boolean> {
    // The question goes into the thread before the request is made, so the
    // typing indicator appears under it rather than beside an empty pane.
    // Rolled back below if the ask never ran.
    const askId = nextId()
    setTurns((t) => [...t, { id: askId, role: 'agent', text: query }])
    setPending(true)
    setShowTrace(false)
    try {
      const answer = await ask({ query, conversation_id: conversationId ?? undefined })
      setTurns((t) => [...t, { id: nextId(), role: 'copilot', answer }])
      if (answer.turn_index != null) setTurnCount(answer.turn_index)
      setCapNotice(null)
      // A resumed closed thread reopens server-side on this ask — refresh so
      // the rail's `closed` marker and turn count reflect that.
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

  async function handleNewSession() {
    try {
      const { conversation_id } = await newConversation(null)
      setConversationId(conversation_id)
    } catch {
      /* endpoint may 404 while the backend lands; still start a fresh local thread */
      setConversationId(null)
    }
    setTurns([])
    setCapNotice(null)
    setTurnCount(0)
    setFocusedEvidence(null)
    setShowTrace(false)
    refreshConversationList()
  }

  /** Loads a past console thread from the rail and makes it active — every
   *  subsequent ask from this screen passes its conversation_id. */
  async function handleSelectConversation(id: string) {
    setCapNotice(null)
    setFocusedEvidence(null)
    setShowTrace(false)
    const c = await getConversation({ conversationId: id })
    applyConversation(c)
  }

  /** Permanent and cascades server-side. If the deleted thread was the active
   *  one, the pane must not keep showing turns from a conversation that no
   *  longer exists — reload the actor's current thread instead. */
  async function handleDeleteConversation(id: string) {
    await deleteConversation(id)
    if (id === conversationId) {
      setCapNotice(null)
      setFocusedEvidence(null)
      setShowTrace(false)
      try {
        applyConversation(await getConversation())
      } catch {
        setTurns([])
        setTurnCount(null)
        setMaxTurns(null)
        setConversationId(null)
      }
    }
    refreshConversationList()
  }

  const latest = turns.filter((t) => t.role === 'copilot').map((t) => t.answer as AskResponse).at(-1) ?? null

  return (
    <div className="h-full w-full bg-slate-50 flex overflow-hidden">
      <Sidebar active="copilot" session={session} onNavigate={onNavigate} />

      {/* Session rail — the single way to manage console-level threads: every
          thread the actor has ever had here, not just the hydrated one. */}
      <SessionRail
        conversations={conversations}
        activeId={conversationId}
        onSelect={handleSelectConversation}
        onNew={handleNewSession}
        onDelete={handleDeleteConversation}
      />

      <main className="flex-1 flex overflow-hidden relative">
        <CopilotThread
          turns={turns}
          pending={pending}
          latestTrace={latest?.trace ?? null}
          turnCount={turnCount}
          maxTurns={maxTurns}
          capNotice={capNotice}
          onNewSession={handleNewSession}
          onAsk={handleAsk}
          onSelectEvidence={setFocusedEvidence}
          onShowTrace={() => setShowTrace((s) => !s)}
          onPropose={setApproving}
          emptyState={
            <div className="max-w-md mx-auto text-center py-10 space-y-2">
              <p className="text-sm font-medium text-slate-700">This thread isn't attached to a ticket.</p>
              <p className="text-xs text-slate-500 leading-relaxed">
                Ask about the whole book here — SLA misses, stuck cohorts, patterns across cities. Questions about a
                specific case belong in that ticket's workspace, where the copilot can see its records.
              </p>
            </div>
          }
        />

        {/* Evidence a console answer cites spans tickets, so it's surfaced as a
            dismissable strip rather than a per-ticket records pane. */}
        {focusedEvidence && (
          <div className="absolute bottom-24 right-4 max-w-sm bg-white border border-slate-200 rounded-lg shadow-lg p-3 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Evidence</span>
              <button
                onClick={() => setFocusedEvidence(null)}
                className="text-[11px] text-slate-400 hover:text-slate-700"
              >
                Close
              </button>
            </div>
            <div className="flex items-center gap-1.5 text-xs font-mono text-slate-700">
              <Link className="w-3 h-3 text-slate-400" />
              {focusedEvidence.table} #{focusedEvidence.record_id}
            </div>
            {focusedEvidence.fields.map((f) => (
              <div key={f.label} className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400">{f.label}</span>
                <span className={`font-mono ${f.triggered ? 'text-amber-700 font-semibold' : 'text-slate-600'}`}>
                  {f.value}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Trace toggled inline — there is no separate evidence-pane tab here. */}
        {showTrace && latest && (
          <div className="absolute top-14 right-4 max-w-sm bg-white border border-slate-200 rounded-lg shadow-lg p-3 space-y-1 font-mono text-[11px] text-slate-600">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Trace</span>
              <button onClick={() => setShowTrace(false)} className="text-slate-400 hover:text-slate-700">
                Close
              </button>
            </div>
            <div>model {latest.trace.model}</div>
            <div>latency {latest.trace.latency_ms}ms</div>
            <div>
              tokens {latest.trace.tokens.prompt} in / {latest.trace.tokens.completion} out
            </div>
            <div>prompt {latest.trace.prompt_version}</div>
            {latest.trace.stages.map((s) => (
              <div key={s.name}>
                {s.name}: {s.ms}ms
              </div>
            ))}
          </div>
        )}
      </main>

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
