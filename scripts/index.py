"""Stage 4: embed the stage 3 chunks and store them in Qdrant.

    python -m scripts.index --series demon_slayer
    python -m scripts.index --series demon_slayer --query "How did Rengoku die?"   # also try searches

Input:  data/chunks/<series>.jsonl   (from scripts/chunk.py)
Output: data/qdrant/                 (local Qdrant storage; the series is replaced each run)
Models are downloaded on the first run into models/.
"""

import argparse
import time
from pathlib import Path

from anichat import container
from anichat.application.index_chunks import IndexChunksService
from anichat.domain.series import SERIES
from anichat.infrastructure.chunk_store import ChunkStore
from anichat.infrastructure.embedding_cache import CachingEmbedder
from anichat.infrastructure.fastembed_embedder import DENSE_MODEL, SPARSE_MODEL, FastEmbedEmbedder
from anichat.infrastructure.qdrant_index import QdrantIndex

DATA = Path(__file__).resolve().parents[1] / "data"


def _preview(embedder: CachingEmbedder, index: QdrantIndex, series: str, question: str) -> None:
    """Print the top 5 hybrid-search hits for a question (a quick look ahead at stage 5).

    Called by: main() for each --query
    """
    hits = index.search(embedder.embed_query(question), limit=5, series=series)
    print(f"\nQ: {question}")
    for hit in hits:
        location = hit.chunk.text.split("\n", 1)[0]
        print(f"   {hit.score:.3f}  {location[:110]}")


def main(series_id: str, queries: list[str]) -> None:
    """Wire chunk store, embedder and Qdrant into IndexChunksService, run it, then preview searches.

    Called by: this file's __main__ block (command line)
    """
    started = time.time()
    embedder = CachingEmbedder(FastEmbedEmbedder(), DATA / "embeddings.sqlite", model=f"{DENSE_MODEL}+{SPARSE_MODEL}")
    index = container.index()  # Qdrant server when QDRANT_URL is set, else the local folder
    try:
        report = IndexChunksService(ChunkStore(DATA / "chunks"), embedder, index, embedder.dense_size).index(series_id)
        print(f"{report.series}: {report.chunks} chunks ({embedder.hits} from cache, {embedder.misses} embedded), "
              f"{report.stored} stored in {time.time() - started:.0f}s | index now holds {index.count()} chunks")
        for q in queries:
            _preview(embedder, index, series_id, q)
    finally:
        index.close()
        embedder.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", required=True, choices=sorted(SERIES))
    parser.add_argument("--query", action="append", default=[], help="preview a search (repeatable)")
    args = parser.parse_args()
    main(args.series, args.query)
