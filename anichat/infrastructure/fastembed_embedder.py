"""Embedder backed by FastEmbed (ONNX models: no PyTorch, small enough for a cheap host).

Models are downloaded on first use into AniChat/models/ (not the OS temp folder,
which disk cleanup can empty).
"""

import os
from pathlib import Path

from fastembed import SparseTextEmbedding, TextEmbedding

from anichat.domain.ports import Embedded, SparseVector

DENSE_MODEL = "BAAI/bge-small-en-v1.5"  # 384 dimensions, 512-token input
SPARSE_MODEL = "Qdrant/bm25"  # classic keyword scoring; Qdrant applies the IDF part
DENSE_SIZE = 384
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
# ANICHAT_EMBED_DEVICE=cuda runs the dense model on an NVIDIA GPU (needs onnxruntime-gpu: see
# README, "Faster indexing"). Same model and vectors as on the CPU, several times faster.
DEVICE = os.getenv("ANICHAT_EMBED_DEVICE", "cpu").lower()


class FastEmbedEmbedder:
    """Implements domain/ports.py Embedder.

    Created by: scripts/index.py  main()
    Used by:    application/index_chunks.py  IndexChunksService (documents)
                scripts/index.py  preview searches (queries); stage 5 will use embed_query()
    """

    dense_size = DENSE_SIZE

    def __init__(self, batch_size: int = 64, device: str = DEVICE):
        MODELS_DIR.mkdir(exist_ok=True)
        if device == "cuda":
            import onnxruntime  # onnxruntime-gpu: load the CUDA/cuDNN libraries installed with it by pip
            onnxruntime.preload_dlls()
            self._dense = TextEmbedding(DENSE_MODEL, cache_dir=str(MODELS_DIR),
                                        providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
            # Small batches: on a 4 GB GPU (GTX 1650) 256 long chunks overflow memory and halve the
            # speed; 16-128 all run at ~16 chunks/s there.
            batch_size = 32
        else:
            self._dense = TextEmbedding(DENSE_MODEL, cache_dir=str(MODELS_DIR))
        self.device = device
        self._sparse = SparseTextEmbedding(SPARSE_MODEL, cache_dir=str(MODELS_DIR))
        self._batch = batch_size

    @staticmethod
    def _sparse_vector(s) -> SparseVector:
        """FastEmbed's sparse result -> our SparseVector. Called by embed_documents(), embed_query()"""
        return SparseVector(indices=s.indices.tolist(), values=s.values.tolist())

    def embed_documents(self, texts: list[str]) -> list[Embedded]:
        """Dense + sparse vectors for passages (chunks).

        Called by: application/index_chunks.py  IndexChunksService.index()
        """
        dense = self._dense.passage_embed(texts, batch_size=self._batch)
        sparse = self._sparse.passage_embed(texts, batch_size=self._batch)
        return [Embedded(dense=d.tolist(), sparse=self._sparse_vector(s)) for d, s in zip(dense, sparse)]

    def embed_query(self, text: str) -> Embedded:
        """Dense + sparse vectors for a question (FastEmbed adds the query instruction bge
        expects, and BM25 weights query words differently from passage words).

        Called by: scripts/index.py  _preview(); stage 5 (retrieval)
        """
        dense = next(iter(self._dense.query_embed(text)))
        sparse = next(iter(self._sparse.query_embed(text)))
        return Embedded(dense=dense.tolist(), sparse=self._sparse_vector(sparse))
