/** Shapes of the AniChat API (anichat/interfaces/api.py) and of the chat on screen. */

/** One series AniChat has knowledge of. From GET /series. */
export interface Series {
  id: string // "naruto_shippuden"
  title: string // "Naruto Shippuden"
  franchise: string // the series it shares pages with, else its own id: groups the picker
  chunks: number // indexed chunks
}

/** A cited wiki page section under an answer. */
export interface Source {
  numbers: number[] // citation numbers in the answer that point here, e.g. [2, 3]
  title: string
  section: string
  url: string
}

/** An earlier question and its answer, sent with a new question (follow-ups). */
export interface Turn {
  question: string
  answer: string
}

/** POST /chat response. */
export interface ChatResponse {
  answer: string
  sources: Source[]
  model: string | null // null when no model was needed or available
  timings: Record<string, number> // seconds: retrieve, generate
}

/** One server-sent event of POST /chat/stream: a piece of text, or the finished answer. */
export type StreamEvent = { type: 'delta'; text: string } | ({ type: 'done' } & ChatResponse)

/** One message in the conversation. */
export type Message =
  | { id: string; role: 'user'; text: string; series: string | null }
  | {
      id: string
      role: 'assistant'
      text: string
      sources: Source[]
      model: string | null
      seconds: number
      streaming?: boolean // still being written
      stopped?: boolean // the user pressed stop: the text is incomplete
    }
  | { id: string; role: 'error'; text: string; question: string; series: string | null }
