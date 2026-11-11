/**
 * Validation of admin-form entries, shared by the Vercel function (api/submissions.ts) and its
 * tests. Mirrors anichat/domain/added.py parse_submission(), which checks them again on the laptop.
 * The leading "_" keeps Vercel from serving this file as an endpoint.
 */

export const TYPES = ['movie', 'anime', 'series', 'other'] as const
export type EntryType = (typeof TYPES)[number]
export const MAX_FACTS = 40
export const MAX_NOTES = 20_000

/** What the form sends. */
export interface EntryInput {
  type: string
  series?: string
  title: string
  year?: number | string | null
  use_tmdb?: boolean
  facts?: Record<string, string>
  notes?: string
  source?: string
}

/** What is stored: the input, cleaned, plus bookkeeping. */
export interface Entry {
  id: string
  type: EntryType
  series: string
  title: string
  year: number | null
  use_tmdb: boolean
  facts: Record<string, string>
  notes: string
  source: string
  submitted_at: string
  status: 'pending' | 'done' | 'error'
  result?: string
}

/** Trim, drop control characters, cut to `max`. Called by: validateEntry() */
function clean(value: unknown, max: number): string {
  // eslint-disable-next-line no-control-regex
  return String(value ?? '').replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '').trim().slice(0, max)
}

/**
 * A stored entry from the form's input, or an error message.
 * Called by: api/submissions.ts POST; tests
 */
export function validateEntry(input: EntryInput, id: string, now: Date): Entry | string {
  const type = clean(input.type, 20).toLowerCase()
  if (!(TYPES as readonly string[]).includes(type)) return `unknown type "${type}"`
  const title = clean(input.title, 200)
  if (!title) return 'missing title'
  const series = clean(input.series, 60).toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^_+|_+$/g, '')
    || (type === 'movie' ? 'movies' : '')
  if (!series) return 'missing series'
  const rawYear = input.year
  let year: number | null = null
  if (rawYear !== undefined && rawYear !== null && rawYear !== '') {
    year = Number(rawYear)
    if (!Number.isInteger(year) || year < 1870 || year > 2100) return `year "${rawYear}" is not a valid year`
  }
  const facts: Record<string, string> = {}
  for (const [k, v] of Object.entries(input.facts ?? {}).slice(0, MAX_FACTS)) {
    const key = clean(k, 60).toLowerCase()
    const value = clean(v, 2000)
    if (key && value) facts[key] = value
  }
  const notes = clean(input.notes, MAX_NOTES)
  const useTmdb = Boolean(input.use_tmdb) && type === 'movie'
  if (!Object.keys(facts).length && !notes && !useTmdb) return 'nothing to add: fill in a fact, notes or TMDb lookup'
  return {
    id, type: type as EntryType, series, title, year, use_tmdb: useTmdb, facts, notes,
    source: clean(input.source, 500), submitted_at: now.toISOString(), status: 'pending',
  }
}
