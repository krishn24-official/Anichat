/**
 * Fields and movie records: the shapes, their validation, the suggested fields and the
 * conversion of TMDb's movie details into a record. Pure (no I/O): used by the functions
 * (api/fields.ts, api/records.ts, api/tmdb.ts), by the admin form, and by tests.
 * anichat/domain/records.py reads the same shapes on the laptop.
 */

// ---------------------------------------------------------------- fields

export const FIELD_TYPES = ['text', 'number', 'money', 'date', 'list', 'daywise', 'url'] as const
export type FieldType = (typeof FIELD_TYPES)[number]
export const CURRENCIES = ['INR', 'USD'] as const
export const UNITS = ['', 'crore', 'lakh', 'million', 'billion'] as const
export const APPLIES_TO = ['movie', 'anime', 'series', 'other'] as const

/** One field, defined once and used by every record: the id never changes, the label may. */
export interface Field {
  id: string // "india_net": from the first label, fixed afterwards
  label: string // "India net collection"
  type: FieldType
  group: string // "Box office", "Streaming"...: sections of the form
  applies_to: string[] // which kinds of entries show it
  currency?: (typeof CURRENCIES)[number] // money
  unit?: (typeof UNITS)[number] // money / number: "crore" -> values are typed in crore
  help?: string // shown under the input
  order: number
  archived?: boolean // hidden from the form; values already saved are kept
  sum_into?: string // day-wise fields: the money field their rows add up to (kept up to date by the editor)
}

/** "India Net Collection!" -> "india_net_collection". Called by: validateField(), tests */
export function slug(text: string): string {
  return text.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '').slice(0, 50)
}

/** Trim, drop control characters, cut to `max`. Called by: the validators below */
export function clean(value: unknown, max: number): string {
  // eslint-disable-next-line no-control-regex
  return String(value ?? '').replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '').trim().slice(0, max)
}

/**
 * A field from the form, or an error message. A new field gets its id from its label; an
 * existing one (same id) keeps its id and type, so saved values stay valid.
 * Called by: api/fields.ts PUT; tests
 */
export function validateField(input: Partial<Field>, existing: Field[]): Field | string {
  const label = clean(input.label, 60)
  if (!label) return 'a field needs a name'
  const before = input.id ? existing.find((f) => f.id === input.id) : undefined
  if (input.id && !before) return `no field "${input.id}"`
  const id = before ? before.id : slug(label)
  if (!id) return 'the name needs letters or digits'
  if (!before && existing.some((f) => f.id === id)) return `a field "${id}" already exists: edit it instead`
  const sameLabel = existing.find((f) => f.id !== id && !f.archived && f.label.toLowerCase() === label.toLowerCase())
  if (sameLabel) return `"${label}" is already the name of field "${sameLabel.id}"`
  const type = (before?.type ?? input.type) as FieldType
  if (!FIELD_TYPES.includes(type)) return `unknown type "${String(input.type)}"`
  const appliesTo = (input.applies_to ?? ['movie']).filter((a) => (APPLIES_TO as readonly string[]).includes(a))
  if (!appliesTo.length) return 'pick what the field is for (movie, anime...)'
  const field: Field = {
    id, label, type, group: clean(input.group, 40) || 'Details', applies_to: appliesTo,
    help: clean(input.help, 200) || undefined, order: Number.isFinite(input.order) ? Number(input.order) : existing.length,
    archived: Boolean(input.archived) || undefined,
  }
  if (type === 'money' || type === 'daywise') {
    field.currency = (CURRENCIES as readonly string[]).includes(String(input.currency)) ? input.currency : 'INR'
  }
  if (type === 'money' || type === 'daywise' || type === 'number') {
    field.unit = (UNITS as readonly string[]).includes(String(input.unit ?? '')) ? input.unit : ''
  }
  if (type === 'daywise' && input.sum_into) {
    // The total must be a money field counted the same way (₹ in crore + ₹ in crore).
    const target = existing.find((f) => f.id === input.sum_into)
    if (!target || target.type !== 'money') return `"${String(input.sum_into)}" is not a money field`
    if (target.currency !== field.currency || (target.unit ?? '') !== (field.unit ?? '')) {
      return `"${target.label}" is in ${target.currency} ${target.unit || ''}: the day-wise rows must use the same currency and unit`
    }
    field.sum_into = target.id
  }
  return field
}

