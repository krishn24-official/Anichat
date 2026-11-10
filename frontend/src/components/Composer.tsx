import { ArrowUp, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

interface Props {
  pending: boolean
  onSend: (question: string) => void
  onStop: () => void
}

const MAX_LENGTH = 500 // the API's limit

/**
 * The question box: Enter sends, Shift+Enter adds a line; grows with its text; a stop
 * button while an answer is pending.
 * Called by: App.tsx
 */
export function Composer({ pending, onSend, onStop }: Props) {
  const [text, setText] = useState('')
  const box = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = box.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [text])

  /** Send the typed question and empty the box. Called by: the form, Enter key */
  const submit = () => {
    if (pending || text.trim().length < 2) return
    onSend(text)
    setText('')
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
      className="flex items-end gap-2 rounded-2xl border border-line bg-panel p-2 focus-within:border-accent"
    >
      <label htmlFor="question" className="sr-only">Your question</label>
      <textarea
        id="question"
        ref={box}
        rows={1}
        value={text}
        maxLength={MAX_LENGTH}
        placeholder="Ask about a character, a fight, an episode…"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            submit()
          }
        }}
        className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-base outline-none placeholder:text-muted"
      />
      {pending ? (
        <button type="button" onClick={onStop} aria-label="Stop" className="rounded-xl bg-panel-2 p-2 text-text hover:bg-line">
          <Square size={18} aria-hidden />
        </button>
      ) : (
        <button type="submit" aria-label="Send" disabled={text.trim().length < 2} className="rounded-xl bg-accent p-2 text-white disabled:opacity-40">
          <ArrowUp size={18} aria-hidden />
        </button>
      )}
    </form>
  )
}
