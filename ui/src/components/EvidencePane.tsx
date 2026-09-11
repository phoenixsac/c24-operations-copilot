import { useState } from 'react'
import type { AskResponse, EvidenceRecord, RecordsGraph } from '@/types/api'

export type PaneTab = 'evidence' | 'records' | 'trace'

const TONE = {
  ok: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  warn: 'text-amber-800 bg-amber-50 border-amber-200',
  bad: 'text-rose-700 bg-rose-50 border-rose-200',
  neutral: 'text-slate-500 bg-slate-50 border-slate-200',
}

/** One cited record. The triggering field is highlighted, not just listed. */
function RecordCard({ record, focused }: { record: EvidenceRecord; focused?: boolean }) {
  const triggered = record.fields.some((f) => f.triggered)

  return (
    <div
      className={`rounded-lg p-3 shadow-2xs relative transition-all ${
        triggered
          ? 'border-2 border-amber-400 bg-amber-50/40'
          : 'border border-slate-200 bg-slate-50/60 hover:border-slate-300'
      } ${focused ? 'ring-2 ring-indigo-500 ring-offset-1' : ''}`}
    >
      {triggered && (
        <div className="absolute -top-2 right-2 px-1.5 py-px bg-amber-500 text-white rounded text-[9px] font-bold tracking-wider uppercase shadow-2xs">
          Trigger Field
        </div>
      )}

      <div className={`flex items-center justify-between pb-2 border-b ${triggered ? 'border-amber-200/60' : 'border-slate-200/60'}`}>
        <div className="flex items-center space-x-1.5">
          <span className="font-mono text-[11px] font-bold text-slate-800">{record.table}</span>
          <span className={`tnum text-[10px] font-mono ${triggered ? 'text-amber-800 font-semibold' : 'text-slate-400'}`}>
            #{record.record_id}
          </span>
        </div>
        {record.status && (
          <span className={`text-[10px] font-mono font-medium border px-1.5 py-px rounded ${TONE[record.status.tone]}`}>
            {record.status.label}
          </span>
        )}
      </div>

      <div className="mt-2 space-y-1.5 font-mono text-[11px]">
        {record.fields.map((f) =>
          f.triggered ? (
            <div
              key={f.label}
              className="bg-amber-100/90 border border-amber-300 rounded p-1.5 flex justify-between items-baseline gap-2"
            >
              <span className="text-amber-900 font-semibold text-[10px]">{f.label}</span>
              <span className="text-amber-950 font-bold bg-amber-200/80 px-1 rounded text-right">"{f.value}"</span>
            </div>
          ) : (
            <div key={f.label} className="flex justify-between items-baseline gap-2">
              <span className="text-slate-400 text-[10px] shrink-0">{f.label}</span>
              <span className="tnum text-slate-800 font-medium text-right truncate">{f.value}</span>
            </div>
          ),
        )}
      </div>

      {record.rule_id && (
        <div className="mt-2 pt-2 border-t border-amber-200/60">
          <span className="text-[10px] font-mono text-amber-800">fired: {record.rule_id}</span>
        </div>
      )}
    </div>
  )
}

