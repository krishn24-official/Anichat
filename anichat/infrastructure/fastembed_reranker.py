"""Reranker backed by a FastEmbed cross-encoder (ONNX, small enough for a cheap host).

A cross-encoder reads the question and a passage *together*, so it can tell "answers
the question" from "uses the same words" much better than vector search. It costs
time proportional to the text it reads, so only the first RERANK_CHARS of each
candidate are scored (chunks start with their location line and main point).
"""

from pathlib import Path

from fastembed.rerank.cross_encoder import TextCrossEncoder

RERANK_MODEL = "jinaai/jina-reranker-v1-tiny-en"  # ~130 MB, the fastest tested on a laptop CPU
RERANK_CHARS = 1000
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


class FastEmbedReranker:
    """Implements domain/ports.py Reranker.

    Created by: scripts/ask.py main(), scripts/evaluate.py main()
    Used by:    application/retrieve.py  RetrievalService.retrieve()
    """

    def __init__(self, model: str = RERANK_MODEL, max_chars: int = RERANK_CHARS):
        MODELS_DIR.mkdir(exist_ok=True)
        self._encoder = TextCrossEncoder(model, cache_dir=str(MODELS_DIR))
        self._max_chars = max_chars

    def score(self, question: str, passages: list[str]) -> list[float]:
        """One relevance score per passage (higher = better answer to the question).

        Called by: application/retrieve.py  RetrievalService.retrieve()
        """
        if not passages:
            return []
        return [float(s) for s in self._encoder.rerank(question, [p[: self._max_chars] for p in passages])]
