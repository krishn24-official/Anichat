import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { call, memoryRedis } from './_fake'
import { DELETE, GET, POST } from './submissions'

const path = '/api/submissions'

describe('submissions function', () => {
  beforeEach(() => {
    vi.stubEnv('ADMIN_PASSWORD', 'secret-pass')
    vi.stubEnv('KV_REST_API_URL', 'https://fake.upstash.io')
    vi.stubEnv('KV_REST_API_TOKEN', 'token')
    vi.stubGlobal('fetch', vi.fn(memoryRedis()))
  })
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('saves, lists and removes entries', async () => {
    const saved = await POST(call(path, 'POST', 'secret-pass', { type: 'anime', series: 'naruto', title: 'Naruto', notes: 'x' }))
    expect(saved.status).toBe(201)
    const { entry } = (await saved.json()) as { entry: { id: string; status: string } }
    expect(entry.status).toBe('pending')

    const listed = (await (await GET(call(path, 'GET', 'secret-pass'))).json()) as { entries: { title: string }[]; total: number }
    expect(listed.total).toBe(1)
    expect(listed.entries[0].title).toBe('Naruto')

    expect((await DELETE(call(`${path}?id=${entry.id}`, 'DELETE', 'secret-pass'))).status).toBe(200)
    expect(((await (await GET(call(path, 'GET', 'secret-pass'))).json()) as { total: number }).total).toBe(0)
  })

  it('rejects bad entries with the reason', async () => {
    const res = await POST(call(path, 'POST', 'secret-pass', { type: 'anime', title: 'Naruto', notes: 'x' }))
    expect(res.status).toBe(400)
    expect(((await res.json()) as { error: string }).error).toBe('missing series')
  })

  it('locks out an IP after repeated wrong passwords', async () => {
    for (let i = 0; i < 10; i++) expect((await GET(call(path, 'GET', 'guess' + i))).status).toBe(401)
    expect((await GET(call(path, 'GET', 'secret-pass'))).status).toBe(429)
  })
})
