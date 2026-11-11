/** Test helper: an in-memory stand-in for Upstash's REST API (the Redis commands the functions use). */
import { vi } from 'vitest'

export function fakeUpstash() {
  const hashes = new Map<string, Map<string, string>>()
  const lists = new Map<string, string[]>()
  const strings = new Map<string, string>()
  const hash = (key: string) => hashes.get(key) ?? hashes.set(key, new Map()).get(key)!
  const list = (key: string) => lists.get(key) ?? lists.set(key, []).get(key)!
  return vi.fn(async (_url: string, init: RequestInit) => {
    const [cmd, key, ...args] = JSON.parse(String(init.body)) as string[]
    let result: unknown = null
    switch (cmd) {
      case 'HSET': hash(key).set(args[0], args[1]); result = 1; break
      case 'HGET': result = hash(key).get(args[0]) ?? null; break
      case 'HDEL': result = Number(hash(key).delete(args[0])); break
      case 'HEXISTS': result = Number(hash(key).has(args[0])); break
      case 'HGETALL': result = [...hash(key).entries()].flat(); break
      case 'LPUSH': list(key).unshift(args[0]); result = list(key).length; break
      case 'LTRIM': lists.set(key, list(key).slice(Number(args[0]), Number(args[1]) + 1)); result = 'OK'; break
      case 'LRANGE': result = list(key).slice(Number(args[0]), Number(args[1]) + 1); break
      case 'GET': result = strings.get(key) ?? null; break
      case 'INCR': strings.set(key, String(Number(strings.get(key) ?? 0) + 1)); result = Number(strings.get(key)); break
      case 'EXPIRE': result = 1; break
      default: throw new Error(`fake Upstash: no ${cmd}`)
    }
    return new Response(JSON.stringify({ result }), { status: 200 })
  })
}

/** A request with the admin password (or another one). */
export function call(path: string, method: string, password: string, body?: unknown): Request {
  return new Request(`https://anichat.vercel.app${path}`, {
    method, body: body === undefined ? undefined : JSON.stringify(body),
    headers: { Authorization: `Bearer ${password}`, 'x-forwarded-for': '1.2.3.4' },
  })
}