/**
 * Totals kept up to date from day-wise rows: for every day-wise field that adds up into another
 * field, that field gets the rows' sum (rounded to 2 decimals). Rows that aren't numbers count
 * as 0; no rows leaves the total as it is.
 * Called by: the movie editor (whenever day-wise rows change); tests
 */
export function dayWiseTotals(values: Record<string, unknown>, fields: Field[]): Record<string, number> {
  const totals: Record<string, number> = {}
  for (const f of fields) {
    const rows = values[f.id]
    if (f.type !== 'daywise' || !f.sum_into || !Array.isArray(rows) || !rows.length) continue
    const sum = rows.reduce((s: number, r) => s + (Number.isFinite(toNumber((r as DayRow).value)) ? toNumber((r as DayRow).value) : 0), 0)
    totals[f.sum_into] = Math.round(sum * 100) / 100
  }
  return totals
}

type Preset = Omit<Field, 'id' | 'order' | 'applies_to'> & { applies_to?: string[] }

/** Fields most movie entries need; the Fields tab adds the ones picked. Used by: FieldsTab */
export const SUGGESTED_FIELDS: Preset[] = [
  { label: 'India net collection', type: 'money', group: 'Box office', currency: 'INR', unit: 'crore' },
  { label: 'India gross collection', type: 'money', group: 'Box office', currency: 'INR', unit: 'crore' },
  { label: 'Overseas gross collection', type: 'money', group: 'Box office', currency: 'INR', unit: 'crore' },
  { label: 'Worldwide gross collection', type: 'money', group: 'Box office', currency: 'INR', unit: 'crore' },
  { label: 'Worldwide gross (USD)', type: 'money', group: 'Box office', currency: 'USD', unit: '',
    help: 'Filled from TMDb ("revenue")' },
  { label: 'Budget', type: 'money', group: 'Box office', currency: 'INR', unit: 'crore' },
  { label: 'Budget (USD)', type: 'money', group: 'Box office', currency: 'USD', unit: '',
    help: 'Filled from TMDb' },
  { label: 'Opening day India net', type: 'money', group: 'Box office', currency: 'INR', unit: 'crore' },
  { label: 'First week India net', type: 'money', group: 'Box office', currency: 'INR', unit: 'crore' },
  { label: 'India net collection (day-wise)', type: 'daywise', group: 'Box office', currency: 'INR',
    unit: 'crore', help: 'Paste rows from Sacnilk: "Day 1 [1st Friday] ₹ 21 Cr"', sum_into: 'india_net_collection' },
  { label: 'Worldwide gross (day-wise)', type: 'daywise', group: 'Box office', currency: 'INR', unit: 'crore',
    sum_into: 'worldwide_gross_collection' },
  { label: 'Box office verdict', type: 'text', group: 'Box office', help: 'Blockbuster, Hit, Average, Flop...' },
  { label: 'India release date', type: 'date', group: 'Release' },
  { label: 'Re-releases', type: 'text', group: 'Release', help: 'Dates and what they earned' },
  { label: 'Certificate', type: 'text', group: 'Release', help: 'U, UA, A...' },
  { label: 'OTT platform', type: 'list', group: 'Streaming', help: 'Every platform it is on now' },
  { label: 'OTT release date', type: 'date', group: 'Streaming' },
  { label: 'Satellite rights', type: 'text', group: 'Streaming' },
]

// ---------------------------------------------------------------- records

export interface CastMember {
  name: string
  character: string
}

export interface DayRow {
  label: string // "Day 1 [1st Friday]", "Week 2"
  value: number
}

export type FieldValue = string | number | string[] | DayRow[]

