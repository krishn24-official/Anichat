"""An Embedder wrapper that remembers vectors, keyed by the exact text and model.

Embedding a full chunk takes ~0.3 s on a laptop CPU (a series: ~20-30 minutes), so
re-indexing should only embed chunks whose text actually changed. Vectors live in
one SQLite file (data/embeddings.sqlite): standard library, nothing to install.
"""

import hashlib
import json
import sqlite3
from array import array
from pathlib import Path

from anichat.domain.ports import Embedded, Embedder, SparseVector


SAVE_EVERY = 256  # chunks embedded between two saves to the cache


def text_key(model: str, text: str) -> str:
    """Cache key: the model name and the text (a different model must never reuse vectors).

    Called by: CachingEmbedder.embed_documents(), CachingEmbedder.seed()
    """
    return hashlib.sha256(f"{model}\n{text}".encode("utf-8")).hexdigest()


class CachingEmbedder:
    """Implements domain/ports.py Embedder by wrapping another Embedder.

    Created by: scripts/index.py  main()   (wraps FastEmbedEmbedder)
    Used by:    application/index_chunks.py  IndexChunksService.index()
    """

    def __init__(self, inner: Embedder, path: Path, model: str):
        self._inner = inner
        self._model = model
        self.dense_size = getattr(inner, "dense_size", None)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Two processes may share the cache (the indexer, and scripts/embed.py filling it ahead on a
        # GPU): wait for the other's write instead of failing with "database is locked".
        self._db = sqlite3.connect(str(path), timeout=120)
        self._db.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, dense BLOB, sparse TEXT)")
        self.hits = 0  # how many chunks came from the cache in this run (printed by scripts/index.py)
        self.misses = 0

    def close(self) -> None:
        """Called by: scripts/index.py main()"""
        self._db.close()

    def _store(self, items: list[tuple[str, Embedded]]) -> None:
        """Save (key, vectors) pairs. Dense as float32 bytes (4x smaller than JSON numbers).

        Called by: embed_documents(), seed()
        """
        self._db.executemany(
            "INSERT OR REPLACE INTO vectors VALUES (?, ?, ?)",
            [(k, array("f", e.dense).tobytes(), json.dumps([e.sparse.indices, e.sparse.values])) for k, e in items],
        )
        self._db.commit()

    def embed_documents(self, texts: list[str]) -> list[Embedded]:
        """Cached vectors where available; only the rest go to the real model.

        Called by: application/index_chunks.py  IndexChunksService.index()
        """
        keys = [text_key(self._model, t) for t in texts]
        found = {}
        for i in range(0, len(keys), 500):  # SQLite limits the number of query parameters
            batch = keys[i:i + 500]
            rows = self._db.execute(
                f"SELECT key, dense, sparse FROM vectors WHERE key IN ({','.join('?' * len(batch))})", batch
            )
            for key, dense, sparse in rows:
                indices, values = json.loads(sparse)
                found[key] = Embedded(dense=array("f", dense).tolist(), sparse=SparseVector(indices, values))

        missing = [i for i, k in enumerate(keys) if k not in found]
        self.hits, self.misses = len(texts) - len(missing), len(missing)
        # Embedded and saved in batches: a run stopped after an hour (One Piece takes ~3 h on a
        # laptop CPU) keeps everything embedded so far, and the next run continues from there.
        for start in range(0, len(missing), SAVE_EVERY):
            batch = missing[start:start + SAVE_EVERY]
            fresh = self._inner.embed_documents([texts[i] for i in batch])
            self._store([(keys[i], e) for i, e in zip(batch, fresh)])
            found.update({keys[i]: e for i, e in zip(batch, fresh)})
        return [found[k] for k in keys]

    def embed_query(self, text: str) -> Embedded:
        """Questions are not cached (each is embedded in well under a second).

        Called by: scripts/index.py  _preview(); stage 5 (retrieval)
        """
        return self._inner.embed_query(text)

    def seed(self, texts: list[str], vectors: list[Embedded]) -> None:
        """Pre-fill the cache with vectors computed elsewhere (e.g. read back from Qdrant).

        Called by: one-off maintenance (filling the cache from the existing index)
        """
        self._store([(text_key(self._model, t), v) for t, v in zip(texts, vectors)])
