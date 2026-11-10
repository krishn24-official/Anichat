/** HTTP calls to the AniChat API. The only module that knows its URLs. */

import { API_URL, REQUEST_TIMEOUT_MS } from '../config'
import type { ChatResponse, Series, StreamEvent, Turn } from '../types'

/** An API call that failed, with a message that can be shown to the user. */
export class ApiError extends Error {}

/**
 * fetch() with a timeout; turns network and HTTP failures into ApiError. The timeout also
 * covers reading the body, so a stalled stream ends too.
 * Called by: request(), askStream()
 */
async function open(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<Response> {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS)
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, signal: combined })
  } catch (err) {
    if (signal?.aborted) throw err // cancelled by the user: not an error to show
    if (timeout.aborted) throw new ApiError('The answer took too long. Please try again.')
    throw new ApiError('Cannot reach AniChat. Is the API running?')
  }
  if (!response.ok) {
    const detail = await response.json().then((b) => b?.detail).catch(() => null)
    throw new ApiError(typeof detail === 'string' ? detail : `Request failed (${response.status}).`)
  }
  return response
}

/** GET a JSON resource. Called by: getSeries() */
async function request<T>(path: string): Promise<T> {
  return (await open(path)).json() as Promise<T>
}

/** The series AniChat can answer about. Called by: hooks/useSeries.ts */
export function getSeries(): Promise<Series[]> {
  return request<Series[]>('/series')
}

/**
 * Split server-sent events out of the text received so far: complete events are parsed,
 * the unfinished rest is returned to be completed by the next read.
 * Called by: askStream(); tested by services/api.test.ts
 */
export function parseEvents(buffer: string): { events: StreamEvent[]; rest: string } {
  const parts = buffer.replace(/\r\n/g, '\n').split('\n\n')
  const rest = parts.pop() ?? ''
  const events: StreamEvent[] = []
  for (const part of parts) {
    const data = part.split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trimStart()).join('\n')
    if (data) events.push(JSON.parse(data) as StreamEvent)
  }
  return { events, rest }
}

/**
 * Ask one question (optionally within one series) and receive the answer while it is written:
 * `onText` gets each new piece, the promise resolves with the finished answer and its sources.
 * `history` (earlier turns) lets the API understand follow-ups like "Who killed him?".
 * Called by: hooks/useChat.ts send()
 */
export async function askStream(
  question: string,
  series: string | null,
  history: Turn[],
  onText: (piece: string) => void,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await open(
    '/chat/stream',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, series, history }) },
    signal,
  )
  if (!response.body) throw new ApiError('This browser cannot read streamed answers.')
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      const parsed = parseEvents(buffer + value)
      buffer = parsed.rest
      for (const event of parsed.events) {
        if (event.type === 'delta') onText(event.text)
        else return event
      }
    }
  } catch (err) {
    if (signal?.aborted) throw err
    throw new ApiError('The connection dropped while answering. Please try again.')
  }
  throw new ApiError('The answer ended unexpectedly. Please try again.')
}
