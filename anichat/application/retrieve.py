"""Stage 5 use case: find the chunks that best answer a question.

    1. exact lookups: "chapter 196" / "episode 1" -> that page's first chunks
    2. hybrid search: top candidates by meaning + keywords (fused)
    3. rerank (optional): a cross-encoder reorders the candidates
    4. exact hits first, then the best ranked chunks, without duplicates
    5. name/alias/title lookup: a page the question names ("Upper Rank Three" -> Akaza)
       but the search missed takes the last slot

Reranking is off by default: on the evaluation set (evals/<series>.json) every small
FastEmbed reranker tried made results worse (search only: 90% of questions answered in
the top 5 in 0.2 s; with a reranker: 75-80% in 1.3-3.5 s). They are trained on web
search and don't know the domain. Re-test with scripts/evaluate.py before enabling one.
"""

import time
from dataclasses import dataclass, field

from anichat.domain.chunking import Chunk
from anichat.domain.entities_lookup import build_phrase_index, lookup
from anichat.domain.ports import Embedder, Reranker, VectorIndex
from anichat.domain.query import parse_question
from anichat.domain.series import search_scope

CANDIDATES = 15  # hybrid-search results passed to the reranker (cost grows with this)
EXACT_PER_PAGE = 2  # chunks taken from a page referenced by number
ENTITY_SLOTS = 1  # result slots a name/alias/title match may take (it must not crowd out search)


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk chosen for a question. Created by RetrievalService.retrieve()."""

    chunk: Chunk
    score: float
    via: str  # "exact", "rerank" or "search": how it was found


@dataclass
class Retrieval:
    """Result of one retrieve() call; timings in seconds (printed by scripts/ask.py, evaluate.py)."""

    question: str
    chunks: list[RetrievedChunk]
    timings: dict[str, float] = field(default_factory=dict)


class RetrievalService:
    """Finds context for questions.

    Created by: scripts/ask.py main(), scripts/evaluate.py main(); stage 6 (the chat API)
    Tested by:  tests/test_retrieve.py
    """

    def __init__(self, embedder: Embedder, index: VectorIndex, reranker: Reranker | None = None,
                 candidates: int = CANDIDATES):
        self._embedder = embedder
        self._index = index
        self._reranker = reranker  # None = hybrid search order only
        self._candidates = candidates
        self._phrase_indexes: dict = {}  # per search scope (series id or ids), built on first use

    def _phrases(self, series: str | tuple[str, ...] | None) -> dict:
        """The name/alias/title -> profile card table for a series (built once from the index).

        Called by: retrieve()
        """
        if series not in self._phrase_indexes:
            self._phrase_indexes[series] = build_phrase_index(self._index.profile_cards(series))
        return self._phrase_indexes[series]

    def retrieve(self, question: str, series: str | None = None, limit: int = 5) -> Retrieval:
        """The `limit` best chunks for the question (optionally within one series).

        Called by: scripts/ask.py, scripts/evaluate.py; stage 6 (answer generation)
        """
        timings, started = {}, time.perf_counter()

        # 1. Exact references ("chapter 196").
        hints = parse_question(question)
        exact = []
        for kind, number in (("chapter", hints.chapter), ("episode", hints.episode)):
            if number is not None:
                exact += [RetrievedChunk(c, 1.0, "exact")
                          for c in self._index.find(kind, number, series, EXACT_PER_PAGE)]
        timings["exact"] = time.perf_counter() - started

        # 2. Hybrid search, also over the pages a sequel shares (Shippuden -> Naruto's characters).
        #    The exact lookups above stay within `series`: "episode 1" is that series' episode 1.
        scope = search_scope(series)
        t = time.perf_counter()
        hits = self._index.search(self._embedder.embed_query(question), self._candidates, scope)
        timings["search"] = time.perf_counter() - t

        # 3. Rerank.
        t = time.perf_counter()
        if self._reranker and hits:
            scores = self._reranker.score(question, [h.chunk.text for h in hits])
            ranked = sorted((RetrievedChunk(h.chunk, s, "rerank") for h, s in zip(hits, scores)),
                            key=lambda r: r.score, reverse=True)
        else:
            ranked = [RetrievedChunk(h.chunk, h.score, "search") for h in hits]
        timings["rerank"] = time.perf_counter() - t

        # 4. Exact first, then ranked, each chunk once.
        seen, chosen = set(), []
        for item in exact + ranked:
            if item.chunk.id not in seen:
                seen.add(item.chunk.id)
                chosen.append(item)
        chosen = chosen[:limit]

        # 5. The profile card of a page the question names ("Upper Rank Three" -> Akaza) takes
        #    the last slot, unless the card is already among the results. Checked by card, not
        #    by page: "Who killed Eren Yeager?" finds Eren's history, but the answer is the
        #    card's "Killed by" line.
        t = time.perf_counter()
        # Only the best matches (longest phrase) are considered: if "Eren Yeager"'s card is already
        # there, the weaker "Yeager" match must not push it out of the last slot.
        present = {c.chunk.id for c in chosen}
        entities = [c for c in lookup(question, self._phrases(scope))[:ENTITY_SLOTS] if c.id not in present]
        if entities:
            chosen = chosen[: limit - len(entities)] + [RetrievedChunk(c, 1.0, "entity") for c in entities]
        timings["entity"] = time.perf_counter() - t
        timings["total"] = time.perf_counter() - started
        return Retrieval(question=question, chunks=chosen, timings=timings)
