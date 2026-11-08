"""Stage 2: build Markdown documents from the raw pages collected in stage 1.

    python -m scripts.build_documents --series demon_slayer

Input:  data/raw/<series>/<kind>/*.json        (from scripts/collect.py)
Output: data/documents/<series>/<kind>/*.md    (rebuilt from scratch each run)
"""

import argparse
from pathlib import Path

from anichat.application.build_documents import BuildDocumentsService
from anichat.domain.series import SERIES
from anichat.infrastructure.document_store import DocumentStore
from anichat.infrastructure.raw_store import RawStore

DATA = Path(__file__).resolve().parents[1] / "data"


def main(series_id: str) -> None:
    """Wire the raw store and document store into BuildDocumentsService, run it, print a summary.

    Called by: this file's __main__ block (command line)
    """
    report = BuildDocumentsService(RawStore(DATA / "raw"), DocumentStore(DATA / "documents")).build(SERIES[series_id])
    print(f"{'kind':16} {'documents':>9} {'stubs':>6} {'avg chars':>10}")
    for kind in sorted(set(report.built) | set(report.stubs)):
        built = report.built.get(kind, 0)
        avg = report.chars.get(kind, 0) // built if built else 0
        print(f"{kind:16} {built:9} {len(report.stubs.get(kind, [])):6} {avg:10}")
    print(f"\nSaved under {DATA / 'documents' / series_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", required=True, choices=sorted(SERIES))
    main(parser.parse_args().series)
