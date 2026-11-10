import { describe, expect, it } from 'vitest'
import { parseBlocks, parseInline } from './answer'

describe('parseInline', () => {
  it('separates text, bold and citation groups', () => {
    expect(parseInline('Rengoku was killed by **Akaza** [1][3] at dawn [2, 4].')).toEqual([
      { kind: 'text', text: 'Rengoku was killed by ' },
      { kind: 'bold', text: 'Akaza' },
      { kind: 'text', text: ' ' },
      { kind: 'cite', numbers: [1, 3] },
      { kind: 'text', text: ' at dawn ' },
      { kind: 'cite', numbers: [2, 4] },
      { kind: 'text', text: '.' },
    ])
  })

  it('keeps square brackets that are not citations as text', () => {
    expect(parseInline('Kira [The First] acted')).toEqual([{ kind: 'text', text: 'Kira [The First] acted' }])
  })
})

describe('parseBlocks', () => {
  it('turns bullet lines into a list and joins wrapped paragraph lines', () => {
    expect(parseBlocks('Two successors:\nnamed below.\n\n- Near [1]\n* Mello [2]')).toEqual([
      { kind: 'paragraph', text: 'Two successors: named below.' },
      { kind: 'list', items: ['Near [1]', 'Mello [2]'] },
    ])
  })

  it('reads streamed 【1】 citations as [1]', () => {
    expect(parseBlocks('Piccolo【1】【7†L3-L5】.')).toEqual([{ kind: 'paragraph', text: 'Piccolo[1][7].' }])
  })
})
