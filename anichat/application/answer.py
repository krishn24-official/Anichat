"""Stage 6 use case: answer a question from retrieved knowledge (RAG).

    question -> retrieve chunks (stage 5) -> grounded prompt -> chat model -> answer + sources
"""

import time
from dataclasses import dataclass, field

from anichat.application.llm_fallback import AllModelsUnavailable
from anichat.application.retrieve import RetrievalService
from anichat.domain.answering import NO_SOURCES_ANSWER, Source, build_messages, cited_sources, normalize_citations
from anichat.domain.llm import ChatModel

CONTEXT_CHUNKS = 5  # sources given to the model per question
BUSY_ANSWER = "My AI models are busy or out of their free daily quota right now. Please try again in a few minutes."


@dataclass
class Answer:
    """What the chat returns. Created by AnswerService.answer(); serialised by
    interfaces/api.py and printed by scripts/chat.py."""

    question: str
    text: str
    sources: list[Source]  # only the ones the answer cites
    model: str | None  # None when no model was needed or available
    timings: dict[str, float] = field(default_factory=dict)


class AnswerService:
    """Answers questions.

    Created by: anichat/container.py  answer_service()
    Used by:    interfaces/api.py  POST /chat;  scripts/chat.py
    Tested by:  tests/test_answer.py
    """

    def __init__(self, retrieval: RetrievalService, model: ChatModel, context_chunks: int = CONTEXT_CHUNKS):
        self._retrieval = retrieval
        self._model = model
        self._k = context_chunks

    def answer(self, question: str, series: str | None = None) -> Answer:
        """Retrieve, then ask the model to answer only from what was retrieved.

        Called by: interfaces/api.py  chat();  scripts/chat.py  main()
        """
        question = question.strip()
        retrieval = self._retrieval.retrieve(question, series=series, limit=self._k)
        chunks = [r.chunk for r in retrieval.chunks]
        timings = {"retrieve": retrieval.timings["total"]}
        if not chunks:
            return Answer(question, NO_SOURCES_ANSWER, [], None, timings)

        started = time.perf_counter()
        try:
            reply = self._model.complete(build_messages(question, chunks))
        except AllModelsUnavailable:
            return Answer(question, BUSY_ANSWER, [], None, timings)
        timings["generate"] = time.perf_counter() - started
        text = normalize_citations(reply.text)
        return Answer(question, text, cited_sources(text, chunks), reply.model, timings)
