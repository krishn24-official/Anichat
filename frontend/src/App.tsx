import { useEffect, useRef, useState } from 'react'
import { Composer } from './components/Composer'
import { EmptyState } from './components/EmptyState'
import { Header } from './components/Header'
import { MessageView, Thinking } from './components/MessageView'
import { useChat } from './hooks/useChat'
import { useSeries } from './hooks/useSeries'

/**
 * The AniChat page: header with the series picker, the conversation, the question box.
 * Called by: main.tsx
 */
export default function App() {
  const { series, error: seriesError } = useSeries()
  const { messages, pending, send, retry, stop, clear } = useChat()
  const [selected, setSelected] = useState<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, pending])

  const franchise = series.find((s) => s.id === selected)?.franchise ?? null
  /** "Naruto Shippuden" for an id, null for "all series". Called by: MessageView */
  const seriesTitle = (id: string | null) => (id ? series.find((s) => s.id === id)?.title ?? id : null)
  /** Ask within the selected series. Called by: Composer, EmptyState */
  const ask = (question: string) => void send(question, selected)

  return (
    <div className="flex h-full flex-col">
      <Header series={series} selected={selected} onSelect={setSelected} onNewChat={clear} canClear={messages.length > 0} />

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 pb-6">
          {seriesError && (
            <p role="alert" className="mt-4 rounded-xl border border-line bg-panel px-4 py-3 text-sm text-muted">
              {seriesError}
            </p>
          )}
          {messages.length === 0 ? (
            <EmptyState franchise={franchise} seriesCount={series.length} onAsk={ask} />
          ) : (
            <div className="space-y-5 pt-6">
              {messages.map((m) => <MessageView key={m.id} message={m} seriesTitle={seriesTitle} onRetry={retry} />)}
              {/* Until the first words of the answer arrive. */}
              {pending && messages.at(-1)?.role === 'user' && <Thinking />}
            </div>
          )}
          <div ref={bottom} />
        </div>
      </main>

      <footer className="border-t border-line bg-bg">
        <div className="mx-auto max-w-3xl px-4 py-3">
          <Composer pending={pending} onSend={ask} onStop={stop} />
          <p className="mt-2 text-center text-[0.7rem] text-muted">
            AniChat answers only from fan-wiki pages and can still be wrong. Check the sources.
          </p>
        </div>
      </footer>
    </div>
  )
}
