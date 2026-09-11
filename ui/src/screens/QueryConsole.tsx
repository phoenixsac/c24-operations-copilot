/**
 * Screen 5 — Query console. Supervisor only.
 *
 * NOTE ON SCOPE: docs/SCOPE.md §3 lists this screen as *skip* — the Records
 * view is the real fallback and this is a supervisor convenience. It is built
 * here because the screen was generated; if the 5-day budget tightens, this is
 * the first thing to drop and the decision is already written down.
 *
 * Four corrections against the generated design, all of them load-bearing:
 *
 *  1. The banner said `tenant_id = 'mum-01'`. There is no tenant — Cars24 is
 *     B2C and the isolation axis is operational (docs/DOMAIN_v2.md §5). The
 *     scoping keys are city_code and region.
 *  2. The generated screen showed an L1 agent in the sidebar while the header
 *     showed a supervisor. An l1_agent must not reach this screen at all
 *     (docs/INVARIANTS.md E7), so the whole screen refuses below that role.
 *  3. The results footer read "8 rows returned (filtered from 4,120 total
 *     records)". That leaks the cardinality of the out-of-scope set. The
 *     connection cannot see those rows, so it cannot count them either.
 *  4. "cryptographically logged" was an overclaim. Queries are logged.
 */
import { useEffect, useState } from 'react'
import { ArrowSmallRight, ChevronDown, ChevronRight, Lock, Search, Shield } from '@/components/Icon'
import { Sidebar, type Dest } from '@/components/Sidebar'
import { getConsoleSchema, getSavedQueries, runQuery } from '@/api/client'
import type { ConsoleTable, QueryResult, Session } from '@/types/api'

