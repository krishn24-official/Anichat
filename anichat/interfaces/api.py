"""HTTP API for AniChat (FastAPI). Thin: validate input, call AnswerService, shape output.

Run:  uvicorn anichat.interfaces.api:app --reload
Docs: http://127.0.0.1:8000/docs  (try POST /chat there)

Endpoints
  GET  /health   liveness + which chat models are configured
  GET  /series   the series that have indexed knowledge (for the frontend's series picker)
  POST /chat     answer one question, with its sources
"""

from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from anichat import config, container
from anichat.domain.series import SERIES


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the embedding model and open the index once at startup (not per request);
    release the index on shutdown.

    Called by: FastAPI on start/stop
    """
    container.answer_service()
    # Read the profile cards for name lookups now: otherwise the first question waits ~20 s.
    await run_in_threadpool(container.retrieval_service().warm_up)
    yield
    container.index().close()


app = FastAPI(title="AniChat", version="0.2", lifespan=lifespan)
# The frontend runs on another origin (Vite dev server, Vercel), so browsers need CORS.
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500, examples=["How did Rengoku die?"])
    series: str | None = Field(default=None, description="limit to one series (an id from GET /series)")


class SourceOut(BaseModel):
    numbers: list[int]  # citation numbers in the answer, e.g. [2, 3]
    title: str
    section: str
    url: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    model: str | None
    timings: dict[str, float]


class SeriesOut(BaseModel):
    id: str  # e.g. "naruto_shippuden"
    title: str  # e.g. "Naruto Shippuden"
    franchise: str  # the series it shares pages with, else itself ("naruto"): groups the picker
    chunks: int  # indexed chunks of this series


@lru_cache(maxsize=1)
def _indexed_series() -> tuple[SeriesOut, ...]:
    """Configured series that have chunks in the index, counted once (the index only changes
    when scripts/index.py runs; restart the API afterwards).

    Called by: series()
    """
    index = container.index()
    found = []
    for source in SERIES.values():
        count = index.count(source.id)
        if count:
            found.append(SeriesOut(id=source.id, title=source.title, franchise=source.shares_with or source.id,
                                   chunks=count))
    return tuple(found)


@app.get("/health")
def health() -> dict:
    """Liveness check for the host (e.g. Render). Called by: hosting health checks"""
    return {"status": "ok", "models": container.chat_model().name}


@app.get("/series", response_model=list[SeriesOut])
def series() -> list[SeriesOut]:
    """The series AniChat can answer about. Called by: the frontend's series picker"""
    return list(_indexed_series())


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Answer one question from the knowledge base, with its sources.

    Called by: the AniChat frontend, /docs
    The answer pipeline is blocking (model + HTTP), so it runs in a worker thread.
    """
    if req.series and req.series not in SERIES:
        raise HTTPException(status_code=422, detail=f"Unknown series '{req.series}'. See GET /series.")
    answer = await run_in_threadpool(container.answer_service().answer, req.question.strip(), req.series)
    return ChatResponse(
        answer=answer.text,
        sources=[SourceOut(numbers=list(s.numbers), title=s.title, section=s.section, url=s.url) for s in answer.sources],
        model=answer.model,
        timings={k: round(v, 3) for k, v in answer.timings.items()},
    )
