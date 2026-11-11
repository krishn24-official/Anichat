/**
 * Calls to the admin functions (frontend/api/*.ts). Same origin as the page, so they work on
 * Vercel whether or not the laptop (and the chat API) is on.
 */
import type { Field, MovieRecord } from '../../api/_records'
import type { Entry, EntryInput } from '../../api/_submission'

export type { Entry, EntryInput, Field, MovieRecord }

/** A movie in the list (api/records.ts GET without id). */
export interface RecordSummary {
  id: string
  title: string
  year: number | null
  version: number
  updated_at: string
  deleted: boolean
  cast: number
  values: number
  synced: boolean // the laptop has indexed this version
}

/** A TMDb search result (api/tmdb.ts). */
export interface TmdbHit {
  tmdb_id: number
  title: string
  year: number | null
  overview: string
}

/** Raised with the server's message ("wrong password", "missing title"...); `body` has extras (409: current). */
export class AdminError extends Error {
  status: number
  body: Record<string, unknown>
  constructor(message: string, status: number, body: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.body = body
  }
}

/** One authorised call; throws AdminError with the server's reason. Called by: the functions below */
async function call<T>(password: string, path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: { Authorization: `Bearer ${password}`, 'Content-Type': 'application/json', ...init.headers },
    })
  } catch {
    throw new AdminError('No connection. Nothing was lost: try again when online.', 0)
  }
  const body = (await res.json().catch(() => ({}))) as T & { error?: string }
  if (!res.ok) throw new AdminError(body.error ?? `HTTP ${res.status}`, res.status, body as Record<string, unknown>)
  return body
}

const put = (body: unknown): RequestInit => ({ method: 'PUT', body: JSON.stringify(body) })

/** Free entries (anime/series/other). Called by: EntriesTab */
export const listEntries = (pw: string) => call<{ entries: Entry[]; total: number }>(pw, '/api/submissions')
export const addEntry = async (pw: string, input: EntryInput) =>
  (await call<{ entry: Entry }>(pw, '/api/submissions', { method: 'POST', body: JSON.stringify(input) })).entry
export const deleteEntry = (pw: string, id: string) =>
  call(pw, `/api/submissions?id=${encodeURIComponent(id)}`, { method: 'DELETE' })

/** Fields. Called by: AdminPage (load), FieldsTab (save) */
export const listFields = async (pw: string) => (await call<{ fields: Field[] }>(pw, '/api/fields')).fields
export const saveFields = async (pw: string, fields: Partial<Field>[]) =>
  (await call<{ saved: Field[] }>(pw, '/api/fields', put({ fields }))).saved

/** Movie records. Called by: MoviesTab, MovieEditor */
export const listRecords = async (pw: string) => (await call<{ records: RecordSummary[] }>(pw, '/api/records')).records
export const getRecord = async (pw: string, id: string) =>
  (await call<{ record: MovieRecord }>(pw, `/api/records?id=${encodeURIComponent(id)}`)).record
export const getHistory = async (pw: string, id: string) =>
  (await call<{ history: MovieRecord[] }>(pw, `/api/records?id=${encodeURIComponent(id)}&history=1`)).history
export const saveRecord = async (pw: string, record: Partial<MovieRecord>, baseVersion: number) =>
  (await call<{ record: MovieRecord }>(pw, '/api/records', put({ record, base_version: baseVersion }))).record
export const deleteRecord = (pw: string, id: string) =>
  call(pw, `/api/records?id=${encodeURIComponent(id)}`, { method: 'DELETE' })

/** TMDb through the server. Called by: MoviesTab */
export const searchTmdb = async (pw: string, q: string, year: string) =>
  (await call<{ results: TmdbHit[] }>(pw, `/api/tmdb?${new URLSearchParams({ q, year })}`)).results
export const tmdbMovie = (pw: string, tmdbId: number) =>
  call<{ record: Partial<MovieRecord>; existing: string | null }>(pw, `/api/tmdb?id=${tmdbId}`)
