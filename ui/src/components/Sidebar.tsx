/**
 * Shared navigation. Every item routes to a real screen backed by a real
 * entity — there are no decorative destinations here:
 *
 *   Queue         → ticket, RLS-scoped
 *   My Tickets    → the same queue filtered to the session actor
 *   Cohorts       → the `cohort` query shape (rule evaluated across the scope)
 *   Audit Log     → the action_audit table
 *   Query Console → supervisor only (E7), hidden entirely below that role
 */
import { Groups, History, Inbox, Robot, Terminal, Ticket, Bolt } from './Icon'
import type { Session } from '@/types/api'

export type Dest = 'queue' | 'mine' | 'cohorts' | 'audit' | 'console' | 'copilot'

function initials(name: string) {
  return name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

export function Sidebar({
  active,
  session,
  counts,
  onNavigate,
}: {
  active: Dest
  session: Session | null
  counts?: Partial<Record<Dest, number>>
  onNavigate: (d: Dest) => void
}) {
  const items: Array<{ id: Dest; icon: typeof Inbox; label: string }> = [
    { id: 'queue', icon: Inbox, label: 'Queue' },
    { id: 'mine', icon: Ticket, label: 'My Tickets' },
    // Not tied to any ticket — questions about the whole book, e.g. SLA misses
    // across the scope. docs/DESIGN.md console-level thread.
    { id: 'copilot', icon: Robot, label: 'Copilot' },
    { id: 'cohorts', icon: Groups, label: 'Cohorts' },
    { id: 'audit', icon: History, label: 'Audit Log' },
  ]

  // Not rendered at all below supervisor. Hiding it is not the control — the
  // database is — but showing a door that always slams is worse than no door.
  if (session?.role === 'supervisor') {
    items.push({ id: 'console', icon: Terminal, label: 'Query Console' })
  }

  return (
    <aside className="w-[220px] shrink-0 h-full bg-white border-r border-slate-200 flex flex-col justify-between">
      <div className="flex flex-col">
        <button
          onClick={() => onNavigate('queue')}
          className="h-14 px-3 flex items-center gap-2 hover:bg-slate-50 transition-colors"
        >
          <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white">
            <Bolt className="w-4 h-4" />
          </div>
          <span className="text-sm font-semibold text-slate-800">Copilot</span>
        </button>

        <nav className="flex flex-col gap-0.5 px-2 mt-2">
          {items.map(({ id, icon: I, label }) => (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              className={`flex items-center justify-between px-2 py-2 rounded-lg transition-colors ${
                active === id
                  ? 'bg-slate-100 text-indigo-600 font-semibold'
                  : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'
              }`}
            >
              <span className="flex items-center gap-2">
                <I className="w-[18px] h-[18px]" />
                <span className="text-xs font-medium">{label}</span>
              </span>
              {counts?.[id] !== undefined && (
                <span className="tnum px-1.5 py-0.5 bg-slate-100 text-slate-500 text-[10px] font-medium rounded leading-none">
                  {counts[id]}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {session && (
        <div className="p-2 m-2 bg-slate-50 rounded-lg flex items-center gap-2 min-w-0">
          <div className="relative shrink-0">
            <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 text-[11px] font-semibold">
              {initials(session.name)}
            </div>
            <span className="absolute bottom-0 right-0 w-2 h-2 rounded-full bg-emerald-500 ring-2 ring-white" />
          </div>
          <div className="min-w-0 flex flex-col">
            <span className="text-xs font-medium text-slate-800 truncate">{session.name}</span>
            <span className="text-[11px] text-slate-500 truncate font-mono">
              {session.role} · {session.city_code}
            </span>
          </div>
        </div>
      )}
    </aside>
  )
}
