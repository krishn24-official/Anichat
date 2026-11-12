import { ArrowDown, ArrowUp, ClipboardPaste, History, Plus, Trash2, X } from 'lucide-react'
import { type FormEvent, type ReactNode, useState } from 'react'
import { dayWiseTotals, type Field, formatValue, parseDayRows } from '../../api/_records'
import { AdminError, deleteRecord, getHistory, type MovieRecord, saveRecord } from './adminApi'
import { type DayRowText, type EditorState, fromEditor, move, parseCastLines, rowsTotal, toEditor } from './recordForm'
import { card, inputBox, inputClass, labelClass, type Notice, primaryButton, secondaryButton } from './ui'

interface Props {
  password: string
  fields: Field[]
  record: Partial<MovieRecord> // from TMDb (new) or a saved record
  baseVersion: number // 0 for a new record
  onSaved: (record: MovieRecord) => void
  onClose: () => void
  notify: (n: Notice) => void
}

/** A labelled text input. Called by: MovieEditor */
function Text({ id, label, value, onChange, placeholder, hint, type = 'text' }: {
  id: string; label: string; value: string; onChange: (v: string) => void; placeholder?: string; hint?: string; type?: string
}) {
  return (
    <div>
      <label htmlFor={id} className={labelClass}>{label}</label>
      <input id={id} type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
             inputMode={type === 'number' ? 'decimal' : undefined} className={inputClass} />
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

/** A titled block of the editor. Called by: MovieEditor */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={`${card} space-y-4`}>
      <h3 className="font-semibold">{title}</h3>
      {children}
    </section>
  )
}

