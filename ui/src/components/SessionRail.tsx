/**
 * The single place sessions are managed, in both ConsoleChat and
 * TicketWorkspace — "New chat", the thread list, and delete all live here so
 * the two screens' session UI cannot drift apart. Purely presentational: the
 * screens keep their own data fetching and pass it in as props.
 */
import { ConversationList } from './ConversationHistory'
import { ChevronLeft, History, Plus } from './Icon'
import type { ConversationSummary } from '@/types/api'

export function SessionRail({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  emptyMessage = 'Threads appear here once you ask something.',
  collapsed,
  onToggleCollapsed,
}: {
  conversations: ConversationSummary[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  emptyMessage?: string
  /** Omit entirely for screens where the rail is always full width
   *  (ConsoleChat). Set for screens tight on horizontal room
   *  (TicketWorkspace), which also pass onToggleCollapsed. */
  collapsed?: boolean
  onToggleCollapsed?: () => void
}) {
  if (collapsed) {
    return (
      <aside className="w-11 shrink-0 bg-white border-r border-slate-200 flex flex-col items-center py-3 gap-2">
        <button
          onClick={onToggleCollapsed}
          title="Show sessions"
          className="p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
        >
          <History className="w-4 h-4" />
        </button>
        <span className="tnum font-mono text-[10px] text-slate-400" title="Sessions for this ticket">
          {conversations.length}
        </span>
      </aside>
    )
  }

  return (
    <aside className="w-60 shrink-0 bg-white border-r border-slate-200 flex flex-col overflow-hidden">
      <div className="p-3 border-b border-slate-200 shrink-0 flex items-center gap-2">
        <button
          onClick={onNew}
          className="flex-1 flex items-center justify-center gap-1.5 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-3 py-2 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          New chat
        </button>
        {onToggleCollapsed && (
          <button
            onClick={onToggleCollapsed}
            title="Hide sessions"
            className="shrink-0 p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        <ConversationList
          conversations={conversations}
          activeId={activeId}
          onSelect={onSelect}
          onDelete={onDelete}
          emptyMessage={emptyMessage}
        />
      </div>
    </aside>
  )
}
