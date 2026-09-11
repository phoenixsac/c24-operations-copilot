/**
 * Shared rendering for a list of past threads — used by SessionRail, the
 * single place both ConsoleChat and TicketWorkspace manage sessions. Same
 * data shape, same click-to-load and delete behaviour, so the row markup
 * lives in one place.
 */
import { useEffect, useRef, useState } from 'react'
import { relativeTime } from '@/lib/relativeTime'
import { Trash } from './Icon'
import type { ConversationSummary } from '@/types/api'

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onDelete,
  emptyMessage,
}: {
  conversations: ConversationSummary[]
  activeId: string | null
  onSelect: (id: string) => void
  /** Omit to render the list without a delete affordance at all. */
  onDelete?: (id: string) => void
  emptyMessage: string
}) {
  // Inline two-step confirm lives here rather than as a window.confirm, so it
  // reads as part of the row instead of interrupting with a native dialog.
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const listRef = useRef<HTMLUListElement>(null)

  // Clicking anywhere outside the pending row, or pressing Escape, backs out
  // of the confirm without deleting — the same "changed my mind" path a
  // popover would give for free.
  useEffect(() => {
    if (!pendingDeleteId) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setPendingDeleteId(null)
    }
    function onClick(e: MouseEvent) {
      if (!listRef.current?.contains(e.target as Node)) setPendingDeleteId(null)
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('mousedown', onClick)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('mousedown', onClick)
    }
  }, [pendingDeleteId])

  if (conversations.length === 0) {
    return <p className="text-[11px] text-slate-400 leading-relaxed px-2 py-3">{emptyMessage}</p>
  }

  return (
    <ul className="space-y-0.5" ref={listRef}>
      {conversations.map((c) => {
        const active = c.id === activeId

        if (pendingDeleteId === c.id) {
          return (
            <li key={c.id}>
              <div className="px-2.5 py-2 rounded-lg border border-rose-200 bg-rose-50 space-y-1.5">
                <p className="text-[11px] text-rose-800">Delete this session?</p>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => {
                      setPendingDeleteId(null)
                      onDelete?.(c.id)
                    }}
                    className="text-[11px] font-medium text-white bg-rose-600 hover:bg-rose-700 rounded-md px-2 py-1 transition-colors"
                  >
                    Delete
                  </button>
                  <button
                    onClick={() => setPendingDeleteId(null)}
                    className="text-[11px] font-medium text-slate-500 hover:text-slate-800 rounded-md px-2 py-1 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </li>
          )
        }

        return (
          <li key={c.id}>
            <div
              className={`group relative rounded-lg transition-colors ${
                active ? 'bg-indigo-50 border border-indigo-200' : 'hover:bg-slate-100 border border-transparent'
              }`}
            >
              <button onClick={() => onSelect(c.id)} className={`w-full text-left px-2.5 py-2 ${onDelete ? 'pr-7' : ''}`}>
                <div className="flex items-center gap-1.5">
                  <span className={`text-xs truncate ${active ? 'text-indigo-800 font-medium' : 'text-slate-700'}`}>
                    {c.title || 'Untitled thread'}
                  </span>
                  {c.closed && (
                    <span className="shrink-0 text-[9px] font-semibold uppercase tracking-wider text-slate-400 bg-slate-100 border border-slate-200 rounded-full px-1.5 py-px">
                      closed
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {c.turn_count} {c.turn_count === 1 ? 'turn' : 'turns'} · {relativeTime(c.last_at)}
                </div>
              </button>
              {onDelete && (
                <button
                  onClick={(e) => {
                    // Must not also select the row underneath it.
                    e.stopPropagation()
                    setPendingDeleteId(c.id)
                  }}
                  title="Delete session"
                  className={`absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded-md text-slate-400 hover:text-rose-700 hover:bg-rose-100 transition-colors ${
                    // Always reachable on the active row (keyboard/touch), not just on hover.
                    active ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus:opacity-100'
                  }`}
                >
                  <Trash className="w-3 h-3" />
                </button>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
