/**
 * Screen 4 — Action approval.
 *
 * Stitch generated two separate screens, agent and supervisor. They are one
 * component here, because the difference is data, not layout: the gate exists
 * when `proposal.approval_gate` is set, and that comes from the server
 * comparing the action against the caller's permitted_actions and limit.
 *
 * Rendering it as two screens would imply the client decides which one to show.
 * It does not. Authorization is checked at proposal and again at execution
 * (docs/INVARIANTS.md D3); this modal only reports what the server already
 * decided, and the button being enabled is never what makes a write legal.
 */
import { useState } from 'react'
import { Check, Link, Lock, Plus, Help } from './Icon'
import { approveAction } from '@/api/client'
import type { ProposedAction, Session } from '@/types/api'

function inr(n: number) {
  return `₹${n.toLocaleString('en-IN')}`
}

function initials(name: string) {
  return name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

export function ApprovalModal({
  proposal,
  session,
  evidence,
  onClose,
}: {
  proposal: ProposedAction
  session: Session | null
  evidence: Array<{ table: string; record_id: string }>
  onClose: () => void
}) {
  const [result, setResult] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const gate = proposal.approval_gate
  const blocked = !!gate
  const isSupervisor = session?.role === 'supervisor'

  async function confirm() {
    if (blocked || busy) return
    setBusy(true)
    try {
      // The idempotency key was minted server-side at proposal time. The client
      // echoes it back; replaying this call must have no second effect. D2.
      const r = await approveAction(proposal.proposal_id, proposal.idempotency_key)
      setResult(r.result)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-[2px] flex items-center justify-center p-4">
      <div className="w-full max-w-[560px] bg-white rounded-2xl shadow-2xl border border-slate-200/90 overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-white shrink-0">
          <div className="flex items-center gap-2.5">
            <div
              className={`w-8 h-8 rounded-lg border flex items-center justify-center ${
                isSupervisor
                  ? 'bg-emerald-50 border-emerald-100 text-emerald-600'
                  : 'bg-indigo-50 border-indigo-100 text-indigo-600'
              }`}
            >
              <Lock className="w-4 h-4" />
            </div>
            <h2 className="text-base font-semibold text-slate-900 tracking-tight flex items-center gap-2">
              Approve action
              <span className="text-[11px] font-normal uppercase tracking-wider px-2 py-0.5 rounded bg-slate-100 text-slate-500 font-mono">
                {isSupervisor ? 'Supervisor view' : 'Agent view'}
              </span>
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="w-8 h-8 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 flex items-center justify-center transition-colors"
          >
            <Plus className="w-4 h-4 rotate-45" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-5 overflow-y-auto">
          <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${blocked ? 'bg-amber-500' : 'bg-indigo-600'}`} />
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Proposed action</span>
              </div>
              <span className="text-xs font-mono font-medium text-slate-500">{proposal.action}</span>
            </div>

            <div className="text-base font-medium text-slate-900 tracking-tight">{proposal.label}</div>

            <div className="grid grid-cols-2 gap-y-2.5 gap-x-4 pt-2 border-t border-slate-200/60 text-xs">
              {Object.entries(proposal.params).map(([k, v]) => (
                <div key={k}>
                  <span className="text-slate-500 block text-[11px] mb-0.5 capitalize">{k.replace(/_/g, ' ')}</span>
                  <span
                    className={
                      k.includes('amount')
                        ? 'tnum font-mono font-bold text-slate-900 text-sm'
                        : k.includes('id')
                          ? 'tnum font-mono font-semibold text-slate-800 bg-white border border-slate-200 px-1.5 py-0.5 rounded text-[11px]'
                          : 'font-medium text-slate-800 text-xs'
                    }
                  >
                    {k.includes('amount') && typeof v === 'number' ? inr(v) : v}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Provenance — no proposal without a rule that motivated it. A6. */}
          <div className="space-y-2">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
              <Help className="w-3.5 h-3.5 text-slate-400" />
              Why this was proposed
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono font-medium bg-rose-50 text-rose-700 border border-rose-200 shadow-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-600" />
                {proposal.motivating_rule}
              </span>
              {evidence.map((e) => (
                <span
                  key={e.record_id}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono text-slate-700 bg-white border border-slate-200 shadow-sm"
                >
                  <Link className="w-3 h-3 text-slate-400" />
                  {e.table} #{e.record_id}
                </span>
              ))}
            </div>
          </div>

          {/* Bulk scope disclosed before execution, not after. D6. */}
          {proposal.bulk && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-3.5 text-xs text-amber-900">
              <p className="font-medium">
                This affects {proposal.bulk.count} orders.
              </p>
              <p className="mt-1 font-mono text-[11px] text-amber-800">
                Sample: {proposal.bulk.sample.join(', ')}
              </p>
            </div>
          )}

          {/* The gate. Present iff the server said so. */}
          {gate && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-3.5 space-y-2">
              <div className="flex items-start gap-2.5">
                <div className="w-5 h-5 rounded-full bg-amber-100 flex items-center justify-center text-amber-700 shrink-0 mt-0.5">
                  <Lock className="w-3.5 h-3.5" />
                </div>
                <div className="text-xs text-amber-900 leading-relaxed font-medium">{gate.reason}</div>
              </div>
              <div className="pl-7 pt-1 border-t border-amber-200/60 flex items-center justify-between text-xs text-amber-800">
                <div className="flex items-center gap-1.5">
                  <span className="text-amber-700/80">Routing to:</span>
                  <span className="font-semibold text-amber-950 flex items-center gap-1">
                    <span className="w-4 h-4 rounded-full bg-amber-200 text-amber-900 text-[10px] flex items-center justify-center font-bold">
                      {initials(gate.routes_to.name)}
                    </span>
                    {gate.routes_to.name}
                  </span>
                  <span className="text-[11px] px-1.5 py-px rounded bg-amber-200/70 text-amber-900 font-medium">
                    {gate.routes_to.role}
                  </span>
                </div>
              </div>
            </div>
          )}

          <div className="rounded-lg bg-slate-50 border border-slate-200/90 px-3 py-2 flex items-center justify-between text-xs text-slate-500 font-mono">
            <div className="flex items-center gap-2 truncate">
              <Help className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <span className="text-slate-600">idempotency key:</span>
              <span className="tnum text-slate-800 font-medium truncate">{proposal.idempotency_key}</span>
            </div>
            <button
              onClick={() => navigator.clipboard?.writeText(proposal.idempotency_key)}
              className="text-[11px] text-indigo-600 hover:text-indigo-700 font-sans font-medium shrink-0 ml-2 hover:underline"
            >
              Copy
            </button>
          </div>

          {result && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800 flex items-center gap-2">
              <Check className="w-4 h-4" />
              Executed — <span className="font-mono">{result}</span>. Recorded in the audit log.
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 flex flex-col gap-2 shrink-0">
          <div className="flex items-center justify-between">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={confirm}
              disabled={blocked || busy || !!result}
              className={`px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                blocked || !!result
                  ? 'bg-slate-200 text-slate-400 border border-slate-300/80 cursor-not-allowed'
                  : 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm'
              }`}
            >
              {blocked ? <Lock className="w-3.5 h-3.5" /> : <Check className="w-3.5 h-3.5" />}
              {blocked ? 'Request supervisor approval' : busy ? 'Executing…' : 'Approve and execute'}
            </button>
          </div>
          <div className="text-[11px] text-slate-400 text-right pr-0.5">
            {result ? 'Executed once. Replaying this key is a no-op.' : 'This action has not been executed.'}
          </div>
        </div>
      </div>
    </div>
  )
}
