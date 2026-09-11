import { useEffect, useRef, useState, type ReactNode } from 'react'
import { AnswerCard } from './AnswerCard'
import { ArrowRight, Bolt } from './Icon'
import type { AskResponse, EvidenceRecord } from '@/types/api'

/**
 * Conversation state is keyed to the ticket, not the user or a global session —
 * it dies when the ticket closes. docs/DESIGN.md §5.
 */
export interface Turn {
  id: string
  role: 'agent' | 'copilot'
  text?: string
  answer?: AskResponse
}

const SUGGESTIONS = [
  { emoji: '✨', label: 'Full status summary' },
  { emoji: '🔍', label: 'Why is this stuck?' },
  { emoji: '✉️', label: 'Draft customer reply' },
]

export function CopilotThread({
  turns,
  pending,
  latestTrace,
  turnCount = null,
  maxTurns = null,
  capNotice = null,
  onAsk,
  onSelectEvidence,
  onShowTrace,
  onPropose,
  onNewSession,
  emptyState,
}: {
  turns: Turn[]
  pending: boolean
  latestTrace: AskResponse['trace'] | null
  /** Current turn count and server-enforced cap, when known. Chip is omitted if either is absent. */
  turnCount?: number | null
  maxTurns?: number | null
  /** Set when the last `ask` was rejected with 429 — the cap is reached. Non-dismissable. */
  capNotice?: string | null
  onAsk: (query: string) => Promise<boolean>
  onSelectEvidence: (r: EvidenceRecord) => void
  onShowTrace: () => void
  onPropose: (a: AskResponse) => void
  /** Closes the current thread server-side and starts a fresh one. */
  onNewSession: () => void
  /** Overrides the default suggestion-chip empty state, e.g. for the console thread. */
  emptyState?: ReactNode
}) {
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns.length, pending])

  // Only cleared on success — a 429 (or any other failure) leaves the
  // operator's text in the box rather than swallowing it.
  async function submit() {
    const q = draft.trim()
    if (!q || pending || capNotice) return
    // Cleared immediately, not after the answer arrives. A live model call runs
    // for tens of seconds, and leaving the question sitting in the box while a
    // typing indicator pulses above it reads as "nothing happened" — the
    // question belongs in the thread the moment it is asked.
    //
    // Restored only if the ask was rejected before it ran (the turn cap), so
    // the operator still has their text to paste into a new session.
    setDraft('')
    const ok = await onAsk(q)
    if (!ok) setDraft(q)
  }

  return (
    <section className="flex-1 min-w-[480px] bg-slate-50/50 flex flex-col h-full border-r border-slate-200 overflow-hidden">
      <div className="h-12 bg-white/90 backdrop-blur-xs border-b border-slate-200 px-5 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-2.5">
          <div className="w-6 h-6 rounded-md bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center text-white shadow-2xs">
            <Bolt className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-bold text-slate-900 tracking-tight">Copilot</span>
          {latestTrace && (
            <>
              {/* Model and latency come from the trace, not from a hardcoded chip. */}
              <span className="font-mono text-[10px] font-semibold bg-violet-50 text-violet-700 border border-violet-200 px-2 py-0.5 rounded-full">
                {latestTrace.model.replace('claude-', '').replace(/-\d+$/, '')}
              </span>
              <span className="tnum font-mono text-[10px] text-slate-500 bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded">
                {(latestTrace.latency_ms / 1000).toFixed(1)}s
              </span>
            </>
          )}
        </div>

        <div className="flex items-center space-x-2 shrink-0">
          {turnCount != null && maxTurns != null && (
            <span
              className={`tnum font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${
                turnCount >= maxTurns
                  ? 'bg-rose-50 text-rose-700 border-rose-200'
                  : turnCount >= 15
                    ? 'bg-amber-50 text-amber-700 border-amber-200'
                    : 'bg-slate-100 text-slate-500 border-slate-200'
              }`}
              title="Turns used in this conversation"
            >
              {turnCount} / {maxTurns}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {turns.length === 0 && !pending && emptyState}

        {turns.map((t) =>
          t.role === 'agent' ? (
            <div key={t.id} className="flex justify-end">
              <div className="max-w-md bg-indigo-600 text-white text-xs leading-relaxed px-4 py-2.5 rounded-2xl rounded-tr-xs shadow-xs">
                {t.text}
              </div>
            </div>
          ) : (
            <AnswerCard
              key={t.id}
              answer={t.answer!}
              onSelectEvidence={onSelectEvidence}
              onShowTrace={onShowTrace}
              onDraftReply={() => onAsk('Draft a reply to the customer explaining this.')}
              onPropose={onPropose}
            />
          ),
        )}

        {pending && (
          <div className="flex justify-start">
            <div className="bg-white rounded-xl border border-slate-200 px-4 py-3 flex items-center space-x-2 shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse" />
              <span className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse [animation-delay:300ms]" />
            </div>
          </div>
        )}

        {/* Non-dismissable — the cap is a server fact, not a toast the operator can wave away. */}
        {capNotice && (
          <div className="flex justify-start">
            <div className="max-w-xl w-full bg-rose-50 border border-rose-300 rounded-xl p-3.5 flex items-center justify-between gap-3 flex-wrap">
              <p className="text-xs text-rose-800">{capNotice}</p>
              <button
                onClick={onNewSession}
                className="shrink-0 px-3 py-1.5 text-xs font-medium text-white bg-rose-600 hover:bg-rose-700 rounded-lg transition-colors"
              >
                Start new session
              </button>
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="p-4 bg-white border-t border-slate-200 shrink-0 space-y-2.5">
        <div className="flex items-center space-x-2 overflow-x-auto pb-0.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s.label}
              onClick={() => onAsk(s.label)}
              disabled={pending || !!capNotice}
              className="shrink-0 text-xs px-2.5 py-1 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 transition-colors disabled:opacity-50"
            >
              {s.emoji} {s.label}
            </button>
          ))}
        </div>

        <div className="relative flex items-center">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="Ask about this ticket…"
            disabled={!!capNotice}
            className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-3.5 pr-12 py-2.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-hidden focus:border-indigo-500 focus:bg-white focus:ring-1 focus:ring-indigo-500 transition-all shadow-2xs disabled:opacity-60"
          />
          <button
            onClick={submit}
            disabled={pending || !!capNotice}
            className="absolute right-2 p-1.5 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 disabled:bg-slate-300 text-white rounded-lg transition-colors shadow-xs"
            title="Send query"
          >
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </section>
  )
}
