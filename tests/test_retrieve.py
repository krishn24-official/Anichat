"""Tests for stage 5: question hints and the retrieval pipeline (fakes, no models)."""

from anichat.application.retrieve import RetrievalService
from anichat.domain.chunking import Chunk
from anichat.domain.ports import Embedded, SearchHit, SparseVector
from anichat.domain.query import parse_question


def chunk(cid, title, kind="character", number=None):
    return Chunk(cid, f"Series › {title}\n\ntext about {title}", "demon_slayer", kind, title, title, "", number, "u", [])


def test_question_hints():
    assert parse_question("What happens in chapter 196?").chapter == 196
    assert parse_question("summary of ch. 12").chapter == 12
    assert parse_question("first episode recap").episode == 1
    assert parse_question("What happens in Episode 19") .episode == 19
    assert parse_question("Who is Nezuko?") == parse_question("")  # no hints


class FakeEmbedder:
    def embed_query(self, text):
        return Embedded([0.0], SparseVector([], []))


class FakeIndex:
    def __init__(self):
        self.hits = [SearchHit(chunk("a", "Hairo"), 0.9), SearchHit(chunk("b", "Kyojuro Rengoku"), 0.8),
                     SearchHit(chunk("c", "Chapter 196", "chapter", 196), 0.7)]

    def search(self, query, limit, series=None):
        return self.hits[:limit]

    def profile_cards(self, series=None):
        akaza = Chunk("ds:character:Akaza:card",
                      "Series › Akaza › Profile\n\nAkaza is a demon who held the position of Upper Rank Three.",
                      "demon_slayer", "character", "Akaza", "Akaza", "Profile", None, "u", [])
        return [akaza]

    def find(self, kind, number, series=None, limit=3):
        return [chunk("c", "Chapter 196", "chapter", 196)] if (kind, number) == ("chapter", 196) else []


class FakeReranker:
    def score(self, question, passages):
        return [1.0 if "Rengoku" in p else 0.1 for p in passages]


def test_reranker_reorders_search_results():
    result = RetrievalService(FakeEmbedder(), FakeIndex(), FakeReranker()).retrieve("How did Rengoku die?")
    assert result.chunks[0].chunk.title == "Kyojuro Rengoku" and result.chunks[0].via == "rerank"
    assert set(result.timings) == {"exact", "search", "rerank", "entity", "total"}


def test_exact_lookup_comes_first_and_is_not_duplicated():
    result = RetrievalService(FakeEmbedder(), FakeIndex(), None).retrieve("What happens in chapter 196?")
    assert result.chunks[0].chunk.title == "Chapter 196" and result.chunks[0].via == "exact"
    assert [r.chunk.id for r in result.chunks].count("c") == 1


def test_without_reranker_search_order_is_kept():
    result = RetrievalService(FakeEmbedder(), FakeIndex(), None).retrieve("Who is Hairo?", limit=2)
    assert [r.chunk.title for r in result.chunks] == ["Hairo", "Kyojuro Rengoku"]


def test_a_title_the_search_missed_takes_the_last_slot():
    result = RetrievalService(FakeEmbedder(), FakeIndex(), None).retrieve("Who is Upper Rank Three?", limit=3)
    assert [r.chunk.title for r in result.chunks] == ["Hairo", "Kyojuro Rengoku", "Akaza"]
    assert result.chunks[-1].via == "entity"
    plain = RetrievalService(FakeEmbedder(), FakeIndex(), None).retrieve("Who is Hairo?", limit=3)
    assert all(r.via != "entity" for r in plain.chunks)
