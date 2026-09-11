/**
 * Screen 1 — Ticket Queue.
 *
 * Every control here does something, and everything it does maps to a column
 * in docs/DOMAIN_v2.md. Removed from the generated design because nothing in
 * the data model backs them: global search in the top bar (duplicated the
 * queue search), notifications bell, help button, a second user avatar, the
 * settings gear, the "Columns: Standard Ops" picker, and the "v2.4" and
 * "Auto-sync active" chips.
 */
import { useEffect, useMemo, useState } from 'react'
import { Fire, Robot, Search, Shield, Sync, Tune, ChevronLeft, ChevronRight } from '@/components/Icon'
import { Sidebar, type Dest } from '@/components/Sidebar'
import { assignTicket, getQueue } from '@/api/client'
import type { Session, TicketQueue, TicketSummary } from '@/types/api'

const CITY_LABEL: Record<string, string> = {
  mum: 'Mumbai, MH',
  pun: 'Pune, MH',
  blr: 'Bengaluru, KA',
}

const PRIORITY: Record<TicketSummary['priority'], { code: string; pill: string }> = {
  urgent: { code: 'P0', pill: 'bg-rose-600 text-white' },
  high: { code: 'P1', pill: 'bg-amber-700 text-white' },
  normal: { code: 'P2', pill: 'bg-indigo-600 text-white' },
  low: { code: 'P3', pill: 'bg-slate-200 text-slate-600' },
}

const STATE_PILL: Record<string, { label: string; cls: string; dot: string }> = {
  OPEN: { label: 'Open', cls: 'bg-violet-100 text-violet-700', dot: 'bg-violet-600' },
  ASSIGNED: { label: 'Assigned', cls: 'bg-slate-200 text-slate-600', dot: 'bg-slate-500' },
  IN_PROGRESS: { label: 'In Progress', cls: 'bg-indigo-100 text-indigo-700', dot: 'bg-indigo-600' },
  AWAITING_CUSTOMER: { label: 'Awaiting Cust', cls: 'bg-amber-100 text-amber-800', dot: 'bg-amber-600' },
  AWAITING_INTERNAL: { label: 'Awaiting Int', cls: 'bg-amber-100 text-amber-800', dot: 'bg-amber-600' },
  RESOLVED: { label: 'Resolved', cls: 'bg-emerald-100 text-emerald-700', dot: 'bg-emerald-600' },
  CLOSED: { label: 'Closed', cls: 'bg-slate-200 text-slate-500', dot: 'bg-slate-400' },
  REOPENED: { label: 'Reopened', cls: 'bg-rose-100 text-rose-700', dot: 'bg-rose-600' },
}

const STATES = Object.keys(STATE_PILL)
const PAGE_SIZE = 6

function initials(name: string) {
  return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()
}

