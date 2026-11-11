/** Pure helpers of the "Other entries" form (anime, series, other facts; tested in form.test.ts). */
import type { EntryInput } from '../../api/_submission'

export type EntryType = 'anime' | 'series' | 'other'

/** One fact row: a field (by its label) and a value. */
export interface FactRow {
  key: string
  value: string
}

/** Everything the form holds (also kept as an unsent draft in localStorage). */
export interface FormState {
  type: EntryType
  series: string
  title: string
  facts: FactRow[]
  notes: string
  source: string
}

/** A blank form for a type. Called by: EntriesTab (start, after sending, type change) */
export function emptyForm(type: EntryType = 'anime'): FormState {
  return { type, series: type === 'other' ? 'other' : '', title: '', facts: [{ key: '', value: '' }], notes: '', source: '' }
}

/**
 * What to send: rows with both a field and a value become facts (later rows win on a repeated field).
 * Called by: EntriesTab submit
 */
export function toInput(form: FormState): EntryInput {
  const facts: Record<string, string> = {}
  for (const row of form.facts) {
    if (row.key.trim() && row.value.trim()) facts[row.key.trim()] = row.value.trim()
  }
  return { type: form.type, series: form.series.trim(), title: form.title.trim(), facts, notes: form.notes.trim(),
    source: form.source.trim() }
}

/** Why the form can't be sent yet, or null. Called by: EntriesTab (disables "Save") */
export function problem(form: FormState): string | null {
  if (!form.title.trim()) return 'Add a title.'
  if (!form.series.trim()) return 'Pick the series it belongs to.'
  const input = toInput(form)
  if (!Object.keys(input.facts ?? {}).length && !input.notes) return 'Add at least one fact or a note.'
  return null
}
