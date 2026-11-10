import { describe, expect, it } from 'vitest'
import { parseEvents } from './api'

describe('parseEvents', () => {
  it('parses complete events and keeps an unfinished one for the next read', () => {
    const received = 'data: {"type":"delta","text":"Rad"}\n\ndata: {"type":"delta","text":"itz"}\n\ndata: {"type":"do'
    const { events, rest } = parseEvents(received)
    expect(events).toEqual([{ type: 'delta', text: 'Rad' }, { type: 'delta', text: 'itz' }])
    expect(rest).toBe('data: {"type":"do')
    const next = parseEvents(rest + 'ne","answer":"Raditz","sources":[],"model":"groq","timings":{}}\n\n')
    expect(next.events[0]).toMatchObject({ type: 'done', answer: 'Raditz' })
    expect(next.rest).toBe('')
  })

  it('accepts CRLF line endings', () => {
    expect(parseEvents('data: {"type":"delta","text":"a"}\r\n\r\n').events).toEqual([{ type: 'delta', text: 'a' }])
  })
})