export function QueueScreen({
  session,
  mineOnly = false,
  onOpenTicket,
  onNavigate,
}: {
  session: Session | null
  mineOnly?: boolean
  onOpenTicket: (id: string) => void
  onNavigate: (d: Dest) => void
}) {
  const [queue, setQueue] = useState<TicketQueue | null>(null)
  const [tab, setTab] = useState('all')
  const [q, setQ] = useState('')
  const [stateFilter, setStateFilter] = useState<string[]>([])
  const [showFilters, setShowFilters] = useState(false)
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState(false)

  const load = () => getQueue().then(setQueue)
  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    setPage(1)
  }, [tab, q, stateFilter, mineOnly])

  const all = queue?.tickets ?? []

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return all.filter((t) => {
      if (mineOnly && t.assignee !== session?.name) return false
      if (tab === 'attention' && !(t.flags.sla_breach || t.flags.reopen_count > 0)) return false
      if (tab === 'high' && t.priority !== 'urgent' && t.priority !== 'high') return false
      if (tab === 'unassigned' && t.assignee) return false
      if (stateFilter.length && !stateFilter.includes(t.state)) return false
      if (!needle) return true
      // Search covers the fields an agent actually has to hand: ticket id,
      // subject, customer name, and order number.
      return (
        t.id.toLowerCase().includes(needle) ||
        t.subject.toLowerCase().includes(needle) ||
        t.customer_name.toLowerCase().includes(needle) ||
        String(t.order_id ?? '').includes(needle)
      )
    })
  }, [all, q, tab, stateFilter, mineOnly, session])

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const rows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  async function assign(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    if (!session) return
    setBusy(true)
    try {
      await assignTicket(id)
      await load()
    } finally {
      setBusy(false)
    }
  }

  if (!queue) {
    return <div className="h-full flex items-center justify-center text-slate-400 text-xs">Loading queue…</div>
  }

  const s = queue.stats
  const TABS = [
    { id: 'all', label: 'All', count: all.filter((t) => !mineOnly || t.assignee === session?.name).length },
    { id: 'attention', label: 'Needs Attention', count: all.filter((t) => t.flags.sla_breach || t.flags.reopen_count > 0).length, dot: 'bg-rose-600' },
    { id: 'high', label: 'High Priority', count: all.filter((t) => t.priority === 'urgent' || t.priority === 'high').length },
    { id: 'unassigned', label: 'Unassigned', count: all.filter((t) => !t.assignee).length },
  ]

  return (
    <div className="h-full w-full bg-slate-50 flex overflow-hidden">
      <Sidebar
        active={mineOnly ? 'mine' : 'queue'}
        session={session}
        counts={{ mine: all.filter((t) => t.assignee === session?.name).length }}
        onNavigate={onNavigate}
      />

      <main className="flex-1 overflow-y-auto px-5 py-5">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-5">
          <div className="flex items-center gap-3">
            <div className="flex items-baseline gap-2">
              <h1 className="text-base font-semibold text-slate-800 tracking-tight">
                {mineOnly ? 'My Tickets' : 'Ticket Queue'}
              </h1>
              <span className="tnum font-mono text-xs px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-medium">
                {filtered.length} shown
              </span>
            </div>
            {/* The RLS boundary, made visible rather than implied. */}
            <div className="hidden sm:flex items-center gap-1 pl-1 text-slate-500 text-[11px] font-medium">
              <Shield className="w-3.5 h-3.5 text-emerald-600" />
              <span className="font-mono">
                scoped to {queue.scope.city_code} · {queue.scope.role}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative min-w-[280px]">
              <Search className="w-[18px] h-[18px] absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="w-full h-8 pl-9 pr-8 bg-white text-slate-800 text-xs rounded shadow-sm placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-600 focus:outline-none transition-all"
                placeholder="Ticket id, subject, customer, order…"
              />
              {q && (
                <button
                  onClick={() => setQ('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700 text-xs"
                >
                  ✕
                </button>
              )}
            </div>
            <button
              onClick={() => setShowFilters((v) => !v)}
              className={`h-8 px-3 text-xs font-medium rounded shadow-sm flex items-center gap-1 transition-colors ${
                stateFilter.length || showFilters
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-slate-800 hover:bg-slate-100'
              }`}
            >
              <Tune className="w-4 h-4" />
              Filters
              {stateFilter.length > 0 && <span className="tnum">({stateFilter.length})</span>}
            </button>
            <button
              onClick={load}
              className="h-8 px-3 bg-white text-slate-800 hover:bg-slate-100 text-xs font-medium rounded shadow-sm flex items-center gap-1 transition-colors"
            >
              <Sync className="w-4 h-4 text-slate-400" />
              Refresh
            </button>
          </div>
        </div>

        {/* Filter panel — ticket.state, a real column. */}
        {showFilters && (
          <div className="mb-4 p-3 bg-white rounded-lg shadow-sm flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mr-1">
              ticket.state
            </span>
            {STATES.map((st) => {
              const on = stateFilter.includes(st)
              return (
                <button
                  key={st}
                  onClick={() => setStateFilter((f) => (on ? f.filter((x) => x !== st) : [...f, st]))}
                  className={`px-2 py-1 rounded font-mono text-[11px] border transition-colors ${
                    on
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                  }`}
                >
                  {st}
                </button>
              )
            })}
            {stateFilter.length > 0 && (
              <button onClick={() => setStateFilter([])} className="ml-auto text-[11px] text-indigo-600 hover:underline">
                Clear
              </button>
            )}
          </div>
        )}

        {/* Stat cards — each sets the filter it describes. */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
          <StatCard label="Unassigned" value={s.unassigned.count} unit="tickets" foot={`${s.unassigned.high_priority} high priority`} onClick={() => setTab('unassigned')} />
          <StatCard tone="rose" label="SLA Breach" value={s.sla_breach.count} unit="critical" foot="Action required" onClick={() => setTab('attention')} />
          <StatCard tone="amber" label="Awaiting Customer" value={s.awaiting_customer.count} unit="pending" foot={`Avg wait ${s.awaiting_customer.avg_wait_hours}h`} onClick={() => { setStateFilter(['AWAITING_CUSTOMER']); setShowFilters(true) }} />
          <StatCard tone="violet" label="Auto-Resolved Today" value={s.auto_resolved_today.count} unit="via copilot" foot={`${(s.auto_resolved_today.mean_confidence * 100).toFixed(1)}% mean confidence`} onClick={() => { setStateFilter(['RESOLVED']); setShowFilters(true) }} />
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 bg-white p-1 rounded-lg shadow-sm mb-2 w-fit">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-all flex items-center gap-1 ${
                tab === t.id ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'
              }`}
            >
              {t.dot && <span className={`w-2 h-2 rounded-full ${t.dot}`} />}
              {t.label}
              <span className="tnum font-mono text-[10px] opacity-80">({t.count})</span>
            </button>
          ))}
        </div>

        {/* Table */}
        <div className="bg-white rounded-lg shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[1000px]">
              <thead>
                <tr className="h-8 bg-slate-50 text-[11px] font-semibold tracking-wide text-slate-500 uppercase select-none">
                  <th className="w-10 px-1 text-center font-medium">Pri</th>
                  <th className="w-28 px-2 font-medium">Ticket</th>
                  <th className="px-2 font-medium">Subject</th>
                  <th className="w-44 px-2 font-medium">Customer</th>
                  <th className="w-28 px-2 font-medium">Order</th>
                  <th className="w-36 px-2 font-medium">State</th>
                  <th className="w-24 px-2 font-medium text-center">Flags</th>
                  <th className="w-16 px-2 text-right font-medium">Age</th>
                  <th className="w-36 px-2 font-medium">Assignee</th>
                </tr>
              </thead>
              <tbody className="text-xs text-slate-800">
                {rows.map((t, i) => {
                  const st = STATE_PILL[t.state]
                  return (
                    <tr
                      key={t.id}
                      onClick={() => onOpenTicket(t.id)}
                      className={`h-11 cursor-pointer transition-colors relative ${i % 2 ? 'bg-slate-50/40' : 'bg-white'} hover:bg-indigo-50/50`}
                    >
                      <td className="px-1 text-center relative">
                        {t.flags.sla_breach && <span className="absolute left-0 top-0 bottom-0 w-1 bg-rose-600" />}
                        <span className={`inline-block px-1.5 py-0.5 rounded font-mono text-[10px] font-bold ${PRIORITY[t.priority].pill}`}>
                          {PRIORITY[t.priority].code}
                        </span>
                      </td>
                      <td className="tnum px-2 font-mono text-xs font-semibold text-indigo-600">{t.id}</td>
                      <td className="px-2 max-w-xs">
                        <span className="truncate block text-slate-800">{t.subject}</span>
                      </td>
                      <td className="px-2">
                        <div className="flex flex-col leading-tight min-w-0">
                          <span className="text-xs font-medium text-slate-800 truncate">{t.customer_name}</span>
                          <span className="text-[11px] text-slate-500 truncate">{CITY_LABEL[t.city_code] ?? t.city_code}</span>
                        </div>
                      </td>
                      <td className="px-2">
                        {t.order_id ? (
                          <span className="tnum font-mono text-xs text-indigo-600 px-1.5 py-0.5 bg-indigo-100 rounded">#{t.order_id}</span>
                        ) : (
                          // Nullable on purpose — tickets arrive with no order number.
                          <span className="font-mono text-xs text-slate-400 px-1.5 py-0.5 bg-slate-100 rounded">unlinked</span>
                        )}
                      </td>
                      <td className="px-2">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${st.cls}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                          {st.label}
                        </span>
                      </td>
                      <td className="px-2 text-center">
                        <div className="flex items-center justify-center gap-1">
                          {t.flags.sla_breach && <Fire className="w-4 h-4 text-rose-600" />}
                          {t.flags.reopen_count > 0 && (
                            <span className="tnum px-1 bg-slate-100 text-slate-500 rounded font-mono text-[10px] font-semibold">
                              {t.flags.reopen_count}x
                            </span>
                          )}
                          {t.flags.auto_replied && <Robot className="w-4 h-4 text-violet-600" />}
                          {/* Suspected injection is flagged and surfaced, never
                              silently stripped. docs/INVARIANTS.md J10. */}
                          {t.flags.flagged_content && <Shield className="w-4 h-4 text-amber-600" />}
                        </div>
                      </td>
                      <td className={`tnum px-2 text-right font-mono text-xs font-semibold ${t.flags.sla_breach ? 'text-rose-600' : 'text-slate-600'}`}>
                        {t.age}
                      </td>
                      <td className="px-2">
                        {t.assignee ? (
                          <div className="flex items-center gap-1">
                            <div className="w-6 h-6 rounded-full bg-indigo-600 text-white font-semibold text-[10px] flex items-center justify-center">
                              {initials(t.assignee)}
                            </div>
                            <span className="text-[11px] font-medium text-slate-800 truncate">{t.assignee}</span>
                          </div>
                        ) : t.flags.auto_replied ? (
                          <span className="text-[11px] font-mono text-violet-600">copilot_auto</span>
                        ) : (
                          <button
                            onClick={(e) => assign(e, t.id)}
                            disabled={busy}
                            className="px-2 py-1 border border-dashed border-slate-300 text-slate-500 rounded text-[11px] hover:border-indigo-400 hover:text-indigo-600 transition-colors disabled:opacity-50"
                          >
                            + Assign to me
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={9} className="h-24 text-center text-xs text-slate-400">
                      No tickets match. {q && <button onClick={() => setQ('')} className="text-indigo-600 underline">Clear search</button>}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-t border-slate-200">
            <span className="tnum text-[11px] text-slate-500">
              {filtered.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of{' '}
              {filtered.length}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="w-7 h-7 rounded flex items-center justify-center text-slate-400 hover:bg-white disabled:opacity-30"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              {Array.from({ length: pages }, (_, i) => i + 1).map((n) => (
                <button
                  key={n}
                  onClick={() => setPage(n)}
                  className={`tnum w-7 h-7 rounded text-xs font-medium ${n === page ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:bg-white'}`}
                >
                  {n}
                </button>
              ))}
              <button
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="w-7 h-7 rounded flex items-center justify-center text-slate-400 hover:bg-white disabled:opacity-30"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

function StatCard({
  label,
  value,
  unit,
  foot,
  onClick,
  tone = 'neutral',
}: {
  label: string
  value: number
  unit: string
  foot: string
  onClick: () => void
  tone?: 'neutral' | 'rose' | 'amber' | 'violet'
}) {
  const T = {
    neutral: { card: 'bg-white', bar: '', label: 'text-slate-500', value: 'text-slate-800', foot: 'text-indigo-600' },
    rose: { card: 'bg-rose-50/40', bar: 'bg-rose-600', label: 'text-rose-600', value: 'text-rose-600', foot: 'text-rose-600' },
    amber: { card: 'bg-amber-50/50', bar: 'bg-amber-600', label: 'text-amber-700', value: 'text-amber-700', foot: 'text-amber-700' },
    violet: { card: 'bg-white', bar: '', label: 'text-slate-500', value: 'text-violet-600', foot: 'text-violet-600' },
  }[tone]

  return (
    <button
      onClick={onClick}
      className={`${T.card} p-3 rounded-lg shadow-sm hover:shadow-md transition-shadow text-left relative overflow-hidden`}
    >
      {T.bar && <div className={`absolute left-0 top-0 bottom-0 w-1 ${T.bar}`} />}
      <div className="flex flex-col gap-0.5">
        <span className={`text-[11px] font-semibold tracking-wider uppercase ${T.label}`}>{label}</span>
        <div className="flex items-baseline gap-1">
          <span className={`tnum text-2xl leading-8 font-bold ${T.value}`}>{value}</span>
          <span className="text-[11px] font-medium text-slate-500">{unit}</span>
        </div>
        <span className={`text-[11px] font-medium ${T.foot}`}>{foot}</span>
      </div>
    </button>
  )
}
