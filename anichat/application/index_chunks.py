"""Stage 4 use case: embed every chunk of a series and store it in the vector index."""

from dataclasses import dataclass
from typing import Iterable, Protocol

from anichat.domain.chunking import Chunk
from anichat.domain.ports import Embedder, VectorIndex


class ChunkReader(Protocol):
    """Implemented by: infrastructure/chunk_store.py  ChunkStore.iter_chunks()"""

    def iter_chunks(self, series: str) -> Iterable[Chunk]: ...


@dataclass
class IndexReport:
    """Created by IndexChunksService.index(); printed by scripts/index.py."""

    series: str
    chunks: int
    stored: int


class IndexChunksService:
    """Embeds and indexes a series' chunks.

    Created by: scripts/index.py  main()
    Tested by:  tests/test_index.py
    """

    def __init__(self, chunks: ChunkReader, embedder: Embedder, index: VectorIndex, dense_size: int):
        self._chunks = chunks
        self._embedder = embedder
        self._index = index
        self._dense_size = dense_size

    def index(self, series: str) -> IndexReport:
        """Embed all chunks, then replace the series in the index. Embedding happens
        first, so if it fails the existing index is left untouched.

        Called by: scripts/index.py  main()
        """
        chunks = list(self._chunks.iter_chunks(series))
        if not chunks:
            raise RuntimeError(f"No chunks for {series}: run scripts/chunk.py first")
        vectors = self._embedder.embed_documents([c.text for c in chunks])
        self._index.ensure_collection(self._dense_size)
        stored = self._index.replace_series(series, chunks, vectors)
        return IndexReport(series=series, chunks=len(chunks), stored=stored)
