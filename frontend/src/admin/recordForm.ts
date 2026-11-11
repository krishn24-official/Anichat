/**
 * The movie editor's state: a record with every list as editable text ("Amar Kaushik, Dinesh
 * Vijan") and every number as typed, so typing is never fought. The server (api/_records.ts
 * validateRecord) turns the text back into lists and numbers. Pure: tested in recordForm.test.ts.
 */
import type { CastMember, DayRow, Field, FieldValue, MovieRecord } from '../../api/_records'

export interface DayRowText {
  label: string
  value: string
}

export interface EditorState {
  id: string
  tmdb_id: number | null
  title: string
  original_title: string
  year: string
  release_date: string
  runtime: string
  genres: string
  language: string
  tagline: string
  overview: string
  directors: string
  writers: string
  producers: string
  music: string
  cast: CastMember[]
  values: Record<string, string | DayRowText[]> // daywise fields: rows; others: text
  notes: string
  sources: string // one per line
}

/** A record (new from TMDb, or saved) as editor state. Called by: MovieEditor (open, restore) */
export function toEditor(r: Partial<MovieRecord>, fields: Field[]): EditorState {
  const join = (xs: string[] | undefined, sep = ', ') => (xs ?? []).join(sep)
  const values: EditorState['values'] = {}
  const types = new Map(fields.map((f) => [f.id, f.type]))
  for (const [id, v] of Object.entries(r.values ?? {})) {
    if (types.get(id) === 'daywise') values[id] = (v as DayRow[]).map((row) => ({ label: row.label, value: String(row.value) }))
    else values[id] = Array.isArray(v) ? join(v as string[]) : String(v)
  }
  return {
    id: r.id ?? '', tmdb_id: r.tmdb_id ?? null, title: r.title ?? '', original_title: r.original_title ?? '',
    year: r.year ? String(r.year) : '', release_date: r.release_date ?? '', runtime: r.runtime ? String(r.runtime) : '',
    genres: join(r.genres), language: r.language ?? '', tagline: r.tagline ?? '', overview: r.overview ?? '',
    directors: join(r.directors), writers: join(r.writers), producers: join(r.producers), music: join(r.music),
    cast: (r.cast ?? []).map((c) => ({ ...c })), values, notes: r.notes ?? '', sources: join(r.sources, '\n'),
  }
}

const NUMBER = /^[₹$]?\s*-?[\d,]*\.?\d+\s*(?:cr(?:ore)?)?$/i

/**
 * Day-wise rows as typed, made whole where the intent is clear: empty rows dropped, an amount
 * typed into the day box ("64.85" | "") moved to the amount, a row without a day named "Day N".
 * Rows still missing an amount stay, so the server names them.
 * Called by: fromEditor(); tests
 */
export function tidyDayRows(rows: DayRowText[]): DayRowText[] {
  return rows
    .map((r) => ({ label: r.label.trim(), value: r.value.trim() }))
    .filter((r) => r.label || r.value)
    .map((r, i) => {
      if (!r.value && NUMBER.test(r.label)) return { label: `Day ${i + 1}`, value: r.label }
      if (!r.label) return { label: `Day ${i + 1}`, value: r.value }
      return r
    })
}

/** Editor state as the record to save (the server parses the text). Called by: MovieEditor save */
export function fromEditor(s: EditorState): Partial<MovieRecord> {
  const values: Record<string, FieldValue> = {}
  for (const [id, v] of Object.entries(s.values)) {
    if (Array.isArray(v)) {
      const rows = tidyDayRows(v)
      if (rows.length) values[id] = rows as unknown as DayRow[] // values as typed: the server reads the numbers
    } else if (v.trim()) {
      values[id] = v.trim()
    }
  }
  const list = (text: string) => text.split(/[,\n]/).map((x) => x.trim()).filter(Boolean)
  return {
    id: s.id || undefined, tmdb_id: s.tmdb_id, title: s.title.trim(), original_title: s.original_title.trim(),
    year: s.year.trim() ? Number(s.year) : null, release_date: s.release_date, runtime: s.runtime.trim() ? Number(s.runtime) : null,
    genres: list(s.genres), language: s.language.trim(), tagline: s.tagline.trim(), overview: s.overview.trim(),
    directors: list(s.directors), writers: list(s.writers), producers: list(s.producers), music: list(s.music),
    cast: s.cast.filter((c) => c.name.trim()).map((c) => ({ name: c.name.trim(), character: c.character.trim() })),
    values, notes: s.notes.trim(), sources: s.sources.split('\n').map((x) => x.trim()).filter(Boolean),
  }
}

/**
 * Cast lines typed or pasted: "Shraddha Kapoor as Stree", "Pankaj Tripathi - Rudra",
 * "Tamannaah Bhatia" -> [{name, character}]. Called by: MovieEditor "Add several"
 */
export function parseCastLines(text: string): CastMember[] {
  return text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
    const m = line.match(/^(.+?)\s+(?:as|-|–|:|\t)\s*(.+)$/i)
    return m ? { name: m[1].trim(), character: m[2].trim() } : { name: line, character: '' }
  })
}

/** Move one item of a list up (-1) or down (+1). Called by: MovieEditor cast rows */
export function move<T>(items: T[], index: number, by: -1 | 1): T[] {
  const to = index + by
  if (to < 0 || to >= items.length) return items
  const copy = [...items]
  ;[copy[index], copy[to]] = [copy[to], copy[index]]
  return copy
}

/** The sum of day-wise rows typed so far (rows that are not numbers count as 0). Called by: MovieEditor */
export function rowsTotal(rows: DayRowText[]): number {
  return rows.reduce((sum, r) => sum + (Number(r.value.replace(/,/g, '')) || 0), 0)
}
