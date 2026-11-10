import { Fragment } from 'react'
import type { Source } from '../types'
import { parseBlocks, parseInline } from '../utils/answer'

interface Props {
  text: string
  sources: Source[]
  answerId: string
}

/**
 * An answer with paragraphs, bullet lists, bold text and clickable citations: [2] links to
 * the cited page and points at its entry in the source list below.
 * Called by: components/MessageView.tsx
 */
export function AnswerText({ text, sources, answerId }: Props) {
  const sourceFor = (n: number) => sources.find((s) => s.numbers.includes(n))

  /** Render one block's inline pieces. Called by: AnswerText (per paragraph / list item) */
  const inline = (value: string) =>
    parseInline(value).map((piece, i) => {
      if (piece.kind === 'bold') return <strong key={i}>{piece.text}</strong>
      if (piece.kind === 'text') return <Fragment key={i}>{piece.text}</Fragment>
      return (
        <sup key={i} className="mx-0.5">
          {piece.numbers.map((n) => {
            const source = sourceFor(n)
            return source ? (
              <a
                key={n}
                href={source.url}
                target="_blank"
                rel="noreferrer"
                aria-describedby={`${answerId}-src-${source.numbers[0]}`}
                title={source.section ? `${source.title} › ${source.section}` : source.title}
                className="mx-px rounded bg-accent-soft px-1 text-[0.7rem] font-medium text-accent no-underline hover:underline"
              >
                {n}
              </a>
            ) : (
              <span key={n} className="mx-px text-[0.7rem] text-muted">{n}</span>
            )
          })}
        </sup>
      )
    })

  return (
    <div className="space-y-3 leading-relaxed">
      {parseBlocks(text).map((block, i) =>
        block.kind === 'list' ? (
          <ul key={i} className="list-disc space-y-1 pl-5">
            {block.items.map((item, j) => <li key={j}>{inline(item)}</li>)}
          </ul>
        ) : (
          <p key={i}>{inline(block.text)}</p>
        ),
      )}
    </div>
  )
}
