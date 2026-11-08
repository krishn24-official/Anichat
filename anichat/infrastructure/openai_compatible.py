"""ChatModel for any OpenAI-compatible chat API, over plain HTTP (no SDKs).

Both free providers speak this format:
- Gemini: https://generativelanguage.googleapis.com/v1beta/openai
- Groq:   https://api.groq.com/openai/v1
"""

import time

import httpx

from anichat.domain.llm import ChatMessage, ModelReply, ModelUnavailable

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GROQ_URL = "https://api.groq.com/openai/v1"
MAX_WAIT_SECONDS = 15  # a per-minute limit asking us to wait this long or less is waited out


def _retry_after(r: httpx.Response) -> float | None:
    """Seconds the provider asks us to wait (Retry-After header), if any. Called by complete()"""
    try:
        return float(r.headers["retry-after"])
    except (KeyError, ValueError):
        return None


def _error_message(r: httpx.Response) -> str:
    """The provider's error as one short line (Gemini returns a multi-line JSON list).

    Called by: OpenAICompatibleModel.complete()
    """
    try:
        data = r.json()
        error = (data[0] if isinstance(data, list) else data).get("error", {})
        message = error.get("message", "") if isinstance(error, dict) else str(error)
    except (ValueError, AttributeError, IndexError):
        message = r.text
    return " ".join(message.split())[:160]


class OpenAICompatibleModel:
    """Implements domain/llm.py ChatModel.

    Created by: anichat/container.py  chat_model()
    Used by:    application/llm_fallback.py  FallbackChatModel
    """

    def __init__(self, provider: str, base_url: str, api_key: str | None, model: str, timeout: float = 60):
        self._url = f"{base_url}/chat/completions"
        self._key = api_key
        self._model = model
        self._timeout = timeout
        self.name = f"{provider}:{model}"

    def complete(self, messages: list[ChatMessage]) -> ModelReply:
        """Send the conversation, return the answer text. Any failure (no key, quota,
        rate limit, outage) raises ModelUnavailable so the fallback tries the next provider.

        Called by: application/llm_fallback.py  FallbackChatModel.complete()
        """
        if not self._key:
            raise ModelUnavailable(f"{self.name}: no API key in .env")
        body = {"model": self._model, "messages": [{"role": m.role, "content": m.content} for m in messages]}
        headers = {"Authorization": f"Bearer {self._key}"}
        try:
            with httpx.Client(timeout=self._timeout) as http:
                for attempt in range(2):
                    r = http.post(self._url, json=body, headers=headers)
                    wait = _retry_after(r)
                    if attempt == 0 and r.status_code == 429 and wait is not None and wait <= MAX_WAIT_SECONDS:
                        time.sleep(wait)  # per-minute limit: wait it out once
                        continue
                    break
        except httpx.HTTPError as e:
            raise ModelUnavailable(f"{self.name}: {e}") from e
        if r.status_code != 200:
            raise ModelUnavailable(f"{self.name}: HTTP {r.status_code} {_error_message(r)}", retry_after=_retry_after(r))
        message = (r.json().get("choices") or [{}])[0].get("message") or {}
        return ModelReply(text=(message.get("content") or "").strip(), model=self.name)
