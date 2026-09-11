/**
 * One copilot answer. The product thesis rendered:
 *   verdict → diagnosis strip → rule chips → explanation → evidence → actions.
 *
 * Four states, all produced by the rules engine over real rows:
 *   diagnosis  — rules fired, cause shown, action proposed
 *   refusal    — no data supports an answer; pointers instead (B2)
 *   proposal   — write proposed, never executed on this turn (D1)
 *   degraded   — a source was unavailable and is named, not silently empty (B5)
 *
 * Nothing here picks a cause or invents an action. Everything rendered comes
 * from the payload; the component's only job is to make provenance legible.
 */
import { useState } from 'react'
import { ArrowSmallRight, ChevronRight, Link } from './Icon'
import type { AskResponse, EvidenceRecord } from '@/types/api'

/** Collapsed by default — the field-level line reads like a raw DB row on
 * purpose, so it stays out of the way until an operator wants to audit it. */
function ProvenanceDisclosure({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="pt-1">
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-600"
      >
        <ChevronRight className={`w-3 h-3 transition-transform ${open ? 'rotate-90' : ''}`} />
        Provenance
      </button>
      {open && (
        <pre className="mt-1.5 font-mono text-[11px] text-slate-600 bg-slate-50 border border-slate-200 rounded-md p-2 whitespace-pre-wrap break-words">
          {text}
        </pre>
      )}
    </div>
  )
}

