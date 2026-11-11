import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { call, memoryRedis } from './_fake'
import { parseDayRows, SUGGESTED_FIELDS, slug, tmdbRecord, validateField, validateRecord, type Field } from './_records'
import * as fieldsApi from './fields'
import * as recordsApi from './records'

const PW = 'secret-pass'
const money = (id: string, label: string): Field =>
  ({ id, label, type: 'money', group: 'Box office', applies_to: ['movie'], currency: 'INR', unit: 'crore', order: 0 })

describe('fields', () => {
  it('get a fixed id from their first name and keep it when renamed', () => {
    const f = validateField({ label: 'India Net Collection!', type: 'money', currency: 'INR', unit: 'crore' }, []) as Field
    expect(f).toMatchObject({ id: 'india_net_collection', type: 'money', currency: 'INR', unit: 'crore', applies_to: ['movie'] })
    const renamed = validateField({ ...f, label: 'India net', type: 'text' }, [f]) as Field
    expect(renamed).toMatchObject({ id: 'india_net_collection', label: 'India net', type: 'money' }) // type can't change
  })

  it('refuse a second field with the same name', () => {
    const f = money('india_net', 'India net')
    expect(validateField({ label: 'India Net' }, [f])).toContain('already')
    expect(validateField({ label: 'india-net', type: 'money' }, [f])).toContain('already exists')
  })

  it('suggested ones are valid', () => {
    const made: Field[] = []
    for (const s of SUGGESTED_FIELDS) {
      const f = validateField(s, made)
      expect(typeof f).toBe('object')
      made.push(f as Field)
    }
    expect(made.map((f) => f.id)).toEqual(SUGGESTED_FIELDS.map((s) => slug(s.label)))
    // The ids TMDb's budget and revenue are filled into (tmdbRecord).
    expect(made.map((f) => f.id)).toEqual(expect.arrayContaining(['budget_usd', 'worldwide_gross_usd']))
  })
})

describe('records', () => {
  const fields = [money('india_net', 'India net'),
    { ...money('daywise', 'India net (day-wise)'), type: 'daywise' as const },
    { id: 'ott', label: 'OTT platform', type: 'list' as const, group: 'Streaming', applies_to: ['movie'], order: 1 }]

  it('are cleaned and checked against the fields', () => {
    const r = validateRecord({ title: ' Stree 2 ', year: 2024, cast: [{ name: 'Rajkummar Rao', character: 'Vicky' }, { name: ' ', character: 'x' }],
      values: { india_net: '₹ 597.99 Cr', daywise: [{ label: 'Day 1', value: '55.4' as unknown as number }], ott: 'Prime Video, , JioHotstar' },
      directors: 'Amar Kaushik' as unknown as string[] }, fields)
    expect(r).toMatchObject({ id: 'm-stree_2-2024', title: 'Stree 2', cast: [{ name: 'Rajkummar Rao', character: 'Vicky' }],
      directors: ['Amar Kaushik'], values: { india_net: 597.99, daywise: [{ label: 'Day 1', value: 55.4 }], ott: ['Prime Video', 'JioHotstar'] } })
  })

  it('refuse values of unknown or mistyped fields', () => {
    expect(validateRecord({ title: 'x', values: { box_office: 5 } }, fields)).toContain('unknown field "box_office"')
    expect(validateRecord({ title: 'x', values: { india_net: 'a lot' } }, fields)).toContain('not a number')
  })

  it('parse day-wise rows pasted from a box office site', () => {
    expect(parseDayRows('Day\tIndia Net Collection\tChange\nDay 1 [1st Thursday]\t₹ 55.4 Cr\t-\nDay 2 [1st Friday]\t₹ 35.3 Cr\t-36.28%\nTotal\t₹ 90.7 Cr\t'))
      .toEqual([{ label: 'Day 1 [1st Thursday]', value: 55.4 }, { label: 'Day 2 [1st Friday]', value: 35.3 }])
    expect(parseDayRows('Day 1: ₹ 1,021.5 Cr\nWeek 2 - 41 crore\nnothing here\nDay 9 [2nd Friday] ₹ 21 Cr'))
      .toEqual([{ label: 'Day 1', value: 1021.5 }, { label: 'Week 2', value: 41 }, { label: 'Day 9 [2nd Friday]', value: 21 }])
    // Each cell on its own line (how some browsers copy a table), with a header and change cells.
    expect(parseDayRows('Day\nIndia Net Collection\nDay 1 [1st Friday]\n₹ 64.85 Cr\n-\nDay 2 [1st Saturday]\n₹ 48.05 Cr\n-25.9%\nTotal\n₹ 112.9 Cr'))
      .toEqual([{ label: 'Day 1 [1st Friday]', value: 64.85 }, { label: 'Day 2 [1st Saturday]', value: 48.05 }])
    // A column of amounts only.
    expect(parseDayRows('64.85\n48.05\n69.80')).toEqual([{ label: 'Day 1', value: 64.85 }, { label: 'Day 2', value: 48.05 },
      { label: 'Day 3', value: 69.8 }])
  })

  it('come from TMDb with crew, cast and the USD money fields that exist', () => {
    const r = tmdbRecord({ id: 1726, title: 'Iron Man', original_title: 'Iron Man', release_date: '2008-04-30', runtime: 126,
      budget: 140000000, revenue: 585174222, original_language: 'en', spoken_languages: [{ iso_639_1: 'en', english_name: 'English' }],
      credits: { cast: [{ name: 'Robert Downey Jr.', character: 'Tony Stark' }],
        crew: [{ name: 'Jon Favreau', job: 'Director' }, { name: 'Ramin Djawadi', job: 'Original Music Composer' }] } },
    [{ ...money('budget_usd', 'Budget (USD)'), currency: 'USD', unit: '' }])
    expect(r).toMatchObject({ id: 'tmdb-1726', year: 2008, language: 'English', original_title: '', directors: ['Jon Favreau'],
      music: ['Ramin Djawadi'], cast: [{ name: 'Robert Downey Jr.', character: 'Tony Stark' }], values: { budget_usd: 140000000 } })
    expect(r.values).not.toHaveProperty('worldwide_gross_usd') // that field doesn't exist
  })
})

