"""Add chosen movies from TMDb (one by one, not the whole catalogue) from the command line.
The admin form (/admin -> Movies -> Add a movie) does the same from a phone.

    python -m scripts.add_movie "Iron Man" --year 2008
    python -m scripts.add_movie --tmdb-id 1726              # exactly this TMDb movie
    python -m scripts.add_movie --file my_movies.txt        # one "Title" or "Title (2008)" per line
    python -m scripts.add_movie "Dune" --search             # only list TMDb's matches, add nothing

Each movie becomes a record in the cloud store (so the form can edit it later: collections,
OTT, cast...), then the sync builds its document and indexes it (--no-sync to do that later).
Movies added before are skipped. Needs TMDB_READ_TOKEN and KV_REST_API_URL/TOKEN in .env.
"""

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from anichat import config
from anichat.domain.records import record_title, tmdb_record
from anichat.infrastructure.submission_store import SubmissionStore
from anichat.infrastructure.tmdb_client import TmdbClient


def _wanted(args: argparse.Namespace) -> list[tuple[str, int | None]]:
    """(title, year) pairs from the command line or the --file ("Iron Man (2008)" -> year 2008).

    Called by: main()
    """
    lines = [args.title] if args.title else []
    if args.file:
        lines += [ln.strip() for ln in Path(args.file).read_text(encoding="utf-8").splitlines()
                  if ln.strip() and not ln.startswith("#")]
    wanted = []
    for line in lines:
        m = re.fullmatch(r"(.+?)\s*\((\d{4})\)", line)
        wanted.append((m.group(1), int(m.group(2))) if m else (line, args.year if line == args.title else None))
    return wanted


def best_match(results: list[dict], title: str) -> dict | None:
    """The exact title if TMDb has it (the most popular of those), else the most popular of the top 3.

    Called by: main(); tests
    """
    if not results:
        return None
    exact = [r for r in results if r.get("title", "").lower() == title.lower()]
    return max(exact or results[:3], key=lambda r: r.get("popularity", 0))


def main(args: argparse.Namespace) -> None:
    """Search, or add each requested movie as a cloud record, then sync.

    Called by: this file's __main__ block (command line)
    """
    tmdb = TmdbClient(config.TMDB_READ_TOKEN, config.TMDB_API_KEY)
    cloud = None if args.search else SubmissionStore(config.KV_REST_API_URL, config.KV_REST_API_TOKEN)
    added = 0
    try:
        field_ids = {f["id"] for f in cloud.fields()} if cloud else set()
        ids = [(args.tmdb_id, "")] if args.tmdb_id else []
        for title, year in _wanted(args):
            results = tmdb.search_movie(title, year)
            if args.search:
                for r in results[:8]:
                    print(f"  {r['id']:>8}  {r.get('title')} ({(r.get('release_date') or '????')[:4]})"
                          f"  popularity {r.get('popularity', 0):.0f}")
                continue
            hit = best_match(results, title)
            if hit is None:
                print(f"skipped {title}: TMDb found nothing" + (f" from {year}" if year else ""))
                continue
            ids.append((hit["id"], title))
        for tmdb_id, asked in ids:
            if cloud.has_record(f"tmdb-{tmdb_id}"):
                print(f"skipped {asked or tmdb_id}: added before (edit it in the form)")
                continue
            record = tmdb_record(tmdb.movie(tmdb_id), field_ids)
            cloud.add_record(record, datetime.now(timezone.utc).isoformat())
            print(f"added {record_title(record)}: {len(record['cast'])} cast, directed by {', '.join(record['directors']) or '?'}")
            added += 1
    finally:
        tmdb.close()
        if cloud:
            cloud.close()
    if added and not args.no_sync:
        from scripts import sync_submissions

        sync_submissions.main(list_only=False, dry_run=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("title", nargs="?", help="movie title")
    parser.add_argument("--year", type=int, help="release year, to pick the right movie")
    parser.add_argument("--tmdb-id", type=int, help="exactly this TMDb movie id")
    parser.add_argument("--file", help="a text file with one movie per line: Title or Title (Year)")
    parser.add_argument("--search", action="store_true", help="only list TMDb's matches")
    parser.add_argument("--no-sync", action="store_true", help="add the records but don't index them yet")
    parsed = parser.parse_args()
    if not (parsed.title or parsed.tmdb_id or parsed.file):
        parser.error("give a title, --tmdb-id or --file")
    main(parsed)
