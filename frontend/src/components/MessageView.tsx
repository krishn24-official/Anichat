import { AlertCircle, RotateCw } from 'lucide-react'
import type { Message } from '../types'
import { AnswerText } from './AnswerText'
import { SourceList } from './SourceList'

interface Props {
  message: Message
  seriesTitle: (id: string | null) => string | null
  onRetry: (id: string) => void
}

/** One message: the user's question, an answer with sources, or an error with a retry. Called by: App.tsx */
export function MessageView({ message, seriesTitle, onRetry }: Props) {
  if (message.role === 'user') {
    const scope = seriesTitle(message.series)
    return (
      <div className="flex flex-col items-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-user px-4 py-2.5">{message.text}</div>
        {scope && <span className="mt-1 text-xs text-muted">in {scope}</span>}
      </div>
    )
  }
  if (message.role === 'error') {
    return (
      <div role="alert" className="flex items-start gap-3 rounded-2xl border border-accent/40 bg-accent-soft px-4 py-3 text-sm">
        <AlertCircle size={18} aria-hidden className="mt-0.5 shrink-0 text-accent" />
        <p className="flex-1">{message.text}</p>
        <button type="button" onClick={() => onRetry(message.id)} className="flex items-center gap-1 font-medium text-accent hover:underline">
          <RotateCw size={14} aria-hidden /> Retry
        </button>
      </div>
    )
  }
  return (
    <article className="rounded-2xl rounded-bl-md border border-line bg-panel px-4 py-3.5">
      <AnswerText text={message.text} sources={message.sources} answerId={message.id} />
      <SourceList sources={message.sources} answerId={message.id} />
      <p className="mt-2 text-[0.7rem] text-muted">
        {message.model ? `${message.model} · ` : ''}
        {message.seconds.toFixed(1)} s
      </p>
    </article>
  )
}

/** "Searching the wikis" dots while an answer is pending. Called by: App.tsx */
export function Thinking() {
  return (
    <div aria-live="polite" className="flex items-center gap-2 px-1 text-sm text-muted">
      <span className="flex gap-1" aria-hidden>
        <span className="dot h-1.5 w-1.5 rounded-full bg-muted" />
        <span className="dot h-1.5 w-1.5 rounded-full bg-muted" />
        <span className="dot h-1.5 w-1.5 rounded-full bg-muted" />
      </span>
      Searching the wikis…
    </div>
  )
}
