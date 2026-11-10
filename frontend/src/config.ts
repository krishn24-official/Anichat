/** Build-time settings (Vite env variables, see .env.example). */

/** Base URL of the AniChat API, without a trailing slash. Used by: services/api.ts */
export const API_URL: string = (import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, '')

/** How long to wait for an answer before giving up (the model can take ~10 s). */
export const REQUEST_TIMEOUT_MS = 60_000
