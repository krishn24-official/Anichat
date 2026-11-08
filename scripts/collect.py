"""Stage 1: collect the raw wiki pages of one series.

    python -m scripts.collect --series demon_slayer               # everything (skips pages already saved)
    python -m scripts.collect --series demon_slayer --kind episode
    python -m scripts.collect --series demon_slayer --refresh     # re-download all

Output: data/raw/<series>/<kind>/<page>.json and data/raw/<series>/manifest.json
"""

import argparse
import asyncio
from pathlib import Path

from anichat.application.collect import CollectService
from anichat.domain.series import SERIES
from anichat.infrastructure.fandom_client import FandomClient
from anichat.infrastructure.raw_store import RawStore

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


async def main(series_id: str, kinds: list[str] | None, refresh: bool) -> None:
    """Wire the wiki client and file store into CollectService, run it, print a summary.

    Called by: this file's __main__ block (command line)
    """
    async with FandomClient() as wiki:
        report = await CollectService(wiki, RawStore(RAW_DIR)).collect(SERIES[series_id], kinds, refresh)
    print(f"{'kind':16} {'listed':>7} {'fetched':>8} {'cached':>7} {'failed':>7}")
    for kind, listed in report.listed.items():
        failed = report.failed.get(kind, [])
        print(f"{kind:16} {listed:7} {report.fetched.get(kind, 0):8} {report.cached.get(kind, 0):7} {len(failed):7}")
        for title in failed[:5]:
            print(f"    failed: {title}")
    print(f"\nSaved under {RAW_DIR / series_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", required=True, choices=sorted(SERIES))
    parser.add_argument("--kind", action="append", help="only this kind (repeatable), e.g. --kind episode")
    parser.add_argument("--refresh", action="store_true", help="re-download pages already saved")
    args = parser.parse_args()
    asyncio.run(main(args.series, args.kind, args.refresh))
