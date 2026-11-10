import { ExternalLink } from 'lucide-react'
import type { Source } from '../types'

interface Props {
  sources: Source[]
  answerId: string
}

/** The pages an answer cites, with their citation numbers. Called by: components/MessageView.tsx */
export function SourceList({ sources, answerId }: Props) {
  if (!sources.length) return null
  return (
    <div className="mt-4 border-t border-line pt-3">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Sources</p>
      <ul className="space-y-1.5">
        {sources.map((s) => (
          <li key={`${s.url}#${s.section}`} id={`${answerId}-src-${s.numbers[0]}`} className="flex gap-2 text-sm">
            <span className="shrink-0 text-xs tabular-nums text-accent">[{s.numbers.join('][')}]</span>
            <a href={s.url} target="_blank" rel="noreferrer" className="group min-w-0 hover:underline">
              <span className="font-medium">{s.title}</span>
              {s.section && <span className="text-muted"> › {s.section}</span>}
              <ExternalLink size={12} aria-hidden className="ml-1 inline align-baseline text-muted opacity-0 group-hover:opacity-100" />
            </a>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[0.7rem] text-muted">Wiki content: fandom.com, CC BY-SA 3.0</p>
    </div>
  )
}
