/**
 * Vercel function: TMDb lookups for the admin form, so the TMDb token stays on the server.
 *
 *   GET /api/tmdb?q=Iron+Man&year=2008   matching movies: [{tmdb_id, title, year, overview}]
 *   GET /api/tmdb?id=1726                 that movie as a new record for the editor, and whether
 *                                         it was added before ("existing": its record id)
 *
 * Needs TMDB_READ_TOKEN (or TMDB_API_KEY) on Vercel, and the admin password like every call.
 */
import { FIELDS_KEY, guarded, hashValues, json, RECORDS_KEY, redis } from './_lib.js'
import { type Field, type TmdbMovie, tmdbRecord } from './_records.js'

const API = 'https://api.themoviedb.org/3'

/** One TMDb API call. Called by: GET */
async function tmdb<T>(path: string, params: Record<string, string>): Promise<T> {
  const token = process.env.TMDB_READ_TOKEN
  const key = process.env.TMDB_API_KEY
  if (!token && !key) throw new Error('TMDB_READ_TOKEN is not set on the server')
  const query = new URLSearchParams(token ? params : { ...params, api_key: key ?? '' })
  const res = await fetch(`${API}${path}?${query}`, {
    headers: { Accept: 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  })
  if (res.status === 404) throw new Error('TMDb has no such movie')
  if (!res.ok) throw new Error(`TMDb error ${res.status}`)
  return (await res.json()) as T
}

/** Search, or one movie as a record. */
export function GET(request: Request): Promise<Response> {
  return guarded(request, async () => {
    const params = new URL(request.url).searchParams
    const id = params.get('id')
    if (id) {
      if (!/^\d+$/.test(id)) return json({ error: 'bad TMDb id' }, 400)
      const [movie, fields, existing] = await Promise.all([
        tmdb<TmdbMovie>(`/movie/${id}`, { append_to_response: 'credits' }),
        hashValues<Field>(FIELDS_KEY),
        redis('HEXISTS', RECORDS_KEY, `tmdb-${id}`),
      ])
      return json({ record: tmdbRecord(movie, fields), existing: existing ? `tmdb-${id}` : null })
    }
    const q = (params.get('q') ?? '').trim()
    if (!q) return json({ error: 'type a movie name' }, 400)
    const year = params.get('year') ?? ''
    const found = await tmdb<{ results: (TmdbMovie & { popularity?: number })[] }>('/search/movie', {
      query: q, include_adult: 'false', ...(/^\d{4}$/.test(year) ? { primary_release_year: year } : {}),
    })
    return json({
      results: found.results.slice(0, 12).map((m) => ({
        tmdb_id: m.id, title: m.title, year: m.release_date ? Number(m.release_date.slice(0, 4)) : null,
        overview: (m.overview ?? '').slice(0, 200),
      })),
    })
  })
}
