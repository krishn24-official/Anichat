/**
 * Vercel function: the field definitions every record uses (see api/_records.ts Field).
 *
 *   GET /api/fields       all fields (archived ones too), in form order
 *   PUT /api/fields       create a field, or edit one (same id): body Field, or {fields: Field[]}
 *
 * Fields are never deleted, only archived, so values already saved stay meaningful.
 * Every call needs "Authorization: Bearer <ADMIN_PASSWORD>".
 */
import { FIELDS_KEY, guarded, hashValues, json, readJson, redis } from './_lib.js'
import { type Field, validateField } from './_records.js'

/** All fields, sorted by group order then position. */
export function GET(request: Request): Promise<Response> {
  return guarded(request, async () => {
    const fields = await hashValues<Field>(FIELDS_KEY)
    fields.sort((a, b) => a.order - b.order || a.label.localeCompare(b.label))
    return json({ fields })
  })
}

/** Create or update one field, or several at once (the "suggested fields" button). */
export function PUT(request: Request): Promise<Response> {
  return guarded(request, async () => {
    const body = await readJson<Partial<Field> | { fields: Partial<Field>[] }>(request, 100_000)
    if (body instanceof Response) return body
    const inputs = 'fields' in body && Array.isArray(body.fields) ? body.fields : [body as Partial<Field>]
    const existing = await hashValues<Field>(FIELDS_KEY)
    const saved: Field[] = []
    for (const input of inputs.slice(0, 100)) {
      const field = validateField(input, existing)
      if (typeof field === 'string') return json({ error: field, saved }, 400)
      await redis('HSET', FIELDS_KEY, field.id, JSON.stringify(field))
      const i = existing.findIndex((f) => f.id === field.id)
      if (i >= 0) existing[i] = field
      else existing.push(field)
      saved.push(field)
    }
    return json({ saved })
  })
}
