"""HTTP API for AniChat (FastAPI). Thin: validate input, call AnswerService, shape output.

Run:  uvicorn anichat.interfaces.api:app --reload
Docs: http://127.0.0.1:8000/docs  (try POST /chat there)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from anichat import container
from anichat.domain.series import SERIES


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the embedding model and open the index once at startup (not per request);
    release the index on shutdown.

    Called by: FastAPI on start/stop
    """
    container.answer_service()
    yield
    container.index().close()


app = FastAPI(title="AniChat", version="0.1", lifespan=lifespan)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500, examples=["How did Rengoku die?"])
    series: str | None = Field(default=None, description=f"limit to one series: {', '.join(SERIES)}")


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


@app.get("/health")
def health() -> dict:
    """Liveness check for the host (e.g. Render). Called by: hosting health checks"""
    return {"status": "ok", "models": container.chat_model().name}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Answer one question from the knowledge base, with its sources.

    Called by: clients (the anime_ai frontend later), /docs
    The answer pipeline is blocking (model + HTTP), so it runs in a worker thread.
    """
    answer = await run_in_threadpool(container.answer_service().answer, req.question, req.series)
    return ChatResponse(
        answer=answer.text,
        sources=[SourceOut(numbers=list(s.numbers), title=s.title, section=s.section, url=s.url) for s in answer.sources],
        model=answer.model,
        timings={k: round(v, 3) for k, v in answer.timings.items()},
    )
