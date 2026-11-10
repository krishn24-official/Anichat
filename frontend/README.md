# AniChat frontend

A standalone chat UI for the AniChat API: ask anime questions, optionally within one series,
and read answers with clickable citations to the fandom wiki pages they came from. Answers
stream in as they are written, and follow-ups work ("Who killed him?"): the last turns are
sent with each question.

Stack: React 19, Vite, TypeScript, Tailwind CSS v4, lucide icons, Vitest.

## Run

```
npm install
cp .env.example .env        # set VITE_API_URL if the API is not on http://127.0.0.1:8000
npm run dev                 # http://localhost:5173 (the API must allow this origin: CORS_ORIGINS)
npm test                    # unit tests
npm run build               # production build in dist/
```

## Layout

```
src/
  config.ts          API URL and timeout (from Vite env)
  types.ts           API and chat message shapes
  services/api.ts    the only module that calls the API (GET /series, POST /chat/stream)
  hooks/useSeries.ts series list for the picker
  hooks/useChat.ts   conversation state (streamed answers, stop, retry), saved in this browser
  utils/history.ts   the earlier turns sent with a question (tested)
  utils/answer.ts    answer text -> paragraphs, lists, bold, citations (tested)
  utils/examples.ts  example questions per series
  components/        Header, SeriesPicker, EmptyState, MessageView, AnswerText, SourceList, Composer
```
