import { describe, expect, it } from 'vitest'
import { emptyForm, problem, toInput } from './form'

describe('other entries form', () => {
  it('sends only complete fact rows, trimmed', () => {
    const form = { ...emptyForm('anime'), series: 'naruto', title: ' Naruto Uzumaki ',
      facts: [{ key: 'Hindi dub ', value: ' Sonal Kaushal' }, { key: 'Studio', value: '' }, { key: '', value: 'lost' }] }
    expect(toInput(form)).toEqual({ type: 'anime', series: 'naruto', title: 'Naruto Uzumaki',
      facts: { 'Hindi dub': 'Sonal Kaushal' }, notes: '', source: '' })
  })

  it('defaults "other" entries to the other series', () => {
    expect(emptyForm('other').series).toBe('other')
  })

  it('explains what is missing', () => {
    expect(problem(emptyForm('anime'))).toBe('Add a title.')
    expect(problem({ ...emptyForm('anime'), title: 'Naruto', notes: 'n' })).toBe('Pick the series it belongs to.')
    expect(problem({ ...emptyForm('anime'), title: 'Naruto', series: 'naruto' })).toBe('Add at least one fact or a note.')
    expect(problem({ ...emptyForm('anime'), title: 'Naruto', series: 'naruto', notes: 'n' })).toBeNull()
  })
})