/** One movie, editable from the form; the laptop turns it into a document. */
export interface MovieRecord {
  id: string // "tmdb-1726", or "m-<slug>" for a movie typed in by hand
  type: 'movie'
  tmdb_id: number | null
  title: string
  original_title: string
  year: number | null
  release_date: string
  runtime: number | null // minutes
  genres: string[]
  language: string
  overview: string
  tagline: string
  directors: string[]
  writers: string[]
  producers: string[]
  music: string[]
  cast: CastMember[] // in billing order: the first six are shown as "starring"
  values: Record<string, FieldValue> // field id -> value
  notes: string
  sources: string[]
  version: number // +1 on every save; a save must name the version it edited
  created_at: string
  updated_at: string
  deleted?: boolean
}

export const MAX_CAST = 150

/** "a, b , ,c" or ["a", " b"] -> ["a", "b"]. Called by: validateRecord(), tmdbRecord() */
function names(value: unknown, max = 30): string[] {
  const items = Array.isArray(value) ? value : String(value ?? '').split(/[,;\n]/)
  return [...new Set(items.map((v) => clean(v, 120)).filter(Boolean))].slice(0, max)
}

/** A number from "1,234.5", "₹ 21.5 Cr" or 21.5; NaN if none. Called by: checkValue(), parseDayRows() */
export function toNumber(value: unknown): number {
  if (typeof value === 'number') return value
  const m = String(value ?? '').replace(/,/g, '').match(/-?\d+(?:\.\d+)?/)
  return m ? Number(m[0]) : Number.NaN
}

type Checked = { value: FieldValue | null } | { error: string }

/** A value for a field, cleaned (null: empty), or why it is wrong. Called by: validateRecord() */
function checkValue(field: Field, value: unknown): Checked {
  if (value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length)) return { value: null }
  switch (field.type) {
    case 'number':
    case 'money': {
      const n = toNumber(value)
      return Number.isFinite(n) ? { value: n } : { error: `${field.label}: "${String(value)}" is not a number` }
    }
    case 'date': {
      const d = clean(value, 10)
      return /^\d{4}-\d{2}-\d{2}$/.test(d) ? { value: d } : { error: `${field.label}: use a date like 2024-08-15` }
    }
    case 'list':
      return { value: names(value, 40) }
    case 'daywise': {
      if (!Array.isArray(value)) return { error: `${field.label}: expected rows` }
      const rows = value.slice(0, 500).map((r) => ({ label: clean((r as DayRow).label, 60), value: toNumber((r as DayRow).value) }))
      const i = rows.findIndex((r) => !r.label || !Number.isFinite(r.value))
      if (i < 0) return { value: rows }
      const what = rows[i].label ? `row ${i + 1} (${rows[i].label}) has no amount` : `row ${i + 1} has no day`
      return { error: `${field.label}: ${what}. Fill it in or remove the row.` }
    }
    case 'url': {
      const u = clean(value, 500)
      return /^https?:\/\//.test(u) ? { value: u } : { error: `${field.label}: a link starts with http` }
    }
    default:
      return { value: clean(value, 4000) }
  }
}

/**
 * A record from the form, cleaned and checked against the fields, or an error message.
 * Values of unknown fields are refused (so names stay consistent); archived fields keep theirs.
 * Called by: api/records.ts PUT; tests
 */
