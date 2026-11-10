"""Tests for streamed answers: provider fallback before the first piece, the answer
service's events, and the server-sent events endpoint (fakes only: no models, no network)."""

import json

from fastapi.testclient import TestClient

from anichat import container
from anichat.application.answer import BUSY_ANSWER, CUT_OFF, Answer, AnswerService
from anichat.application.llm_fallback import AllModelsUnavailable, FallbackChatModel
from anichat.domain.answering import Source
from anichat.domain.llm import ModelUnavailable
from anichat.interfaces import api
from tests.test_answer import EP33, FakeRetrieval


class StreamingModel:
    """Yields `pieces`; fails before the first one (fail_at=0) or after some (fail_at=n)."""

    def __init__(self, name, pieces=("Rengoku ", "died [1]", "."), fail_at=None):
        self.name, self.pieces, self.fail_at = name, pieces, fail_at

    def stream(self, messages):
        for i, piece in enumerate(self.pieces):
            if i == self.fail_at:
                raise ModelUnavailable("429 quota")
            yield piece
        if self.fail_at is not None and self.fail_at >= len(self.pieces):
            raise ModelUnavailable("connection dropped")


def test_fallback_switches_provider_only_before_the_first_piece():
    model = FallbackChatModel([StreamingModel("gemini", fail_at=0), StreamingModel("groq")])
    name, pieces = model.stream([])
    assert name == "groq" and "".join(pieces) == "Rengoku died [1]."

    try:
        FallbackChatModel([StreamingModel("gemini", fail_at=0)]).stream([])
        assert False, "expected AllModelsUnavailable"
    except AllModelsUnavailable:
        pass


def test_stream_yields_pieces_then_the_finished_answer():
    events = list(AnswerService(FakeRetrieval([EP33]), FallbackChatModel([StreamingModel("groq")])).stream("q?"))
    assert events[:3] == ["Rengoku ", "died [1]", "."]
    final = events[-1]
    assert isinstance(final, Answer) and final.text == "Rengoku died [1]." and final.model == "groq"
    assert [s.numbers for s in final.sources] == [(1,)]
    assert {"retrieve", "first_token", "generate"} <= set(final.timings)


def test_stream_reports_busy_models_and_a_cut_off_answer():
    busy = list(AnswerService(FakeRetrieval([EP33]), FallbackChatModel([StreamingModel("g", fail_at=0)])).stream("q?"))
    assert len(busy) == 1 and busy[0].text == BUSY_ANSWER

    cut = list(AnswerService(FakeRetrieval([EP33]), FallbackChatModel([StreamingModel("g", fail_at=3)])).stream("q?"))
    assert cut[-1].text.startswith("Rengoku died [1].") and cut[-1].text.endswith(CUT_OFF)


class FakeStreamingAnswers:
    def stream(self, question, series=None, history=()):
        yield "Rengoku "
        yield "died [1]."
        yield Answer(question, "Rengoku died [1].", [Source((1,), "Kyojuro Rengoku", "Death", "https://w/Rengoku")],
                     "groq", {"retrieve": 0.21234})


def test_stream_endpoint_sends_server_sent_events(monkeypatch):
    monkeypatch.setattr(container, "answer_service", lambda: FakeStreamingAnswers())
    http = TestClient(api.app)  # not a context manager: lifespan (model loading) skipped
    r = http.post("/chat/stream", json={"question": "How did Rengoku die?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[len("data: "):]) for line in r.text.split("\n\n") if line.startswith("data: ")]
    assert [e["type"] for e in events] == ["delta", "delta", "done"]
    assert events[0]["text"] == "Rengoku "
    assert events[-1]["answer"] == "Rengoku died [1]." and events[-1]["sources"][0]["numbers"] == [1]
    assert events[-1]["timings"] == {"retrieve": 0.212}
    assert http.post("/chat/stream", json={"question": "Who?", "series": "pokemon"}).status_code == 422
