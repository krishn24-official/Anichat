import { ArrowLeft, Check, CircleAlert, LogOut, X } from 'lucide-react'
import { type FormEvent, useCallback, useEffect, useState } from 'react'
import type { Field } from '../../api/_records'
import { AdminError, listFields } from './adminApi'
import { EntriesTab } from './EntriesTab'
import { FieldsTab } from './FieldsTab'
import { MoviesTab } from './MoviesTab'
import { card, inputClass, labelClass, load, type Notice, primaryButton, store } from './ui'

const PASSWORD_KEY = 'anichat-admin-password'
const TAB_KEY = 'anichat-admin-tab'
const TABS = [
  { id: 'movies', label: 'Movies' },
  { id: 'fields', label: 'Fields' },
  { id: 'entries', label: 'Other entries' },
] as const
type Tab = (typeof TABS)[number]['id']

/**
 * /admin: add and edit knowledge from anywhere (phone included). Movies are editable records
 * (TMDb-prefilled); fields keep names consistent; other entries add facts to anime/series.
 * Everything waits in the cloud until `python -m scripts.sync_submissions` runs on the laptop.
 * Called by: Root.tsx (when the path is /admin)
 */
export default function AdminPage() {
  const [password, setPassword] = useState(() => load(PASSWORD_KEY) ?? '')
  const [remember, setRemember] = useState(() => load(PASSWORD_KEY) !== null)
  const [fields, setFields] = useState<Field[] | null>(null) // loaded = signed in
  const [busy, setBusy] = useState(() => load(PASSWORD_KEY) !== null) // signing in with the saved password
  const [notice, setNotice] = useState<Notice>(null)
  const [tab, setTab] = useState<Tab>(() => (TABS.some((t) => t.id === load(TAB_KEY)) ? load(TAB_KEY) as Tab : 'movies'))

  /** Check the password by loading the fields. Called by: sign-in, the saved-password effect */
  const signInWith = useCallback(
    (pw: string) =>
      listFields(pw)
        .then((f) => {
          setFields(f)
          setNotice(null)
        })
        .catch((e: Error) => {
          if (e instanceof AdminError && e.status === 401) store(PASSWORD_KEY, null)
          setNotice({ kind: 'error', text: e.message })
        })
        .finally(() => setBusy(false)),
    [],
  )

  // Signed in automatically when this device remembers the password.
  useEffect(() => {
    const saved = load(PASSWORD_KEY)
    if (saved) void signInWith(saved)
  }, [signInWith])

  /** Sign in with the typed password. Called by: the sign-in form */
  const signIn = (e: FormEvent) => {
    e.preventDefault()
    store(PASSWORD_KEY, remember ? password : null)
    setBusy(true)
    void signInWith(password)
  }

  /** Forget the password on this device. Called by: "Sign out" */
  const signOut = () => {
    store(PASSWORD_KEY, null)
    setPassword('')
    setFields(null)
  }

  /** Switch tab (remembered). Called by: the tab bar */
  const choose = (t: Tab) => {
    setTab(t)
    store(TAB_KEY, t)
  }

  const notify = useCallback((n: Notice) => setNotice(n), [])

  return (
    <div className="min-h-full bg-bg">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex max-w-2xl items-center gap-3 px-4 py-3">
          <a href="/" className="text-muted hover:text-text" title="Back to the chat"><ArrowLeft size={18} aria-hidden /></a>
          <h1 className="text-lg font-semibold tracking-tight">AniChat admin</h1>
          {fields && (
            <button type="button" onClick={signOut} className="ml-auto flex items-center gap-1.5 text-sm text-muted hover:text-text">
              <LogOut size={15} aria-hidden /> Sign out
            </button>
          )}
        </div>
        {fields && (
          <nav className="mx-auto flex max-w-2xl gap-1 px-4" aria-label="Sections">
            {TABS.map((t) => (
              <button key={t.id} type="button" onClick={() => choose(t.id)} aria-current={tab === t.id ? 'page' : undefined}
                      className={`border-b-2 px-3 py-2 text-sm ${tab === t.id ? 'border-accent font-medium' : 'border-transparent text-muted'}`}>
                {t.label}
              </button>
            ))}
          </nav>
        )}
      </header>

      <main className="mx-auto max-w-2xl px-4 py-6">
        {notice && (
          <p role={notice.kind === 'error' ? 'alert' : 'status'}
             className={`mb-4 flex items-start gap-2 rounded-xl border px-4 py-3 text-sm ${notice.kind === 'error'
               ? 'border-accent/40 bg-accent-soft' : 'border-line bg-panel'}`}>
            {notice.kind === 'error' ? <CircleAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
              : <Check size={16} className="mt-0.5 shrink-0" aria-hidden />}
            <span className="flex-1">{notice.text}</span>
            <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss"><X size={15} /></button>
          </p>
        )}

        {!fields ? (
          <form onSubmit={signIn} className={`${card} space-y-4`}>
            <p className="text-sm text-muted">Changes are saved online and reach AniChat the next time the sync runs on the laptop.</p>
            <div>
              <label htmlFor="pw" className={labelClass}>Admin password</label>
              <input id="pw" type="password" autoComplete="current-password" value={password}
                     onChange={(e) => setPassword(e.target.value)} className={inputClass} />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              Remember on this device
            </label>
            <button type="submit" disabled={!password || busy} className={`${primaryButton} w-full`}>
              {busy ? 'Checking…' : 'Sign in'}
            </button>
          </form>
        ) : tab === 'movies' ? (
          <MoviesTab password={password} fields={fields} notify={notify} />
        ) : tab === 'fields' ? (
          <FieldsTab password={password} fields={fields} onChange={setFields} notify={notify} />
        ) : (
          <EntriesTab password={password} fields={fields} notify={notify} />
        )}
      </main>
    </div>
  )
}
