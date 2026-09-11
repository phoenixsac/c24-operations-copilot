/**
 * Audit log — the `action_audit` table.
 *
 * Append-only: there is no UPDATE or DELETE grant on this table
 * (docs/INVARIANTS.md A4), which is exactly why nothing on this screen is
 * editable. Every row records who proposed, who approved, which rule motivated
 * it, and the result (A6).
 *
 * The `replayed_noop` result is the visible form of D2: the same idempotency
 * key submitted twice executes once and records the second call as a no-op.
 */
import { Fragment, useEffect, useState } from 'react'
import { Sidebar, type Dest } from '@/components/Sidebar'
import { Lock } from '@/components/Icon'
import { getAuditLog } from '@/api/client'
import type { AuditEntry, Session } from '@/types/api'

const RESULT: Record<AuditEntry['result'], { label: string; cls: string }> = {
  executed: { label: 'executed', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  pending_approval: { label: 'pending approval', cls: 'bg-amber-50 text-amber-800 border-amber-200' },
  rejected: { label: 'rejected', cls: 'bg-slate-100 text-slate-600 border-slate-200' },
  replayed_noop: { label: 'replayed · no-op', cls: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
}

export function AuditLogScreen({
  session,
  onNavigate,
  onOpenAnswer,
}: {
  session: Session | null
  onNavigate: (d: Dest) => void
  onOpenAnswer: (answerId: string) => void
}) {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [filter, setFilter] = useState<AuditEntry['result'] | 'all'>('all')
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    getAuditLog().then(setEntries)
  }, [])

  const rows = entries.filter((e) => filter === 'all' || e.result === filter)

  return (
    <div className="h-full w-full bg-slate-50 flex overflow-hidden">
      <Sidebar active="audit" session={session} onNavigate={onNavigate} />

      <main className="flex-1 overflow-y-auto px-5 py-5">
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-base font-semibold text-slate-800 tracking-tight">Audit Log</h1>
          <span className="tnum font-mono text-xs px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-medium">
            {rows.length} writes
          </span>
        </div>
        <p className="text-[11px] text-slate-500 mb-4 flex items-center gap-1.5">
          <Lock className="w-3 h-3 text-slate-400" />
          Append-only. No update or delete path exists on this table.
        </p>

        <div className="flex items-center gap-1 bg-white p-1 rounded-lg shadow-sm mb-3 w-fit">
          {(['all', 'executed', 'pending_approval', 'replayed_noop', 'rejected'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-all ${
                filter === f ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'
              }`}
            >
              {f === 'all' ? 'All' : RESULT[f].label}
              <span className="tnum font-mono text-[10px] opacity-80 ml-1">
                ({f === 'all' ? entries.length : entries.filter((e) => e.result === f).length})
              </span>
            </button>
          ))}
        </div>

        <div className="bg-white rounded-lg shadow-sm overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="h-8 bg-slate-50 text-[11px] font-semibold tracking-wide text-slate-500 uppercase">
                <th className="w-28 px-3 font-medium">Entry</th>
                <th className="px-3 font-medium">Proposal</th>
                <th className="w-44 px-3 font-medium">Rule</th>
                <th className="w-32 px-3 font-medium">Proposed by</th>
                <th className="w-32 px-3 font-medium">Approved by</th>
                <th className="w-36 px-3 font-medium">Result</th>
              </tr>
            </thead>
            <tbody className="text-xs">
              {rows.map((e, i) => (
                <Fragment key={e.id}>
                  <tr
                    onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                    className={`h-10 cursor-pointer transition-colors hover:bg-indigo-50/50 ${
                      i % 2 ? 'bg-slate-50/40' : 'bg-white'
                    }`}
                  >
                    <td className="tnum px-3 font-mono text-slate-500">{e.id}</td>
                    <td className="px-3 text-slate-800">{e.proposal}</td>
                    <td className="px-3">
                      <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200">
                        {e.rule_id}
                      </span>
                    </td>
                    <td className="px-3 font-mono text-[11px] text-slate-600">{e.proposed_by}</td>
                    <td className="px-3 font-mono text-[11px] text-slate-600">{e.approved_by ?? '—'}</td>
                    <td className="px-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-mono font-medium border ${RESULT[e.result].cls}`}>
                        {RESULT[e.result].label}
                      </span>
                    </td>
                  </tr>
                  {expanded === e.id && (
                    <tr className="bg-slate-50">
                      <td colSpan={6} className="px-3 py-3">
                        <div className="grid grid-cols-2 gap-x-8 gap-y-1.5 font-mono text-[11px] max-w-3xl">
                          <Row label="answer_id" value={e.answer_id} />
                          <Row label="action" value={e.action} />
                          <Row label="idempotency_key" value={e.idempotency_key} />
                          <Row label="order_id" value={e.order_id ? `#${e.order_id}` : '—'} />
                          <Row label="executed_at" value={e.executed_at ?? 'not executed'} />
                          <Row label="result" value={e.result} />
                        </div>
                        <button
                          onClick={(ev) => {
                            ev.stopPropagation()
                            onOpenAnswer(e.answer_id)
                          }}
                          className="mt-3 px-2.5 py-1.5 rounded-lg text-[11px] font-medium text-white bg-indigo-600 hover:bg-indigo-700"
                        >
                          Replay this answer →
                        </button>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-slate-200/60 py-0.5">
      <span className="text-slate-400 shrink-0">{label}</span>
      <span className="tnum text-slate-800 truncate">{value}</span>
    </div>
  )
}
