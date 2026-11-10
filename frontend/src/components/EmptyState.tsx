import { Sparkles } from 'lucide-react'
import { examplesFor } from '../utils/examples'

interface Props {
  franchise: string | null
  seriesCount: number
  onAsk: (question: string) => void
}

/** Welcome screen with example questions for the chosen series. Called by: App.tsx */
export function EmptyState({ franchise, seriesCount, onAsk }: Props) {
  return (
    <div className="flex flex-col items-center px-4 pt-16 text-center sm:pt-24">
      <div className="mb-4 rounded-2xl bg-accent-soft p-3 text-accent">
        <Sparkles size={28} aria-hidden />
      </div>
      <h2 className="text-2xl font-semibold tracking-tight">Ask anything about anime</h2>
      <p className="mt-2 max-w-md text-sm text-muted">
        Answers come from fan-wiki knowledge{seriesCount ? ` of ${seriesCount} series` : ''}, with the sources
        cited. Pick a series above to focus the search.
      </p>
      <div className="mt-8 grid w-full max-w-xl gap-2 sm:grid-cols-2">
        {examplesFor(franchise).map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onAsk(q)}
            className="rounded-xl border border-line bg-panel px-4 py-3 text-left text-sm hover:border-accent"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
