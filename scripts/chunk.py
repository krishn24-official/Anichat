"""Stage 3: split the stage 2 documents into chunks.

    python -m scripts.chunk --series demon_slayer
    python -m scripts.chunk --series demon_slayer --show 3     # also print 3 sample chunks

Input:  data/documents/<series>/<kind>/*.md   (from scripts/build_documents.py, or hand-written)
Output: data/chunks/<series>.jsonl             (one chunk per line, replaced each run)
"""

import argparse
import random
import statistics
from pathlib import Path

from anichat.application.chunk_documents import ChunkDocumentsService
from anichat.domain.series import SERIES
from anichat.infrastructure.chunk_store import ChunkStore
from anichat.infrastructure.document_store import DocumentStore

DATA = Path(__file__).resolve().parents[1] / "data"


def main(series_id: str, show: int) -> None:
    """Wire the document and chunk stores into ChunkDocumentsService, run it, print a summary
    (and optionally a few random sample chunks).

    Called by: this file's __main__ block (command line)
    """
    store = ChunkStore(DATA / "chunks")
    report, chunks = ChunkDocumentsService(DocumentStore(DATA / "documents"), store).chunk(series_id)
    print(f"{'kind':16} {'documents':>9} {'chunks':>7}")
    for kind in sorted(report.chunks):
        print(f"{kind:16} {report.documents[kind]:9} {report.chunks[kind]:7}")
    sizes = sorted(report.sizes)
    if sizes:
        print(f"\n{len(sizes)} chunks | characters: median {statistics.median(sizes):.0f}, "
              f"smallest {sizes[0]}, largest {sizes[-1]} | over 2,000: {sum(s > 2000 for s in sizes)}")
    if report.skipped:
        print(f"skipped (missing front matter): {report.skipped}")
    print(f"Saved to {store.path(series_id)}")
    for chunk in random.Random(7).sample(chunks, min(show, len(chunks))):
        print(f"\n--- {chunk.id}  (mentions: {', '.join(chunk.mentions[:6])})\n{chunk.text[:700]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", required=True, choices=sorted(SERIES))
    parser.add_argument("--show", type=int, default=0, help="print N random sample chunks")
    args = parser.parse_args()
    main(args.series, args.show)