export function validateRecord(input: Partial<MovieRecord>, fields: Field[]): Omit<MovieRecord, 'version' | 'created_at' | 'updated_at'> | string {
  const title = clean(input.title, 200)
  if (!title) return 'a movie needs a title'
  const year = input.year === null || input.year === undefined || (input.year as unknown) === '' ? null : Number(input.year)
  if (year !== null && (!Number.isInteger(year) || year < 1870 || year > 2100)) return 'the year is four digits, like 2008'
  const releaseDate = clean(input.release_date, 10)
  if (releaseDate && !/^\d{4}-\d{2}-\d{2}$/.test(releaseDate)) return 'release date: use a date like 2024-08-15'
  const cast = (Array.isArray(input.cast) ? input.cast : []).slice(0, MAX_CAST)
    .map((c) => ({ name: clean(c?.name, 120), character: clean(c?.character, 200) })).filter((c) => c.name)
  const byId = new Map(fields.map((f) => [f.id, f]))
  const values: Record<string, FieldValue> = {}
  for (const [id, raw] of Object.entries(input.values ?? {})) {
    const field = byId.get(id)
    if (!field) return `unknown field "${id}": create it in the Fields tab first`
    const checked = checkValue(field, raw)
    if ('error' in checked) return checked.error
    if (checked.value !== null) values[id] = checked.value
  }
  const tmdbId = input.tmdb_id ? Number(input.tmdb_id) : null
  return {
    id: clean(input.id, 80) || (tmdbId ? `tmdb-${tmdbId}` : `m-${slug(title)}${year ? `-${year}` : ''}`),
    type: 'movie', tmdb_id: tmdbId, title, original_title: clean(input.original_title, 200), year,
    release_date: releaseDate, runtime: input.runtime ? Math.round(toNumber(input.runtime)) || null : null,
    genres: names(input.genres, 10), language: clean(input.language, 40), overview: clean(input.overview, 5000),
    tagline: clean(input.tagline, 300), directors: names(input.directors), writers: names(input.writers),
    producers: names(input.producers), music: names(input.music), cast, values,
    notes: clean(input.notes, 20_000), sources: names(input.sources, 20), deleted: input.deleted ? true : undefined,
  }
}

// An amount alone: "₹ 64.85 Cr", "64.85", "Rs 1,021.5 crore" (not "-36.28%": a change, not an amount).
const AMOUNT_ONLY = /^(?:₹|rs\.?|inr|\$)?\s*(-?[\d,]*\.?\d+)\s*(?:cr(?:ore)?s?|l(?:akh)?s?|m(?:illion)?)?\.?$/i
// A label then an amount on one line: "Day 1 [1st Friday] ₹ 21 Cr", "Week 2 - 41 crore".
const LABEL_THEN_AMOUNT = /^(.*?\D)\s*(?:₹|rs\.?|inr|\$)\s*(-?[\d,]*\.?\d+)\s*(?:cr(?:ore)?s?|l(?:akh)?s?)?\.?$|^(.*?)[\s:\-–|]+(-?[\d,]*\.?\d+)\s*(?:cr(?:ore)?s?|l(?:akh)?s?)\.?$|^(.*?):\s*(-?[\d,]*\.?\d+)$/i

/**
 * Rows pasted from a box office site, in any of the shapes copying a table gives:
 *   "Day 1 [1st Friday]\t₹ 64.85 Cr\t-"       one row per line, cells separated by tabs
 *   "Day 1 [1st Friday] ₹ 64.85 Cr"           one row per line
 *   "Day 1 [1st Friday]" then "₹ 64.85 Cr"    each cell on its own line
 *   "64.85" (a column of amounts only)        -> "Day 1", "Day 2"...
 * Headers, "-" and "+12%" change cells are skipped, and so is a "Total" row (not a day).
 * Called by: the admin form's day-wise editor; tests
 */
export function parseDayRows(text: string): DayRow[] {
  const rows: DayRow[] = []
  let pending = '' // a label line still waiting for its amount
  const add = (label: string, amountText: string) => {
    const value = toNumber(amountText)
    const name = label.replace(/[:\-–|]+$/, '').trim() || `Day ${rows.length + 1}`
    if (Number.isFinite(value) && !/^total\b/i.test(name)) rows.push({ label: name, value })
  }
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || /^[-–—]$/.test(line) || /^[+-]?[\d.,]+\s*%$/.test(line)) continue // empty, "no change", "+12%"
    const cells = line.split('\t').map((c) => c.trim()).filter(Boolean)
    if (cells.length > 1) {
      const amountAt = cells.findIndex((c, i) => i > 0 && AMOUNT_ONLY.test(c))
      if (amountAt > 0) add(cells.slice(0, amountAt).join(' '), cells[amountAt])
      pending = ''
      continue
    }
    const alone = line.match(AMOUNT_ONLY)
    if (alone) {
      add(pending, alone[1])
      pending = ''
      continue
    }
    const both = line.match(LABEL_THEN_AMOUNT)
    if (both) {
      add(both[1] ?? both[3] ?? both[5] ?? '', both[2] ?? both[4] ?? both[6] ?? '')
      pending = ''
      continue
    }
    pending = /^total\b/i.test(line) ? 'Total' : line // a label (or a header: replaced by the next label)
  }
  return rows
}

