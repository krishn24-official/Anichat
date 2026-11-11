import { describe, expect, it } from 'vitest'
import type { Field } from '../../api/_records'
import { fromEditor, move, parseCastLines, rowsTotal, toEditor } from './recordForm'

const fields: Field[] = [
  { id: 'india_net', label: 'India net', type: 'money', group: 'Box office', applies_to: ['movie'], currency: 'INR', unit: 'crore', order: 0 },
  { id: 'daywise', label: 'Day-wise', type: 'daywise', group: 'Box office', applies_to: ['movie'], currency: 'INR', unit: 'crore', order: 1 },
  { id: 'ott', label: 'OTT', type: 'list', group: 'Streaming', applies_to: ['movie'], order: 2 },
]

describe('movie editor state', () => {
  it('round-trips a record through editable text', () => {
    const record = { id: 'tmdb-1', tmdb_id: 1, title: 'Stree 2', year: 2024, runtime: 147, directors: ['Amar Kaushik'],
      genres: ['Comedy', 'Horror'], cast: [{ name: 'Rajkummar Rao', character: 'Vicky' }], sources: ['https://a', 'https://b'],
      values: { india_net: 597.99, daywise: [{ label: 'Day 1', value: 55.4 }], ott: ['Prime Video', 'JioHotstar'] } }
    const state = toEditor(record, fields)
    expect(state).toMatchObject({ year: '2024', genres: 'Comedy, Horror', sources: 'https://a\nhttps://b',
      values: { india_net: '597.99', ott: 'Prime Video, JioHotstar', daywise: [{ label: 'Day 1', value: '55.4' }] } })
    expect(fromEditor(state)).toMatchObject({ title: 'Stree 2', year: 2024, runtime: 147, genres: ['Comedy', 'Horror'],
      directors: ['Amar Kaushik'], sources: ['https://a', 'https://b'],
      values: { india_net: '597.99', ott: 'Prime Video, JioHotstar', daywise: [{ label: 'Day 1', value: '55.4' }] } })
  })

  it('drops empty values, empty day rows and nameless cast', () => {
    const state = { ...toEditor({ title: 'x' }, fields), values: { india_net: ' ', daywise: [{ label: '', value: '' }] },
      cast: [{ name: ' ', character: 'nobody' }] }
    expect(fromEditor(state)).toMatchObject({ values: {}, cast: [] })
  })

  it('reads pasted cast lines', () => {
    expect(parseCastLines('Shraddha Kapoor as Stree\nPankaj Tripathi - Rudra\n\nTamannaah Bhatia'))
      .toEqual([{ name: 'Shraddha Kapoor', character: 'Stree' }, { name: 'Pankaj Tripathi', character: 'Rudra' },
        { name: 'Tamannaah Bhatia', character: '' }])
  })

  it('moves cast members and adds up day rows', () => {
    expect(move(['a', 'b', 'c'], 2, -1)).toEqual(['a', 'c', 'b'])
    expect(move(['a', 'b'], 0, -1)).toEqual(['a', 'b'])
    expect(rowsTotal([{ label: 'Day 1', value: '55.4' }, { label: 'Day 2', value: '1,035.3' }, { label: 'x', value: '?' }])).toBeCloseTo(1090.7)
  })
})
