"""Add chosen movies from TMDb (not the whole catalogue) as editable records, from the command line.
The admin form (/admin -> Movies -> Add a movie) does the same one movie at a time.

    python -m scripts.add_movie "Iron Man" --year 2008
    python -m scripts.add_movie --tmdb-id 1726                      # exactly this TMDb movie
    python -m scripts.add_movie --file my_movies.txt                # one "Title" or "Title (2008)" per line
    python -m scripts.add_movie --collection "Jumanji"              # a film series
    python -m scripts.add_movie --director "Christopher Nolan"      # everything they directed
    python -m scripts.add_movie --company 420                       # a studio (TMDb company ids, "420|7505")
    python -m scripts.add_movie --collection "Fast and the Furious" --dry-run   # list, add nothing
    python -m scripts.add_movie "Dune" --search                     # only list TMDb's matches
    python -m scripts.add_movie --fill-missing                      # older records: add film series and studios

Only released feature films are added: unreleased ones, shorts (under MIN_RUNTIME minutes),
documentaries and (from studio lists) little-known animated releases are skipped. Each movie
becomes a record in the cloud store (so the form can edit it later: collections, OTT, cast...);
the sync then builds its document, embeds it and adds it to the movies table (--no-sync to do
that later). Movies added before are skipped. Needs TMDB_READ_TOKEN and KV_REST_API_URL/TOKEN.
"""

import argparse
import re
from datetime import date, datetime, timezone
from pathlib import Path

from anichat import config
from anichat.domain.records import record_title, tmdb_record
from anichat.infrastructure.submission_store import SubmissionStore
from anichat.infrastructure.tmdb_client import TmdbClient

MIN_RUNTIME = 60  # minutes: shorter is a short film or a special (Nolan's Following is 69)
ANIMATION = 16  # TMDb genre ids
DOCUMENTARY = 99
MAX_DIRECTORS = 3  # more: an anthology of shorts, not one film
FAMOUS_ANIMATION_VOTES = 2000  # from studio lists, animated films need this many votes (Spider-Verse yes, direct-to-video no)


def _wanted(args: argparse.Namespace) -> list[tuple[str, int | None]]:
    """(title, year) pairs from the command line or the --file ("Iron Man (2008)" -> year 2008).

    Called by: candidates()
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

    Called by: candidates(); tests
    """
    if not results:
        return None
    exact = [r for r in results if r.get("title", "").lower() == title.lower()]
    return max(exact or results[:3], key=lambda r: r.get("popularity", 0))


def released(movie: dict, today: str) -> bool:
    """Out already (has a release date, not in the future). Called by: candidates(), main()"""
    return bool(movie.get("release_date")) and movie["release_date"] <= today


def candidates(args: argparse.Namespace, tmdb: TmdbClient, today: str) -> list[tuple[int, str]]:
    """(TMDb id, where it came from) for every requested movie, without repeats.

    Called by: main()
    """
    found: dict[int, str] = {}
    if args.tmdb_id:
        found[args.tmdb_id] = "id"
    for title, year in _wanted(args):
        hit = best_match(tmdb.search_movie(title, year), title)
        if hit is None:
            print(f"skipped {title}: TMDb found nothing" + (f" from {year}" if year else ""))
        else:
            found.setdefault(hit["id"], f"title {title}")
    for name in args.collection or []:
        label, parts = tmdb.collection(name)
        for m in parts:
            if released(m, today):
                found.setdefault(m["id"], label)
    for name in args.director or []:
        label, films = tmdb.directed_by(name)
        for m in films:
            if released(m, today):
                found.setdefault(m["id"], f"directed by {label}")
    for ids in args.company or []:
        for m in tmdb.by_companies(ids, today):
            animated = ANIMATION in m.get("genre_ids", [])
            if animated and m.get("vote_count", 0) < FAMOUS_ANIMATION_VOTES:
                continue
            found.setdefault(m["id"], f"studio {ids}")
    return list(found.items())


def feature_film(movie: dict, today: str) -> str | None:
    """Why a movie isn't wanted (None: it is): not released, a short, a documentary, or a
    compilation of several directors' shorts ("Cinema16: British Short Films" lists Nolan).

    Called by: main(); tests
    """
    if not released(movie, today):
        return "not released yet"
    if (movie.get("runtime") or 0) < MIN_RUNTIME:
        return f"short ({movie.get('runtime') or '?'} min)"
    if any(g.get("id") == DOCUMENTARY for g in movie.get("genres", [])):
        return "documentary"
    directors = {c.get("name") for c in (movie.get("credits") or {}).get("crew", []) if c.get("job") == "Director"}
    if len(directors) > MAX_DIRECTORS:
        return f"anthology ({len(directors)} directors)"
    return None


