"""Tests for the HTTP API with fake services (no models, index or network)."""

from fastapi.testclient import TestClient

from anichat import container
from anichat.application.answer import Answer
from anichat.domain.answering import Source
from anichat.interfaces import api


class FakeAnswers:
    def __init__(self):
        self.asked = []

    def answer(self, question, series=None, history=()):
        self.asked.append((question, series))
        self.history = list(history)
        return Answer(question, "Rengoku died fighting Akaza [1].",
                      [Source((1,), "Kyojuro Rengoku", "Death", "https://example/wiki/Rengoku")],
                      "gemini:gemini-2.5-flash", {"retrieve": 0.21234, "generate": 1.5})


class FakeIndex:
    def count(self, series=None):
        return {"demon_slayer": 4125, "naruto_shippuden": 2497}.get(series, 0)


def client(monkeypatch) -> tuple[TestClient, FakeAnswers]:
    answers = FakeAnswers()
    monkeypatch.setattr(container, "answer_service", lambda: answers)
    monkeypatch.setattr(container, "index", lambda: FakeIndex())
    api._indexed_series.cache_clear()
    return TestClient(api.app), answers  # not used as a context manager: lifespan (model loading) skipped


def test_chat_returns_the_answer_with_sources_and_rounded_timings(monkeypatch):
    http, answers = client(monkeypatch)
    r = http.post("/chat", json={"question": "  How did Rengoku die? ", "series": "demon_slayer"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("Rengoku died") and body["model"] == "gemini:gemini-2.5-flash"
    assert body["sources"] == [{"numbers": [1], "title": "Kyojuro Rengoku", "section": "Death",
                                "url": "https://example/wiki/Rengoku"}]
    assert body["timings"]["retrieve"] == 0.212
    assert answers.asked == [("How did Rengoku die?", "demon_slayer")]


def test_chat_rejects_unknown_series_and_too_short_questions(monkeypatch):
    http, answers = client(monkeypatch)
    assert http.post("/chat", json={"question": "Who is Goku?", "series": "pokemon"}).status_code == 422
    assert http.post("/chat", json={"question": "?"}).status_code == 422
    assert answers.asked == []


def test_series_lists_only_indexed_series_with_their_franchise(monkeypatch):
    http, _ = client(monkeypatch)
    body = http.get("/series").json()
    assert [s["id"] for s in body] == ["demon_slayer", "naruto_shippuden"]
    assert body[1] == {"id": "naruto_shippuden", "title": "Naruto Shippuden", "franchise": "naruto", "chunks": 2497}


def test_cors_allows_the_frontend_origin(monkeypatch):
    http, _ = client(monkeypatch)
    r = http.options("/chat", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_chat_passes_the_conversation_history(monkeypatch):
    http, answers = client(monkeypatch)
    history = [{"question": "Who is Akaza?", "answer": "Upper Rank Three [1]."}]
    assert http.post("/chat", json={"question": "Who killed him?", "history": history}).status_code == 200
    assert [(t.question, t.answer) for t in answers.history] == [("Who is Akaza?", "Upper Rank Three [1].")]
    too_long = [{"question": "q", "answer": "a"}] * 21
    assert http.post("/chat", json={"question": "Who killed him?", "history": too_long}).status_code == 422
