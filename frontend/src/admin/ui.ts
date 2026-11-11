/** Shared look and small helpers of the admin pages. */

/** An input without a width, for rows that size their inputs (w-1/2, flex-1...). */
export const inputBox = 'rounded-lg border border-line bg-panel px-3 py-2.5 text-base outline-none focus:border-accent'
export const inputClass = `w-full ${inputBox}`
export const labelClass = 'mb-1 block text-sm font-medium text-muted'
export const primaryButton = 'rounded-lg bg-accent px-4 py-2.5 font-medium text-white disabled:opacity-50'
export const secondaryButton = 'rounded-lg border border-line px-3 py-2 text-sm hover:bg-panel-2 disabled:opacity-50'
export const card = 'rounded-2xl border border-line bg-panel p-5'

/** localStorage read that never throws (private mode, blocked storage). Called by: the admin pages */
export function load(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** localStorage write (null: remove) that never throws. Called by: the admin pages */
export function store(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    /* storage unavailable: the page still works, it just won't remember */
  }
}

/** A message for the banner at the top of the admin page. */
export type Notice = { kind: 'ok' | 'error'; text: string } | null
