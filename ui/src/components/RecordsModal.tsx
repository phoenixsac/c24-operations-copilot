/**
 * Screen 3 — Records explorer. The fallback path.
 *
 * This view is invariant F4 seen from the UI side: if the model provider is
 * unavailable, an agent still has every record linked to the ticket, laid out
 * by entity, with the order timeline — enough to work it by hand. So it renders
 * entirely from `getRecords()` and makes no model call, ever.
 *
 * Raw table browsing is deliberately not offered here. An agent assembling
 * their own joins produces confident wrong conclusions, which is the thing the
 * rules engine exists to prevent (docs/README_v3.md §Console).
 */
import { useState } from 'react'
import { Lock, Plus, Warning } from './Icon'
import type { RecordsGraph } from '@/types/api'

export function RecordsModal({
  records,
  ticketId,
  onClose,
}: {
  records: RecordsGraph
  ticketId: string
  onClose: () => void
}) {
  const firstFired = records.nodes.find((n) => n.rule_fired) ?? records.nodes.find((n) => n.count > 0)
  const [selected, setSelected] = useState(firstFired?.entity ?? '')
  const node = records.nodes.find((n) => n.entity === selected) ?? firstFired

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-[2px] flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[900px] max-h-[88vh] bg-white rounded-2xl shadow-2xl border border-slate-200/90 overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-start justify-between shrink-0">
          <div>
            <h2 className="text-base font-semibold text-slate-900 tracking-tight">All records for {ticketId}</h2>
            <p className="text-[11px] text-slate-500 flex items-center gap-1.5 mt-1">
              <Lock className="w-3 h-3 text-slate-400" />
              Read only. This view works when the copilot is unavailable.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="w-8 h-8 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 flex items-center justify-center transition-colors"
          >
            <Plus className="w-4 h-4 rotate-45" />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Entity tree */}
          <nav className="w-[180px] shrink-0 border-r border-slate-200 bg-slate-50/60 p-2 overflow-y-auto">
            <div className="flex items-center justify-between px-2 py-1.5 text-slate-700 font-medium text-xs">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                Ticket
              </span>
              <span className="tnum text-[11px] font-mono text-slate-400">1</span>
            </div>

            <div className="flex flex-col gap-0.5 pl-3 border-l border-slate-200 ml-3.5 my-0.5">
              {records.nodes.map((n) => {
                const empty = n.count === 0
                const active = n.entity === node?.entity
                return (
                  <button
                    key={n.entity}
                    disabled={empty}
                    onClick={() => setSelected(n.entity)}
                    className={`w-full text-left rounded-md px-2 py-1 flex items-center justify-between transition-colors ${
                      empty
                        ? 'text-slate-300 cursor-not-allowed'
                        : active
                          ? 'bg-indigo-50/90 text-indigo-700 font-medium border border-indigo-100/80'
                          : 'text-slate-600 hover:bg-slate-100'
                    }`}
                  >
                    <span className="flex items-center gap-1.5 overflow-hidden">
                      <span className="font-mono text-[10px] text-slate-300">├</span>
                      <span className="text-xs truncate">{n.label}</span>
                      {/* A rule fired on this entity. */}
                      {n.rule_fired && <span className="w-2 h-2 rounded-full bg-rose-500 shrink-0" />}
                    </span>
                    <span className={`tnum text-[11px] font-mono ${empty ? 'text-slate-300' : 'text-slate-400'}`}>
                      {n.count}
                    </span>
                  </button>
                )
              })}
            </div>
          </nav>

          {/* Selected entity */}
          <div className="flex-1 overflow-y-auto p-5">
            {node && (
              <>
                <div className="flex items-center gap-2 mb-4">
                  <h3 className="text-sm font-semibold text-slate-900">{node.label}</h3>
                  {node.records[0] && (
                    <span className="tnum font-mono text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                      {node.records[0].id}
                    </span>
                  )}
                  {node.rule_fired && (
                    <span className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                      RULE FIRED
                    </span>
                  )}
                </div>

                {node.records.map((rec) => (
                  <div
                    key={rec.id}
                    className="mb-4 rounded-lg border border-slate-200 divide-y divide-slate-100 overflow-hidden"
                  >
                    {rec.fields.map((f) => (
                      <div
                        key={f.label}
                        className={`flex items-center justify-between gap-4 px-3 h-7 ${
                          f.triggered ? 'bg-amber-50' : ''
                        }`}
                      >
                        <span
                          className={`font-mono text-[11px] shrink-0 ${
                            f.triggered ? 'text-amber-900 font-semibold' : 'text-slate-500'
                          }`}
                        >
                          {f.label}
                        </span>
                        <span className="flex items-center gap-2 min-w-0">
                          {f.triggered && <Warning className="w-3.5 h-3.5 text-amber-600 shrink-0" />}
                          <span
                            className={`tnum font-mono text-[11px] truncate ${
                              f.triggered ? 'text-amber-950 font-bold' : 'text-slate-800'
                            }`}
                          >
                            {f.triggered ? `"${f.value}"` : f.value}
                          </span>
                          {f.rule_id && (
                            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 shrink-0">
                              {f.rule_id}
                            </span>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                ))}

                {node.records.length === 0 && (
                  <p className="text-xs text-slate-400">No records for this entity.</p>
                )}

                {/* Order state timeline */}
                <h4 className="text-sm font-semibold text-slate-800 mt-6 mb-3">Order state timeline</h4>
                <div className="rounded-lg border border-slate-200 p-4 overflow-x-auto">
                  <ol className="flex items-start min-w-[640px]">
                    {records.timeline.map((s, i) => (
                      <li key={s.state} className="flex-1 flex flex-col items-center relative">
                        {i > 0 && (
                          <span
                            className={`absolute top-3 right-1/2 w-full h-0.5 ${
                              s.status === 'pending' ? 'bg-slate-200' : 'bg-emerald-400'
                            }`}
                          />
                        )}
                        <span
                          className={`relative z-10 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white ${
                            s.status === 'done'
                              ? 'bg-emerald-500'
                              : s.status === 'current'
                                ? 'bg-indigo-600'
                                : s.status === 'blocked'
                                  ? 'bg-rose-500'
                                  : 'bg-slate-200'
                          }`}
                        >
                          {s.status === 'done' ? '✓' : s.status === 'blocked' ? '!' : ''}
                        </span>
                        <span
                          className={`text-[10px] font-mono font-medium mt-2 text-center ${
                            s.status === 'pending' ? 'text-slate-300' : 'text-slate-600'
                          }`}
                        >
                          {s.state}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>

                <div className="mt-3 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2.5 text-xs text-amber-900">
                  {records.timeline_caption}
                </div>
              </>
            )}
          </div>
        </div>

        <div className="px-6 py-3 border-t border-slate-100 bg-slate-50/80 flex items-center justify-between shrink-0">
          <span className="text-[11px] text-slate-400">
            Read-only projection of the ticket's entity graph. No model call was made to render this.
          </span>
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 border border-slate-200 hover:bg-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
