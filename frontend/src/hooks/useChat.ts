/** Conversation state: messages, the pending request, persistence across reloads. */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, ask } from '../services/api'
import type { Message } from '../types'

const STORAGE_KEY = 'anichat.messages.v1'
const MAX_STORED = 100 // keep the last messages only

/** Messages saved in this browser, or [] (storage can be unavailable). Called by: useChat() */
function loadMessages(): Message[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Message[]) : []
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

  useEffect(() => saveMessages(messages), [messages])

  /** Ask a question and append the answer (or an error with a retry). Called by: Composer, EmptyState, retry() */
  const send = useCallback(async (question: string, series: string | null) => {
    const text = question.trim()
    if (text.length < 2 || controller.current) return
    setMessages((m) => [...m, { id: newId(), role: 'user', text, series }])
    setPending(true)
    controller.current = new AbortController()
    const started = performance.now()
    try {
      const reply = await ask(text, series, controller.current.signal)
      const seconds = (performance.now() - started) / 1000
      setMessages((m) => [...m, { id: newId(), role: 'assistant', text: reply.answer, sources: reply.sources, model: reply.model, seconds }])
    } catch (err) {
      if (!(err instanceof ApiError)) return // stopped by the user
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
