"""A ChatModel that tries free-tier providers in order (Gemini, then Groq, ...)."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from anichat.domain.llm import ChatMessage, ChatModel, ModelReply, ModelUnavailable

logger = logging.getLogger(__name__)

# An out-of-quota provider is skipped for a while instead of failing on every question.
# Per-minute limits say how long to wait (retry_after) and only skip that long.
COOLDOWN = timedelta(minutes=15)


class AllModelsUnavailable(Exception):
    """Every provider is out of quota or failing. Raised by FallbackChatModel.complete();
    handled by application/answer.py AnswerService.answer()."""


class FallbackChatModel:
    """Implements domain/llm.py ChatModel on top of several others.

    Created by: anichat/container.py  chat_model()
    Used by:    application/answer.py  AnswerService
    Tested by:  tests/test_answer.py
    """

    def __init__(self, models: list[ChatModel], clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._models = models
        self._clock = clock
        self._cooling: dict[str, datetime] = {}  # model name -> skip until
        self.name = "fallback(" + ", ".join(m.name for m in models) + ")"

    def complete(self, messages: list[ChatMessage]) -> ModelReply:
        """The first available model's answer.

        Called by: application/answer.py  AnswerService.answer()
        """
        now = self._clock()
        ready = [m for m in self._models if self._cooling.get(m.name, now) <= now]
        for model in ready or self._models:  # all cooling down: try anyway, quotas may have reset
            try:
                reply = model.complete(messages)
                self._cooling.pop(model.name, None)
                return reply
            except ModelUnavailable as e:
                logger.warning("model %s unavailable, trying the next: %s", model.name, e)
                self._cooling[model.name] = now + (timedelta(seconds=e.retry_after) if e.retry_after else COOLDOWN)
        raise AllModelsUnavailable("no chat model available")
