"""Composition root: the one place that builds services from concrete implementations.

Swapping a technology (e.g. Qdrant local -> Qdrant Cloud, or adding an LLM provider)
means changing only this file (and config.py).

Used by: interfaces/api.py (on startup), scripts/chat.py
"""

from functools import lru_cache

from anichat import config
from anichat.application.answer import AnswerService
from anichat.application.llm_fallback import FallbackChatModel
from anichat.application.retrieve import RetrievalService
from anichat.infrastructure.fastembed_embedder import FastEmbedEmbedder
from anichat.infrastructure.openai_compatible import GEMINI_URL, GROQ_URL, OpenAICompatibleModel
from anichat.infrastructure.qdrant_index import QdrantIndex


@lru_cache(maxsize=None)
def index() -> QdrantIndex:
    """Qdrant Cloud when QDRANT_URL is set, otherwise the local folder.
    Called by: answer_service(); interfaces/api.py on shutdown (close)"""
    if config.QDRANT_URL:
        return QdrantIndex(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)
    return QdrantIndex(path=config.QDRANT_PATH)


@lru_cache(maxsize=None)
def chat_model() -> FallbackChatModel:
    """Providers in LLM_PROVIDERS order (each with one or more models); ones without a key
    are left out.
    Called by: answer_service()"""
    providers = {
        "gemini": (config.GEMINI_API_KEY, GEMINI_URL, config.GEMINI_MODELS),
        "groq": (config.GROQ_API_KEY, GROQ_URL, [config.GROQ_MODEL]),
    }
    models = [
        OpenAICompatibleModel(name, url, key, model)
        for name in config.LLM_PROVIDERS if name in providers
        for key, url, names in [providers[name]] if key
        for model in names
    ]
    return FallbackChatModel(models)


@lru_cache(maxsize=None)
def answer_service() -> AnswerService:
    """Retrieval (stage 5, no reranker: see application/retrieve.py) + the chat model.
    Called by: interfaces/api.py, scripts/chat.py"""
    return AnswerService(RetrievalService(FastEmbedEmbedder(), index()), chat_model())
