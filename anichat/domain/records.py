"""Movie records and fields from the admin form, as documents. Pure Python, no I/O.

The form (frontend/api/_records.ts) defines the shapes: a Field is a named, typed slot defined
once ("India net collection", money in ₹ crore); a record is one movie with TMDb's details
(prefilled, editable), its cast in billing order, and a value per field. Here a record becomes
the Document the chunker indexes: facts for the numbers, sections for cast, crew, box office
and day-wise collections.
"""

from dataclasses import dataclass, field

from anichat.domain.added import ADDED_LICENSE, MOVIES, TMDB_LICENSE
from anichat.domain.documents import Document

STARRING = 6  # the first cast members, shown as "starring" (move an actor up in the form to add them)
TMDB_URL = "https://www.themoviedb.org/movie/{id}"


@dataclass
class Field:
    """One field definition (mirrors frontend/api/_records.ts Field).

    Created by: parse_fields()
    """

    id: str
    label: str
    type: str  # text, number, money, date, list, daywise, url
    group: str = "Details"
    applies_to: list[str] = field(default_factory=lambda: ["movie"])
    currency: str = ""
    unit: str = ""
    order: int = 0
    archived: bool = False


def parse_fields(raw: list[dict]) -> dict[str, Field]:
    """Field definitions as stored by the form -> {id: Field}, in form order.

    Called by: scripts/sync_submissions.py; tests
    """
    keys = Field.__dataclass_fields__
    fields = [Field(**{k: v for k, v in r.items() if k in keys and v is not None}) for r in raw if r.get("id")]
    return {f.id: f for f in sorted(fields, key=lambda f: (f.order, f.label))}


def _amount(f: Field, n: float) -> str:
    """597.99 (₹, crore) -> "₹597.99 crore"; 140000000 ($) -> "$140,000,000". Called by: format_value()"""
    symbol = ("$" if f.currency == "USD" else "₹") if f.type in ("money", "daywise") else ""
    if f.unit:
        digits = f"{n:,.2f}".rstrip("0").rstrip(".")
    else:
        digits = f"{int(n):,}" if float(n).is_integer() else f"{n:,.3f}".rstrip("0").rstrip(".")
    return f"{symbol}{digits}{' ' + f.unit if f.unit else ''}"


