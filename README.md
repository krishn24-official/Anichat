# AniChat

A chatbot for anime (and later all entertainment) questions, answered from collected
wiki knowledge with retrieval-augmented generation (RAG).

## Plan (one series at a time)

| Stage | What | Status |
|---|---|---|
| 1. Collect | Download raw wiki pages (episodes, chapters, characters, arcs, ...) | ✅ `scripts/collect.py` |
| 2. Documents | Clean wikitext into one Markdown document per page, with metadata | ✅ `scripts/build_documents.py` |
| 3. Chunk | Split documents by heading into ~300-500 token chunks | ✅ `scripts/chunk.py` |
| 4. Embed + index | FastEmbed (bge-small dense + BM25 sparse) into Qdrant, with an embedding cache | ✅ `scripts/index.py` |
| 5. Retrieve | Hybrid search + exact chapter/episode lookups (reranking measured: off) | ✅ `scripts/ask.py`, `scripts/evaluate.py` |
| 6. Answer | FastAPI + Gemini -> Groq, answers only from sources, with citations | ✅ `anichat/interfaces/api.py`, `scripts/chat.py` |
| 7. Evaluate | Question sets with known answers, per series | ✅ `evals/*.json`, `scripts/evaluate.py`, `scripts/evaluate_answers.py` |

Heavy work (stages 1-4) runs on a laptop; the hosted API (stages 5-6) stays light:
small ONNX models, Qdrant Cloud, LLM APIs.

## Series

