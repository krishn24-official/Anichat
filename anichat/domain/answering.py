"""Building the grounded prompt and reading citations back. Pure Python, no I/O.

The model only sees numbered sources (the retrieved chunks) and must cite them as
[1], [2]... That keeps answers checkable and makes "I don't know" the honest default
when retrieval found nothing relevant.
"""

import re
from dataclasses import dataclass

from anichat.domain.chunking import Chunk
from anichat.domain.conversation import Turn, history_messages
from anichat.domain.llm import ChatMessage

SYSTEM_PROMPT = """You are AniChat, a friendly anime expert.

Answer the user's question using ONLY the numbered sources provided. Rules:
- Cite the sources that support each statement, like [1] or [2][3], right after it.
- If the sources do not contain the answer, say you don't have that information. Never use outside knowledge or guess.
- Be concise: a few sentences, or a short bulleted list for several items.
- Mention episode or chapter numbers when the sources give them.
- Plain text only: no tables or headings."""
# Added when earlier turns are included: they only say who "he"/"that" refers to.
FOLLOW_UP_RULE = """
- Earlier messages are only there to tell you what the new question refers to ("he", "that fight"). Facts still come only from the numbered sources of the latest question."""

NO_SOURCES_ANSWER = "I couldn't find anything about that in my knowledge base yet."
_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
# Some models (gpt-oss on Groq) cite as 【1】 or 【1†L3-L5】 instead of [1].
_ALT_CITATION = re.compile(r"【(\d+)(?:†[^】]*)?】")


@dataclass(frozen=True)
class Source:
    """A cited page section, shown under the answer. Created by cited_sources()."""

    numbers: tuple[int, ...]  # citation numbers in the answer that point here, e.g. (2, 3)
    title: str  # e.g. "Episode 33: Set Your Heart Ablaze"
    section: str  # e.g. "Synopsis"
    url: str


def normalize_citations(answer: str) -> str:
    """Rewrite other citation styles as [n], so they are parsed and shown consistently.

    Called by: application/answer.py  AnswerService.answer()
    """
    return _ALT_CITATION.sub(r"[\1]", answer)


def build_messages(question: str, chunks: list[Chunk], history: list[Turn] | None = None) -> list[ChatMessage]:
    """System rules + earlier turns (if any) + the numbered sources + the question.

    Called by: application/answer.py  AnswerService.answer()
    """
    sources = "\n\n".join(f"[{i}] {c.text}" for i, c in enumerate(chunks, 1))
    return [
        ChatMessage("system", SYSTEM_PROMPT + (FOLLOW_UP_RULE if history else "")),
        *history_messages(history or []),
        ChatMessage("user", f"Sources:\n\n{sources}\n\nQuestion: {question}"),
    ]


def cited_numbers(answer: str, available: int) -> list[int]:
    """Source numbers the answer cites ("[1]", "[2][3]", "[1, 4]"), in first-cited order,
    ignoring numbers that don't exist.

    Called by: cited_sources()
    """
    numbers = []
    for group in _CITATION.findall(answer):
        for n in (int(x) for x in group.split(",")):
            if 1 <= n <= available and n not in numbers:
                numbers.append(n)
    return numbers


def cited_sources(answer: str, chunks: list[Chunk]) -> list[Source]:
    """The chunks the answer actually cites, one entry per page section (several chunks of
    the same section, e.g. a long chapter summary, are listed once with all their numbers).

    Called by: application/answer.py  AnswerService.answer()
    """
    grouped: dict[tuple[str, str], list[int]] = {}
    for n in cited_numbers(answer, len(chunks)):
        c = chunks[n - 1]
        grouped.setdefault((c.source, c.section), []).append(n)
    sources = []
    for (url, section), numbers in grouped.items():
        c = chunks[numbers[0] - 1]
        sources.append(Source(numbers=tuple(numbers), title=c.display_title, section=section, url=url))
    return sources
