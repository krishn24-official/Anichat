"""Tests for stage 4 (indexing) with fakes, and the real Qdrant local mode in a temp folder
(Qdrant's local mode needs no server, so this stays fast and offline)."""

import pytest

from anichat.application.index_chunks import IndexChunksService
from anichat.domain.chunking import Chunk
from anichat.domain.ports import Embedded, SparseVector
from anichat.infrastructure.qdrant_index import QdrantIndex, point_id


def chunk(i, series="demon_slayer", text=None):
    return Chunk(f"{series}:episode:Episode {i}:0", text or f"Episode {i} text", series, "episode",
                 f"Episode {i}", f"Episode {i}", "", i, "https://w", [])


class FakeEmbedder:
    """Three-dimensional 'meaning' vectors and a one-word keyword vector, enough to test search."""

    def embed_documents(self, texts):
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text):
        n = int(text.split()[1]) if text.split()[1].isdigit() else 1
        return Embedded(dense=[1.0, float(n), 0.5], sparse=SparseVector(indices=[n], values=[1.0]))


class Chunks:
    def __init__(self, items):
        self.items = items

    def iter_chunks(self, series):
        return [c for c in self.items if c.series == series]


@pytest.fixture
def index(tmp_path):
    idx = QdrantIndex(path=str(tmp_path / "qdrant"))
    yield idx
    idx.close()


def test_indexing_replaces_a_series_without_touching_others(index):
    embedder = FakeEmbedder()
    other = [chunk(1, series="one_piece")]
    IndexChunksService(Chunks(other), embedder, index, 3).index("one_piece")
    service = IndexChunksService(Chunks([chunk(1), chunk(2), chunk(3)]), embedder, index, 3)
    service.index("demon_slayer")
    assert index.count("demon_slayer") == 3

    # Re-index with one chunk fewer: the removed chunk must disappear, other series stay.
    IndexChunksService(Chunks([chunk(1), chunk(2)]), embedder, index, 3).index("demon_slayer")
    assert index.count("demon_slayer") == 2 and index.count("one_piece") == 1


def test_hybrid_search_finds_the_keyword_match_and_filters_by_series(index):
    embedder = FakeEmbedder()
    IndexChunksService(Chunks([chunk(i) for i in range(1, 6)]), embedder, index, 3).index("demon_slayer")
    hits = index.search(embedder.embed_query("Episode 4"), limit=3, series="demon_slayer")
    assert hits[0].chunk.number == 4 and hits[0].chunk.series == "demon_slayer"
    assert index.search(embedder.embed_query("Episode 4"), limit=3, series="one_piece") == []


def test_point_ids_are_stable_uuids():
    assert point_id("demon_slayer:episode:Episode 1:0") == point_id("demon_slayer:episode:Episode 1:0")
    assert point_id("a") != point_id("b") and len(point_id("a")) == 36


def test_no_chunks_is_an_error_and_leaves_the_index_alone(index):
    with pytest.raises(RuntimeError, match="run scripts/chunk.py"):
        IndexChunksService(Chunks([]), FakeEmbedder(), index, 3).index("demon_slayer")
