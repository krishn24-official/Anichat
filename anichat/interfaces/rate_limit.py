"""Per-visitor limits on chat questions, so one visitor can't use up the free model quotas.

In memory (one API process): enough for a single small server. With several processes or
servers, each counts separately; a shared store (Redis) would be needed then.
"""

import threading
import time
from collections import deque
from typing import Callable

from fastapi import HTTPException, Request

WINDOWS = (("minute", 60), ("day", 24 * 3600))


class RateLimiter:
    """Allows up to `per_minute` and `per_day` questions per client (sliding windows).

    Created by: interfaces/api.py (one per process)
    Tested by:  tests/test_rate_limit.py
    """

    def __init__(self, per_minute: int, per_day: int, clock: Callable[[], float] = time.monotonic):
        self._limits = {"minute": per_minute, "day": per_day}
        self._clock = clock
        self._seen: dict[str, deque[float]] = {}  # client -> times of its questions in the last day
        self._lock = threading.Lock()  # requests are handled in several threads

    def check(self, client: str) -> float | None:
        """Record a question from `client`; None if allowed, else seconds until it would be.
        A limit of 0 means no limit.

        Called by: interfaces/api.py  limit_chat()
        """
        now = self._clock()
        with self._lock:
            times = self._seen.setdefault(client, deque())
            while times and now - times[0] >= WINDOWS[-1][1]:
                times.popleft()  # older than the longest window: no longer counted
            for name, seconds in WINDOWS:
                limit = self._limits[name]
                recent = [t for t in times if now - t < seconds]
                if limit and len(recent) >= limit:
                    return seconds - (now - recent[-limit])  # when the oldest counted one expires
            times.append(now)
            return None


def client_id(request: Request, trust_proxy: bool) -> str:
    """Who is asking: the client IP; behind a hosting proxy (Render, Fly...), the first
    X-Forwarded-For address, since the direct peer is the proxy.

    Called by: interfaces/api.py  limit_chat()
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if trust_proxy and forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def too_many(wait: float) -> HTTPException:
    """The 429 response for a client over its limit. Called by: interfaces/api.py  limit_chat()"""
    minutes = max(1, round(wait / 60))
    when = f"{minutes} minute{'s' if minutes > 1 else ''}" if wait < 3600 else f"{round(wait / 3600)} hours"
    return HTTPException(status_code=429, detail=f"You've asked a lot of questions. Please try again in {when}.",
                         headers={"Retry-After": str(int(wait) + 1)})
