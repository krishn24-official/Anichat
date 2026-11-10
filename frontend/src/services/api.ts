/** HTTP calls to the AniChat API. The only module that knows its URLs. */

import { API_URL, REQUEST_TIMEOUT_MS } from '../config'
import type { ChatResponse, Series } from '../types'

/** An API call that failed, with a message that can be shown to the user. */
export class ApiError extends Error {}

/**
 * fetch() with a timeout and JSON parsing; turns network and HTTP failures into ApiError.
 * Called by: getSeries(), ask()
 */
async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
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
  return response.json() as Promise<T>
}

/** The series AniChat can answer about. Called by: hooks/useSeries.ts */
export function getSeries(): Promise<Series[]> {
  return request<Series[]>('/series')
}

/**
 * Ask one question, optionally limited to one series.
 * Called by: hooks/useChat.ts send()
 */
export function ask(question: string, series: string | null, signal?: AbortSignal): Promise<ChatResponse> {
  return request<ChatResponse>(
    '/chat',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, series }) },
    signal,
  )
}
