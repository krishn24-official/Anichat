"""Fill the embedding cache for series ahead of indexing (no Qdrant needed).

Run on a GPU while scripts/index.py works through its queue on the CPU: when the indexer
reaches a series, its vectors are already cached and it only stores them.

    set ANICHAT_EMBED_DEVICE=cuda
    .venv-gpu\\Scripts\\python -m scripts.embed --series bleach fairy_tail mcu

Uses the same model and cache key as scripts/index.py, so the vectors are interchangeable.
"""

import argparse
import time
from pathlib import Path

from anichat.domain.series import SERIES
from anichat.infrastructure.chunk_store import ChunkStore
from anichat.infrastructure.embedding_cache import CachingEmbedder
from anichat.infrastructure.fastembed_embedder import DENSE_MODEL, SPARSE_MODEL, FastEmbedEmbedder

DATA = Path(__file__).resolve().parents[1] / "data"
BATCH = 2048  # chunks per pass: the cache saves every 256 of them, so a stop loses little


def main(series_ids: list[str]) -> None:
    """Embed every chunk of each series not in the cache yet, printing progress.

    Called by: this file's __main__ block (command line)
    """
    inner = FastEmbedEmbedder()
    embedder = CachingEmbedder(inner, DATA / "embeddings.sqlite", model=f"{DENSE_MODEL}+{SPARSE_MODEL}")
    store = ChunkStore(DATA / "chunks")
    try:
        for series_id in series_ids:
            texts = [c.text for c in store.iter_chunks(series_id)]
            started, embedded = time.time(), 0
            for i in range(0, len(texts), BATCH):
                embedder.embed_documents(texts[i:i + BATCH])
                embedded += embedder.misses
            took = time.time() - started
            rate = embedded / took if took else 0
            print(f"{series_id}: {len(texts)} chunks, {embedded} embedded on {inner.device} in {took:.0f}s "
                  f"({rate:.1f}/s)", flush=True)
    finally:
        embedder.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", nargs="+", required=True, choices=sorted(SERIES))
    main(parser.parse_args().series)
