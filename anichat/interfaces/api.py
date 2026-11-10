"""HTTP API for AniChat (FastAPI). Thin: validate input, call AnswerService, shape output.

Run:  uvicorn anichat.interfaces.api:app --reload
Docs: http://127.0.0.1:8000/docs  (try POST /chat there)

Endpoints
  GET  /health   liveness + which chat models are configured
  GET  /series   the series that have indexed knowledge (for the frontend's series picker)
  POST /chat     answer one question, with its sources
  POST /chat/stream  the same, streamed as server-sent events: {"type": "delta", "text": ...}
                     pieces while the model writes, then {"type": "done", ...ChatResponse}
"""

import json
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Iterator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from anichat import config, container
from anichat.application.answer import Answer
from anichat.domain.conversation import Turn
from anichat.domain.series import SERIES
from anichat.interfaces.rate_limit import RateLimiter, client_id, too_many


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


app = FastAPI(title="AniChat", version="0.3", lifespan=lifespan)
# The frontend runs on another origin (Vite dev server, Vercel), so browsers need CORS.
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"], expose_headers=["Retry-After"])


limiter = RateLimiter(config.CHAT_PER_MINUTE, config.CHAT_PER_DAY)


def limit_chat(request: Request) -> None:
    """Refuse (429) a visitor over their question limit.

    Called by: FastAPI before chat() and chat_stream() (a dependency)
    """
    wait = limiter.check(client_id(request, config.TRUST_PROXY))
    if wait is not None:
        raise too_many(wait)


class TurnIn(BaseModel):
    question: str = Field(max_length=500)
    answer: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500, examples=["How did Rengoku die?"])
    series: str | None = Field(default=None, description="limit to one series (an id from GET /series)")
    history: list[TurnIn] = Field(default=[], max_length=20,
                                  description="earlier turns, oldest first; the last few make follow-ups work")


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


def _check_series(req: ChatRequest) -> None:
    """Reject a series id the frontend may have cached from an older /series.

    Called by: chat(), chat_stream()
    """
    if req.series and req.series not in SERIES:
        raise HTTPException(status_code=422, detail=f"Unknown series '{req.series}'. See GET /series.")


def _history(req: ChatRequest) -> list[Turn]:
    """The request's earlier turns as domain objects. Called by: chat(), chat_stream()"""
    return [Turn(t.question, t.answer) for t in req.history]


def _response(answer: Answer) -> ChatResponse:
    """An Answer in the API's shape. Called by: chat(), chat_stream()"""
    return ChatResponse(
        answer=answer.text,
        sources=[SourceOut(numbers=list(s.numbers), title=s.title, section=s.section, url=s.url) for s in answer.sources],
        model=answer.model,
        timings={k: round(v, 3) for k, v in answer.timings.items()},
    )


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(limit_chat)])
async def chat(req: ChatRequest) -> ChatResponse:
    """Answer one question from the knowledge base, with its sources.

    Called by: /docs, scripts; the frontend uses chat_stream()
    The answer pipeline is blocking (model + HTTP), so it runs in a worker thread.
    """
    _check_series(req)
    answer = await run_in_threadpool(container.answer_service().answer, req.question.strip(), req.series,
                                     _history(req))
    return _response(answer)


def _events(req: ChatRequest) -> Iterator[str]:
    """Server-sent events for one question: text pieces, then the finished answer.

    Called by: chat_stream() (Starlette runs this blocking generator in a worker thread)
    """
    for item in container.answer_service().stream(req.question.strip(), req.series, _history(req)):
        if isinstance(item, Answer):
            event = {"type": "done", **_response(item).model_dump()}
        else:
            event = {"type": "delta", "text": item}
        yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


@app.post("/chat/stream", dependencies=[Depends(limit_chat)])
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Like POST /chat, but the answer arrives while it is written (shown word by word).

    Called by: the AniChat frontend (services/api.ts askStream)
    """
    _check_series(req)
    return StreamingResponse(_events(req), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