// ---------------------------------------------------------------- TMDb

interface TmdbCredit {
  name?: string
  character?: string
  job?: string
}

export interface TmdbMovie {
  id: number
  title: string
  original_title?: string
  release_date?: string
  runtime?: number
  genres?: { name: string }[]
  spoken_languages?: { english_name?: string; iso_639_1?: string }[]
  original_language?: string
  overview?: string
  tagline?: string
  budget?: number
  revenue?: number
  credits?: { cast?: TmdbCredit[]; crew?: TmdbCredit[] }
}

/** Crew names for some jobs, in TMDb's order, without repeats. Called by: tmdbRecord() */
function crew(movie: TmdbMovie, jobs: string[]): string[] {
  return names((movie.credits?.crew ?? []).filter((c) => jobs.includes(c.job ?? '')).map((c) => c.name ?? ''))
}

/**
 * TMDb's movie details (with append_to_response=credits) as a new record for the editor.
 * Budget and revenue (US dollars) go into the "budget_usd" / "worldwide_gross_usd" fields when
 * those exist. anichat/domain/records.py tmdb_record() does the same on the laptop.
 * Called by: api/tmdb.ts; tests
 */
export function tmdbRecord(movie: TmdbMovie, fields: Field[], castLimit = 40): Partial<MovieRecord> {
  const ids = new Set(fields.map((f) => f.id))
  const values: Record<string, FieldValue> = {}
  if (movie.budget && ids.has('budget_usd')) values.budget_usd = movie.budget
  if (movie.revenue && ids.has('worldwide_gross_usd')) values.worldwide_gross_usd = movie.revenue
  const language = movie.spoken_languages?.find((l) => l.iso_639_1 === movie.original_language)?.english_name
  return {
    id: `tmdb-${movie.id}`, type: 'movie', tmdb_id: movie.id, title: movie.title,
    original_title: movie.original_title && movie.original_title !== movie.title ? movie.original_title : '',
    year: movie.release_date ? Number(movie.release_date.slice(0, 4)) : null, release_date: movie.release_date ?? '',
    runtime: movie.runtime || null, genres: (movie.genres ?? []).map((g) => g.name),
    language: language ?? movie.original_language ?? '', overview: movie.overview ?? '', tagline: movie.tagline ?? '',
    directors: crew(movie, ['Director']), writers: crew(movie, ['Screenplay', 'Writer', 'Story', 'Dialogue']),
    producers: crew(movie, ['Producer']), music: crew(movie, ['Original Music Composer', 'Music']),
    cast: (movie.credits?.cast ?? []).filter((c) => c.name).slice(0, castLimit)
      .map((c) => ({ name: c.name ?? '', character: c.character ?? '' })),
    values, notes: '', sources: [`https://www.themoviedb.org/movie/${movie.id}`],
  }
}

/**
 * A value as text, the way documents show it: 597.99 (INR, crore) -> "₹597.99 crore",
 * 140000000 (USD) -> "$140,000,000". anichat/domain/records.py format_value() matches it.
 * Called by: the admin form (previews); tests
 */
export function formatValue(field: Field, value: FieldValue): string {
  const amount = (n: number) => {
    const symbol = field.type === 'money' || field.type === 'daywise' ? (field.currency === 'USD' ? '$' : '₹') : ''
    const digits = field.unit ? n.toLocaleString('en-US', { maximumFractionDigits: 2 }) : n.toLocaleString('en-US')
    return `${symbol}${digits}${field.unit ? ` ${field.unit}` : ''}`
  }
  if (Array.isArray(value)) {
    if (field.type === 'daywise') return (value as DayRow[]).map((r) => `${r.label}: ${amount(r.value)}`).join('; ')
    return (value as string[]).join(', ')
  }
  return typeof value === 'number' ? amount(value) : value
}