function EvidenceChip({
  record,
  highlighted,
  onSelect,
}: {
  record: EvidenceRecord
  highlighted: boolean
  onSelect?: (r: EvidenceRecord) => void
}) {
  const base =
    'inline-flex items-center px-2.5 py-1 rounded-md text-xs font-mono font-medium border transition-colors group'
  const tone = highlighted
    ? 'bg-amber-50 hover:bg-amber-100 text-amber-900 border-amber-300'
    : 'bg-slate-100 hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 border-slate-200 hover:border-indigo-200'

  return (
    <button className={`${base} ${tone}`} onClick={() => onSelect?.(record)}>
      <Link className={`w-3 h-3 mr-1.5 ${highlighted ? 'text-amber-600' : 'text-slate-400 group-hover:text-indigo-500'}`} />
      {record.table} #{record.record_id}
      {highlighted && <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-amber-500" />}
    </button>
  )
}

export function AnswerCard({
  answer,
  onSelectEvidence,
  onShowTrace,
  onDraftReply,
  onPropose,
}: {
  answer: AskResponse
  onSelectEvidence?: (r: EvidenceRecord) => void
  onShowTrace?: () => void
  onDraftReply?: () => void
  onPropose?: (a: AskResponse) => void
}) {
  // ---- Refusal -----------------------------------------------------------
  // Grey, quiet, and carries pointers rather than an answer. Refusal is a
  // supported outcome, not an error path.
  if (answer.refusal) {
    return (
      <div className="flex justify-start">
        <div className="max-w-xl w-full bg-slate-100/90 rounded-xl border border-slate-200 p-3.5 space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-200 text-slate-600">
              Insufficient data
            </span>
            <span
              className="text-[10px] text-slate-400 font-mono"
              title={
                'How sure the router was that it picked the right query shape. ' +
                'It is the model\u2019s own estimate of its own output, not a ' +
                'measure of whether the answer is right \u2014 what fired is ' +
                'decided by the rules engine. It gates nothing.'
              }
            >
              routing confidence {answer.confidence}
            </span>
          </div>

          <p className="text-xs text-slate-700 italic">“{answer.verdict}”</p>
          <p className="text-xs text-slate-600 leading-relaxed">{answer.explanation}</p>

          {answer.refusal.evidence_pointers.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {answer.refusal.evidence_pointers.map((r) => (
                <button
                  key={r.record_id}
                  onClick={() => onSelectEvidence?.(r)}
                  className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono bg-white text-slate-600 border border-slate-200 hover:border-slate-300"
                >
                  <Link className="w-2.5 h-2.5 mr-1 text-slate-400" />
                  {r.table} #{r.record_id}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  const v = answer.violation
  const isDegraded = !!answer.degraded

  return (
    <div className="flex justify-start">
      <div className="max-w-2xl w-full bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3.5">
        {/* 1. Verdict */}
        <div className="flex items-center space-x-2">
          <span className={`w-2 h-2 rounded-full shrink-0 ${isDegraded ? 'bg-slate-400' : 'bg-amber-500'}`} />
          <p className="text-sm font-medium text-slate-900">{answer.verdict}</p>
        </div>

        {/* Degraded banner — the gap is named, never treated as an empty result. */}
        {answer.degraded && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-2.5">
            <p className="text-[11px] font-semibold text-amber-900">
              Unavailable: {answer.degraded.unavailable.join(', ')}
            </p>
            <p className="text-[11px] text-amber-800 mt-0.5">{answer.degraded.note}</p>
          </div>
        )}

        {/* 2. Diagnosis strip — expected vs observed is the whole idea. */}
        {v && (
          <div className="grid grid-cols-3 gap-2 bg-slate-50 p-2.5 rounded-lg border border-slate-200/80">
            <div className="border-r border-slate-200 pr-2">
              <div className="text-[10px] font-medium text-slate-400 uppercase tracking-wider">Expected</div>
              <div className="tnum font-mono text-xs font-semibold text-slate-700 mt-0.5 truncate">
                {v.expected_state}
              </div>
            </div>
            <div className="border-r border-slate-200 pr-2">
              <div className="text-[10px] font-medium text-slate-400 uppercase tracking-wider">Observed</div>
              <div className="tnum font-mono text-xs font-semibold text-emerald-700 mt-0.5 truncate">
                {v.observed_state}
              </div>
            </div>
            <div>
              <div className="text-[10px] font-medium text-slate-400 uppercase tracking-wider">Stuck</div>
              <div className="tnum font-mono text-xs font-bold text-rose-600 mt-0.5">{v.stuck_for}</div>
            </div>
          </div>
        )}

        {/* 3. Rule chips — id + version, so any answer can be replayed. */}
        <div className="flex items-center flex-wrap gap-2">
          {answer.fired_rules.map((r) => (
            <span
              key={r.rule_id}
              title={Object.entries(r.triggering_fields)
                .map(([k, val]) => `${k} = ${val}`)
                .join('\n')}
              className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-mono font-medium bg-rose-50 text-rose-700 border border-rose-200 cursor-help"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 mr-1.5" />
              {r.rule_id} v{r.version}
            </span>
          ))}
          <span className="tnum inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-mono font-medium bg-slate-100 text-slate-600 border border-slate-200">
            routing confidence {answer.confidence}
          </span>
        </div>

        {/* 4. Explanation */}
        <div className="text-xs text-slate-600 leading-relaxed">{answer.explanation}</div>

        {/* 5. Cited evidence */}
        {answer.evidence.length > 0 && (
          <div className="pt-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Cited Evidence
            </div>
            <div className="flex flex-wrap gap-2">
              {answer.evidence.map((r) => (
                <EvidenceChip
                  key={`${r.table}-${r.record_id}`}
                  record={r}
                  highlighted={!!r.rule_id}
                  onSelect={onSelectEvidence}
                />
              ))}
            </div>
          </div>
        )}

        {/* Tier-2 auto-reply verdict — separate from the diagnosis itself. */}
        {answer.tier2 &&
          (answer.tier2.auto_reply ? (
            <p className="text-[11px] font-medium text-emerald-700">
              Auto-reply eligible — queued for review
            </p>
          ) : (
            answer.tier2.reasons.length > 0 && (
              <p className="text-[11px] text-slate-500">
                Not auto-replied: {answer.tier2.reasons.join(', ')}
              </p>
            )
          ))}

        {/* Draft reply — drafted, never sent. There is deliberately no send button. */}
        {answer.draft && (
          <div className="rounded-lg border-2 border-dashed border-indigo-300 bg-indigo-50/50 p-3 space-y-2">
            <div className="flex items-center justify-between flex-wrap gap-1.5">
              <div className="flex items-center gap-1.5">
                <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-indigo-100 text-indigo-700 border border-indigo-200">
                  {answer.draft.style}
                </span>
                <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-100 text-slate-600 border border-slate-200">
                  {answer.draft.source}
                </span>
              </div>
              <span className="text-[10px] font-semibold text-indigo-700 uppercase tracking-wider">
                Draft — not sent
              </span>
            </div>
            <div className="bg-white border border-slate-200 rounded-md p-2.5 text-xs text-slate-700 leading-relaxed whitespace-pre-wrap">
              {answer.draft.text}
            </div>
            <button
              onClick={() => {
                navigator.clipboard?.writeText(answer.draft!.text).catch(() => {})
              }}
              className="px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-white rounded-lg border border-slate-200 transition-colors"
            >
              Copy
            </button>
          </div>
        )}

        {/* Proposal — surfaced but never executed from here. */}
        {answer.proposal && (
          <div className="rounded-lg border border-amber-300 bg-amber-50/70 p-3 space-y-1.5">
            <p className="text-xs font-semibold text-amber-900">
              {answer.proposal.label} · {answer.proposal.motivating_rule}
            </p>
            {answer.proposal.bulk && (
              <p className="text-[11px] text-amber-900">
                Affects {answer.proposal.bulk.count} orders — e.g. {answer.proposal.bulk.sample.join(', ')}
              </p>
            )}
            {answer.proposal.approval_gate && (
              <p className="text-[11px] text-amber-800">
                {answer.proposal.approval_gate.reason} Routing to{' '}
                {answer.proposal.approval_gate.routes_to.name} ({answer.proposal.approval_gate.routes_to.role}).
              </p>
            )}
            <p className="tnum text-[10px] font-mono text-slate-500">
              idempotency key: {answer.proposal.idempotency_key.slice(0, 8)}…
            </p>
            <p className="text-[11px] font-medium text-slate-600">This action has not been executed.</p>
          </div>
        )}

        {/* Provenance — the exact field-level line, rendered verbatim. */}
        {answer.provenance && <ProvenanceDisclosure text={answer.provenance} />}

        {/* 6. Footer */}
        <div className="pt-2 border-t border-slate-100 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center space-x-2">
            <button
              onClick={onShowTrace}
              className="px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
            >
              Show trace
            </button>
            <button
              onClick={onDraftReply}
              className="px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
            >
              Draft reply
            </button>
          </div>

          {/* Only rendered when the rules engine actually produced an action —
              either as a suggestion on the violation, or as a full proposal. */}
          {(answer.proposal || v?.suggested_action) && (
            <button
              onClick={() => onPropose?.(answer)}
              className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-2xs transition-colors"
            >
              <ArrowSmallRight className="w-3.5 h-3.5 mr-1.5" />
              {answer.proposal
                ? `Review action: ${answer.proposal.label}`
                : `Propose action: ${ACTION_LABEL[v!.suggested_action] ?? v!.suggested_action}`}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/** Display labels for the rules engine's action enum. */
const ACTION_LABEL: Record<string, string> = {
  escalate_rto: 'Escalate to RTO',
  replay_webhook: 'Replay webhook',
  notify_customer_delay: 'Notify customer of delay',
  schedule_delivery: 'Schedule delivery',
  call_customer: 'Call customer',
  freeze_and_review: 'Freeze and review',
  route_to_sellside: 'Route to sell-side',
  cancel_later_order: 'Cancel later order',
  supervisor_exception: 'Request supervisor exception',
  reconcile: 'Reconcile ledger',
  refund: 'Issue refund',
}
