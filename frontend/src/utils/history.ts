/**
 * The earlier turns sent with a question, so the API can answer follow-ups ("Who killed him?").
 * Pure function: called by hooks/useChat.ts send().
 */

import type { Message, Turn } from '../types'

export const HISTORY_TURNS = 3 // the API uses the last 3 (anichat/domain/conversation.py MAX_TURNS)

/**
 * Question/answer pairs from the conversation, oldest first: each answer with the question
 * right above it. Errors and unanswered questions are skipped.
 * Called by: hooks/useChat.ts send()
 */
export function historyFrom(messages: Message[], turns = HISTORY_TURNS): Turn[] {
  const pairs: Turn[] = []
  messages.forEach((m, i) => {
    const before = messages[i - 1]
    if (m.role === 'assistant' && before?.role === 'user') pairs.push({ question: before.text, answer: m.text })
  })
  return pairs.slice(-turns)
}