describe('records function', () => {
  beforeEach(() => {
    vi.stubEnv('ADMIN_PASSWORD', PW)
    vi.stubEnv('KV_REST_API_URL', 'https://fake.upstash.io')
    vi.stubEnv('KV_REST_API_TOKEN', 'token')
    vi.stubGlobal('fetch', vi.fn(memoryRedis()))
  })
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('saves versions, refuses stale edits, keeps history and marks deletions', async () => {
    await fieldsApi.PUT(call('/api/fields', 'PUT', PW, { fields: [{ label: 'India net', type: 'money', unit: 'crore' }] }))
    const created = await recordsApi.PUT(call('/api/records', 'PUT', PW, { record: { title: 'Stree 2', year: 2024, values: { india_net: 500 } }, base_version: 0 }))
    expect(created.status).toBe(201)
    const { record } = (await created.json()) as { record: { id: string; version: number } }
    expect(record.version).toBe(1)

    // Re-release: the collection changes.
    const edited = await recordsApi.PUT(call('/api/records', 'PUT', PW, { record: { ...record, values: { india_net: 598 } }, base_version: 1 }))
    expect(((await edited.json()) as { record: { version: number } }).record.version).toBe(2)
    // Another device still had version 1 open: refused, with the current version.
    const stale = await recordsApi.PUT(call('/api/records', 'PUT', PW, { record: { ...record, values: { india_net: 1 } }, base_version: 1 }))
    expect(stale.status).toBe(409)
    expect(((await stale.json()) as { current: { values: { india_net: number } } }).current.values.india_net).toBe(598)

    const history = (await (await recordsApi.GET(call(`/api/records?id=${record.id}&history=1`, 'GET', PW))).json()) as { history: { version: number }[] }
    expect(history.history.map((h) => h.version)).toEqual([1])

    const list = (await (await recordsApi.GET(call('/api/records', 'GET', PW))).json()) as { records: { id: string; synced: boolean }[] }
    expect(list.records).toMatchObject([{ id: record.id, synced: false }])

    expect((await recordsApi.DELETE(call(`/api/records?id=${record.id}`, 'DELETE', PW))).status).toBe(200)
    const gone = (await (await recordsApi.GET(call(`/api/records?id=${record.id}`, 'GET', PW))).json()) as { record: { deleted: boolean; version: number } }
    expect(gone.record).toMatchObject({ deleted: true, version: 3 })
  })

  it('refuses a value for a field that was never created', async () => {
    const res = await recordsApi.PUT(call('/api/records', 'PUT', PW, { record: { title: 'x', values: { collection: 5 } }, base_version: 0 }))
    expect(res.status).toBe(400)
  })
})

describe('day-wise validation', () => {
  it('names the row that is incomplete', () => {
    const f: Field = { id: 'd', label: 'India net (day-wise)', type: 'daywise', group: 'Box office', applies_to: ['movie'], order: 0 }
    expect(validateRecord({ title: 'x', values: { d: [{ label: 'Day 1', value: 5 }, { label: 'Day 2', value: '' as unknown as number }] } }, [f]))
      .toBe('India net (day-wise): row 2 (Day 2) has no amount. Fill it in or remove the row.')
  })
})
