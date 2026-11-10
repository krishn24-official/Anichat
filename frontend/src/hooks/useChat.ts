/** Conversation state: messages, the pending request, persistence across reloads. */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, askStream } from '../services/api'
import type { Message } from '../types'
import { historyFrom } from '../utils/history'

type AssistantMessage = Extract<Message, { role: 'assistant' }>

const STORAGE_KEY = 'anichat.messages.v1'
const MAX_STORED = 100 // keep the last messages only

/** Messages saved in this browser, or [] (storage can be unavailable). Called by: useChat() */
function loadMessages(): Message[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const messages = raw ? (JSON.parse(raw) as Message[]) : []
    // An answer still being written when the page closed will never finish: mark it stopped.
    return messages.map((m) => (m.role === 'assistant' && m.streaming ? { ...m, streaming: false, stopped: true } : m))
  } catch {
    return []
  }
}

/** Save the latest messages; failures (private mode, quota) are ignored. Called by: useChat() */
function saveMessages(messages: Message[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_STORED)))
  } catch {
    /* not critical */
  }
}

/** A short unique id for React keys. Called by: useChat() send() */
const newId = () => crypto.randomUUID()

/**
 * The chat: messages, whether an answer is pending, and actions to send, retry, stop and clear.
 * Called by: App.tsx
 */
export function useChat() {
  const [messages, setMessages] = useState<Message[]>(loadMessages)
  const [pending, setPending] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const latest = useRef(messages) // the conversation so far, read by send() without re-creating it

  useEffect(() => {
    latest.current = messages
    saveMessages(messages)
  }, [messages])

  /** Ask a question and append the answer (or an error with a retry). Called by: Composer, EmptyState, retry() */
  const send = useCallback(async (question: string, series: string | null) => {
    const text = question.trim()
    if (text.length < 2 || controller.current) return
    const history = historyFrom(latest.current)
    setMessages((m) => [...m, { id: newId(), role: 'user', text, series }])
    setPending(true)
    controller.current = new AbortController()
    const started = performance.now()
    const answerId = newId()
    const seconds = () => (performance.now() - started) / 1000
    /** Change the answer being written (if it was added yet). Called by: the callbacks below */
    const updateAnswer = (change: (a: AssistantMessage) => Message | null) =>
      setMessages((m) => m.flatMap((x) => (x.id === answerId && x.role === 'assistant' ? (change(x) ?? []) : [x])))

    try {
      const reply = await askStream(text, series, history, (piece) => {
        setMessages((m) =>
          m.some((x) => x.id === answerId) // the first piece adds the answer, later ones extend it
            ? m.map((x) => (x.id === answerId && x.role === 'assistant' ? { ...x, text: x.text + piece } : x))
            : [...m, { id: answerId, role: 'assistant', text: piece, sources: [], model: null, seconds: 0, streaming: true }],
        )
      }, controller.current.signal)
      const done: AssistantMessage = { id: answerId, role: 'assistant', text: reply.answer, sources: reply.sources, model: reply.model, seconds: seconds() }
      // The finished answer replaces the streamed text (citations cleaned up, sources added).
      setMessages((m) => (m.some((x) => x.id === answerId) ? m.map((x) => (x.id === answerId ? done : x)) : [...m, done]))
    } catch (err) {
      if (!(err instanceof ApiError)) {
        // Stopped by the user: keep what was written so far.
        updateAnswer((a) => ({ ...a, streaming: false, stopped: true, seconds: seconds() }))
        return
      }
      updateAnswer(() => null) // a half-written answer is replaced by the error and its retry
      setMessages((m) => [...m, { id: newId(), role: 'error', text: err.message, question: text, series }])
    } finally {
      controller.current = null
      setPending(false)
    }
  }, [])

  /** Re-ask a failed question (the error and its question are replaced). Called by: MessageView */
  const retry = useCallback((errorId: string) => {
    const at = messages.findIndex((m) => m.id === errorId)
    const failed = messages[at]
    if (!failed || failed.role !== 'error') return
    const asked = messages[at - 1]?.role === 'user' ? at - 1 : at // the question shown above the error
    setMessages((m) => [...m.slice(0, asked), ...m.slice(at + 1)])
    void send(failed.question, failed.series)
  }, [messages, send])

  /** Cancel the pending answer. Called by: Composer stop button */
  const stop = useCallback(() => controller.current?.abort(), [])

  /** Start a new conversation. Called by: Header "New chat" */
  const clear = useCallback(() => {
    controller.current?.abort()
    setMessages([])
  }, [])

  return { messages, pending, send, retry, stop, clear }
}
