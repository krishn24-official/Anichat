"""Remove saved pages that the series' current configuration no longer collects (after
tightening exclude_titles / exclude_categories in anichat/domain/series.py).

    python -m scripts.prune --series tokyo_revengers            # list what would be removed
    python -m scripts.prune --series tokyo_revengers --apply    # remove raw pages + their documents

Afterwards re-run scripts.chunk (and scripts.index) for the series. Only the category lists are
read from the wiki; no pages are downloaded.
"""

import argparse
import asyncio
from pathlib import Path

from anichat.application.collect import CollectService
from anichat.domain.series import SERIES
from anichat.infrastructure.fandom_client import FandomClient
from anichat.infrastructure.raw_store import RawStore, safe_filename

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


async def main(series_id: str, apply: bool) -> None:
    """List (or delete, with --apply) saved pages missing from CollectService.wanted().

    Called by: this file's __main__ block (command line)
    """
    store = RawStore(DATA_DIR / "raw")
    async with FandomClient() as wiki:
        wanted = await CollectService(wiki, store).wanted(SERIES[series_id])
    # None: the kind comes from split pages, whose titles can't be listed (kept).
    stale = [p for p in store.iter_pages(series_id)
             if wanted.get(p.kind, set()) is not None and p.title not in wanted.get(p.kind, set())]
    for page in stale:
        print(f"{page.kind:16} {page.title}")
        if apply:
            name = safe_filename(page.title)
            for path in (DATA_DIR / "raw" / series_id / page.kind / f"{name}.json",
                         DATA_DIR / "documents" / series_id / page.kind / f"{name}.md"):
                path.unlink(missing_ok=True)
    action = "Removed" if apply else "Would remove (add --apply)"
    print(f"\n{action}: {len(stale)} pages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", required=True, choices=sorted(SERIES))
    parser.add_argument("--apply", action="store_true", help="delete the files (default: only list them)")
    args = parser.parse_args()
    asyncio.run(main(args.series, args.apply))
