"""Reading hints out of a question. Pure Python, no I/O.

Vector search is bad at numbers ("chapter 196" and "chapter 169" look alike to an
embedding), so explicit chapter/episode references are looked up exactly instead.
"""

import re
from dataclasses import dataclass

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
            "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "last": None}


@dataclass(frozen=True)
class QueryHints:
    """Exact references found in a question.

    Created by: parse_question()
    Used by:    application/retrieve.py  RetrievalService.retrieve()
    """

    chapter: int | None = None
    episode: int | None = None


def _number(unit: str, text: str) -> int | None:
    """"chapter 12" / "ch. 12" / "ch12" / "first chapter" -> 12 / 12 / 12 / 1 (same for episodes).

    Called by: parse_question()
    """
    short = {"chapter": "ch", "episode": "ep"}[unit]
    # What some wikis call them instead: Gintama "Lesson 12", Rurouni Kenshin "Act 12", Shaman
    # King "Reincarnation 12"; Cowboy Bebop's episodes are "sessions". Only with a number after.
    other = {"chapter": "lesson|act|reincarnation", "episode": "session"}[unit]
    m = re.search(rf"\b(?:{unit}s?|{short}\.?|(?:{other})s?)\s*#?\s*(\d{{1,4}})\b", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(rf"\b({'|'.join(k for k, v in ORDINALS.items() if v)})\s+{unit}\b", text, re.I)
    return ORDINALS[m.group(1).lower()] if m else None


def parse_question(text: str) -> QueryHints:
    """Chapter/episode numbers mentioned in a question.

    Called by: application/retrieve.py  RetrievalService.retrieve()
    """
    return QueryHints(chapter=_number("chapter", text), episode=_number("episode", text))
