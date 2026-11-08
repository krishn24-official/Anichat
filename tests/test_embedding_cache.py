"""Tests for the embedding cache (real SQLite file in a temp folder)."""

from anichat.domain.ports import Embedded, SparseVector
from anichat.infrastructure.embedding_cache import CachingEmbedder


class CountingEmbedder:
    dense_size = 2

    def __init__(self):
        self.embedded = []

    def embed_documents(self, texts):
        self.embedded += texts
        return [Embedded([float(len(t)), 0.5], SparseVector([len(t)], [1.0])) for t in texts]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


def test_only_new_or_changed_texts_are_embedded(tmp_path):
    inner = CountingEmbedder()
    cache = CachingEmbedder(inner, tmp_path / "e.sqlite", model="m1")
    first = cache.embed_documents(["a", "bb"])
    assert inner.embedded == ["a", "bb"] and (cache.hits, cache.misses) == (0, 2)

    again = cache.embed_documents(["bb", "a", "ccc"])  # order changes, one new text
    assert inner.embedded == ["a", "bb", "ccc"] and (cache.hits, cache.misses) == (2, 1)
    assert again[0] == first[1] and again[1] == first[0]  # vectors come back in the asked order
    cache.close()


def test_another_model_never_reuses_vectors(tmp_path):
    inner = CountingEmbedder()
    CachingEmbedder(inner, tmp_path / "e.sqlite", model="m1").embed_documents(["a"])
    CachingEmbedder(inner, tmp_path / "e.sqlite", model="m2").embed_documents(["a"])
    assert inner.embedded == ["a", "a"]


def test_seed_prefills_the_cache(tmp_path):
    inner = CountingEmbedder()
    cache = CachingEmbedder(inner, tmp_path / "e.sqlite", model="m1")
    cache.seed(["x"], [Embedded([1.0, 2.0], SparseVector([3], [0.5]))])
    assert cache.embed_documents(["x"])[0] == Embedded([1.0, 2.0], SparseVector([3], [0.5]))
    assert inner.embedded == []
