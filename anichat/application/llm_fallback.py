"""A ChatModel that tries free-tier providers in order (Gemini, then Groq, ...)."""

import logging
from datetime import datetime, timedelta, timezone
from itertools import chain
from typing import Callable, Iterator

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

    def stream(self, messages: list[ChatMessage]) -> tuple[str, Iterator[str]]:
        """(model name, the answer in pieces) from the first model that starts answering.
        A provider is only switched before its first piece: once text was shown, a failure
        is the caller's to report.

        Called by: application/answer.py  AnswerService.stream()
        """
        now = self._clock()
        ready = [m for m in self._models if self._cooling.get(m.name, now) <= now]
        for model in ready or self._models:
            pieces = model.stream(messages)
            try:
                first = next(pieces)
            except StopIteration:
                first = ""  # an empty answer: still this model's answer
            except ModelUnavailable as e:
                logger.warning("model %s unavailable, trying the next: %s", model.name, e)
                self._cooling[model.name] = now + (timedelta(seconds=e.retry_after) if e.retry_after else COOLDOWN)
                continue
            self._cooling.pop(model.name, None)
            return model.name, chain([first], pieces)
        raise AllModelsUnavailable("no chat model available")