/** The rows of a day-wise field, with paste-from-Sacnilk. Called by: MovieEditor */
function DayRows({ field, rows, onChange }: { field: Field; rows: DayRowText[]; onChange: (rows: DayRowText[]) => void }) {
  const [paste, setPaste] = useState<string | null>(null)
  const total = rowsTotal(rows)
  /** Add the pasted rows (replacing all, or appending). Called by: the paste box buttons */
  const addPasted = (replace: boolean) => {
    const parsed = parseDayRows(paste ?? '').map((r) => ({ label: r.label, value: String(r.value) }))
    onChange(replace ? parsed : [...rows.filter((r) => r.label || r.value), ...parsed])
    setPaste(null)
  }
  return (
    <div>
      <p className={labelClass}>{field.label}</p>
      {field.help && <p className="mb-2 text-xs text-muted">{field.help}</p>}
      <div className="space-y-1.5">
        {rows.map((row, i) => (
          <div key={i} className="flex gap-2">
            <input aria-label="Day" value={row.label} placeholder={`Day ${i + 1}`} className={`${inputBox} w-1/2 min-w-0`}
                   onChange={(e) => onChange(rows.map((r, j) => (j === i ? { ...r, label: e.target.value } : r)))} />
            <input aria-label={`Amount in ${field.unit || field.currency}`} value={row.value} inputMode="decimal"
                   placeholder={field.unit || '0'} className={`${inputBox} min-w-0 flex-1`}
                   onChange={(e) => onChange(rows.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))} />
            <button type="button" aria-label="Remove row" onClick={() => onChange(rows.filter((_, j) => j !== i))}
                    className="px-1 text-muted hover:text-text"><X size={16} /></button>
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
        <button type="button" className="flex items-center gap-1 text-accent"
                onClick={() => onChange([...rows, { label: `Day ${rows.length + 1}`, value: '' }])}>
          <Plus size={14} aria-hidden /> Row
        </button>
        <button type="button" className="flex items-center gap-1 text-accent" onClick={() => setPaste('')}>
          <ClipboardPaste size={14} aria-hidden /> Paste rows
        </button>
        {rows.length > 0 && (
          <span className="ml-auto text-muted">
            {rows.length} rows · sum {formatValue(field, Math.round(total * 100) / 100)}
          </span>
        )}
      </div>
      {paste !== null && (
        <div className="mt-2 space-y-2 rounded-lg border border-line p-3">
          <textarea rows={6} value={paste} onChange={(e) => setPaste(e.target.value)} className={inputClass} autoFocus
                    placeholder={'Copy the table from Sacnilk and paste here:\nDay 1 [1st Friday]\t₹ 21 Cr\nDay 2 [1st Saturday]\t₹ 30.5 Cr'} />
          <p className="text-xs text-muted">{parseDayRows(paste).length} rows found (headers and "Total" are skipped).</p>
          <div className="flex gap-2">
            <button type="button" className={secondaryButton} onClick={() => addPasted(true)}>Replace all rows</button>
            <button type="button" className={secondaryButton} onClick={() => addPasted(false)}>Add after</button>
            <button type="button" className={secondaryButton} onClick={() => setPaste(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Edit one movie: basics, people (cast order matters: the first six are "starring"), every
 * movie field grouped as in the Fields tab, notes and sources. Saves a new version; another
 * device's newer version is never overwritten silently.
 * Called by: MoviesTab
 */
export function MovieEditor({ password, fields, record, baseVersion, onSaved, onClose, notify }: Props) {
  const [state, setState] = useState<EditorState>(() => toEditor(record, fields))
  const [version, setVersion] = useState(baseVersion)
  const [busy, setBusy] = useState(false)
  const [castPaste, setCastPaste] = useState<string | null>(null)
  const [history, setHistory] = useState<MovieRecord[] | null>(null)
  const update = (patch: Partial<EditorState>) => setState((s) => ({ ...s, ...patch }))
  const setValue = (id: string, v: string | DayRowText[]) => setState((s) => ({ ...s, values: { ...s.values, [id]: v } }))
  /** Change a day-wise field's rows, and the total they add up into (Fields tab: "adds up into"). Called by: DayRows */
  const setDayRows = (id: string, rows: DayRowText[]) => setState((s) => {
    const values = { ...s.values, [id]: rows }
    for (const [target, sum] of Object.entries(dayWiseTotals(values, fields.filter((f) => f.id === id)))) {
      values[target] = String(sum)
    }
    return { ...s, values }
  })

  // Movie fields to show: active ones, plus archived ones that still hold a value here.
  const shown = fields.filter((f) => f.applies_to.includes('movie') && (!f.archived || state.values[f.id] !== undefined))
  const groups = [...new Set(shown.map((f) => f.group))]

  /** Save a new version. Called by: the form */
  const save = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const saved = await saveRecord(password, fromEditor(state), version)
      setVersion(saved.version)
      setState(toEditor(saved, fields))
      notify({ kind: 'ok', text: `Saved "${saved.title}" (version ${saved.version}). Run the sync on the laptop to update AniChat.` })
      onSaved(saved)
    } catch (err) {
      const current = err instanceof AdminError && err.status === 409 ? (err.body.current as MovieRecord | null) : null
      if (current && window.confirm(`${(err as Error).message}\n\nLoad the newer version? (Your unsaved changes here will be replaced.)`)) {
        setState(toEditor(current, fields))
        setVersion(current.version)
      }
      notify({ kind: 'error', text: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  /** Delete the movie (the laptop removes it from AniChat at the next sync). Called by: "Delete" */
  const remove = async () => {
    if (!window.confirm(`Delete "${state.title}" from AniChat?`)) return
    try {
      await deleteRecord(password, state.id)
      notify({ kind: 'ok', text: `Deleted "${state.title}". It disappears from AniChat at the next sync.` })
      onClose()
    } catch (err) {
      notify({ kind: 'error', text: (err as Error).message })
    }
  }

  /** Show earlier versions. Called by: "History" */
  const showHistory = async () => {
    try {
      setHistory(await getHistory(password, state.id))
    } catch (err) {
      notify({ kind: 'error', text: (err as Error).message })
    }
  }

  return (
    <form onSubmit={save} className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="min-w-0 flex-1 truncate text-lg font-semibold">{state.title || 'New movie'}{state.year && ` (${state.year})`}</h2>
        <span className="text-xs text-muted">{version ? `version ${version}` : 'not saved yet'}</span>
      </div>

      <Section title="Basics">
        <div className="grid gap-4 sm:grid-cols-[1fr_7rem]">
          <Text id="m-title" label="Title" value={state.title} onChange={(v) => update({ title: v })} />
          <Text id="m-year" label="Year" value={state.year} onChange={(v) => update({ year: v })} type="number" />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Text id="m-release" label="Release date" value={state.release_date} onChange={(v) => update({ release_date: v })} type="date" />
          <Text id="m-runtime" label="Runtime (minutes)" value={state.runtime} onChange={(v) => update({ runtime: v })} type="number" />
          <Text id="m-lang" label="Language" value={state.language} onChange={(v) => update({ language: v })} placeholder="Hindi" />
        </div>
        <Text id="m-genres" label="Genres" value={state.genres} onChange={(v) => update({ genres: v })} placeholder="Comedy, Horror" />
        <Text id="m-orig" label="Original title (if different)" value={state.original_title} onChange={(v) => update({ original_title: v })} />
        <div>
          <label htmlFor="m-overview" className={labelClass}>Story (overview)</label>
          <textarea id="m-overview" rows={4} value={state.overview} onChange={(e) => update({ overview: e.target.value })} className={inputClass} />
        </div>
        <Text id="m-tagline" label="Tagline" value={state.tagline} onChange={(v) => update({ tagline: v })} />
      </Section>

      <Section title="People">
        <div className="grid gap-4 sm:grid-cols-2">
          <Text id="m-dir" label="Directed by" value={state.directors} onChange={(v) => update({ directors: v })} hint="Separate names with commas" />
          <Text id="m-writers" label="Written by" value={state.writers} onChange={(v) => update({ writers: v })} />
          <Text id="m-producers" label="Produced by" value={state.producers} onChange={(v) => update({ producers: v })} />
          <Text id="m-music" label="Music by" value={state.music} onChange={(v) => update({ music: v })} />
        </div>
        <div>
          <p className={labelClass}>Cast ({state.cast.length}) · the first six are shown as "starring"</p>
          <div className="space-y-1.5">
            {state.cast.map((c, i) => (
              <div key={i} className={`flex items-center gap-1.5 ${i === 5 ? 'border-b border-dashed border-line pb-1.5' : ''}`}>
                <span className="w-6 shrink-0 text-right text-xs text-muted">{i + 1}</span>
                <input aria-label="Actor" value={c.name} placeholder="Actor" className={`${inputBox} w-2/5 min-w-0 py-2`}
                       onChange={(e) => update({ cast: state.cast.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
                <input aria-label="Character" value={c.character} placeholder="as character" className={`${inputBox} min-w-0 flex-1 py-2`}
                       onChange={(e) => update({ cast: state.cast.map((x, j) => (j === i ? { ...x, character: e.target.value } : x)) })} />
                <button type="button" aria-label="Move up" disabled={i === 0} onClick={() => update({ cast: move(state.cast, i, -1) })}
                        className="text-muted hover:text-text disabled:opacity-30"><ArrowUp size={15} /></button>
                <button type="button" aria-label="Move down" disabled={i === state.cast.length - 1}
                        onClick={() => update({ cast: move(state.cast, i, 1) })}
                        className="text-muted hover:text-text disabled:opacity-30"><ArrowDown size={15} /></button>
                <button type="button" aria-label={`Remove ${c.name}`} onClick={() => update({ cast: state.cast.filter((_, j) => j !== i) })}
                        className="text-muted hover:text-text"><X size={15} /></button>
              </div>
            ))}
          </div>
          <div className="mt-2 flex gap-4 text-sm">
            <button type="button" className="flex items-center gap-1 text-accent"
                    onClick={() => update({ cast: [...state.cast, { name: '', character: '' }] })}>
              <Plus size={14} aria-hidden /> Actor
            </button>
            <button type="button" className="flex items-center gap-1 text-accent" onClick={() => setCastPaste('')}>
              <ClipboardPaste size={14} aria-hidden /> Add several
            </button>
          </div>
          {castPaste !== null && (
            <div className="mt-2 space-y-2 rounded-lg border border-line p-3">
              <textarea rows={5} value={castPaste} onChange={(e) => setCastPaste(e.target.value)} className={inputClass} autoFocus
                        placeholder={'One per line:\nShraddha Kapoor as Stree\nAbhishek Banerjee as Jana'} />
              <div className="flex gap-2">
                <button type="button" className={secondaryButton}
                        onClick={() => { update({ cast: [...state.cast, ...parseCastLines(castPaste)] }); setCastPaste(null) }}>
                  Add {parseCastLines(castPaste).length}
                </button>
                <button type="button" className={secondaryButton} onClick={() => setCastPaste(null)}>Cancel</button>
              </div>
            </div>
          )}
        </div>
      </Section>

      {groups.map((group) => (
        <Section key={group} title={group}>
          {shown.filter((f) => f.group === group).map((f) => {
            const value = state.values[f.id]
            if (f.type === 'daywise') {
              return <DayRows key={f.id} field={f} rows={Array.isArray(value) ? value : []} onChange={(rows) => setDayRows(f.id, rows)} />
            }
            const text = typeof value === 'string' ? value : ''
            const unit = f.type === 'money' ? `${f.currency === 'USD' ? '$' : '₹'}${f.unit ? ` in ${f.unit}` : ''}` : f.unit
            const preview = (f.type === 'money' || f.type === 'number') && text.trim() && Number.isFinite(Number(text.replace(/,/g, '')))
              ? `= ${formatValue(f, Number(text.replace(/,/g, '')))}` : ''
            // A total kept up to date from day-wise rows: say so, and warn if it was changed by hand since.
            const source = shown.find((d) => d.type === 'daywise' && d.sum_into === f.id && Array.isArray(state.values[d.id])
              && (state.values[d.id] as DayRowText[]).length)
            const sum = source ? dayWiseTotals({ [source.id]: state.values[source.id] }, [source])[f.id] : undefined
            const auto = source && sum !== undefined
              ? (Number(text.replace(/,/g, '')) === sum ? `Added up from ${source.label}`
                : `⚠ ${source.label} adds up to ${formatValue(f, sum)}`) : ''
            return (
              <Text key={f.id} id={`v-${f.id}`} value={text} onChange={(v) => setValue(f.id, v)}
                    label={`${f.label}${unit ? ` (${unit})` : ''}${f.archived ? ' · archived' : ''}`}
                    type={f.type === 'date' ? 'date' : f.type === 'url' ? 'url' : 'text'}
                    placeholder={f.type === 'list' ? 'Netflix, Prime Video' : undefined}
                    hint={[auto, f.help, f.type === 'list' ? 'Separate with commas' : '', preview].filter(Boolean).join(' · ') || undefined} />
            )
          })}
        </Section>
      ))}
      {groups.length === 0 && (
        <p className={`${card} text-sm text-muted`}>No movie fields yet: create them in the Fields tab (box office, OTT...).</p>
      )}

      <Section title="Notes and sources">
        <div>
          <label htmlFor="m-notes" className={labelClass}>Notes (anything else, in your words)</label>
          <textarea id="m-notes" rows={4} value={state.notes} onChange={(e) => update({ notes: e.target.value })} className={inputClass} />
        </div>
        <div>
          <label htmlFor="m-sources" className={labelClass}>Sources (one link per line)</label>
          <textarea id="m-sources" rows={2} value={state.sources} onChange={(e) => update({ sources: e.target.value })} className={inputClass} />
        </div>
      </Section>

      {history && (
        <Section title={`Earlier versions (${history.length})`}>
          {history.length === 0 && <p className="text-sm text-muted">None yet.</p>}
          <ul className="space-y-2 text-sm">
            {history.map((h) => (
              <li key={h.version} className="flex items-center gap-2">
                <span className="flex-1">Version {h.version} · {new Date(h.updated_at).toLocaleString()} · {h.cast.length} cast · {Object.keys(h.values).length} values</span>
                <button type="button" className={secondaryButton}
                        onClick={() => { setState({ ...toEditor(h, fields), id: state.id }); notify({ kind: 'ok', text: `Loaded version ${h.version}: save to restore it.` }) }}>
                  Load
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <div className="sticky bottom-0 -mx-4 flex gap-2 border-t border-line bg-bg/95 px-4 py-3 backdrop-blur">
        <button type="submit" disabled={busy || !state.title.trim()} className={`${primaryButton} flex-1`}>
          {busy ? 'Saving…' : 'Save'}
        </button>
        {version > 0 && (
          <>
            <button type="button" onClick={() => void showHistory()} className={secondaryButton} aria-label="History"><History size={16} /></button>
            <button type="button" onClick={() => void remove()} className={secondaryButton} aria-label="Delete"><Trash2 size={16} /></button>
          </>
        )}
        <button type="button" onClick={onClose} className={secondaryButton}>Close</button>
      </div>
    </form>
  )
}
