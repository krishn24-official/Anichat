"""The movies table: a SQLite copy of the movie records (data/movies.sqlite), for questions that
rank, filter or add up across movies (domain/movie_query.py). Rebuilt from the records at every
sync, so it never needs migrating: the records in the cloud store stay the source of truth.

Tables (fields from the Fields tab need no schema change: their values are rows):
    movies(id, title, year, release_date, runtime, language, genres, collection, companies)
    movie_people(movie_id, name, role, character, position)     role: cast/director/writer/producer/music
    movie_values(movie_id, field_id, num, text)                  num: numbers and money; text: the rest
    movie_days(movie_id, field_id, position, label, value)       day-wise rows, in order
    fields(id, label, type, currency, unit)
"""

import sqlite3
from pathlib import Path

from anichat.domain.movie_query import BUILTIN_SORTS, MovieQuery

SCHEMA = """
CREATE TABLE movies (id TEXT PRIMARY KEY, title TEXT, year INTEGER, release_date TEXT, runtime INTEGER,
                     language TEXT, genres TEXT, collection TEXT, companies TEXT);
CREATE TABLE movie_people (movie_id TEXT, name TEXT, role TEXT, character TEXT, position INTEGER);
CREATE TABLE movie_values (movie_id TEXT, field_id TEXT, num REAL, text TEXT);
CREATE TABLE movie_days (movie_id TEXT, field_id TEXT, position INTEGER, label TEXT, value REAL);
CREATE TABLE fields (id TEXT PRIMARY KEY, label TEXT, type TEXT, currency TEXT, unit TEXT);
CREATE INDEX people_name ON movie_people (lower(name));
CREATE INDEX values_field ON movie_values (field_id, num);
"""
_NOISE = {"the", "and", "of", "a", "an", "movie", "movies", "film", "films", "series", "collection", "franchise", "&"}


def franchise_words(franchise: str | None) -> list[str]:
    """"Fast & Furious movies" -> ["fast", "furious"]: the words a franchise filter needs.

    Called by: MovieDB.run(); tests
    """
    return [w for w in (franchise or "").lower().replace("&", " ").split() if w not in _NOISE and len(w) > 1]


CREW = (("directors", "director"), ("writers", "writer"), ("producers", "producer"), ("music", "music"))
SHOWN_CAST = 6  # cast members listed per movie in the results (all are searchable)


