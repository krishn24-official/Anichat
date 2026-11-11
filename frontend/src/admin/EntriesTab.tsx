import { Check, CircleAlert, Clock, Plus, RefreshCw, Trash2, X } from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useState } from 'react'
import type { Field } from '../../api/_records'
import { addEntry, deleteEntry, type Entry, listEntries } from './adminApi'
import { type EntryType, type FormState, emptyForm, problem, toInput } from './form'
import seriesList from './series.json'
import { card, inputBox, inputClass, labelClass, load, type Notice, primaryButton, store } from './ui'

const DRAFT_KEY = 'anichat-admin-draft'
const TYPES: { id: EntryType; label: string }[] = [{ id: 'anime', label: 'Anime' }, { id: 'series', label: 'Series' }, { id: 'other', label: 'Other' }]

interface Props {
  password: string
  fields: Field[]
  notify: (n: Notice) => void
}

/** The unsent draft from an earlier visit, or a blank form. Called by: EntriesTab (first render) */
function initialForm(): FormState {
  try {
    const saved = load(DRAFT_KEY)
    const draft = saved ? { ...emptyForm(), ...(JSON.parse(saved) as FormState) } : emptyForm()
    return TYPES.some((t) => t.id === draft.type) ? draft : emptyForm()
  } catch {
    return emptyForm()
  }
}

/**
 * The "Other entries" tab: facts about anime characters, series and anything else, added to the
 * chosen series at the next sync. Fact names are the fields defined for that type (Fields tab).
 * Called by: AdminPage
 */
