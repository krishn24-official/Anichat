import { MessageSquarePlus, Settings } from 'lucide-react'
import type { Series } from '../types'
import { SeriesPicker } from './SeriesPicker'

interface Props {
  series: Series[]
  selected: string | null
  onSelect: (id: string | null) => void
  onNewChat: () => void
  canClear: boolean
}

/** Top bar: name, series picker, "New chat", the link to the admin form. Called by: App.tsx */
export function Header({ series, selected, onSelect, onNewChat, canClear }: Props) {
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-bg/85 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
        <div className="flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <h1 className="text-lg font-semibold tracking-tight">AniChat</h1>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <SeriesPicker series={series} value={selected} onChange={onSelect} />
          <button
            type="button"
            onClick={onNewChat}
            disabled={!canClear}
            title="New chat"
            className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-sm text-muted hover:text-text disabled:opacity-40"
          >
            <MessageSquarePlus size={16} aria-hidden />
            <span className="hidden sm:inline">New chat</span>
          </button>
          {/* The admin form (password-protected): add and edit movies, fields, facts. */}
          <a
            href="/admin"
            title="Admin: add and edit knowledge"
            className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-sm text-muted hover:text-text"
          >
            <Settings size={16} aria-hidden />
            <span className="hidden sm:inline">Admin</span>
          </a>
        </div>
      </div>
    </header>
  )
}
