import { CheckCircle2, Clock, Film, Plus, Search } from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useState } from 'react'
import type { Field } from '../../api/_records'
import {
  getRecord, listRecords, type MovieRecord, type RecordSummary, searchTmdb, type TmdbHit, tmdbMovie,
} from './adminApi'
import { MovieEditor } from './MovieEditor'
import { card, inputBox, inputClass, type Notice, primaryButton, secondaryButton } from './ui'

interface Props {
  password: string
  fields: Field[]
  notify: (n: Notice) => void
}

type Open = { record: Partial<MovieRecord>; version: number } | null

/**
 * The Movies tab: the movies added so far (with whether AniChat has their latest version),
 * adding one from TMDb (prefilled: you only add what's missing) or by hand, and editing any.
 * Called by: AdminPage
 */
export function MoviesTab({ password, fields, notify }: Props) {
  const [records, setRecords] = useState<RecordSummary[] | null>(null)
  const [filter, setFilter] = useState('')
  const [open, setOpen] = useState<Open>(null)
  const [adding, setAdding] = useState(false)
  const [query, setQuery] = useState({ q: '', year: '' })
  const [hits, setHits] = useState<TmdbHit[] | null>(null)
  const [sample, setSample] = useState(false) // local preview without a TMDb key
  const [busy, setBusy] = useState(false)

  /** Reload the list. Called by: first render, after closing the editor */
  const reload = useCallback(
    () => listRecords(password).then(setRecords).catch((e: Error) => notify({ kind: 'error', text: e.message })),
    [password, notify],
  )
  useEffect(() => {
    void reload()
  }, [reload])

  /** Search TMDb. Called by: the search form */
  const search = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const found = await searchTmdb(password, query.q, query.year)
      setHits(found.results)
      setSample(Boolean(found.sample))
    } catch (err) {
      notify({ kind: 'error', text: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  /** Open a TMDb movie: the saved record if it was added before, else TMDb's details as a new one. Called by: a search hit */
  const pick = async (hit: TmdbHit) => {
    setBusy(true)
    try {
      const { record, existing } = await tmdbMovie(password, hit.tmdb_id)
      if (existing) {
        const saved = await getRecord(password, existing)
        notify({ kind: 'ok', text: `"${saved.title}" was added before: opened it for editing.` })
        setOpen({ record: saved, version: saved.version })
      } else {
        setOpen({ record, version: 0 })
      }
      setAdding(false)
      setHits(null)
    } catch (err) {
      notify({ kind: 'error', text: (err as Error).message })
    } finally {
      setBusy(false)
    }
  }

  /** Open a saved movie. Called by: the list */
  const edit = async (id: string) => {
    try {
      const saved = await getRecord(password, id)
      setOpen({ record: saved, version: saved.version })
    } catch (err) {
      notify({ kind: 'error', text: (err as Error).message })
    }
  }

  if (open) {
    return (
      <MovieEditor key={`${open.record.id}-${open.version}`} password={password} fields={fields} record={open.record}
                   baseVersion={open.version} notify={notify} onSaved={() => void reload()}
                   onClose={() => { setOpen(null); void reload() }} />
    )
  }

  const shown = (records ?? []).filter((r) => !r.deleted && r.title.toLowerCase().includes(filter.toLowerCase()))
  const waiting = (records ?? []).filter((r) => !r.synced).length

  return (
    <div className="space-y-6">
      {adding ? (
        <div className={`${card} space-y-4`}>
          <form onSubmit={search} className="flex gap-2">
            <input aria-label="Movie name" value={query.q} onChange={(e) => setQuery({ ...query, q: e.target.value })}
                   placeholder="Movie name" className={`${inputBox} min-w-0 flex-1`} autoFocus />
            <input aria-label="Year" value={query.year} onChange={(e) => setQuery({ ...query, year: e.target.value })}
                   placeholder="Year" inputMode="numeric" maxLength={4} className={`${inputBox} w-24 shrink-0`} />
            <button type="submit" disabled={busy || !query.q.trim()} className={`${primaryButton} shrink-0`} aria-label="Search TMDb">
              <Search size={18} />
            </button>
          </form>
          {sample && (
            <p className="rounded-lg bg-panel-2 px-3 py-2 text-sm text-muted">
              Local preview without a TMDb key: only the sample movies <b>Iron Man</b> and <b>Stree 2</b> can be found.
              Put <code>TMDB_READ_TOKEN</code> in AniChat's <code>.env</code> and restart the preview to search every movie,
              or add this one by hand.
            </p>
          )}
          {hits && hits.length === 0 && !sample && <p className="text-sm text-muted">TMDb found nothing. Check the spelling, or add it by hand.</p>}
          {hits && hits.length > 0 && (
            <ul className="divide-y divide-line">
              {hits.map((h) => (
                <li key={h.tmdb_id}>
                  <button type="button" disabled={busy} onClick={() => void pick(h)} className="w-full py-2.5 text-left hover:bg-panel-2">
                    <span className="font-medium">{h.title}</span> <span className="text-muted">{h.year ?? ''}</span>
                    {h.overview && <span className="block truncate text-sm text-muted">{h.overview}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex gap-2">
            <button type="button" className={secondaryButton}
                    onClick={() => { setOpen({ record: { title: query.q, year: Number(query.year) || null }, version: 0 }); setAdding(false) }}>
              Add by hand instead
            </button>
            <button type="button" className={secondaryButton} onClick={() => { setAdding(false); setHits(null) }}>Cancel</button>
          </div>
        </div>
      ) : (
        <button type="button" onClick={() => setAdding(true)} className={`${primaryButton} flex w-full items-center justify-center gap-2`}>
          <Plus size={18} aria-hidden /> Add a movie
        </button>
      )}

      <section>
        <div className="mb-3 flex items-center gap-3">
          <h2 className="font-semibold">Movies <span className="text-sm font-normal text-muted">({shown.length})</span></h2>
          {waiting > 0 && <span className="text-xs text-muted">{waiting} waiting for the laptop's sync</span>}
        </div>
        {(records?.length ?? 0) > 5 && (
          <input aria-label="Filter movies" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter…"
                 className={`${inputClass} mb-3`} />
        )}
        {records === null ? <p className="text-sm text-muted">Loading…</p> : shown.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-muted"><Film size={16} aria-hidden /> No movies yet.</p>
        ) : (
          <ul className="space-y-2">
            {shown.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => void edit(r.id)}
                        className="flex w-full items-center gap-3 rounded-xl border border-line bg-panel px-4 py-3 text-left text-sm hover:bg-panel-2">
                  {r.synced ? <CheckCircle2 size={16} className="shrink-0 text-green-500" aria-label="in AniChat" />
                    : <Clock size={16} className="shrink-0 text-muted" aria-label="waiting for the laptop's sync" />}
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{r.title}</span> <span className="text-muted">{r.year ?? ''}</span>
                    <span className="block text-xs text-muted">
                      {r.cast} cast · {r.values} values · edited {new Date(r.updated_at).toLocaleDateString()}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
