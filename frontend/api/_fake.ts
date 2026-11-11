/**
 * An in-memory stand-in for Upstash's REST API (the Redis commands the functions use). Used by
 * the tests (fakeUpstash) and by the local admin preview (dev/adminPreview.ts).
 */

/** The whole store as plain JSON (the preview saves it to a file between restarts). */
export interface Snapshot {
  hashes: Record<string, Record<string, string>>
  lists: Record<string, string[]>
  strings: Record<string, string>
}

const WRITES = new Set(['HSET', 'HDEL', 'LPUSH', 'LTRIM', 'INCR'])

/**
 * A fetch-like function answering Upstash REST calls from memory, optionally starting from a
 * snapshot and reporting every change (`onChange`).
 * Called by: the tests, dev/adminPreview.ts
 */
export function memoryRedis(start?: Snapshot, onChange?: (s: Snapshot) => void) {
  const hashes = new Map(Object.entries(start?.hashes ?? {}).map(([k, v]) => [k, new Map(Object.entries(v))]))
  const lists = new Map(Object.entries(start?.lists ?? {}).map(([k, v]) => [k, [...v]]))
  const strings = new Map(Object.entries(start?.strings ?? {}))
  const hash = (key: string) => hashes.get(key) ?? hashes.set(key, new Map()).get(key)!
  const list = (key: string) => lists.get(key) ?? lists.set(key, []).get(key)!
  const snapshot = (): Snapshot => ({
    hashes: Object.fromEntries([...hashes].map(([k, v]) => [k, Object.fromEntries(v)])),
    lists: Object.fromEntries(lists), strings: Object.fromEntries(strings),
  })
  return async (_url: string, init: RequestInit): Promise<Response> => {
    const [cmd, key, ...args] = (JSON.parse(String(init.body)) as unknown[]).map(String)
    try {
      return await run(cmd, key, args)
    } finally {
      if (onChange && WRITES.has(cmd)) onChange(snapshot())
    }
  }

  /** One command. Called by: the returned function */
  async function run(cmd: string, key: string, args: string[]): Promise<Response> {
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
      default: return new Response(JSON.stringify({ error: `memory store: no ${cmd}` }), { status: 400 })
    }
    return new Response(JSON.stringify({ result }), { status: 200 })
  }
}

/** A request with the admin password (or another one). Called by: the tests */
export function call(path: string, method: string, password: string, body?: unknown): Request {
  return new Request(`https://anichat.vercel.app${path}`, {
    method, body: body === undefined ? undefined : JSON.stringify(body),
    headers: { Authorization: `Bearer ${password}`, 'x-forwarded-for': '1.2.3.4' },
  })
}
