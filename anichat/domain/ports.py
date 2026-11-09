"""Interfaces the application layer depends on. Implemented in infrastructure/.

Keeping these as Protocols means the wiki client or storage can be swapped
(e.g. another wiki, or a database instead of JSON files) without touching
application code, and tests can use simple fakes.
"""

from dataclasses import dataclass
from typing import Protocol

from anichat.domain.chunking import Chunk
from anichat.domain.entities import RawPage


@dataclass(frozen=True)
class SparseVector:
    """Keyword-style vector: only the non-zero dimensions (token ids and their weights)."""

    indices: list[int]
    values: list[float]


@dataclass(frozen=True)
class Embedded:
    """Both vectors of one text. Created by Embedder; stored/searched by VectorIndex."""

    dense: list[float]  # meaning (bge-small: 384 numbers)
    sparse: SparseVector  # keywords (BM25)


@dataclass(frozen=True)
class SearchHit:
    """One search result. Created by VectorIndex.search(); used by scripts/index.py and stage 5."""

    chunk: Chunk
    score: float


class Embedder(Protocol):
    """Turns text into vectors.

    Implemented by: infrastructure/fastembed_embedder.py  FastEmbedEmbedder
    Used by:        application/index_chunks.py           IndexChunksService
    """

    def embed_documents(self, texts: list[str]) -> list[Embedded]:
        """Vectors for chunks being indexed."""
        ...

    def embed_query(self, text: str) -> Embedded:
        """Vectors for a question (models may treat questions differently from passages)."""
        ...


class VectorIndex(Protocol):
    """Stores chunk vectors and searches them.

    Implemented by: infrastructure/qdrant_index.py  QdrantIndex
    Used by:        application/index_chunks.py     IndexChunksService
    """

    def ensure_collection(self, dense_size: int) -> None: ...

    def replace_series(self, series: str, chunks: list[Chunk], vectors: list[Embedded]) -> int:
        """Delete the series' previous points and store these; returns how many were stored."""
        ...

    def count(self, series: str | None = None) -> int: ...

    def search(self, query: Embedded, limit: int, series: str | tuple[str, ...] | None = None) -> list[SearchHit]:
        """Hybrid search: dense and keyword results fused into one ranking."""
        ...

    def find(self, kind: str, number: int, series: str | None = None, limit: int = 3) -> list[Chunk]:
        """Chunks of the page with this kind and number (e.g. chapter 196), in reading order."""
        ...

    def profile_cards(self, series: str | tuple[str, ...] | None = None) -> list[Chunk]:
        """Every profile card (section "Profile"), for the name/alias/title lookup."""
        ...


class Reranker(Protocol):
    """Scores how well each passage answers a question (reads both together, unlike search).

    Implemented by: infrastructure/fastembed_reranker.py  FastEmbedReranker
    Used by:        application/retrieve.py               RetrievalService
    """

    def score(self, question: str, passages: list[str]) -> list[float]:
        """One relevance score per passage, higher is better."""
        ...


class WikiClient(Protocol):
    """Reads pages from a MediaWiki wiki.

    Implemented by: infrastructure/fandom_client.py  FandomClient
    Used by:        application/collect.py           CollectService
    """

    async def category_pages(self, host: str, category: str, include_subcategories: bool) -> list[str]:
        """Titles of the article pages in a category (optionally one level of sub-categories)."""
        ...

    async def fetch_page(self, host: str, series: str, kind: str, title: str) -> RawPage | None:
        """The page's raw wikitext, or None if it does not exist or cannot be fetched."""
        ...

    async def redirects_to(self, host: str, titles: list[str]) -> dict[str, list[str]]:
        """Titles of the redirect pages pointing at each page ("Pain" -> "Nagato"): its other names."""
        ...

    async def page_properties(self, host: str, title: str) -> dict[str, list[str]]:
        """Semantic MediaWiki properties of a page ({"Parent": ["Minato Namikaze", ...]}), {} if none."""
        ...


class RawStore(Protocol):
    """Keeps fetched pages on disk so nothing is downloaded twice.

    Implemented by: infrastructure/raw_store.py  RawStore (JSON files)
    Used by:        application/collect.py       CollectService
    """

    def has(self, series: str, kind: str, title: str) -> bool: ...

    def load(self, series: str, kind: str, title: str) -> RawPage | None: ...

    def save(self, page: RawPage) -> None: ...

    def write_manifest(self, series: str, manifest: dict) -> None: ...