export function QueryConsole({
  session,
  onBack,
  onNavigate,
  onOpenTicket,
}: {
  session: Session | null
  onBack: () => void
  onNavigate: (d: Dest) => void
  onOpenTicket: (id: string) => void
}) {
  const [schema, setSchema] = useState<ConsoleTable[]>([])
  const [open, setOpen] = useState<string | null>('rc_cases')
  const [saved, setSaved] = useState<Array<{ name: string; sql: string }>>([])
  const [sql, setSql] = useState('')
  const [result, setResult] = useState<QueryResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [tableFilter, setTableFilter] = useState('')

  useEffect(() => {
    getConsoleSchema().then(setSchema).catch(() => setSchema([]))
    getSavedQueries()
      .then((q) => {
        setSaved(q)
        setSql((cur) => cur || q[0]?.sql || '')
      })
      .catch(() => setSaved([]))
  }, [])

  // E7 — free-form SQL is available only to roles that could already see the
  // same rows. The gate is here as well as in the API; neither is sufficient
  // alone, and the database is the one that actually enforces it.
  if (session && session.role !== 'supervisor') {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-center px-6">
        <Lock className="w-6 h-6 text-slate-400" />
        <p className="text-sm font-semibold text-slate-800">Supervisor access required</p>
        <p className="text-xs text-slate-500 max-w-sm">
          The query console is restricted to roles that can already read the rows it returns. Your session is{' '}
          <span className="font-mono">{session.role}</span>, scoped to{' '}
          <span className="font-mono">{session.city_code}</span>.
        </p>
        <button
          onClick={onBack}
          className="mt-2 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 border border-slate-200 hover:bg-white"
        >
          Back to queue
        </button>
      </div>
    )
  }

  const needle = tableFilter.trim().toLowerCase()
  const visible = needle
    ? schema.filter(
        (t) => t.name.includes(needle) || t.columns.some((c) => c.name.includes(needle)),
      )
    : schema

  async function run() {
    setBusy(true)
    try {
      setResult(await runQuery(sql))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full w-full bg-slate-50 flex overflow-hidden">
      <Sidebar active="console" session={session} onNavigate={onNavigate} />
      <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-14 bg-white border-b border-slate-200 px-5 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-slate-400 hover:text-slate-700 text-xs font-medium"
          >
            ← Back
          </button>
          <h1 className="text-base font-semibold text-slate-900">Query Console</h1>
          <span className="px-2 py-0.5 rounded bg-indigo-600 text-white text-[10px] font-bold uppercase tracking-wider">
            Supervisor
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 font-mono text-[11px] px-2 py-1 rounded bg-amber-50 text-amber-800 border border-amber-200">
            <Lock className="w-3 h-3" />
            Read only · 500 row limit · 5s timeout
          </span>
          {session && (
            <span className="text-xs text-slate-600">
              {session.name} · {session.region}
            </span>
          )}
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Schema browser */}
        <aside className="w-[200px] shrink-0 bg-white border-r border-slate-200 flex flex-col overflow-hidden">
          <div className="p-2 border-b border-slate-200">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={tableFilter}
                onChange={(e) => setTableFilter(e.target.value)}
                placeholder="Search tables, columns…"
                className="w-full h-7 pl-7 pr-2 bg-slate-50 border border-slate-200 rounded text-[11px] focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-1">
            {visible.map((t) => (
              <div key={t.name}>
                <button
                  onClick={() => setOpen(open === t.name ? null : t.name)}
                  className="w-full flex items-center justify-between px-2 py-1 rounded hover:bg-slate-50 text-left"
                >
                  <span className="flex items-center gap-1 min-w-0">
                    {open === t.name ? (
                      <ChevronDown className="w-3 h-3 text-slate-400 shrink-0" />
                    ) : (
                      <ChevronRight className="w-3 h-3 text-slate-400 shrink-0" />
                    )}
                    <span className="font-mono text-[11px] text-slate-700 truncate">{t.name}</span>
                  </span>
                  <span className="tnum text-[10px] text-slate-400 shrink-0">{t.columns.length}</span>
                </button>
                {open === t.name && (
                  <div className="pl-6 pb-1">
                    {t.columns.map((c) => (
                      <div key={c.name} className="flex items-center justify-between gap-2 py-0.5">
                        <span
                          className={`font-mono text-[11px] truncate ${
                            // city_code and region are the scoping keys — worth
                            // making visible in the browser.
                            c.name === 'city_code' || c.name === 'region'
                              ? 'text-indigo-600 font-semibold'
                              : 'text-slate-600'
                          }`}
                        >
                          {c.pk && <span className="text-slate-400 mr-1">🔑</span>}
                          {c.name}
                        </span>
                        <span className="font-mono text-[10px] text-slate-400 shrink-0">{c.type}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="p-2 border-t border-slate-200 flex items-center justify-between text-[10px] text-slate-400">
            <span>PostgreSQL 16</span>
            <span className="text-emerald-600">Connected</span>
          </div>
        </aside>

        {/* Editor + results */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="bg-slate-100 border-b border-slate-200 px-4 py-1.5 flex items-center justify-between">
            {/* Corrected banner: city_code / region, not tenant_id. */}
            <code className="text-[11px] font-mono text-slate-600">
              -- city_code / region scoping is applied by the database to every query
            </code>
            <span className="text-[10px] font-mono text-slate-500">
              {session ? `${session.role} · ${session.region}` : ''}
            </span>
          </div>

          <textarea
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            spellCheck={false}
            className="h-56 shrink-0 w-full p-4 font-mono text-xs leading-relaxed text-slate-800 bg-white resize-none focus:outline-none"
          />

          <div className="px-4 py-2 bg-white border-y border-slate-200 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <button
                onClick={run}
                disabled={busy}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-xs font-semibold rounded-lg transition-colors"
              >
                <ArrowSmallRight className="w-3.5 h-3.5" />
                {busy ? 'Running…' : 'Run query'}
              </button>
              <select
                onChange={(e) => {
                  const q = saved.find((x) => x.name === e.target.value)
                  if (q) setSql(q.sql)
                }}
                className="bg-white border border-slate-200 text-slate-700 text-[11px] px-2 py-1.5 rounded focus:outline-none"
              >
                {saved.map((q) => (
                  <option key={q.name}>{q.name}</option>
                ))}
              </select>
            </div>
            {result && (
              <span className="tnum font-mono text-[11px] text-slate-500">
                {result.row_count} rows · {result.ms}ms
                {result.truncated && <span className="text-amber-700"> · truncated at 500</span>}
              </span>
            )}
          </div>

          <div className="flex-1 overflow-auto bg-white">
            {!result && (
              <p className="p-4 text-xs text-slate-400">Run a query to see results.</p>
            )}
            {result && (
              <table className="w-full text-left border-collapse">
                <thead className="sticky top-0">
                  <tr className="h-8 bg-slate-50 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    {result.columns.map((c) => (
                      <th key={c} className="px-3 font-medium whitespace-nowrap">
                        {c}
                      </th>
                    ))}
                    <th className="px-3 font-medium text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-[11px]">
                  {result.rows.map((r, i) => (
                    <tr key={i} className={i % 2 ? 'bg-slate-50/50' : 'bg-white'}>
                      {result.columns.map((c) => (
                        <td key={c} className="tnum px-3 h-8 whitespace-nowrap text-slate-700">
                          {String(r[c] ?? '')}
                        </td>
                      ))}
                      <td className="px-3 h-8 text-right">
                        {r.ticket_id ? (
                          <button
                            onClick={() => onOpenTicket(String(r.ticket_id))}
                            className="text-indigo-600 hover:underline text-[11px]"
                          >
                            Open ticket →
                          </button>
                        ) : (
                          <span className="text-[11px] text-slate-300">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      <footer className="px-4 py-2 bg-slate-100 border-t border-slate-200 flex items-center gap-2 shrink-0">
        <Shield className="w-3.5 h-3.5 text-slate-400" />
        <span className="text-[11px] text-slate-500">
          Every query is logged to the audit trail.
          {result && <span className="font-mono"> Session {result.audit_id}.</span>}
        </span>
      </footer>
      </div>
    </div>
  )
}
