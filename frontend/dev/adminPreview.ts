/**
 * Local preview of the admin form (`npm run dev:admin`): serves the Vercel functions (api/*.ts)
 * from the Vite dev server, with a local store instead of Upstash (kept in .preview-store.json)
 * and sample TMDb data unless TMDB_READ_TOKEN is set. Password: "preview" (or ADMIN_PASSWORD).
 * Nothing leaves the laptop except real TMDb calls when a token is set.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import type { IncomingMessage, ServerResponse } from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Plugin, ViteDevServer } from 'vite'
import { memoryRedis, type Snapshot } from '../api/_fake.js'
import { sampleTmdb } from './tmdbSample.js'

const STORE_URL = 'https://preview-memory.local'
export const SAMPLE_TOKEN = 'sample' // api/tmdb.ts reports "sample: true" with it

/**
 * Some settings from AniChat's .env (one folder up), and nothing else from it: the TMDb key, and
 * with `live` the real store's URL and token (`npm run dev:admin:live`: the preview then edits
 * the same data as the deployed form).
 * Called by: adminPreview()
 */
function keysFromDotenv(live: boolean): Record<string, string> {
  try {
    const text = readFileSync(fileURLToPath(new URL('../../.env', import.meta.url)), 'utf8')
    const names = ['TMDB_READ_TOKEN', 'TMDB_API_KEY', ...(live ? ['KV_REST_API_URL', 'KV_REST_API_TOKEN'] : [])]
    const keys: Record<string, string> = {}
    for (const m of text.matchAll(/^([A-Z_]+)\s*=\s*["']?([^"'\r\n#]+?)["']?\s*$/gm)) if (names.includes(m[1])) keys[m[1]] = m[2]
    return keys
  } catch {
    return {}
  }
}

/** Read the request body. Called by: handle() */
function body(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = ''
    req.on('data', (chunk) => (data += chunk))
    req.on('end', () => resolve(data))
    req.on('error', reject)
  })
}

/** Run one function (api/<name>.ts, exported per HTTP method) like Vercel would. Called by: the middleware */
async function handle(server: ViteDevServer, req: IncomingMessage, res: ServerResponse, name: string): Promise<void> {
  const mod = (await server.ssrLoadModule(`/api/${name}.ts`)) as Record<string, (r: Request) => Promise<Response>>
  const method = req.method ?? 'GET'
  const handler = mod[method]
  if (!handler) {
    res.statusCode = 405
    res.end()
    return
  }
  const text = method === 'GET' || method === 'HEAD' ? undefined : await body(req)
  const headers = new Headers()
  for (const [k, v] of Object.entries(req.headers)) if (typeof v === 'string') headers.set(k, v)
  const response = await handler(new Request(`http://localhost${req.url}`, { method, headers, body: text }))
  res.statusCode = response.status
  response.headers.forEach((v, k) => res.setHeader(k, v))
  res.end(Buffer.from(await response.arrayBuffer()))
}

/** The Vite plugin. Used by: vite.config.ts in mode "admin" */
export function adminPreview(live = false): Plugin {
  return {
    name: 'anichat-admin-preview',
    apply: 'serve',
    configureServer(server) {
      process.env.ADMIN_PASSWORD ??= 'preview'
      // `live` (npm run dev:admin:live): the real store from AniChat's .env, the same data as the
      // deployed form. Otherwise a local store, kept in a file between restarts (git-ignored).

      for (const [key, value] of Object.entries(keysFromDotenv(live))) process.env[key] ??= value
      if (live && !(process.env.KV_REST_API_URL && process.env.KV_REST_API_TOKEN)) {
        throw new Error('dev:admin:live needs KV_REST_API_URL and KV_REST_API_TOKEN in AniChat/.env')
      }
      if (!live) {
        process.env.KV_REST_API_URL = STORE_URL
        process.env.KV_REST_API_TOKEN = 'preview'
      }
      const storeFile = path.resolve(server.config.root, '.preview-store.json')
      let saved: Snapshot | undefined
      try {
        saved = JSON.parse(readFileSync(storeFile, 'utf8')) as Snapshot
      } catch {
        saved = undefined // first start
      }
      const store = memoryRedis(saved, (s) => writeFileSync(storeFile, JSON.stringify(s)))
      const realFetch = globalThis.fetch
      const useSample = !process.env.TMDB_READ_TOKEN && !process.env.TMDB_API_KEY
      if (useSample) process.env.TMDB_READ_TOKEN = SAMPLE_TOKEN // answered by sampleTmdb(), never sent anywhere
      globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input instanceof Request ? input.url : input)
        if (!live && url.startsWith(STORE_URL)) return store(url, init ?? {})
        if (useSample && url.startsWith('https://api.tmdb.org/')) return sampleTmdb(url)
        return realFetch(input, init)
      }) as typeof fetch
      // The laptop's sync reads the local store like Upstash: KV_REST_API_URL=http://localhost:<port>/preview-store
      if (!live) server.middlewares.use('/preview-store', (req, res) => {
        const ok = req.method === 'POST' && req.headers.authorization === 'Bearer preview'
        if (!ok) {
          res.statusCode = 401
          res.end(JSON.stringify({ error: 'preview store: POST with "Bearer preview"' }))
          return
        }
        body(req).then((text) => store(STORE_URL, { body: text }))
          .then(async (r) => {
            res.statusCode = r.status
            res.setHeader('Content-Type', 'application/json')
            res.end(await r.text())
          })
          .catch((e: Error) => {
            res.statusCode = 500
            res.end(JSON.stringify({ error: e.message }))
          })
      })
      server.middlewares.use((req, res, next) => {
        const m = req.url?.match(/^\/api\/(submissions|fields|records|tmdb)(?:\?|$)/)
        if (!m) return next()
        handle(server, req, res, m[1]).catch((e: Error) => {
          res.statusCode = 500
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ error: e.message }))
        })
      })
      server.config.logger.info(
        `\n  Admin preview: http://localhost:${server.config.server.port ?? 5173}/admin  (password: ${process.env.ADMIN_PASSWORD === 'preview' ? 'preview' : 'your ADMIN_PASSWORD'})` +
        (live ? '\n  Store: LIVE (the deployed form\'s Upstash store: edits are real)'
          : `\n  Store: .preview-store.json (${saved ? 'loaded' : 'new'}); laptop sync: KV_REST_API_URL=http://localhost:${server.config.server.port ?? 5173}/preview-store`) +
        `\n  TMDb: ${useSample ? 'sample movies (Iron Man, Stree 2)' : 'real API'}\n`,
      )
    },
  }
}