class MovieDB:
    """Created by: scripts/sync_submissions.py (rebuild), anichat/container.py (queries)
    Used by:    application/movie_questions.py  MovieQuestions
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def exists(self) -> bool:
        """Whether a sync has built the table yet. Called by: MovieQuestions"""
        return self.path.exists()

    def rebuild(self, records: list[dict], fields: list[dict]) -> int:
        """Replace the table with these records (deleted ones left out). Written to a temporary file
        and swapped in, so a question asked meanwhile never sees half a table. Returns the movie count.

        Called by: scripts/sync_submissions.py  main()
        """
        tmp = self.path.with_suffix(".tmp")
        tmp.unlink(missing_ok=True)
        types = {f["id"]: f.get("type") for f in fields}
        db = sqlite3.connect(tmp)
        try:
            db.executescript(SCHEMA)
            db.executemany("INSERT INTO fields VALUES (?, ?, ?, ?, ?)",
                           [(f["id"], f.get("label", f["id"]), f.get("type"), f.get("currency", ""), f.get("unit", ""))
                            for f in fields])
            count = 0
            for r in records:
                if r.get("deleted"):
                    continue
                count += 1
                db.execute("INSERT INTO movies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (r["id"], r["title"], r.get("year"), r.get("release_date") or None, r.get("runtime"),
                            r.get("language") or None, ", ".join(r.get("genres", [])), r.get("collection") or "",
                            ", ".join(r.get("companies", []))))
                people = [(r["id"], c["name"], "cast", c.get("character", ""), i) for i, c in enumerate(r.get("cast", []))]
                people += [(r["id"], name, role, "", i) for key, role in CREW for i, name in enumerate(r.get(key, []))]
                db.executemany("INSERT INTO movie_people VALUES (?, ?, ?, ?, ?)", people)
                for fid, value in r.get("values", {}).items():
                    if types.get(fid) == "daywise" and isinstance(value, list):
                        db.executemany("INSERT INTO movie_days VALUES (?, ?, ?, ?, ?)",
                                       [(r["id"], fid, i + 1, row["label"], row["value"]) for i, row in enumerate(value)])
                    elif isinstance(value, (int, float)) and not isinstance(value, bool):
                        db.execute("INSERT INTO movie_values VALUES (?, ?, ?, NULL)", (r["id"], fid, float(value)))
                    else:
                        text = ", ".join(value) if isinstance(value, list) else str(value)
                        db.execute("INSERT INTO movie_values VALUES (?, ?, NULL, ?)", (r["id"], fid, text))
            db.commit()
        finally:
            db.close()
        tmp.replace(self.path)
        return count

    def fields(self) -> list[dict]:
        """The field definitions stored with the table, each with "filled": how many movies have a
        value for it (so the planner picks "Budget (USD)" when the ₹ "Budget" is empty).

        Called by: MovieQuestions
        """
        if not self.exists():
            return []
        with self._connect() as db:
            counts = dict(db.execute("SELECT field_id, count(DISTINCT movie_id) FROM movie_values GROUP BY field_id"))
            counts.update(db.execute("SELECT field_id, count(DISTINCT movie_id) FROM movie_days GROUP BY field_id"))
            return [{**dict(row), "filled": counts.get(row["id"], 0)} for row in db.execute("SELECT * FROM fields")]

    def _connect(self) -> sqlite3.Connection:
        """A read connection (rows as dicts). Called by: fields(), run()"""
        db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        return db

    def run(self, q: MovieQuery) -> tuple[list[dict], int, str]:
        """The movies matching the query (at most q.limit, sorted as asked), how many match in all,
        and a note when the sort field is empty for all of them (then they are listed by release
        date instead, with whatever values they have).
        Each movie: title, year, its values {field id: number or text}, directors, first cast
        members, the queried person's role, and (with days_field) the day rows and their sum.

        Only whitelisted SQL is built here; everything from the question is a bound parameter.
        Called by: application/movie_questions.py  MovieQuestions.source()
        """
        where, params, join = [], [], ""
        if q.title:
            where.append("lower(m.title) LIKE ?")
            params.append(f"%{q.title.lower()}%")
        for word in franchise_words(q.franchise):
            # "fast furious" matches "The Fast and the Furious Collection"; "marvel" matches "Marvel Studios".
            where.append("lower(m.title || ' ' || m.collection || ' ' || m.companies) LIKE ?")
            params.append(f"%{word}%")
        if q.year:
            where.append("m.year = ?")
            params.append(q.year)
        if q.year_from:
            where.append("m.year >= ?")
            params.append(q.year_from)
        if q.year_to:
            where.append("m.year <= ?")
            params.append(q.year_to)
        if q.language:
            where.append("lower(m.language) = ?")
            params.append(q.language.lower())
        if q.genre:
            where.append("lower(m.genres) LIKE ?")
            params.append(f"%{q.genre.lower()}%")
        if q.person:
            where.append("EXISTS (SELECT 1 FROM movie_people p WHERE p.movie_id = m.id AND lower(p.name) LIKE ?"
                         + (" AND p.role = ?)" if q.role else ")"))
            params += [f"%{q.person.lower()}%"] + ([q.role] if q.role else [])
        order = "DESC" if q.order == "desc" else "ASC"
        if q.sort_by in BUILTIN_SORTS:
            sort = f"m.{q.sort_by}"  # a fixed column name from BUILTIN_SORTS
            where.append(f"{sort} IS NOT NULL")
        elif q.sort_by:
            join = "JOIN movie_values s ON s.movie_id = m.id AND s.field_id = ? AND s.num IS NOT NULL"
            params.insert(0, q.sort_by)
            sort = "s.num"
        else:
            sort = "m.release_date"
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        note = ""
        with self._connect() as db:
            total = db.execute(f"SELECT count(*) FROM movies m {join} {clause}", params).fetchone()[0]
            if not total and join:  # nobody has that field filled in: list the matches anyway
                params, join, sort, order = params[1:], "", "m.release_date", "DESC"
                total = db.execute(f"SELECT count(*) FROM movies m {clause}", params).fetchone()[0]
                note = "none of them has a value for the field asked to sort by"
            rows = db.execute(f"SELECT m.* FROM movies m {join} {clause} ORDER BY {sort} {order} NULLS LAST, m.title "
                              "LIMIT ?", [*params, q.limit]).fetchall()
            movies = [self._details(db, dict(row), q) for row in rows]
        return movies, total, note

    def _details(self, db: sqlite3.Connection, movie: dict, q: MovieQuery) -> dict:
        """Add a movie's values, people and (if asked) day rows. Called by: run()"""
        mid = movie["id"]
        movie["values"] = {r["field_id"]: (r["num"] if r["num"] is not None else r["text"])
                           for r in db.execute("SELECT field_id, num, text FROM movie_values WHERE movie_id = ?", (mid,))}
        people = db.execute("SELECT name, role, character FROM movie_people WHERE movie_id = ? ORDER BY role, position",
                            (mid,)).fetchall()
        movie["directors"] = [p["name"] for p in people if p["role"] == "director"]
        movie["cast"] = [f"{p['name']} as {p['character']}" if p["character"] else p["name"]
                         for p in people if p["role"] == "cast"][:SHOWN_CAST]
        if q.person:
            movie["person_roles"] = [f"{p['name']}: {p['role']}" + (f" ({p['character']})" if p["character"] else "")
                                     for p in people if q.person.lower() in p["name"].lower()]
        if q.days_field:
            rows = db.execute("SELECT position, label, value FROM movie_days WHERE movie_id = ? AND field_id = ? "
                              "AND position BETWEEN ? AND ? ORDER BY position",
                              (mid, q.days_field, q.days_from or 1, q.days_to or 100000)).fetchall()
            movie["days"] = [(r["label"], r["value"]) for r in rows]
            movie["days_sum"] = round(sum(r["value"] for r in rows), 2)
        return movie

