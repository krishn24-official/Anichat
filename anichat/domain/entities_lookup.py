"""Exact entity lookup by name, alias or title. Pure Python, no I/O.

Embeddings miss questions that name an entity only by a title ("Who is Upper Rank
Three?" -> Akaza): the phrase appears in dozens of story chunks. Like chapter numbers,
such references are looked up exactly instead: every profile card contributes its
distinctive phrases (name, aliases, titles in its first sentences), and a question
containing one gets that card added to its results.
"""

import re
from collections import defaultdict

from anichat.domain.chunking import Chunk

MAX_ENTITIES_PER_PHRASE = 2  # a phrase shared by more pages ("Twelve Kizuki") identifies no one
MIN_PHRASE_CHARS = 4
# Capitalised multi-word phrases: "Upper Rank Three", "Sound Hashira", "Demon King".
_TITLE = re.compile(r"\b[A-Z][a-z]+(?:\s+(?:of\s+the\s+|of\s+)?[A-Z][a-z]+){1,3}\b")
_FACT_LINE = re.compile(r"^(?:Alias|Occupation|Rank|Affiliation): (.+)$", re.M)


def card_phrases(card: Chunk, series_title: str = "") -> set[str]:
    """Lower-cased phrases that may identify the card's entity: its name, its first name,
    aliases/occupations from the facts, and title-like phrases from its description.

    Called by: build_phrase_index()
    """
    body = card.text.split("\n\n", 1)[-1]
    name = card.title.split(" (")[0]
    phrases = {card.title, name}
    if len(name.split()) > 1:
        phrases.add(name.split()[0])  # first name ("Tengen"); one shared by 3+ pages is dropped later
    for value in _FACT_LINE.findall(body):
        for part in re.split(r"[;,]|\(|\)", value):  # "Shinobi (Formerly) ; Sound Hashira (Formerly)"
            part = part.strip()
            if part and part.lower() not in ("formerly", "human", "demon"):
                phrases.add(part)
    phrases.update(_TITLE.findall(body))
    ignore = {series_title.lower(), "kimetsu no yaiba"}
    return {p.lower() for p in phrases if len(p) >= MIN_PHRASE_CHARS and p.lower() not in ignore}


def build_phrase_index(cards: list[Chunk], series_title: str = "") -> dict[str, list[Chunk]]:
    """phrase -> the (at most MAX_ENTITIES_PER_PHRASE) cards it identifies.

    Called by: application/retrieve.py  RetrievalService._phrases() (built once, on first use,
               from the cards returned by VectorIndex.profile_cards())
    """
    index: dict[str, list[Chunk]] = defaultdict(list)
    for card in cards:
        for phrase in card_phrases(card, series_title):
            index[phrase].append(card)
    return {p: cs for p, cs in index.items() if len(cs) <= MAX_ENTITIES_PER_PHRASE}


def lookup(question: str, phrase_index: dict[str, list[Chunk]], limit: int = 2) -> list[Chunk]:
    """Cards whose phrases appear in the question, longest phrase first ("upper rank three"
    beats "three"), each card once.

    Called by: application/retrieve.py  RetrievalService.retrieve()
    """
    q = question.lower()
    found: list[Chunk] = []
    for phrase in sorted(phrase_index, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", q):
            for card in phrase_index[phrase]:
                if card.id not in {c.id for c in found}:
                    found.append(card)
        if len(found) >= limit:
            break
    return found[:limit]
