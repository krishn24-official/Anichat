import { describe, expect, it } from 'vitest'
import type { Message } from '../types'
import { historyFrom } from './history'

const user = (id: string, text: string): Message => ({ id, role: 'user', text, series: null })
const bot = (id: string, text: string): Message => ({ id, role: 'assistant', text, sources: [], model: 'm', seconds: 1 })

describe('historyFrom', () => {
  it('pairs answers with their questions, skips errors and keeps the last turns', () => {
    const messages: Message[] = [
      user('1', 'q1'), bot('2', 'a1'),
      user('3', 'q2'), { id: '4', role: 'error', text: 'busy', question: 'q2', series: null },
      user('5', 'q3'), bot('6', 'a3'),
      user('7', 'q4'), bot('8', 'a4'),
      user('9', 'q5'), bot('10', 'a5'),
    ]
    expect(historyFrom(messages)).toEqual([
      { question: 'q3', answer: 'a3' },
      { question: 'q4', answer: 'a4' },
      { question: 'q5', answer: 'a5' },
    ])
  })
})
