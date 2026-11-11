/**
 * Vercel function for the admin form's free entries (anime, series, other facts): saved in Upstash
 * while the laptop is off; scripts/sync_submissions.py brings them in later. Movies have their
 * own editable records (api/records.ts).
 *
 *   GET    /api/submissions          the latest entries with their status
 *   POST   /api/submissions          add an entry (JSON body: EntryInput)
 *   DELETE /api/submissions?id=...   remove an entry that is still pending
 *
 * Every call needs "Authorization: Bearer <ADMIN_PASSWORD>" (see api/_lib.ts).
 */
import { randomUUID } from 'node:crypto'
import { guarded, hashValues, json, readJson, redis } from './_lib.js'
import { type EntryInput, validateEntry } from './_submission.js'

const KEY = 'anichat:submissions'
const LIST_LIMIT = 50

/** The latest entries, newest first. */
export function GET(request: Request): Promise<Response> {
  return guarded(request, async () => {
    const entries = await hashValues<{ submitted_at: string }>(KEY)
    entries.sort((x, y) => y.submitted_at.localeCompare(x.submitted_at))
    return json({ entries: entries.slice(0, LIST_LIMIT), total: entries.length })
  })
}

/** Save a new entry (status "pending"). */
export function POST(request: Request): Promise<Response> {
  return guarded(request, async () => {
    const input = await readJson<EntryInput>(request, 60_000)
    if (input instanceof Response) return input
    const entry = validateEntry(input, randomUUID(), new Date())
    if (typeof entry === 'string') return json({ error: entry }, 400)
    await redis('HSET', KEY, entry.id, JSON.stringify(entry))
    return json({ entry }, 201)
  })
}

/** Remove an entry that the laptop has not processed yet (a mistake). */
export function DELETE(request: Request): Promise<Response> {
  return guarded(request, async () => {
    const id = new URL(request.url).searchParams.get('id') ?? ''
    const stored = (await redis('HGET', KEY, id)) as string | null
    if (!stored) return json({ error: 'no such entry' }, 404)
    if ((JSON.parse(stored) as { status: string }).status !== 'pending') {
      return json({ error: 'already processed: it is in the index now' }, 409)
    }
    await redis('HDEL', KEY, id)
    return json({ deleted: id })
  })
}