def format_value(f: Field, value) -> str:
    """A value as text, as the form shows it (frontend/api/_records.ts formatValue).

    Called by: record_document(); tests
    """
    if isinstance(value, list):
        if f.type == "daywise":
            return "; ".join(f"{r['label']}: {_amount(f, r['value'])}" for r in value)
        return ", ".join(str(v) for v in value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _amount(f, value)
    return str(value)


def _and(names: list[str]) -> str:
    """["A"] -> "A"; ["A", "B", "C"] -> "A, B and C". Called by: record_document()"""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def record_title(record: dict) -> str:
    """"Stree 2 (2024)": the page title, unique across remakes. Called by: record_document(), sync"""
    return f"{record['title']} ({record['year']})" if record.get("year") else record["title"]


def record_document(record: dict, fields: dict[str, Field], series_title: str = "Movies") -> Document:
    """One movie record -> the Document to index.

    Facts hold what people ask for in one line (director, release, collections); the body says
    who is in it (all cast, in billing order), the crew, each field group as a section, day-wise
    collections as a table, and the notes.

    Called by: application/added_data.py  RecordSync.sync(); tests
    """
    title = record_title(record)
    cast = [c for c in record.get("cast", []) if c.get("name")]
    starring = [c["name"] for c in cast[:STARRING]]
    directors = record.get("directors", [])
    facts = {
        "also called": record.get("original_title", ""),
        "released": record.get("release_date", ""),
        "runtime": f"{record['runtime']} minutes" if record.get("runtime") else "",
        "language": record.get("language", ""),
        "genres": ", ".join(record.get("genres", [])),
        "directed by": ", ".join(directors),
        "written by": ", ".join(record.get("writers", [])),
        "produced by": ", ".join(record.get("producers", [])),
        "music by": ", ".join(record.get("music", [])),
        "starring": ", ".join(starring),
    }
    values = record.get("values", {})
    sections: dict[str, list[str]] = {}
    tables: list[str] = []
    for fid, f in fields.items():
        if fid not in values or values[fid] in (None, "", []):
            continue
        if f.type == "daywise":
            rows = "\n".join(f"- {r['label']}: {_amount(f, r['value'])}" for r in values[fid])
            tables.append(f"## {f.label}\n\n{rows}")
            continue
        text = format_value(f, values[fid])
        facts[f.label] = text
        sections.setdefault(f.group, []).append(f"- {f.label}: {text}")
    if record.get("tmdb_id"):
        facts["tmdb id"] = str(record["tmdb_id"])
    facts = {k: v for k, v in facts.items() if v}

    year = f"{record['year']} " if record.get("year") else ""
    language = f"{record['language']} " if record.get("language") else ""
    intro = f"{title} is a {year}{language}film" + (f" directed by {_and(directors)}" if directors else "")
    intro += (f", starring {_and(starring[:4])}." if starring else ".")
    parts = [" ".join(p for p in (intro, record.get("overview", "")) if p)]
    if record.get("tagline"):
        parts.append(f"Tagline: \"{record['tagline']}\"")
    if cast:
        parts.append("## Cast\n\n" + "\n".join(f"- {c['name']} as {c['character']}" if c.get("character") else f"- {c['name']}"
                                               for c in cast))
    crew = [(label, record.get(key, [])) for key, label in (("directors", "Directed by"), ("writers", "Written by"),
                                                             ("producers", "Produced by"), ("music", "Music by"))]
    if any(names for _, names in crew):
        parts.append("## Crew\n\n" + "\n".join(f"- {label}: {', '.join(names)}" for label, names in crew if names))
    parts += [f"## {group}\n\n" + "\n".join(lines) for group, lines in sections.items()]
    parts += tables
    if record.get("notes"):
        parts.append(f"## Notes\n\n{record['notes']}")

    sources = record.get("sources", [])
    url = TMDB_URL.format(id=record["tmdb_id"]) if record.get("tmdb_id") else (sources[0] if sources else "")
    return Document(
        series=MOVIES, series_title=series_title, kind="movie", title=title, display_title=title, source_url=url,
        revision_id=int(record.get("version", 0)), facts=facts, mentions=starring + list(directors), body="\n\n".join(parts),
        license=f"{TMDB_LICENSE}; edited by hand" if record.get("tmdb_id") else ADDED_LICENSE,
    )


def tmdb_record(movie: dict, field_ids: set[str], cast_limit: int = 40) -> dict:
    """TMDb's movie details (with credits) as a new record, like the form makes it
    (frontend/api/_records.ts tmdbRecord). Used when adding movies from the command line.

    Called by: scripts/add_movie.py; tests
    """
    credits = movie.get("credits") or {}

    def crew(jobs: tuple[str, ...]) -> list[str]:
        return list(dict.fromkeys(c["name"] for c in credits.get("crew", []) if c.get("job") in jobs and c.get("name")))[:30]

    values = {}
    if movie.get("budget") and "budget_usd" in field_ids:
        values["budget_usd"] = movie["budget"]
    if movie.get("revenue") and "worldwide_gross_usd" in field_ids:
        values["worldwide_gross_usd"] = movie["revenue"]
    language = next((lang.get("english_name") for lang in movie.get("spoken_languages", [])
                     if lang.get("iso_639_1") == movie.get("original_language")), None)
    release = movie.get("release_date") or ""
    return {
        "id": f"tmdb-{movie['id']}", "type": "movie", "tmdb_id": movie["id"], "title": movie["title"],
        "original_title": movie.get("original_title", "") if movie.get("original_title") != movie["title"] else "",
        "year": int(release[:4]) if release else None, "release_date": release, "runtime": movie.get("runtime") or None,
        "genres": [g["name"] for g in movie.get("genres", [])], "language": language or movie.get("original_language", ""),
        "overview": movie.get("overview", ""), "tagline": movie.get("tagline", ""),
        "directors": crew(("Director",)), "writers": crew(("Screenplay", "Writer", "Story", "Dialogue")),
        "producers": crew(("Producer",)), "music": crew(("Original Music Composer", "Music")),
        "cast": [{"name": c["name"], "character": c.get("character", "")} for c in credits.get("cast", []) if c.get("name")][:cast_limit],
        "values": values, "notes": "", "sources": [TMDB_URL.format(id=movie["id"])],
    }
