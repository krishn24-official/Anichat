"""Follow-up questions. Pure Python, no I/O.

The API is stateless: the frontend sends the last few turns with each question. They are
used twice:
- retrieval: "Who is his brother?" alone finds nothing about Goku, so a question that
  looks like a follow-up is searched together with the previous question
- the prompt: the previous turns are given to the model, so it can tell who "his" is
"""

import re
from dataclasses import dataclass

from anichat.domain.llm import ChatMessage

MAX_TURNS = 3  # previous question/answer pairs used; older ones rarely matter and cost tokens
MAX_ANSWER_CHARS = 1200  # a long previous answer is cut: the start says what it was about

# Words that point back at something said before ("his", "that fight", "what about...").
_FOLLOW_UP = re.compile(
    r"\b(he|him|his|himself|she|her|hers|herself|they|them|their|it|its|this|that|these|those|"
    r"there|then|the same|other|another|else)\b|^\s*(and|also|what about|how about|why|how come)\b",
    re.I,
)
_CITATION = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")


@dataclass(frozen=True)
class Turn:
    """One earlier question and its answer. Created by interfaces/api.py from the request."""

    question: str
    answer: str


def looks_like_follow_up(question: str) -> bool:
    """True if the question refers back to the conversation ("Who killed him?").

    Called by: application/answer.py  AnswerService.answer()
    """
    return bool(_FOLLOW_UP.search(question))


def recent(history: list[Turn] | tuple[Turn, ...]) -> list[Turn]:
    """The last MAX_TURNS turns that have both a question and an answer.

    Called by: application/answer.py  AnswerService.answer()
    """
    return [t for t in history if t.question.strip() and t.answer.strip()][-MAX_TURNS:]


def history_messages(history: list[Turn]) -> list[ChatMessage]:
    """Earlier turns as chat messages. Citation numbers are removed: they pointed at that
    turn's sources, not this one's, and would confuse the model.

    Called by: domain/answering.py  build_messages()
    """
    messages = []
    for turn in history:
        answer = _CITATION.sub("", turn.answer).strip()
        if len(answer) > MAX_ANSWER_CHARS:
            answer = answer[:MAX_ANSWER_CHARS].rsplit(" ", 1)[0] + " ..."
        messages += [ChatMessage("user", turn.question.strip()), ChatMessage("assistant", answer)]
    return messages
