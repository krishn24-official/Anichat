"""Shared test setup."""

import pytest

from anichat.interfaces import api
from anichat.interfaces.rate_limit import RateLimiter


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    """API tests ask many questions from one client: give each test an unlimited limiter
    (tests/test_rate_limit.py checks the limits themselves)."""
    monkeypatch.setattr(api, "limiter", RateLimiter(per_minute=0, per_day=0))
