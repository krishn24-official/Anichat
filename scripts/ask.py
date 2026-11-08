"""Try retrieval by hand: print the chunks found for a question (no LLM yet; stage 6 adds answers).

    python -m scripts.ask --series demon_slayer "How did Rengoku die?"
    python -m scripts.ask --series demon_slayer --rerank "Who is Nezuko?"    # try the (optional) reranker
"""

import argparse
from pathlib import Path

from anichat.application.retrieve import RetrievalService
from anichat.domain.series import SERIES
from anichat.infrastructure.fastembed_embedder import FastEmbedEmbedder
from anichat.infrastructure.fastembed_reranker import FastEmbedReranker
from anichat.infrastructure.qdrant_index import QdrantIndex

DATA = Path(__file__).resolve().parents[1] / "data"


def main(series_id: str, question: str, rerank: bool) -> None:
    """Retrieve and print the top chunks with how each was found and the time taken.

    Called by: this file's __main__ block (command line)
    """
    index = QdrantIndex(path=str(DATA / "qdrant"))
    try:
        service = RetrievalService(FastEmbedEmbedder(), index, FastEmbedReranker() if rerank else None)
        result = service.retrieve(question, series=series_id)
        times = ", ".join(f"{k} {v:.2f}s" for k, v in result.timings.items())
        print(f"Q: {question}   ({times})")
        for r in result.chunks:
            location, _, text = r.chunk.text.partition("\n\n")
            print(f"\n[{r.via} {r.score:.3f}] {location}\n{text[:300]}...")
    finally:
        index.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question")
    parser.add_argument("--series", required=True, choices=sorted(SERIES))
    parser.add_argument("--rerank", action="store_true", help="also rerank (off by default: see application/retrieve.py)")
    args = parser.parse_args()
    main(args.series, args.question, args.rerank)
