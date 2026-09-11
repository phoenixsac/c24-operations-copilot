import { useEffect, useState } from 'react'
import { QueueScreen } from '@/screens/QueueScreen'
import { TicketWorkspace } from '@/screens/TicketWorkspace'
import { QueryConsole } from '@/screens/QueryConsole'
import { CohortsScreen } from '@/screens/CohortsScreen'
import { AuditLogScreen } from '@/screens/AuditLogScreen'
import { ConsoleChat } from '@/screens/ConsoleChat'
import { getSession, setActor } from '@/api/client'
import type { Dest } from '@/components/Sidebar'
import type { Session } from '@/types/api'

type Route = { name: Dest } | { name: 'ticket'; id: string }

/**
 * Minimal router. Every destination is a real screen over a real entity.
 *
 * The role switcher is a DEMO AFFORDANCE ONLY. In the real system the session
 * is derived server-side from the authenticated actor and is never settable
 * from the client (docs/README_v3.md §Authentication). It exists here so the
 * supervisor-gated paths can be shown without a second login.
 */
export default function App() {
  const [route, setRoute] = useState<Route>({ name: 'queue' })
  const [session, setSession] = useState<Session | null>(null)

  useEffect(() => {
    getSession().then(setSession).catch(() => setSession(null))
  }, [])

  const isSupervisor = session?.role === 'supervisor'
  const openTicket = (id: string) => setRoute({ name: 'ticket', id })
  const navigate = (d: Dest) => setRoute({ name: d })

  /**
   * Names a different actor and re-fetches. The session that comes back is the
   * server's, resolved from the actor row — the client cannot mint one, and
   * asking to be a supervisor does not make you one.
   */
  async function toggleRole() {
    setActor(isSupervisor ? 'u_priya' : 'u_anil')
    const next = await getSession()
    setSession(next)
    // Dropping to l1_agent while on a supervisor-only screen must not strand
    // the user on a screen they can no longer read.
    if (next.role !== 'supervisor' && route.name === 'console') setRoute({ name: 'queue' })
  }

  const screen = (() => {
    switch (route.name) {
      case 'ticket':
        return (
          <TicketWorkspace
            ticketId={route.id}
            onBack={() => setRoute({ name: 'queue' })}
            onSearchCustomer={() => setRoute({ name: 'queue' })}
          />
        )
      case 'console':
        return (
          <QueryConsole
            session={session}
            onBack={() => setRoute({ name: 'queue' })}
            onNavigate={navigate}
            onOpenTicket={openTicket}
          />
        )
      case 'copilot':
        return <ConsoleChat session={session} onNavigate={navigate} />
      case 'cohorts':
        return <CohortsScreen session={session} onOpenTicket={openTicket} onNavigate={navigate} />
      case 'audit':
        return (
          <AuditLogScreen
            session={session}
            onNavigate={navigate}
            onOpenAnswer={() => setRoute({ name: 'ticket', id: 'TKT-4821' })}
          />
        )
      case 'mine':
        return <QueueScreen session={session} mineOnly onOpenTicket={openTicket} onNavigate={navigate} />
      default:
        return <QueueScreen session={session} onOpenTicket={openTicket} onNavigate={navigate} />
    }
  })()

  return (
    <>
      {screen}
      <button
        onClick={toggleRole}
        title="Demo only — the real session comes from the server"
        className="fixed bottom-3 right-3 z-50 px-3 py-1.5 rounded-lg bg-slate-900/90 text-white text-[11px] font-mono shadow-lg hover:bg-slate-900"
      >
        demo · view as {isSupervisor ? 'l1_agent' : 'supervisor'}
      </button>
    </>
  )
}
