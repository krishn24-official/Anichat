/**
 * Turn an answer's text into blocks (paragraphs, bullet lists) and inline pieces (text,
 * **bold**, citations like [2] or [2][3]). Pure functions: rendered by components/AnswerText.tsx.
 */

export type Inline =
  | { kind: 'text'; text: string }
  | { kind: 'bold'; text: string }
  | { kind: 'cite'; numbers: number[] }

export type Block = { kind: 'paragraph'; text: string } | { kind: 'list'; items: string[] }

const CITATIONS = /((?:\[\d+(?:\s*,\s*\d+)*\])+)/ // "[2]", "[2][3]", "[2, 3]"
const BOLD = /\*\*([^*]+)\*\*/
const ALT_CITATION = /【(\d+)(?:†[^】]*)?】/g // gpt-oss on Groq cites as 【1】 or 【1†L3-L5】

/**
 * Rewrite other citation styles as [n]. The API does this for finished answers; streamed
 * text arrives raw. Called by: parseBlocks()
 */
export function normalizeCitations(text: string): string {
  return text.replace(ALT_CITATION, '[$1]')
}

/**
 * Split an answer into paragraphs and bullet lists ("- item" / "* item" lines).
 * Called by: components/AnswerText.tsx
 */
export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = []
  for (const chunk of normalizeCitations(text).trim().split(/\n\s*\n/)) {
    const lines = chunk.split('\n').map((l) => l.trim()).filter(Boolean)
    if (lines.length && lines.every((l) => /^[-*•]\s+/.test(l))) {
      blocks.push({ kind: 'list', items: lines.map((l) => l.replace(/^[-*•]\s+/, '')) })
    } else if (lines.length) {
      blocks.push({ kind: 'paragraph', text: lines.join(' ') })
    }
  }
  return blocks
}

/**
 * Split one block's text into plain text, bold text and citation groups.
 * Called by: components/AnswerText.tsx
 */
export function parseInline(text: string): Inline[] {
  const out: Inline[] = []
  for (const part of text.split(CITATIONS)) {
    if (!part) continue
    if (CITATIONS.test(part) && part.startsWith('[')) {
      const numbers = [...part.matchAll(/\d+/g)].map((m) => Number(m[0]))
      out.push({ kind: 'cite', numbers: [...new Set(numbers)] })
      continue
    }
    const pieces = part.split(BOLD) // odd indexes are the bold parts
    pieces.forEach((piece, i) => {
      if (piece) out.push(i % 2 ? { kind: 'bold', text: piece } : { kind: 'text', text: piece })
    })
  }
  return out
}
