/**
 * Cohorts — the `cohort` query shape from docs/README_v3.md §Query shapes:
 * SQL plus per-item rules.
 *
 * A cohort here is always *a rule evaluated across the scope*, never a saved
 * filter someone typed. That is what makes the counts aggregate: because causes
 * are structured rule ids rather than sentences, "what is the top reason
 * deliveries slipped" is answerable at all.
 */
import { useEffect, useState } from 'react'
import { Sidebar, type Dest } from '@/components/Sidebar'
import { ChevronRight, Shield } from '@/components/Icon'
import { getCohorts, getTicketCohorts } from '@/api/client'
import type { Cohort, Session, TicketCohort } from '@/types/api'

export function CohortsScreen({
  session,
  onOpenTicket,
  onNavigate,
}: {
  session: Session | null
  onOpenTicket: (id: string) => void
  onNavigate: (d: Dest) => void
}) {
  const [cohorts, setCohorts] = useState<Cohort[]>([])
  const [ticketCohorts, setTicketCohorts] = useState<TicketCohort[]>([])
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    getCohorts().then((c) => {
      setCohorts(c)
      setSelected((s) => s ?? c[0]?.id ?? null)
    })
    getTicketCohorts().then(setTicketCohorts).catch(() => setTicketCohorts([]))
  }, [])

  const active = cohorts.find((c) => c.id === selected)
  const activeTicket = ticketCohorts.find((c) => c.id === selected)
  const total = cohorts.length + ticketCohorts.length

  return (
    <div className="h-full w-full bg-slate-50 flex overflow-hidden">
      <Sidebar active="cohorts" session={session} onNavigate={onNavigate} />

      <main className="flex-1 overflow-y-auto px-5 py-5">
        <div className="flex items-center gap-3 mb-5">
          <h1 className="text-base font-semibold text-slate-800 tracking-tight">Cohorts</h1>
          <span className="tnum font-mono text-xs px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-medium">
            {total} rules
          </span>
          <div className="flex items-center gap-1 text-slate-500 text-[11px] font-medium">
            <Shield className="w-3.5 h-3.5 text-emerald-600" />
            <span className="font-mono">
              scoped to {session?.city_code} · {session?.role}
            </span>
          </div>
        </div>

        <div className="flex gap-4">
          {/* Rule list */}
          <div className="w-[300px] shrink-0 space-y-2">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-1">
              Order rules
            </div>
            {cohorts.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelected(c.id)}
                className={`w-full text-left p-3 rounded-lg shadow-sm transition-all ${
                  c.id === selected ? 'bg-white ring-2 ring-indigo-500' : 'bg-white hover:shadow-md'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-semibold text-slate-800">{c.label}</span>
                  <span className="tnum text-sm font-bold text-slate-800 shrink-0">{c.members.length}</span>
                </div>
                <span className="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded font-mono text-[10px] bg-rose-50 text-rose-700 border border-rose-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                  {c.rule_id}
                </span>
              </button>
            ))}

            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-1 pt-3">
              Ticket rules
            </div>
            {ticketCohorts.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelected(c.id)}
                className={`w-full text-left p-3 rounded-lg shadow-sm transition-all ${
                  c.id === selected ? 'bg-white ring-2 ring-indigo-500' : 'bg-white hover:shadow-md'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-semibold text-slate-800">{c.label}</span>
                  <span className="tnum text-sm font-bold text-slate-800 shrink-0">{c.members.length}</span>
                </div>
                <span className="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded font-mono text-[10px] bg-amber-50 text-amber-800 border border-amber-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                  {c.rule_id}
                </span>
              </button>
            ))}
          </div>

          {/* Members */}
          <div className="flex-1 bg-white rounded-lg shadow-sm overflow-hidden">
            {activeTicket && (
              <>
                <div className="px-4 py-3 border-b border-slate-200">
                  <h2 className="text-sm font-semibold text-slate-800">{activeTicket.label}</h2>
                  <p className="text-[11px] text-slate-500 mt-0.5">{activeTicket.description}</p>
                </div>

                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="h-8 bg-slate-50 text-[11px] font-semibold tracking-wide text-slate-500 uppercase">
                      <th className="w-28 px-3 font-medium">Ticket</th>
                      <th className="px-3 font-medium">Subject</th>
                      <th className="w-40 px-3 font-medium">State</th>
                      <th className="w-24 px-3 font-medium">Waiting</th>
                      <th className="w-24 px-3 font-medium">Order</th>
                    </tr>
                  </thead>
                  <tbody className="text-xs">
                    {activeTicket.members.map((m, i) => (
                      <tr
                        key={m.ticket_id}
                        onClick={() => onOpenTicket(m.ticket_id)}
                        className={`h-10 cursor-pointer transition-colors hover:bg-indigo-50/50 ${
                          i % 2 ? 'bg-slate-50/40' : 'bg-white'
                        }`}
                      >
                        <td className="tnum px-3 font-mono text-indigo-600 font-semibold">{m.ticket_id}</td>
                        <td className="px-3 truncate max-w-xs">{m.subject}</td>
                        <td className="px-3">
                          <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-700">
                            {m.state}
                          </span>
                        </td>
                        <td className="tnum px-3 font-mono font-semibold text-amber-700">{m.waiting_for}</td>
                        <td className="tnum px-3 font-mono text-[11px] text-slate-500">
                          {m.order_id ? `#${m.order_id}` : 'unlinked'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="px-4 py-2 bg-slate-50 border-t border-slate-200 text-[11px] text-slate-500">
                  {activeTicket.members.length} tickets matched by{' '}
                  <span className="font-mono text-slate-700">{activeTicket.rule_id}</span> within scope.
                </div>
              </>
            )}

            {active && !activeTicket && (
              <>
                <div className="px-4 py-3 border-b border-slate-200">
                  <h2 className="text-sm font-semibold text-slate-800">{active.label}</h2>
                  <p className="text-[11px] text-slate-500 mt-0.5">{active.description}</p>
                </div>

                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="h-8 bg-slate-50 text-[11px] font-semibold tracking-wide text-slate-500 uppercase">
                      <th className="w-24 px-3 font-medium">Order</th>
                      <th className="w-40 px-3 font-medium">State</th>
                      <th className="w-24 px-3 font-medium">Stuck</th>
                      <th className="px-3 font-medium">Blocking reason</th>
                      <th className="w-32 px-3 font-medium">Ticket</th>
                    </tr>
                  </thead>
                  <tbody className="text-xs">
                    {active.members.map((m, i) => (
                      <tr
                        key={`${m.order_id}-${i}`}
                        onClick={() => m.ticket_id && onOpenTicket(m.ticket_id)}
                        className={`h-10 transition-colors ${m.ticket_id ? 'cursor-pointer hover:bg-indigo-50/50' : ''} ${
                          i % 2 ? 'bg-slate-50/40' : 'bg-white'
                        }`}
                      >
                        <td className="tnum px-3 font-mono text-indigo-600 font-semibold">#{m.order_id}</td>
                        <td className="px-3">
                          <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-700">
                            {m.state}
                          </span>
                        </td>
                        <td className="tnum px-3 font-mono font-semibold text-rose-600">{m.stuck_for}</td>
                        <td className="px-3 font-mono text-[11px] text-amber-800">{m.blocking_reason ?? '—'}</td>
                        <td className="px-3">
                          {m.ticket_id ? (
                            <span className="tnum font-mono text-[11px] text-indigo-600 inline-flex items-center gap-0.5">
                              {m.ticket_id}
                              <ChevronRight className="w-3 h-3" />
                            </span>
                          ) : (
                            <span className="text-[11px] text-slate-400">no ticket</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="px-4 py-2 bg-slate-50 border-t border-slate-200 text-[11px] text-slate-500">
                  {active.members.length} orders matched by{' '}
                  <span className="font-mono text-slate-700">{active.rule_id}</span> within scope.
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
