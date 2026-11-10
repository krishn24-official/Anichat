"""Stage 6 use case: answer a question from retrieved knowledge (RAG).

    question -> retrieve chunks (stage 5) -> grounded prompt -> chat model -> answer + sources
"""

import time
from dataclasses import dataclass, field
from typing import Iterator

from anichat.application.llm_fallback import AllModelsUnavailable
from anichat.application.retrieve import RetrievalService
from anichat.domain.answering import NO_SOURCES_ANSWER, Source, build_messages, cited_sources, normalize_citations
from anichat.domain.conversation import Turn, looks_like_follow_up, recent
from anichat.domain.chunking import Chunk
from anichat.domain.llm import ChatModel, ModelUnavailable

# Sources given to the model per question. 8, not 5: the passage that answers a short question
# is often ranked 6th-8th ("Who killed L?" -> "The End of L" was 8th). ~1k extra tokens per
# question, still inside Groq's free per-minute limit.
CONTEXT_CHUNKS = 8
BUSY_ANSWER = "My AI models are busy or out of their free daily quota right now. Please try again in a few minutes."
CUT_OFF = "The answer was cut off (the AI model stopped responding). Please try again."


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

    def _context(self, question: str, series: str | None,
                 history: list[Turn] | tuple[Turn, ...]) -> tuple[list[Turn], list[Chunk], dict[str, float]]:
        """(recent turns, retrieved chunks, timings) for a question: the part answer() and
        stream() share. A follow-up is searched together with the previous question.

        Called by: answer(), stream()
        """
        history = recent(history)
        context = history[-1].question if history and looks_like_follow_up(question) else ""
        retrieval = self._retrieval.retrieve(question, series=series, limit=self._k, context=context)
        return history, [r.chunk for r in retrieval.chunks], {"retrieve": retrieval.timings["total"]}

    def answer(self, question: str, series: str | None = None, history: list[Turn] | tuple[Turn, ...] = ()) -> Answer:
        """Retrieve, then ask the model to answer only from what was retrieved.

        `history`: earlier turns of this conversation, oldest first (see domain/conversation.py).

        Called by: interfaces/api.py  chat();  scripts/chat.py  main()
        """
        question = question.strip()
        history, chunks, timings = self._context(question, series, history)
        if not chunks:
            return Answer(question, NO_SOURCES_ANSWER, [], None, timings)

        started = time.perf_counter()
        try:
            reply = self._model.complete(build_messages(question, chunks, history))
        except AllModelsUnavailable:
            return Answer(question, BUSY_ANSWER, [], None, timings)
        timings["generate"] = time.perf_counter() - started
        text = normalize_citations(reply.text)
        return Answer(question, text, cited_sources(text, chunks), reply.model, timings)

    def stream(self, question: str, series: str | None = None,
               history: list[Turn] | tuple[Turn, ...] = ()) -> Iterator[str | Answer]:
        """Like answer(), but yields the text in pieces (str) as the model writes it, then the
        finished Answer (citations normalised, sources, timings). If the model stops midway,
        the Answer keeps what was written and adds a note.

        Called by: interfaces/api.py  chat_stream()
        """
        question = question.strip()
        history, chunks, timings = self._context(question, series, history)
        if not chunks:
            yield Answer(question, NO_SOURCES_ANSWER, [], None, timings)
            return

        started = time.perf_counter()
        try:
            model, pieces = self._model.stream(build_messages(question, chunks, history))
        except AllModelsUnavailable:
            yield Answer(question, BUSY_ANSWER, [], None, timings)
            return
        written = []
        try:
            for piece in pieces:
                if not written:
                    timings["first_token"] = time.perf_counter() - started
                written.append(piece)
                yield piece
        except ModelUnavailable:
            written.append("\n\n" + CUT_OFF)
        timings["generate"] = time.perf_counter() - started
        text = normalize_citations("".join(written).strip())
        yield Answer(question, text, cited_sources(text, chunks), model, timings)
