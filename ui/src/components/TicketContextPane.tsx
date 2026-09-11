import { useState } from 'react'
import { ChevronDown, ChevronRight, Lock, Mail, Pin, WhatsApp } from './Icon'
import type { CustomerMessage, TicketDetail } from '@/types/api'

function lakh(inr: number) {
  return `₹${(inr / 100_000).toFixed(1)}L`
}

function initials(name: string) {
  return name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

function relative(iso: string) {
  const then = new Date(iso)
  const now = new Date('2026-09-10T12:00:00+05:30')
  const days = Math.floor((now.getTime() - then.getTime()) / 86_400_000)
  const hhmm = then.toTimeString().slice(0, 5)
  if (days <= 0) return `Today, ${hhmm}`
  if (days === 1) return `Yesterday, ${hhmm}`
  return `${days}d ago, ${hhmm}`
}

const CHANNEL = {
  whatsapp: { label: 'WhatsApp', dot: 'bg-emerald-600', text: 'text-emerald-700' },
  email: { label: 'Email', dot: 'bg-blue-600', text: 'text-blue-700' },
  call: { label: 'Call', dot: 'bg-slate-500', text: 'text-slate-700' },
} as const

/**
 * Customer text is untrusted. It is rendered as a JSX child, which escapes it —
 * never via dangerouslySetInnerHTML. docs/INVARIANTS.md J12.
 */
function Message({ msg }: { msg: CustomerMessage }) {
  const ch = CHANNEL[msg.channel]
  return (
    <div className="relative">
      <span
        className={`absolute -left-4 top-1 w-3.5 h-3.5 rounded-full ${ch.dot} flex items-center justify-center text-white ring-2 ring-white shadow-2xs`}
        title={ch.label}
      >
        {msg.channel === 'email' ? <Mail className="w-2 h-2" /> : <WhatsApp />}
      </span>

      <div className="bg-slate-100 rounded-lg p-2.5 border border-slate-200">
        <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
          <span className="font-medium text-slate-700 flex items-center">
            <span className={`${ch.text} mr-1`}>{ch.label}</span>
            {msg.flagged && (
              <span className="ml-1 text-amber-700" title="flagged content">
                🛡
              </span>
            )}
          </span>
          <span className="tnum">{relative(msg.at)}</span>
        </div>
        <p className="text-xs text-slate-700 leading-relaxed">{msg.body}</p>
      </div>
    </div>
  )
}

export function TicketContextPane({
  ticket,
  onSearchCustomer,
}: {
  ticket: TicketDetail
  onSearchCustomer?: (name: string) => void
}) {
  const [showLedger, setShowLedger] = useState(false)
  const c = ticket.customer
  return (
    <aside className="w-[300px] shrink-0 bg-white border-r border-slate-200 flex flex-col h-full overflow-hidden">
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
        {/* Customer */}
        <section className="bg-slate-50/80 rounded-xl p-3 border border-slate-200/80 shadow-2xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold tracking-wider uppercase text-slate-400">Customer Details</span>
            <span className="w-2 h-2 rounded-full bg-emerald-500" title="Verified customer" />
          </div>
          <div className="flex items-start space-x-2.5">
            <div className="w-9 h-9 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 font-semibold text-xs shrink-0">
              {initials(c.name)}
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-xs font-bold text-slate-900 truncate">{c.name}</h2>
              <p className="tnum text-[11px] text-slate-500 font-mono mt-0.5">{c.phone}</p>
              <p className="text-[11px] text-slate-500 flex items-center mt-0.5">
                <Pin className="w-3 h-3 mr-1 text-slate-400" />
                {c.city}
              </p>
            </div>
          </div>
          <div className="mt-2.5 pt-2 border-t border-slate-200/60 flex items-center justify-between">
            <button
              onClick={() => onSearchCustomer?.(c.name)}
              className="text-[11px] font-medium text-indigo-600 hover:text-indigo-800 flex items-center transition-colors"
            >
              <span>{c.prior_tickets} previous tickets</span>
              <ChevronRight className="w-3 h-3 ml-0.5" />
            </button>
            <span className="text-[10px] text-slate-400">Since {c.since}</span>
          </div>
        </section>

        {/* Linked order — nullable on purpose. Tickets arrive with no order id. */}
        {ticket.order ? (
          <section className="bg-slate-50/80 rounded-xl p-3 border border-slate-200/80 shadow-2xs">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-bold tracking-wider uppercase text-slate-400">Linked Order</span>
              <span className="tnum font-mono text-[11px] font-semibold text-slate-700 bg-white px-1.5 py-0.5 rounded border border-slate-200">
                #{ticket.order.id}
              </span>
            </div>

            <div className="space-y-1.5">
              <div>
                <p className="text-[11px] text-slate-400">Vehicle</p>
                <p className="text-xs font-semibold text-slate-800">{ticket.order.vehicle}</p>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1">
                <div>
                  <p className="text-[10px] text-slate-400">Reg No</p>
                  <p className="tnum text-xs font-mono font-medium text-slate-700">{ticket.order.reg_no}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-400">Amount</p>
                  <p className="tnum text-xs font-semibold text-slate-900 font-mono">{lakh(ticket.order.amount_inr)}</p>
                </div>
              </div>

              <div className="pt-2 flex items-center justify-between">
                <span className="text-[10px] text-slate-400">Order State</span>
                <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                  {ticket.order.state}
                </span>
              </div>
            </div>
          </section>
        ) : (
          <section className="bg-slate-50/80 rounded-xl p-3 border border-dashed border-slate-300 text-center">
            <p className="text-[11px] text-slate-500">No linked order</p>
            <p className="text-[10px] text-slate-400 mt-0.5">Resolve the customer to an order before acting.</p>
          </section>
        )}

        {/* Customer thread */}
        <section className="pt-1">
          <div className="flex items-center justify-between mb-2 px-0.5">
            <span className="text-[10px] font-bold tracking-wider uppercase text-slate-400">Customer Thread</span>
            <span className="tnum text-[10px] text-slate-400">{ticket.messages.length} messages</span>
          </div>

          <div className="mb-2 bg-amber-50 border border-amber-200 rounded px-2 py-1 text-[10px] font-medium text-amber-800 flex items-center">
            <Lock className="w-3 h-3 mr-1 text-amber-600 shrink-0" />
            Customer message — read only
          </div>

          <div className="relative pl-4 space-y-3.5 before:absolute before:left-1.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
            {ticket.messages.map((m) => (
              <Message key={m.id} msg={m} />
            ))}
          </div>
        </section>
      </div>

      <div className="border-t border-slate-200 bg-slate-50 shrink-0 max-h-[45%] flex flex-col">
        <button
          onClick={() => setShowLedger((v) => !v)}
          className="w-full p-3 flex items-center justify-between text-xs font-semibold text-slate-700 hover:text-slate-900 transition-colors group shrink-0"
        >
          <span className="flex items-center">
            <ChevronDown
              className={`w-3.5 h-3.5 mr-2 text-slate-400 group-hover:text-slate-600 transition-transform ${
                showLedger ? '' : '-rotate-90'
              }`}
            />
            Order state timeline ({ticket.order_events.length} events)
          </span>
          <span className="text-[10px] font-mono text-slate-400 bg-white border border-slate-200 px-1.5 py-0.5 rounded">
            {showLedger ? 'order_event' : 'Collapsed'}
          </span>
        </button>

        {/* The ledger, not order.state. When the two disagree that is a real
            defect — state_ledger_mismatch. docs/DOMAIN_v2.md §1. */}
        {showLedger && (
          <ol className="overflow-y-auto px-3 pb-3 space-y-1.5">
            {ticket.order_events.map((e) => (
              <li key={e.id} className="flex gap-2 text-[11px]">
                <span className="tnum font-mono text-slate-300 w-4 shrink-0">{e.id}</span>
                <span className="flex-1 min-w-0">
                  <span className="font-mono text-slate-700">
                    {e.from_state && e.from_state !== e.to_state ? `${e.from_state} → ` : ''}
                    <span className={e.from_state === e.to_state ? 'text-slate-400' : 'font-semibold'}>
                      {e.to_state}
                    </span>
                  </span>
                  {e.reason && <span className="block text-slate-500 truncate">{e.reason}</span>}
                  <span className="block text-slate-400 font-mono">
                    {e.actor} · {e.at}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  )
}
