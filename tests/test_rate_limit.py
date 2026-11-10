"""Tests for the per-visitor question limits (fake clock, no network)."""

from fastapi.testclient import TestClient

from anichat import container
from anichat.interfaces import api
from anichat.interfaces.rate_limit import RateLimiter
from tests.test_api import FakeAnswers


def test_per_minute_and_per_day_limits_with_sliding_windows():
    now = {"t": 0.0}
    limiter = RateLimiter(per_minute=2, per_day=3, clock=lambda: now["t"])
    assert limiter.check("a") is None and limiter.check("a") is None
    assert limiter.check("a") == 60  # third in the same minute: wait for the first to expire
    assert limiter.check("b") is None  # other visitors are counted separately
    now["t"] = 61
    assert limiter.check("a") is None  # a new minute; 3 today
    now["t"] = 200
    wait = limiter.check("a")
    assert wait is not None and wait > 3600  # the daily limit: wait until the first expires
    now["t"] = 24 * 3600 + 1
    assert limiter.check("a") is None


def test_the_api_answers_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(container, "answer_service", lambda: FakeAnswers())
    monkeypatch.setattr(api, "limiter", RateLimiter(per_minute=1, per_day=0))
    http = TestClient(api.app)  # not a context manager: lifespan (model loading) skipped
    assert http.post("/chat", json={"question": "Who is Goku?"}).status_code == 200
    r = http.post("/chat/stream", json={"question": "Who is Vegeta?"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    assert "try again in 1 minute" in r.json()["detail"]
