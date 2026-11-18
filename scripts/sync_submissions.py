"""Bring in what was added or edited in the admin form (frontend /admin) while the laptop was off.

    python -m scripts.sync_submissions             # sync movies and entries, then re-index
    python -m scripts.sync_submissions --list      # what is waiting, change nothing
    python -m scripts.sync_submissions --dry-run   # check the waiting entries, change nothing
    python -m scripts.sync_submissions --every 10  # keep running: sync whenever the form changed something

Movies: every record edited since the last sync (new collections, OTT changes, cast added...)
gets its document rebuilt; deleted ones are removed. The movies table (data/movies.sqlite:
rankings and totals across movies) is rebuilt from all records. Free entries: each pending one is added
under data/added/<series>/ and marked "done" or "error" (the reason shows in the form). Every
series that changed is then re-chunked and re-indexed (only changed chunks are embedded).
Needs KV_REST_API_URL and KV_REST_API_TOKEN in .env.
"""

import argparse
import time
from pathlib import Path

from anichat import config
from anichat.application.added_data import AddedDataService, AddedStore, RecordSync
from anichat.domain.added import MOVIES, parse_submission
from anichat.domain.records import parse_fields, record_title
from anichat.domain.series import SERIES
from anichat.infrastructure.movie_db import MovieDB
from anichat.infrastructure.submission_store import SubmissionStore

DATA = Path(__file__).resolve().parents[1] / "data"


def reindex(series: str) -> None:
    """Re-chunk and re-index one series (only new or changed chunks get embedded).

    Called by: main(); scripts/add_movie.py
    """
    from scripts import chunk, index

    chunk.main(series, show=0)
    index.main(series, queries=[])


def main(list_only: bool, dry_run: bool) -> None:
    """List, check or apply what the form saved.

    Called by: this file's __main__ block (command line)
    """
    cloud = SubmissionStore(config.KV_REST_API_URL, config.KV_REST_API_TOKEN)
    store = AddedStore(DATA / "added")
    records_sync = RecordSync(store, SERIES[MOVIES].title)
    changed_series: set[str] = set()
    try:
        records, synced = cloud.records(), cloud.synced()
        waiting = records_sync.changed(records, synced)
        pending = cloud.pending()
        print(f"{len(waiting)} movies changed, {len(pending)} entries pending")
        if list_only or dry_run:
            for r in waiting:
                print(f"  movie  {'delete ' if r.get('deleted') else ''}{record_title(r)} (version {r.get('version')})")
            for e in pending:
                try:
                    sub = parse_submission(e)
                    print(f"  entry  {sub.series}/{sub.title}: {len(sub.facts)} facts" + (", notes" if sub.notes else ""))
                except ValueError as err:
                    print(f"  entry  {e.get('title', '?')}: will fail: {err}")
            return

        fields = cloud.fields()
        if waiting:
            for record, what in records_sync.sync(records, parse_fields(fields), synced):
                print(f"  movie  {what}: {record_title(record)}")
            changed_series.add(MOVIES)
        # The movies table (rankings, totals across movies): rebuilt from all records every time.
        count = MovieDB(DATA / "movies.sqlite").rebuild(records, [f for f in fields if "movie" in f.get("applies_to", ["movie"])])
        print(f"  table  {count} movies in data/movies.sqlite")

        entries = AddedDataService(store, {k: s.title for k, s in SERIES.items()})
        for entry in pending:
            try:
                doc, message = entries.apply(entry)
                cloud.mark(entry, "done", message)
                changed_series.add(doc.series)
                print(f"  entry  {message}")
            except ValueError as err:
                print(f"  entry  error: {entry.get('title', '?')}: {err}")
                cloud.mark(entry, "error", str(err))

        for series in sorted(changed_series):
            reindex(series)
        # Only now (indexed) do the movies count as synced: if indexing failed, they are retried.
        for record in waiting:
            cloud.mark_synced(record)
    finally:
        cloud.close()


def watch(minutes: float) -> None:
    """Check every few minutes and sync whenever the form changed something; Ctrl+C stops.
    A failed round (no internet, Qdrant down) is reported and retried at the next one.

    Called by: this file's __main__ block (--every)
    """
    print(f"Watching the admin form's store every {minutes:g} minutes (Ctrl+C to stop).")
    while True:
        try:
            cloud = SubmissionStore(config.KV_REST_API_URL, config.KV_REST_API_TOKEN)
            try:
                busy = bool(RecordSync(AddedStore(DATA / "added")).changed(cloud.records(), cloud.synced()) or cloud.pending())
            finally:
                cloud.close()
            if busy:
                print(f"[{time.strftime('%H:%M')}] changes found: syncing")
                main(list_only=False, dry_run=False)
        except Exception as err:  # keep watching: the next round retries
            print(f"[{time.strftime('%H:%M')}] sync failed, retrying next round: {err}")
        time.sleep(minutes * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="show what is waiting")
    parser.add_argument("--dry-run", action="store_true", help="check what is waiting, change nothing")
    parser.add_argument("--every", type=float, metavar="MINUTES", help="keep running: sync whenever something changed")
    args = parser.parse_args()
    if args.every:
        watch(args.every)
    else:
        main(args.list, args.dry_run)
