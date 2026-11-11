/**
 * Shared by the admin functions (api/*.ts): Upstash Redis calls, JSON responses and the admin
 * password check. The leading "_" keeps Vercel from serving this file as an endpoint.
 *
 * Vercel environment variables: ADMIN_PASSWORD; KV_REST_API_URL / KV_REST_API_TOKEN (connect an
 * Upstash Redis store in the project's Storage tab); TMDB_READ_TOKEN (for api/tmdb.ts).
 */
import { timingSafeEqual } from 'node:crypto'

const MAX_FAILED_LOGINS = 10 // per IP per 15 minutes

/** Run one Redis command through Upstash's REST API. Called by: every admin function */
export async function redis(...command: (string | number)[]): Promise<unknown> {
  const url = process.env.KV_REST_API_URL ?? process.env.UPSTASH_REDIS_REST_URL
  const token = process.env.KV_REST_API_TOKEN ?? process.env.UPSTASH_REDIS_REST_TOKEN
  if (!url || !token) throw new Error('storage is not connected (KV_REST_API_URL / KV_REST_API_TOKEN)')
  const res = await fetch(url, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(command),
  })
  const body = (await res.json()) as { result?: unknown; error?: string }
  if (!res.ok || body.error) throw new Error(`storage error: ${body.error ?? res.status}`)
  return body.result
}

/** All values of a Redis hash, parsed from JSON. Called by: api/fields.ts, api/records.ts, api/submissions.ts */
export async function hashValues<T>(key: string): Promise<T[]> {
  const flat = ((await redis('HGETALL', key)) as string[] | null) ?? []
  return flat.filter((_, i) => i % 2 === 1).map((v) => JSON.parse(v) as T)
}

/** A JSON response that is never cached. Called by: every admin function */
export function json(data: unknown, status = 200): Response {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } })
}

/** The request body as JSON (at most `maxChars`), or an error response. Called by: POST/PUT handlers */
export async function readJson<T>(request: Request, maxChars: number): Promise<T | Response> {
  const text = await request.text()
  if (text.length > maxChars) return json({ error: 'too large' }, 413)
  try {
    return JSON.parse(text) as T
  } catch {
    return json({ error: 'body is not JSON' }, 400)
  }
}

/**
 * null when the request carries the admin password, else the error response. Wrong passwords
 * are counted per IP so the password can't be guessed by trying many.
 * Called by: every admin function, before anything else
 */
export async function denied(request: Request): Promise<Response | null> {
  const expected = process.env.ADMIN_PASSWORD
  if (!expected) return json({ error: 'ADMIN_PASSWORD is not set on the server' }, 500)
  const ip = (request.headers.get('x-forwarded-for') ?? 'unknown').split(',')[0].trim()
  const failKey = `anichat:failed-login:${ip}`
  const failures = Number((await redis('GET', failKey)) ?? 0)
  if (failures >= MAX_FAILED_LOGINS) return json({ error: 'too many wrong passwords, try again in 15 minutes' }, 429)
  const given = Buffer.from((request.headers.get('authorization') ?? '').replace(/^Bearer\s+/i, ''))
  const wanted = Buffer.from(expected)
  if (given.length === wanted.length && timingSafeEqual(given, wanted)) return null
  await redis('INCR', failKey)
  await redis('EXPIRE', failKey, 900)
  return json({ error: 'wrong password' }, 401)
}

/** Run a handler, turning any thrown error into a 500 JSON response. Called by: every admin function */
export async function guarded(request: Request, handler: () => Promise<Response>): Promise<Response> {
  try {
    const no = await denied(request)
    return no ?? (await handler())
  } catch (e) {
    return json({ error: (e as Error).message }, 500)
  }
}

/** Redis keys of the admin data. */
export const FIELDS_KEY = 'anichat:fields' // field id -> Field
export const RECORDS_KEY = 'anichat:records' // record id -> MovieRecord
export const SYNCED_KEY = 'anichat:synced' // record id -> the version the laptop has indexed
