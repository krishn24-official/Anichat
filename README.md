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
| 7. Evaluate | Question set with known answers | ✅ started: `evals/demon_slayer.json` (20 questions) |

Heavy work (stages 1-4) runs on a laptop; the hosted API (stages 5-6) stays light:
small ONNX models, Qdrant Cloud, LLM APIs.

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
python -m scripts.chunk --series demon_slayer            # stage 3 -> data/chunks/
python -m scripts.index --series demon_slayer            # stage 4 -> data/qdrant/ (first run ~25 min on CPU)
```

Embedding a full chunk takes ~0.3 s on a laptop CPU, so the first index of a series takes
~25 minutes. Vectors are cached in `data/embeddings.sqlite` by text, so later runs only embed
chunks that changed (a full re-index from cache takes ~30 s).

## Chat

Put your keys in `.env` (copy `.env.example`), then:

```
python -m scripts.chat "How did Rengoku die?"        # one question in the terminal
python -m scripts.chat                               # interactive
uvicorn anichat.interfaces.api:app --reload          # API: open http://127.0.0.1:8000/docs
```

## Data source and license

Wiki content comes from fandom wikis (CC BY-SA 3.0). Every collected page keeps its
source URL; keep attribution when showing or reusing it.
