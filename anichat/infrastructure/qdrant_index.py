"""VectorIndex backed by Qdrant.

Local mode (a folder, no server) during development:  QdrantIndex(path="data/qdrant")
Qdrant Cloud when hosted:  QdrantIndex(url="https://...", api_key="...")
Everything else stays the same.
"""

import time
import uuid
from dataclasses import asdict

from qdrant_client import QdrantClient, models

from anichat.domain.chunking import Chunk
from anichat.domain.ports import Embedded, SearchHit

COLLECTION = "anichat"
DENSE = "dense"  # named vectors inside each point
SPARSE = "bm25"
UPSERT_BATCH = 128
UPSERT_RETRIES = 5  # a busy server (optimizing after a big upload) can time out a batch
FUSION_CANDIDATES = 30  # per vector type, before fusing


def point_id(chunk_id: str) -> str:
    """Qdrant ids must be integers or UUIDs: derive a stable UUID from our chunk id,
    so re-indexing the same chunk overwrites it instead of adding a copy.

    Called by: QdrantIndex.replace_series()
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"anichat:{chunk_id}"))


class QdrantIndex:
    """Implements domain/ports.py VectorIndex.

    Created by: scripts/index.py  main()
    Used by:    application/index_chunks.py  IndexChunksService; stage 5 (retrieval)
    """

    def __init__(self, path: str | None = None, url: str | None = None, api_key: str | None = None):
        # Server timeout 120 s, not 5: uploads run while the CPU is busy embedding.
        self._client = QdrantClient(path=path) if path else QdrantClient(url=url, api_key=api_key, timeout=120)

    def close(self) -> None:
        """Release the local storage lock. Called by: scripts/index.py main()"""
        self._client.close()

    def ensure_collection(self, dense_size: int) -> None:
        """Create the collection on first use: a cosine dense vector + a BM25 sparse vector
        (with IDF computed by Qdrant across all chunks).

        Called by: application/index_chunks.py  IndexChunksService.index()
        """
        if self._client.collection_exists(COLLECTION):
            return
        self._client.create_collection(
            COLLECTION,
            vectors_config={DENSE: models.VectorParams(size=dense_size, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )

    @staticmethod
    def _series_condition(series: str | tuple[str, ...]) -> models.FieldCondition:
        """`series` is one id or several (a sequel and the series it shares pages with).
        Called by: _series_filter(), find(), profile_cards()"""
        if isinstance(series, str):
            return models.FieldCondition(key="series", match=models.MatchValue(value=series))
        return models.FieldCondition(key="series", match=models.MatchAny(any=list(series)))

    @classmethod
    def _series_filter(cls, series: str | tuple[str, ...] | None) -> models.Filter | None:
        """Filter on the `series` payload field. Called by replace_series(), count(), search()"""
        if not series:
            return None
        return models.Filter(must=[cls._series_condition(series)])

    def replace_series(self, series: str, chunks: list[Chunk], vectors: list[Embedded]) -> int:
        """Delete every point of the series, then store the new ones (so chunks removed
        from the documents disappear from the index too).

        Called by: application/index_chunks.py  IndexChunksService.index()
        """
        self._client.delete(COLLECTION, points_selector=models.FilterSelector(filter=self._series_filter(series)))
        points = [
            models.PointStruct(
                id=point_id(c.id),
                vector={
                    DENSE: v.dense,
                    SPARSE: models.SparseVector(indices=v.sparse.indices, values=v.sparse.values),
                },
                payload=asdict(c),
            )
            for c, v in zip(chunks, vectors)
        ]
        for i in range(0, len(points), UPSERT_BATCH):
            self._upsert(points[i:i + UPSERT_BATCH])
        return len(points)

    def _upsert(self, points: list) -> None:
        """Store one batch, retrying with a growing pause when the server times out (it may be
        busy optimizing segments after a large upload). Upserting the same ids twice is harmless.

        Called by: replace_series()
        """
        for attempt in range(UPSERT_RETRIES):
            try:
                self._client.upsert(COLLECTION, points=points)
                return
            except Exception:  # timeouts surface as ResponseHandlingException / httpx errors
                if attempt == UPSERT_RETRIES - 1:
                    raise
                time.sleep(15 * (attempt + 1))

    def count(self, series: str | None = None) -> int:
        """Number of stored chunks (of one series, or all).

        Called by: scripts/index.py  main()
        """
        return self._client.count(COLLECTION, count_filter=self._series_filter(series), exact=True).count

    def find(self, kind: str, number: int, series: str | None = None, limit: int = 3) -> list[Chunk]:
        """Chunks of the page with this kind and number (e.g. chapter 196), first chunks first
        (the intro and summary come before trivia).

        Called by: application/retrieve.py  RetrievalService.retrieve()  (exact lookups)
        """
        conditions = [
            models.FieldCondition(key="kind", match=models.MatchValue(value=kind)),
            models.FieldCondition(key="number", match=models.MatchValue(value=number)),
        ]
        if series:
            conditions.append(self._series_condition(series))
        points, _ = self._client.scroll(COLLECTION, scroll_filter=models.Filter(must=conditions), limit=100, with_payload=True)
        chunks = [Chunk(**p.payload) for p in points]
        # ids end with the chunk's position; a profile card (":card") comes first
        chunks.sort(key=lambda c: int(c.id.rsplit(":", 1)[1]) if c.id.rsplit(":", 1)[1].isdigit() else -1)
        return chunks[:limit]

    def profile_cards(self, series: str | tuple[str, ...] | None = None) -> list[Chunk]:
        """All profile cards (a few hundred per series), for the exact name/alias lookup.

        Called by: application/retrieve.py  RetrievalService._phrases()  (once, then cached)
        """
        conditions = [models.FieldCondition(key="section", match=models.MatchValue(value="Profile"))]
        if series:
            conditions.append(self._series_condition(series))
        cards, offset = [], None
        while True:
            points, offset = self._client.scroll(COLLECTION, scroll_filter=models.Filter(must=conditions),
                                                 limit=500, offset=offset, with_payload=True)
            cards += [Chunk(**p.payload) for p in points]
            if offset is None:
                return cards

    def search(self, query: Embedded, limit: int, series: str | tuple[str, ...] | None = None) -> list[SearchHit]:
        """Hybrid search: top candidates by meaning and by keywords, fused with Reciprocal
        Rank Fusion (a chunk ranked high by either method rises to the top).

        Called by: scripts/index.py  _preview(); stage 5 (retrieval)
        """
        flt = self._series_filter(series)
        result = self._client.query_points(
            COLLECTION,
            prefetch=[
                models.Prefetch(query=query.dense, using=DENSE, limit=FUSION_CANDIDATES, filter=flt),
                models.Prefetch(
                    query=models.SparseVector(indices=query.sparse.indices, values=query.sparse.values),
                    using=SPARSE, limit=FUSION_CANDIDATES, filter=flt,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
        return [SearchHit(chunk=Chunk(**p.payload), score=p.score) for p in result.points]
