import { Archive, ArchiveRestore, Pencil, Plus, Sparkles } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { APPLIES_TO, CURRENCIES, FIELD_TYPES, type Field, SUGGESTED_FIELDS, slug, UNITS } from '../../api/_records'
import { saveFields } from './adminApi'
import { card, inputClass, labelClass, type Notice, primaryButton, secondaryButton } from './ui'

const TYPE_HELP: Record<string, string> = {
  text: 'Text', number: 'Number', money: 'Money (₹ or $)', date: 'Date', list: 'List (several values)',
  daywise: 'Day-wise table (day → amount)', url: 'Link',
}

interface Props {
  password: string
  fields: Field[]
  onChange: (fields: Field[]) => void
  notify: (n: Notice) => void
}

/** A blank field form. Called by: FieldsTab */
const blank = (): Partial<Field> => ({ label: '', type: 'money', group: 'Box office', applies_to: ['movie'], currency: 'INR', unit: 'crore' })

/**
 * The Fields tab: the names every movie (and entry) uses, defined once so "collection" and
 * "box office" never become two different things. Renaming keeps the id; fields are archived,
 * never deleted.
 * Called by: AdminPage
 */
export function FieldsTab({ password, fields, onChange, notify }: Props) {
  const [draft, setDraft] = useState<Partial<Field> | null>(null)
  const [busy, setBusy] = useState(false)
  const existingIds = new Set(fields.map((f) => f.id))
  const missing = SUGGESTED_FIELDS.filter((s) => !existingIds.has(slug(s.label)))

  /** Save fields and merge them into the list. Called by: the form, archive buttons, suggestions */
  const save = async (changes: Partial<Field>[], done: string) => {
    setBusy(true)
    try {
      const saved = await saveFields(password, changes)
      const byId = new Map(fields.map((f) => [f.id, f]))
      for (const f of saved) byId.set(f.id, f)
      onChange([...byId.values()].sort((a, b) => a.order - b.order))
      setDraft(null)
      notify({ kind: 'ok', text: done })
    } catch (e) {
      notify({ kind: 'error', text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  /** Submit the create/edit form. Called by: the field form */
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (draft) void save([{ ...draft, order: draft.order ?? fields.length }], `Saved "${draft.label}".`)
  }

  const groups = [...new Set(fields.map((f) => f.group))]
  const isNew = draft !== null && !draft.id

  return (
    <div className="space-y-6">
      {missing.length > 0 && (
        <div className={card}>
          <p className="mb-3 flex items-center gap-2 font-medium"><Sparkles size={16} aria-hidden /> Suggested fields</p>
          <p className="mb-3 text-sm text-muted">Common box office and streaming fields. Add them all, then rename or archive any you don't want.</p>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {missing.map((s) => <span key={s.label} className="rounded-full bg-panel-2 px-2.5 py-1 text-xs">{s.label}</span>)}
          </div>
          <button type="button" disabled={busy} className={secondaryButton}
                  onClick={() => void save(missing.map((s, i) => ({ ...s, order: fields.length + i })), `Added ${missing.length} fields.`)}>
            Add these {missing.length} fields
          </button>
        </div>
      )}

      {draft ? (
        <form onSubmit={submit} className={`${card} space-y-4`}>
          <p className="font-medium">{isNew ? 'New field' : `Edit "${draft.label}"`}</p>
          <div>
            <label htmlFor="f-label" className={labelClass}>Name</label>
            <input id="f-label" value={draft.label ?? ''} onChange={(e) => setDraft({ ...draft, label: e.target.value })}
                   className={inputClass} placeholder="India net collection" />
            {isNew && draft.label && <p className="mt-1 text-xs text-muted">Saved as <code>{slug(draft.label)}</code> (this id never changes)</p>}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="f-type" className={labelClass}>Type {!isNew && '(fixed)'}</label>
              <select id="f-type" value={draft.type} disabled={!isNew} className={inputClass}
                      onChange={(e) => setDraft({ ...draft, type: e.target.value as Field['type'] })}>
                {FIELD_TYPES.map((t) => <option key={t} value={t}>{TYPE_HELP[t]}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="f-group" className={labelClass}>Group (section of the form)</label>
              <input id="f-group" list="f-groups" value={draft.group ?? ''} className={inputClass}
                     onChange={(e) => setDraft({ ...draft, group: e.target.value })} />
              <datalist id="f-groups">{groups.map((g) => <option key={g} value={g} />)}</datalist>
            </div>
          </div>
          {(draft.type === 'money' || draft.type === 'daywise' || draft.type === 'number') && (
            <div className="grid gap-4 sm:grid-cols-2">
              {draft.type !== 'number' && (
                <div>
                  <label htmlFor="f-cur" className={labelClass}>Currency</label>
                  <select id="f-cur" value={draft.currency ?? 'INR'} className={inputClass}
                          onChange={(e) => setDraft({ ...draft, currency: e.target.value as Field['currency'] })}>
                    {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
              )}
              <div>
                <label htmlFor="f-unit" className={labelClass}>Values are typed in</label>
                <select id="f-unit" value={draft.unit ?? ''} className={inputClass}
                        onChange={(e) => setDraft({ ...draft, unit: e.target.value as Field['unit'] })}>
                  {UNITS.map((u) => <option key={u} value={u}>{u || 'full amount'}</option>)}
                </select>
              </div>
            </div>
          )}
          <fieldset>
            <legend className={labelClass}>Used for</legend>
            <div className="flex flex-wrap gap-4">
              {APPLIES_TO.map((a) => (
                <label key={a} className="flex items-center gap-1.5 text-sm">
                  <input type="checkbox" checked={draft.applies_to?.includes(a) ?? false}
                         onChange={(e) => setDraft({ ...draft, applies_to: e.target.checked
                           ? [...(draft.applies_to ?? []), a] : (draft.applies_to ?? []).filter((x) => x !== a) })} />
                  {a}
                </label>
              ))}
            </div>
          </fieldset>
          <div>
            <label htmlFor="f-help" className={labelClass}>Hint (optional)</label>
            <input id="f-help" value={draft.help ?? ''} onChange={(e) => setDraft({ ...draft, help: e.target.value })}
                   className={inputClass} placeholder="From Sacnilk, in crore" />
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={busy || !draft.label?.trim()} className={`${primaryButton} flex-1`}>Save field</button>
            <button type="button" onClick={() => setDraft(null)} className={secondaryButton}>Cancel</button>
          </div>
        </form>
      ) : (
        <button type="button" onClick={() => setDraft(blank())} className={`${secondaryButton} flex items-center gap-1.5`}>
          <Plus size={15} aria-hidden /> New field
        </button>
      )}

      {groups.map((group) => (
        <section key={group}>
          <h3 className="mb-2 text-sm font-semibold text-muted">{group}</h3>
          <ul className="divide-y divide-line rounded-xl border border-line bg-panel">
            {fields.filter((f) => f.group === group).map((f) => (
              <li key={f.id} className={`flex items-center gap-3 px-4 py-2.5 text-sm ${f.archived ? 'opacity-50' : ''}`}>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{f.label}{f.archived && ' (archived)'}</p>
                  <p className="text-xs text-muted">
                    <code>{f.id}</code> · {TYPE_HELP[f.type]}{f.currency ? ` · ${f.currency}` : ''}{f.unit ? ` in ${f.unit}` : ''} · {f.applies_to.join(', ')}
                  </p>
                </div>
                <button type="button" aria-label={`Edit ${f.label}`} onClick={() => setDraft(f)} className="text-muted hover:text-text">
                  <Pencil size={15} />
                </button>
                <button type="button" aria-label={f.archived ? `Restore ${f.label}` : `Archive ${f.label}`} disabled={busy}
                        className="text-muted hover:text-text"
                        onClick={() => void save([{ ...f, archived: !f.archived }], f.archived ? `Restored "${f.label}".` : `Archived "${f.label}" (its values are kept).`)}>
                  {f.archived ? <ArchiveRestore size={15} /> : <Archive size={15} />}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {fields.length === 0 && !missing.length && <p className="text-sm text-muted">No fields yet.</p>}
    </div>
  )
}