export function EvidencePane({
  answer,
  records,
  tab,
  onTabChange,
  focusedRecord,
  onExpandRecords,
}: {
  answer: AskResponse | null
  records: RecordsGraph | null
  tab: PaneTab
  onTabChange: (t: PaneTab) => void
  focusedRecord?: string | null
  onExpandRecords?: () => void
}) {
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null)

  const cited = answer?.evidence ?? answer?.refusal?.evidence_pointers ?? []
  const activeNode =
    records?.nodes.find((n) => n.entity === selectedEntity) ??
    records?.nodes.find((n) => n.rule_fired) ??
    records?.nodes[0]

  return (
    <aside className="w-[340px] shrink-0 bg-white flex flex-col h-full overflow-hidden">
      <div className="p-3 border-b border-slate-200 shrink-0">
        <div className="bg-slate-100 p-0.5 rounded-lg grid grid-cols-3 gap-0.5 text-xs font-medium">
          {(['evidence', 'records', 'trace'] as PaneTab[]).map((t) => (
            <button
              key={t}
              onClick={() => onTabChange(t)}
              className={`py-1.5 text-center rounded-md capitalize transition-colors ${
                tab === t
                  ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
        {tab === 'evidence' && (
          <>
            <div className="flex items-center justify-between px-0.5">
              <span className="text-[10px] font-bold tracking-wider uppercase text-slate-400">
                Cited in current turn ({cited.length})
              </span>
            </div>

            {cited.length === 0 && (
              <p className="text-[11px] text-slate-400 px-0.5">
                No records cited. Ask a question to populate this pane.
              </p>
            )}

            {cited.map((r) => (
              <RecordCard
                key={`${r.table}-${r.record_id}`}
                record={r}
                focused={focusedRecord === `${r.table}-${r.record_id}`}
              />
            ))}
          </>
        )}

        {/* Records — the fallback path. Works when the provider is down. F4. */}
        {tab === 'records' && records && (
          <>
            <div className="flex flex-wrap gap-1.5">
              {records.nodes.map((n) => (
                <button
                  key={n.entity}
                  disabled={n.count === 0}
                  onClick={() => setSelectedEntity(n.entity)}
                  className={`inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono border transition-colors ${
                    n.count === 0
                      ? 'text-slate-300 border-slate-100 cursor-not-allowed'
                      : activeNode?.entity === n.entity
                        ? 'bg-slate-900 text-white border-slate-900'
                        : 'text-slate-600 border-slate-200 hover:border-slate-400'
                  }`}
                >
                  {n.label} ({n.count})
                  {n.rule_fired && <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />}
                </button>
              ))}
            </div>

            {activeNode?.records.map((rec) => (
              <RecordCard
                key={rec.id}
                record={{
                  table: activeNode.entity,
                  record_id: rec.id,
                  fields: rec.fields,
                  rule_id: rec.fields.find((f) => f.rule_id)?.rule_id,
                }}
              />
            ))}

            <div className="pt-2">
              <div className="text-[10px] font-bold tracking-wider uppercase text-slate-400 mb-2">
                Order state timeline
              </div>
              <ol className="space-y-1">
                {records.timeline.map((s) => (
                  <li key={s.state} className="flex items-center gap-2 text-[11px] font-mono">
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${
                        s.status === 'done'
                          ? 'bg-emerald-500'
                          : s.status === 'current'
                            ? 'bg-indigo-600'
                            : s.status === 'blocked'
                              ? 'bg-rose-500'
                              : 'bg-slate-200'
                      }`}
                    />
                    <span className={s.status === 'pending' ? 'text-slate-300' : 'text-slate-700'}>{s.state}</span>
                    {s.at && <span className="tnum text-slate-400 ml-auto">{s.at}</span>}
                  </li>
                ))}
              </ol>
              <p className="text-[11px] text-slate-500 mt-2">{records.timeline_caption}</p>
            </div>
          </>
        )}

        {tab === 'trace' && answer && (
          <div className="space-y-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 font-mono text-[11px] space-y-1.5">
              <Row label="answer_id" value={answer.answer_id} />
              <Row label="model" value={answer.trace.model} />
              <Row label="prompt_version" value={answer.trace.prompt_version} />
              <Row label="latency" value={`${answer.trace.latency_ms} ms`} />
              <Row
                label="tokens"
                value={`${answer.trace.tokens.prompt} in / ${answer.trace.tokens.completion} out`}
              />
              <Row label="shape" value={answer.ir.shape} />
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
              <div className="text-[10px] font-bold tracking-wider uppercase text-slate-400 mb-2">
                Per-stage breakdown
              </div>
              {answer.trace.stages.map((s) => (
                <div key={s.name} className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-[10px] text-slate-500 w-20 shrink-0">{s.name}</span>
                  <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 rounded-full"
                      style={{ width: `${(s.ms / answer.trace.latency_ms) * 100}%` }}
                    />
                  </div>
                  <span className="tnum font-mono text-[10px] text-slate-600 w-12 text-right">{s.ms}ms</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="p-3 border-t border-slate-200 bg-slate-50/80 shrink-0">
        <p className="text-[11px] text-slate-500 leading-normal">
          {tab === 'evidence' ? (
            <>
              Showing {cited.length} cited records. Switch to{' '}
              <button onClick={() => onTabChange('records')} className="font-medium text-slate-700 underline">
                Records
              </button>{' '}
              for all data linked to this ticket.
            </>
          ) : tab === 'records' ? (
            <>
              Read only, works when the copilot is unavailable.{' '}
              <button onClick={onExpandRecords} className="font-medium text-slate-700 underline">
                Expand
              </button>
            </>
          ) : (
            <>Every LLM call is traced with prompt version, model, tokens and latency.</>
          )}
        </p>
      </div>
    </aside>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-baseline gap-2">
      <span className="text-slate-400 text-[10px] shrink-0">{label}</span>
      <span className="tnum text-slate-800 font-medium truncate text-right">{value}</span>
    </div>
  )
}