export function EntriesTab({ password, fields, notify }: Props) {
  const [form, setForm] = useState<FormState>(initialForm)
  const [entries, setEntries] = useState<Entry[] | null>(null)
  const [busy, setBusy] = useState(false)
  const update = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }))
  const usable = fields.filter((f) => !f.archived && f.applies_to.includes(form.type))

  /** Reload the list of entries. Called by: first render, "Refresh", after changes */
  const reload = useCallback(
    () => listEntries(password).then((d) => setEntries(d.entries)).catch((e: Error) => notify({ kind: 'error', text: e.message })),
    [password, notify],
  )
  useEffect(() => {
    void reload()
  }, [reload])
  // Keep the unsent draft, so a lost connection or closed tab loses nothing.
  useEffect(() => {
    store(DRAFT_KEY, JSON.stringify(form))
  }, [form])

  /** Save the entry. Called by: the form */
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (problem(form)) return
    setBusy(true)
    try {
      const entry = await addEntry(password, toInput(form))
      setForm(emptyForm(form.type))
      notify({ kind: 'ok', text: `Saved "${entry.title}". It will be added when you run the sync on your laptop.` })
      await reload()
    } catch (err) {
      notify({ kind: 'error', text: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  /** Remove a pending entry. Called by: the trash button */
  const remove = async (entry: Entry) => {
    if (!window.confirm(`Remove "${entry.title}"? It hasn't been added yet.`)) return
    try {
      await deleteEntry(password, entry.id)
      await reload()
    } catch (err) {
      notify({ kind: 'error', text: (err as Error).message })
    }
  }

  const blocked = problem(form)
  return (
    <div className="space-y-8">
      <form onSubmit={submit} className={`${card} space-y-4`}>
        <div className="grid grid-cols-3 gap-1 rounded-lg bg-panel-2 p-1" role="radiogroup" aria-label="Type">
          {TYPES.map((t) => (
            <button key={t.id} type="button" role="radio" aria-checked={form.type === t.id}
                    onClick={() => setForm((f) => ({ ...emptyForm(t.id), title: f.title, notes: f.notes, source: f.source,
                      series: t.id === 'other' ? 'other' : f.series === 'other' ? '' : f.series }))}
                    className={`rounded-md py-2 text-sm ${form.type === t.id ? 'bg-panel font-medium shadow-sm' : 'text-muted'}`}>
              {t.label}
            </button>
          ))}
        </div>
        <div>
          <label htmlFor="e-title" className={labelClass}>What is it about? (a character, an episode, the series…)</label>
          <input id="e-title" value={form.title} onChange={(e) => update({ title: e.target.value })} className={inputClass}
                 placeholder="Naruto Uzumaki" />
        </div>
        {form.type !== 'other' && (
          <div>
            <label htmlFor="e-series" className={labelClass}>Series</label>
            <input id="e-series" list="series-list" value={form.series} onChange={(e) => update({ series: e.target.value })}
                   className={inputClass} placeholder="naruto" />
            <datalist id="series-list">
              {seriesList.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
            </datalist>
          </div>
        )}
        <fieldset>
          <legend className={labelClass}>Facts</legend>
          {usable.length === 0 ? (
            <p className="text-sm text-muted">No fields for {form.type} yet: create them in the Fields tab (tick "{form.type}").</p>
          ) : (
            <>
              <div className="space-y-2">
                {form.facts.map((row, i) => (
                  <div key={i} className="flex gap-2">
                    <select aria-label="Field" value={row.key} className={`${inputBox} w-2/5 min-w-0`}
                            onChange={(e) => update({ facts: form.facts.map((r, j) => (j === i ? { ...r, key: e.target.value } : r)) })}>
                      <option value="">Field…</option>
                      {usable.map((f) => <option key={f.id} value={f.label}>{f.label}</option>)}
                    </select>
                    <input aria-label="Value" value={row.value} className={`${inputBox} min-w-0 flex-1`}
                           onChange={(e) => update({ facts: form.facts.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)) })} />
                    <button type="button" aria-label="Remove this fact" disabled={form.facts.length === 1}
                            onClick={() => update({ facts: form.facts.filter((_, j) => j !== i) })}
                            className="px-1 text-muted hover:text-text disabled:opacity-30"><X size={16} /></button>
                  </div>
                ))}
              </div>
              <button type="button" onClick={() => update({ facts: [...form.facts, { key: '', value: '' }] })}
                      className="mt-2 flex items-center gap-1 text-sm text-accent">
                <Plus size={15} aria-hidden /> Add a fact
              </button>
            </>
          )}
        </fieldset>
        <div>
          <label htmlFor="e-notes" className={labelClass}>Notes (any details, in your words)</label>
          <textarea id="e-notes" rows={4} value={form.notes} onChange={(e) => update({ notes: e.target.value })} className={inputClass} />
        </div>
        <div>
          <label htmlFor="e-source" className={labelClass}>Source (link, optional)</label>
          <input id="e-source" value={form.source} onChange={(e) => update({ source: e.target.value })} className={inputClass}
                 placeholder="https://…" />
        </div>
        <button type="submit" disabled={!!blocked || busy} className={`${primaryButton} w-full`}>{busy ? 'Saving…' : 'Save'}</button>
        {blocked && <p className="text-center text-sm text-muted">{blocked}</p>}
      </form>

      <section>
        <div className="mb-3 flex items-center">
          <h2 className="font-semibold">Saved entries</h2>
          <button type="button" onClick={() => void reload()} className="ml-auto flex items-center gap-1 text-sm text-muted hover:text-text">
            <RefreshCw size={14} aria-hidden /> Refresh
          </button>
        </div>
        {entries === null ? <p className="text-sm text-muted">Loading…</p> : entries.length === 0 ? (
          <p className="text-sm text-muted">Nothing saved yet.</p>
        ) : (
          <ul className="space-y-2">
            {entries.map((e) => (
              <li key={e.id} className="flex items-start gap-2 rounded-xl border border-line bg-panel px-4 py-3 text-sm">
                {e.status === 'done' ? <Check size={16} className="mt-0.5 text-green-500" aria-label="added" />
                  : e.status === 'error' ? <CircleAlert size={16} className="mt-0.5 text-accent" aria-label="not added" />
                    : <Clock size={16} className="mt-0.5 text-muted" aria-label="waiting for the laptop" />}
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{e.title}<span className="font-normal text-muted"> · {e.series}</span></p>
                  <p className="text-muted">
                    {e.status === 'pending' ? 'Waiting for the laptop' : e.result} · {Object.keys(e.facts).length} facts ·{' '}
                    {new Date(e.submitted_at).toLocaleDateString()}
                  </p>
                </div>
                {e.status === 'pending' && (
                  <button type="button" onClick={() => void remove(e)} aria-label={`Remove ${e.title}`} className="text-muted hover:text-text">
                    <Trash2 size={15} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
