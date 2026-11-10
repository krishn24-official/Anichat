"""Tests for stage 6: prompt + citations, model fallback, the answer service and the API
(fakes only: no models, no network)."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from anichat import container
from anichat.application.answer import BUSY_ANSWER, AnswerService
from anichat.application.llm_fallback import COOLDOWN, AllModelsUnavailable, FallbackChatModel
from anichat.application.retrieve import Retrieval, RetrievedChunk
from anichat.domain.answering import NO_SOURCES_ANSWER, build_messages, cited_numbers, cited_sources, normalize_citations
from anichat.domain.chunking import Chunk
from anichat.domain.llm import ModelReply, ModelUnavailable

EP33 = Chunk("ds:episode:Episode 33:0", "Demon Slayer › Episode 33 › Synopsis\n\nRengoku dies after fighting Akaza.",
             "demon_slayer", "episode", "Episode 33", "Episode 33: Set Your Heart Ablaze", "Synopsis", 33,
             "https://w/wiki/Episode_33", ["Akaza"])
AKAZA = Chunk("ds:character:Akaza:0", "Demon Slayer › Akaza\n\nAkaza is Upper Rank Three.", "demon_slayer",
              "character", "Akaza", "Akaza", "", None, "https://w/wiki/Akaza", [])


def test_prompt_numbers_sources_and_citations_are_read_back():
    messages = build_messages("How did Rengoku die?", [EP33, AKAZA])
    assert messages[0].role == "system" and "ONLY the numbered sources" in messages[0].content
    assert "[1] Demon Slayer › Episode 33" in messages[1].content and messages[1].content.endswith("How did Rengoku die?")
    assert cited_numbers("He died [1][2]. Also [1, 2] and [7].", available=2) == [1, 2]  # [7] doesn't exist


class FakeRetrieval:
    def __init__(self, chunks):
        self.chunks = chunks

    def retrieve(self, question, series=None, limit=5):
        return Retrieval(question, [RetrievedChunk(c, 1.0, "search") for c in self.chunks], {"total": 0.1})


class FakeModel:
    def __init__(self, name="gemini", text="Rengoku died fighting Akaza [1].", fail=False):
        self.name, self.text, self.fail, self.calls = name, text, fail, 0

    def complete(self, messages):
        self.calls += 1
        if self.fail:
            raise ModelUnavailable("429 quota")
        return ModelReply(self.text, self.name)


def test_answer_cites_only_the_sources_it_used():
    answer = AnswerService(FakeRetrieval([EP33, AKAZA]), FakeModel()).answer("How did Rengoku die?")
    assert answer.text == "Rengoku died fighting Akaza [1]."
    assert [s.title for s in answer.sources] == ["Episode 33: Set Your Heart Ablaze"]
    assert answer.model == "gemini" and {"retrieve", "generate"} <= set(answer.timings)


def test_nothing_retrieved_means_no_model_call():
    model = FakeModel()
    answer = AnswerService(FakeRetrieval([]), model).answer("Who is Goku?")
    assert answer.text == NO_SOURCES_ANSWER and model.calls == 0


def test_fallback_order_cooldown_and_all_busy():
    now = {"t": datetime(2026, 11, 8, tzinfo=timezone.utc)}
    gemini, groq = FakeModel("gemini", fail=True), FakeModel("groq")
    model = FallbackChatModel([gemini, groq], clock=lambda: now["t"])
    assert model.complete([]).model == "groq"
    model.complete([])
    assert gemini.calls == 1  # skipped while cooling down
    now["t"] += COOLDOWN + timedelta(seconds=1)
    gemini.fail = False
    assert model.complete([]).model == "gemini"

    busy = AnswerService(FakeRetrieval([EP33]), FallbackChatModel([FakeModel(fail=True)])).answer("q?")
    assert busy.text == BUSY_ANSWER and busy.sources == []


def test_api_chat_endpoint(monkeypatch):
    from anichat.interfaces import api

    service = AnswerService(FakeRetrieval([EP33]), FakeModel())
    monkeypatch.setattr(container, "answer_service", lambda: service)

    class NoIndex:
        def close(self):
            pass

    class NoWarmUp:
        def warm_up(self):  # the startup step that reads profile cards from the index
            pass

    monkeypatch.setattr(container, "index", lambda: NoIndex())
    monkeypatch.setattr(container, "retrieval_service", lambda: NoWarmUp())
    with TestClient(api.app) as client:
        r = client.post("/chat", json={"question": "How did Rengoku die?"})
        assert r.status_code == 200
        body = r.json()
        assert body["answer"].startswith("Rengoku died") and body["sources"][0]["numbers"] == [1]
        assert client.post("/chat", json={"question": ""}).status_code == 422  # validation


def test_other_citation_styles_and_same_section_sources_are_merged():
    assert normalize_citations("Thunder Breathing【1】 and 【2†L3-L5】.") == "Thunder Breathing[1] and [2]."
    part2 = Chunk("ds:episode:Episode 33:1", "more", "demon_slayer", "episode", "Episode 33",
                  "Episode 33: Set Your Heart Ablaze", "Synopsis", 33, "https://w/wiki/Episode_33", [])
    sources = cited_sources("A [1]. B [2]. C [3].", [EP33, part2, AKAZA])
    assert [(s.numbers, s.title) for s in sources] == [((1, 2), "Episode 33: Set Your Heart Ablaze"), ((3,), "Akaza")]