FILLABLE = ("collection", "companies")  # TMDb details records made before these existed lack


def fill_missing(cloud: SubmissionStore, tmdb: TmdbClient, dry_run: bool) -> int:
    """Give records from TMDb the details they were made without (film series, studios), as a new
    version each; what you edited is never touched. Returns how many records changed.

    Called by: main() (--fill-missing)
    """
    changed = 0
    now = datetime.now(timezone.utc).isoformat()
    for record in cloud.records():
        missing = [k for k in FILLABLE if k not in record]
        if record.get("deleted") or not record.get("tmdb_id") or not missing:
            continue
        fresh = tmdb_record(tmdb.movie(record["tmdb_id"]), set())
        changes = {k: fresh[k] for k in missing}
        if dry_run:
            print(f"  would fill  {record_title(record)}: {changes}")
        elif cloud.update_record(record, changes, now):
            print(f"  filled  {record_title(record)}: {changes['collection'] or '(no series)'}; {', '.join(changes['companies'][:3])}")
            changed += 1
        else:
            print(f"  skip   {record_title(record)}: edited meanwhile, run again")
    print(f"{changed} records filled" + (" (dry run)" if dry_run else ""))
    return changed


def main(args: argparse.Namespace) -> None:
    """Search, or add each requested movie as a cloud record, then sync.

    Called by: this file's __main__ block (command line)
    """
    today = date.today().isoformat()
    tmdb = TmdbClient(config.TMDB_READ_TOKEN, config.TMDB_API_KEY)
    cloud = None if args.search else SubmissionStore(config.KV_REST_API_URL, config.KV_REST_API_TOKEN)
    added = skipped = 0
    try:
        if args.search:
            for title, year in _wanted(args):
                for r in tmdb.search_movie(title, year)[:8]:
                    print(f"  {r['id']:>8}  {r.get('title')} ({(r.get('release_date') or '????')[:4]})"
                          f"  popularity {r.get('popularity', 0):.0f}")
            return
        if args.fill_missing:
            added = fill_missing(cloud, tmdb, args.dry_run)
            return
        field_ids = {f["id"] for f in cloud.fields()}
        existing = {r["id"] for r in cloud.records()}
        for tmdb_id, origin in candidates(args, tmdb, today):
            if f"tmdb-{tmdb_id}" in existing:
                skipped += 1
                continue
            movie = tmdb.movie(tmdb_id)
            why_not = feature_film(movie, today)
            if why_not:
                print(f"  skip   {movie['title']} ({(movie.get('release_date') or '????')[:4]}): {why_not}")
                continue
            record = tmdb_record(movie, field_ids)
            if args.dry_run:
                print(f"  would add  {record_title(record)}  [{origin}]")
                continue
            cloud.add_record(record, datetime.now(timezone.utc).isoformat())
            existing.add(record["id"])
            print(f"  added  {record_title(record)}: {len(record['cast'])} cast, directed by "
                  f"{', '.join(record['directors']) or '?'}  [{origin}]")
            added += 1
    finally:
        tmdb.close()
        if cloud:
            cloud.close()
    if not args.fill_missing:
        print(f"{added} added, {skipped} already there" + (" (dry run: nothing was added)" if args.dry_run else ""))
    if added and not args.no_sync:
        from scripts import sync_submissions

        sync_submissions.main(list_only=False, dry_run=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("title", nargs="?", help="movie title")
    parser.add_argument("--year", type=int, help="release year, to pick the right movie")
    parser.add_argument("--tmdb-id", type=int, help="exactly this TMDb movie id")
    parser.add_argument("--file", help="a text file with one movie per line: Title or Title (Year)")
    parser.add_argument("--collection", action="append", help="a film series (name or TMDb id); repeatable")
    parser.add_argument("--director", action="append", help="every film a person directed; repeatable")
    parser.add_argument("--company", action="append", help='a studio\'s films: TMDb company ids, "420|7505"; repeatable')
    parser.add_argument("--search", action="store_true", help="only list TMDb's matches")
    parser.add_argument("--dry-run", action="store_true", help="list what would be added, add nothing")
    parser.add_argument("--no-sync", action="store_true", help="add the records but don't index them yet")
    parser.add_argument("--fill-missing", action="store_true",
                        help="give existing TMDb records the details they lack (film series, studios)")
    parsed = parser.parse_args()
    if not (parsed.title or parsed.tmdb_id or parsed.file or parsed.collection or parsed.director or parsed.company
            or parsed.fill_missing):
        parser.error("give a title, --tmdb-id, --file, --collection, --director, --company or --fill-missing")
    main(parsed)