| Series | Wiki | Pages | Chunks | Retrieval (top 5) | Answers correct |
|---|---|---|---|---|---|
| Demon Slayer | kimetsu-no-yaiba.fandom.com | 499 | 4,125 | 95% | 20/20 |
| Death Note | deathnote.fandom.com | 338 | 1,800 | 100% | 12/12 |
| Attack on Titan | attackontitan.fandom.com | 540 | 5,561 | 100% | 14/14 |
| Jujutsu Kaisen | jujutsu-kaisen.fandom.com | 754 | 5,412 | 100% | 14/15 |
| Naruto | naruto.fandom.com | 3,929 | 20,888 | 100% | 14/14 |
| Naruto Shippuden | naruto.fandom.com (shares Naruto's characters/jutsu) | 947 | 2,497 | 100% | 10/10 |
| One Piece | onepiece.fandom.com | 4,152 | 34,576 | 100% | 14/14 |

Each series is configured in `anichat/domain/series.py` (wiki categories per page kind, infobox
filters for wikis that mix several series, Semantic MediaWiki properties to fetch). Known miss:
"Who killed Satoru Gojo?" (the Jujutsu Kaisen wiki has no "People killed" lists).

What the pipeline adds beyond page text:
- **Profile cards**: a short "who/what is X" chunk per entity with its key facts.
- **Other names** from wiki redirects ("Pain" -> Nagato, "Tobi" -> Obito Uchiha).
- **Derived facts**: "Killed by" from other pages' "People killed" lists, "Children" from "Parents".
- **Exact lookups**: "chapter 139" / "episode 1" go straight to that page; names, aliases and
  titles ("Third Hokage") go straight to the entity's card.

## Layout

```
anichat/
  domain/          pure: entities, series config, ports (interfaces)
  application/     use cases (e.g. collect.py)
  infrastructure/  wiki client, file storage (implement the ports)
scripts/           command-line entry points
tests/             tests with in-memory fakes
data/raw/          collected pages (git-ignored)
```

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest
python -m scripts.collect --series demon_slayer          # stage 1 -> data/raw/
python -m scripts.build_documents --series demon_slayer  # stage 2 -> data/documents/
python -m scripts.check_documents --series demon_slayer  # leftover markup / missing numbers
python -m scripts.chunk --series demon_slayer            # stage 3 -> data/chunks/
python -m scripts.index --series demon_slayer            # stage 4 -> Qdrant (first run ~25 min on CPU)
python -m scripts.evaluate --series demon_slayer         # retrieval quality (no LLM)
python -m scripts.evaluate_answers --series demon_slayer # answer quality (uses the LLM APIs)
```

### Vector database (Qdrant)

With several series, use a Qdrant server: the local folder mode (no `QDRANT_URL`) is pure
Python and slows down past ~10k chunks (3.8 s per search at 17k; the server takes ~1 s at 75k).
Start Docker Desktop, then once:

```
docker run -d --name anichat-qdrant --restart unless-stopped -p 6333:6333 -v "${PWD}\data\qdrant_server:/qdrant/storage" qdrant/qdrant:v1.19.2
```

and set `QDRANT_URL=http://localhost:6333` in `.env` (dashboard: http://localhost:6333/dashboard).
For hosting, use a Qdrant Cloud cluster instead: set its URL and `QDRANT_API_KEY`, then re-run
`scripts.index` for each series (vectors come from the cache, no re-embedding).

Embedding a full chunk takes ~0.3 s on a laptop CPU, so the first index of a series takes
~25 minutes (One Piece, 34k chunks: ~3 h). Vectors are cached in `data/embeddings.sqlite` by
text and saved every 256 chunks, so an interrupted run continues where it stopped and later runs
only embed chunks that changed.

### Faster indexing on an NVIDIA GPU

With an NVIDIA GPU, embed into the cache first, then index (the indexer then only stores):

```
python -m venv .venv-gpu
.venv-gpu\Scripts\pip install -r requirements.txt
.venv-gpu\Scripts\pip uninstall -y onnxruntime
.venv-gpu\Scripts\pip install "onnxruntime-gpu[cuda,cudnn]"     # ~3 GB of CUDA/cuDNN libraries
set ANICHAT_EMBED_DEVICE=cuda
.venv-gpu\Scripts\python -m scripts.embed --series bleach fairy_tail
python -m scripts.index --series bleach                          # vectors come from the cache
```

On a GTX 1650 (4 GB) this embeds ~15 chunks/s, about 5x the laptop CPU, with the same vectors
(cosine 0.99999 against CPU-made ones). Keep the GPU batch small (32): larger batches of long
chunks overflow a 4 GB card and halve the speed. Don't run CPU indexing that embeds at the same
time: both need the CPU and slow each other down.

## Chat

Put your keys in `.env` (copy `.env.example`), then:

```
python -m scripts.chat "How did Rengoku die?"        # one question in the terminal
python -m scripts.chat                               # interactive
uvicorn anichat.interfaces.api:app --reload          # API: open http://127.0.0.1:8000/docs
```

The interactive chat remembers the conversation, so follow-ups work ("Who is Raditz?" then
"Who killed him?").

API endpoints:

| Endpoint | What it does |
|---|---|
| `GET /health` | liveness + configured chat models |
| `GET /series` | indexed series, for the picker (restart the API after indexing a new series) |
| `POST /chat` | `{"question", "series"?, "history"?}` -> answer, cited sources, model, timings |
| `POST /chat/stream` | the same as server-sent events: `{"type": "delta", "text"}` while the model writes, then `{"type": "done", ...}` with the cleaned answer and sources |

`history` is the earlier turns, oldest first (`[{"question", "answer"}]`); the API is stateless
and uses the last 3. A question that refers back ("he", "that", "what about...") is searched
together with the previous question, and the earlier turns go into the prompt.

Each visitor (IP) may ask `CHAT_PER_MINUTE` (10) and `CHAT_PER_DAY` (200) questions; more get
HTTP 429 with `Retry-After`. Set `TRUST_PROXY=1` when hosted behind a proxy (Render, Fly...) so the
visitor's IP is read from `X-Forwarded-For`. Browser origins allowed by CORS come from
`CORS_ORIGINS` (default: the Vite dev server). On startup the API loads the embedding models and
every profile card; after that a question takes ~1 s to retrieve plus the model's time.

### Docker

The `Dockerfile` builds the API only (the embedding models are downloaded into the image; ~800 MB):

```
docker build -t anichat-api .
docker run --rm -p 8000:8000 --env-file .env -e QDRANT_URL=http://host.docker.internal:6333 anichat-api
```

It listens on `$PORT` (default 8000), as hosts like Render expect.

## Frontend

A standalone chat UI in `frontend/` (React + Vite + TypeScript + Tailwind). With the API running:

```
cd frontend
npm install
npm run dev            # http://localhost:5173
```

See `frontend/README.md`.

## Data source and license

Wiki content comes from fandom wikis (CC BY-SA 3.0). Every collected page keeps its
source URL; keep attribution when showing or reusing it.
