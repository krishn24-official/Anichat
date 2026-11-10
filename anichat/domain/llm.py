"""Chat model vocabulary, independent of any provider. Pure Python, no I/O."""

from dataclasses import dataclass
from typing import Iterator, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system", "user" or "assistant"
    content: str


@dataclass(frozen=True)
class ModelReply:
    """Created by a ChatModel.complete(); used by application/answer.py."""

    text: str
    model: str  # which model answered, e.g. "gemini:gemini-2.5-flash-lite"


class ModelUnavailable(Exception):
    """Quota exhausted, rate limited, missing key or provider down: try the next one.

    Raised by:  infrastructure/openai_compatible.py  OpenAICompatibleModel.complete()
    Handled by: application/llm_fallback.py          FallbackChatModel.complete()
    """

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after  # seconds, when the provider said


class ChatModel(Protocol):
    """One provider's chat model.

    Implemented by: infrastructure/openai_compatible.py  OpenAICompatibleModel (Gemini, Groq)
                    application/llm_fallback.py          FallbackChatModel (tries several)
    Used by:        application/answer.py                AnswerService
    """

    name: str

    def complete(self, messages: list[ChatMessage]) -> ModelReply:
        """One answer for the conversation. Raises ModelUnavailable to let another provider try."""
        ...

    def stream(self, messages: list[ChatMessage]) -> Iterator[str]:
        """The answer in pieces as the model writes it. Raises ModelUnavailable before the first
        piece to let another provider try; a failure later raises ModelUnavailable mid-stream."""
        ...
