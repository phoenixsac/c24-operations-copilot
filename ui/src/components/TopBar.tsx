import { ArrowLeft, Check, Clock } from './Icon'
import type { Session, TicketDetail } from '@/types/api'

const STATE_LABEL: Record<string, string> = {
  OPEN: 'Open',
  ASSIGNED: 'Assigned',
  IN_PROGRESS: 'In Progress',
  AWAITING_CUSTOMER: 'Awaiting Customer',
  AWAITING_INTERNAL: 'Awaiting Internal',
  RESOLVED: 'Resolved',
  CLOSED: 'Closed',
  REOPENED: 'Reopened',
}

const SLA_TONE = {
  ok: 'bg-emerald-50 text-emerald-800 border-emerald-300',
  at_risk: 'bg-amber-50 text-amber-800 border-amber-300',
  breached: 'bg-rose-50 text-rose-800 border-rose-300',
}

function initials(name: string) {
  return name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

export function TopBar({
  ticket,
  session,
  onResolve,
  onBack,
  resolveError,
}: {
  ticket: TicketDetail
  session: Session | null
  onResolve: () => void
  onBack?: () => void
  resolveError?: string | null
}) {
  return (
    <header className="h-14 bg-white border-b border-slate-200 px-4 flex items-center justify-between shrink-0 z-20 shadow-xs">
      <div className="flex items-center space-x-3 overflow-hidden">
        <button
          onClick={onBack}
          className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-800 transition-colors shrink-0"
          title="Back to Tickets"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>

        <span className="tnum font-mono font-semibold text-xs text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded">
          {ticket.id}
        </span>

        <div className="h-4 w-px bg-slate-200 shrink-0" />

        <h1 className="text-sm font-semibold text-slate-900 truncate max-w-xs md:max-w-md" title={ticket.subject}>
          {ticket.subject}
        </h1>

        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 shrink-0">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 mr-1.5 animate-pulse" />
          {STATE_LABEL[ticket.state] ?? ticket.state}
        </span>

        {ticket.resolution ? (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-mono font-medium bg-emerald-50 text-emerald-800 border border-emerald-200 shrink-0">
            {ticket.resolution.resolution_code} · {ticket.resolution.resolved_by}
          </span>
        ) : (
          <div
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border shrink-0 ${SLA_TONE[ticket.sla.status]}`}
          >
            <Clock className="w-3.5 h-3.5 mr-1" />
            {ticket.sla.label}
          </div>
        )}
      </div>

      <div className="flex items-center space-x-3 shrink-0">
        {session && (
          <div className="flex items-center space-x-2 pl-2 border-l border-slate-200">
            <div className="relative">
              <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-indigo-600 to-violet-500 text-white flex items-center justify-center font-semibold text-xs shadow-xs border border-white">
                {initials(session.name)}
              </div>
              <span className="absolute bottom-0 right-0 w-2 h-2 rounded-full bg-emerald-500 ring-1 ring-white" />
            </div>
            <span className="text-xs font-medium text-slate-600 hidden sm:inline">{session.name}</span>
          </div>
        )}

        <div className="relative">
          <button
            onClick={onResolve}
            disabled={ticket.state === 'RESOLVED'}
            className="inline-flex items-center px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 disabled:bg-emerald-600 disabled:cursor-default text-white text-xs font-medium rounded-lg shadow-sm transition-all focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1"
          >
            <Check className="w-3.5 h-3.5 mr-1.5" />
            {ticket.state === 'RESOLVED' ? 'Resolved' : 'Resolve'}
          </button>

          {/* Refusing to close without a cause is the point, so say why. */}
          {resolveError && (
            <div className="absolute right-0 top-full mt-2 w-72 z-30 rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-[11px] text-amber-900 shadow-lg">
              {resolveError}
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
