"""Measure retrieval quality on a question set with known answers.

    python -m scripts.evaluate --series demon_slayer                    # search only vs search + rerank
    python -m scripts.evaluate --series demon_slayer --candidates 10    # try another candidate count
    python -m scripts.evaluate --series demon_slayer --reranker Xenova/ms-marco-MiniLM-L-6-v2 --reranker ...

A question counts as answered ("hit") when one of its expected pages is among the
top 5 chunks. MRR (mean reciprocal rank) also rewards putting it first:
1.0 = always rank 1, 0.5 = rank 2 on average, 0 = never found.

Question sets live in evals/<series>.json (kept in git; add your own questions).
"""

import argparse
import json
from pathlib import Path

from anichat.application.retrieve import CANDIDATES, RetrievalService
from anichat.domain.series import SERIES
from anichat.infrastructure.fastembed_embedder import FastEmbedEmbedder
from anichat.infrastructure.fastembed_reranker import RERANK_MODEL, FastEmbedReranker
from anichat.infrastructure.qdrant_index import QdrantIndex

ROOT = Path(__file__).resolve().parents[1]
TOP = 5


def evaluate(service: RetrievalService, cases: list[dict], series: str) -> tuple[float, float, float, list[str]]:
    """(hit rate, MRR, average seconds per question, misses) for one retrieval setup.

    Called by: main() once per setup
    """
    hits, reciprocal, seconds, misses = 0, 0.0, 0.0, []
    for case in cases:
        result = service.retrieve(case["question"], series=series, limit=TOP)
        seconds += result.timings["total"]
        titles = [r.chunk.title for r in result.chunks]
        rank = next((i + 1 for i, t in enumerate(titles) if t in case["expect"]), None)
        if rank:
            hits += 1
            reciprocal += 1 / rank
        else:
            misses.append(f"{case['question']}  -> got {titles[:3]}")
    n = len(cases)
    return hits / n, reciprocal / n, seconds / n, misses


def main(series_id: str, candidates: int, rerankers: list[str]) -> None:
    """Run the question set with search only and with each reranker, print the scores.

    Called by: this file's __main__ block (command line)
    """
    cases = json.loads((ROOT / "evals" / f"{series_id}.json").read_text(encoding="utf-8"))
    embedder = FastEmbedEmbedder()
    index = QdrantIndex(path=str(ROOT / "data" / "qdrant"))
    try:
        setups = {"search only": RetrievalService(embedder, index, None, candidates)}
        for model in rerankers:
            setups[f"+ {model.split('/')[-1]}"] = RetrievalService(embedder, index, FastEmbedReranker(model), candidates)
        print(f"{len(cases)} questions, top {TOP}, {candidates} candidates\n")
        print(f"{'setup':34} {'hit rate':>9} {'MRR':>6} {'sec/question':>13}")
        all_misses = {}
        for name, service in setups.items():
            hit_rate, mrr, secs, misses = evaluate(service, cases, series_id)
            print(f"{name:34} {hit_rate:9.0%} {mrr:6.2f} {secs:13.2f}")
            all_misses[name] = misses
        for name, misses in all_misses.items():
            if misses:
                print(f"\nMissed with {name}:")
                for m in misses:
                    print(f"  - {m}")
    finally:
        index.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", required=True, choices=sorted(SERIES))
    parser.add_argument("--candidates", type=int, default=CANDIDATES)
    parser.add_argument("--reranker", action="append", default=None,
                        help=f"FastEmbed reranker to compare (repeatable); default {RERANK_MODEL}")
    args = parser.parse_args()
    main(args.series, args.candidates, args.reranker or [RERANK_MODEL])
