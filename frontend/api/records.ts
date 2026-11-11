/**
 * Vercel function: movie records, editable at any time from the admin form. The laptop's
 * scripts/sync_submissions.py rebuilds the documents of records that changed since it last ran.
 *
 *   GET    /api/records                  every record, summarised (with "synced": in AniChat yet?)
 *   GET    /api/records?id=...           one record in full
 *   GET    /api/records?id=...&history=1 its previous versions (the last 20)
 *   PUT    /api/records                  save: {record, base_version} (0 for a new record)
 *   DELETE /api/records?id=...           remove (the laptop then drops it from the index)
 *
 * A save names the version it was edited from: if the record changed since (another device),
 * it is refused with 409 and the current version, so nothing is overwritten unseen.
 * Every call needs "Authorization: Bearer <ADMIN_PASSWORD>".
 */
import { FIELDS_KEY, guarded, hashValues, json, readJson, RECORDS_KEY, redis, SYNCED_KEY } from './_lib.js'
import { type Field, type MovieRecord, validateRecord } from './_records.js'

const HISTORY = 20

/** A record's stored JSON, or null. Called by: GET, PUT, DELETE */
async function load(id: string): Promise<MovieRecord | null> {
  const stored = (await redis('HGET', RECORDS_KEY, id)) as string | null
  return stored ? (JSON.parse(stored) as MovieRecord) : null
}

/** Store a new version, keeping the previous one in the history. Called by: PUT, DELETE */
async function store(record: MovieRecord, previous: MovieRecord | null): Promise<void> {
  if (previous) {
    await redis('LPUSH', `anichat:history:${record.id}`, JSON.stringify(previous))
    await redis('LTRIM', `anichat:history:${record.id}`, 0, HISTORY - 1)
  }
  await redis('HSET', RECORDS_KEY, record.id, JSON.stringify(record))
}

/** The list, one record, or one record's history. */
export function GET(request: Request): Promise<Response> {
  return guarded(request, async () => {
    const params = new URL(request.url).searchParams
    const id = params.get('id')
    if (id && params.get('history')) {
      const items = ((await redis('LRANGE', `anichat:history:${id}`, 0, HISTORY - 1)) as string[] | null) ?? []
      return json({ history: items.map((s) => JSON.parse(s) as MovieRecord) })
    }
    if (id) {
      const record = await load(id)
      return record ? json({ record }) : json({ error: 'no such movie' }, 404)
    }
    const [records, synced] = await Promise.all([
      hashValues<MovieRecord>(RECORDS_KEY),
      redis('HGETALL', SYNCED_KEY) as Promise<string[] | null>,
    ])
    const syncedVersion = new Map<string, number>()
    const flat = synced ?? []
    for (let i = 0; i < flat.length; i += 2) syncedVersion.set(flat[i], Number(flat[i + 1]))
    const list = records.filter((r) => !r.deleted || syncedVersion.has(r.id)).map((r) => ({
      id: r.id, title: r.title, year: r.year, version: r.version, updated_at: r.updated_at, deleted: r.deleted ?? false,
      cast: r.cast.length, values: Object.keys(r.values).length, synced: syncedVersion.get(r.id) === r.version,
    }))
    list.sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    return json({ records: list })
  })
}

/** Save a record (new, or an edit of `base_version`). */
export function PUT(request: Request): Promise<Response> {
  return guarded(request, async () => {
    const body = await readJson<{ record: Partial<MovieRecord>; base_version: number }>(request, 400_000)
    if (body instanceof Response) return body
    const fields = await hashValues<Field>(FIELDS_KEY)
    const clean = validateRecord(body.record ?? {}, fields)
    if (typeof clean === 'string') return json({ error: clean }, 400)
    const previous = await load(clean.id)
    const base = Number(body.base_version ?? 0)
    if ((previous?.version ?? 0) !== base) {
      return json({ error: previous ? 'changed on another device since you opened it: reload to see the changes'
        : 'this movie was deleted', current: previous }, 409)
    }
    const now = new Date().toISOString()
    const record: MovieRecord = { ...clean, version: base + 1, created_at: previous?.created_at ?? now, updated_at: now }
    await store(record, previous)
    return json({ record }, previous ? 200 : 201)
  })
}

/** Mark a record deleted (kept until the laptop has removed it from the index). */
export function DELETE(request: Request): Promise<Response> {
  return guarded(request, async () => {
    const id = new URL(request.url).searchParams.get('id') ?? ''
    const previous = await load(id)
    if (!previous) return json({ error: 'no such movie' }, 404)
    const record: MovieRecord = { ...previous, deleted: true, version: previous.version + 1, updated_at: new Date().toISOString() }
    await store(record, previous)
    return json({ deleted: id })
  })
}
