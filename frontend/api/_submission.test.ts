import { describe, expect, it } from 'vitest'
import { validateEntry } from './_submission'

const now = new Date('2026-11-11T10:00:00Z')

describe('validateEntry', () => {
  it('cleans a movie entry and defaults its series', () => {
    const entry = validateEntry({ type: 'Movie', title: ' Iron Man ', year: '2008', use_tmdb: true,
      facts: { 'India collection ': '₹20 crore', empty: ' ' } }, 'id1', now)
    expect(entry).toMatchObject({ id: 'id1', type: 'movie', series: 'movies', title: 'Iron Man', year: 2008,
      use_tmdb: true, facts: { 'india collection': '₹20 crore' }, status: 'pending', submitted_at: now.toISOString() })
  })

  it('turns a series name into an id and drops TMDb for non-movies', () => {
    const entry = validateEntry({ type: 'anime', series: 'Naruto Shippuden', title: 'Itachi', notes: 'x', use_tmdb: true }, 'i', now)
    expect(entry).toMatchObject({ series: 'naruto_shippuden', use_tmdb: false })
  })

  it.each([
    [{ type: 'song', title: 'x', notes: 'y' }, 'unknown type'],
    [{ type: 'anime', title: '  ', notes: 'y' }, 'missing title'],
    [{ type: 'anime', title: 'Naruto', notes: 'y' }, 'missing series'],
    [{ type: 'movie', title: 'x', year: 'soon', notes: 'y' }, 'not a valid year'],
    [{ type: 'other', series: 'other', title: 'x' }, 'nothing to add'],
  ])('rejects %j', (input, reason) => {
    expect(validateEntry(input, 'i', now)).toContain(reason)
  })
})
