"""Questions about many movies at once ("which movie earned the most?", "Ranbir Kapoor's films
by collection", "total of days 1-3"), answered from the movies table instead of text chunks.
Pure Python, no I/O.

Chunk search sees ~8 passages, so it can't rank or add up across movies. For such questions the
chat model first turns the question into a MovieQuery (JSON, only known fields and options:
never SQL), infrastructure/movie_db.py runs it, and the rows go to the model as one more source.
"""

import json
import re
from dataclasses import dataclass

from anichat.domain.llm import ChatMessage

ROLES = ("cast", "director", "writer", "producer", "music")
BUILTIN_SORTS = {"year": "release year", "release_date": "release date", "runtime": "runtime (minutes)"}
MAX_LIMIT = 20

# Words that suggest a question about several movies or about numbers across them. Questions
# without them ("Who played Ravana?", "What is Ramayana about?") go to chunk search only.
_STRUCTURED = re.compile(
    r"\b(most|highest|lowest|least|top|best|worst|biggest|largest|smallest|longest|shortest|rank\w*|list|"
    r"all (?:the )?(?:movies|films)|how many|total|sum|add(?:ed)? up|average|compare|comparison|"
    r"which (?:movie|film)s?|movies|films|earned|grossed|collections?|box[- ]office|day[- ]?wise|"
    r"(?:first|opening) (?:day|week(?:end)?)|days? \d+\s*(?:to|-|–|and|through)\s*\d+|"
    r"(?:first|opening|initial|last) \d+ days?|\d+[- ]days?)\b", re.I)


def looks_structured(question: str) -> bool:
    """Whether the question may need the movies table (ranking, filtering, totals).

    Called by: application/movie_questions.py  MovieQuestions.source(); tests
    """
    return bool(_STRUCTURED.search(question))


@dataclass(frozen=True)
class MovieQuery:
    """What to look up in the movies table. Every part is optional; values are checked by
    parse_query() against the known fields, and become bound SQL parameters (never SQL text).

    Created by: parse_query()
    Used by:    infrastructure/movie_db.py  MovieDB.run()
    """

    title: str | None = None  # part of the title: "ramayana"
    franchise: str | None = None  # a film series or studio: "Fast & Furious", "Marvel" (title, series or studio)
    year: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    language: str | None = None  # "Hindi"
    genre: str | None = None  # "Horror"
    person: str | None = None  # part of a name: "ranbir kapoor"
    role: str | None = None  # one of ROLES, with person
    sort_by: str | None = None  # a number/money field id, or one of BUILTIN_SORTS
    order: str = "desc"  # "desc" (highest first) or "asc"
    limit: int = 10
    days_field: str | None = None  # a day-wise field id: add up its rows...
    days_from: int | None = None  # ...from this row (1 = first)...
    days_to: int | None = None  # ...to this one


def planner_messages(question: str, fields: list[dict]) -> list[ChatMessage]:
    """The prompt that turns a question into a MovieQuery (as JSON) or {"query": null}.

    `fields`: the movie fields ({"id", "label", "type", "currency", "unit"}).
    Called by: application/movie_questions.py  MovieQuestions.source()
    """
    def describe(f: dict) -> str:
        money = f" ({f.get('currency', '')} {f.get('unit', '')}".rstrip() + ")" if f.get("currency") or f.get("unit") else ""
        filled = f", filled for {f['filled']} movies" if "filled" in f else ""
        return f'"{f["id"]}": {f["label"]}{money}{filled}'

    # Most-filled first: "Budget (USD)" (from TMDb, every movie) before "Budget" (₹, typed by hand).
    sortable = sorted((f for f in fields if f.get("type") in ("money", "number")), key=lambda f: -f.get("filled", 0))
    daywise = [f for f in fields if f.get("type") == "daywise"]
    system = (
        "You turn a question about movies into a JSON query for a movies table, or decide it isn't one.\n"
        "Answer with JSON only, no other text: {\"query\": {...}} or {\"query\": null}.\n"
        "Use null when the question is about a story, a character, or one movie's single detail that "
        "needs no ranking, filtering, listing or adding up.\n"
        "Query keys (all optional): title (part of a movie title), franchise (a film series or studio such as "
        "Marvel, DC, Fast & Furious, Jumanji: use it, not title, for a series), year, year_from, year_to, language, genre, "
        f"person (part of a person's name), role (one of {', '.join(ROLES)}), sort_by, order (\"desc\" = highest "
        f"first, \"asc\"), limit (1-{MAX_LIMIT}), days_field, days_from, days_to (row numbers, 1 = first day).\n"
        "sort_by is one of: " + ", ".join([f'"{k}": {v}' for k, v in BUILTIN_SORTS.items()] + [describe(f) for f in sortable]) + ".\n"
        "days_field is one of: " + (", ".join(describe(f) for f in daywise) or "(none)") + ".\n"
        "When two fields fit (budget in USD or in INR), pick the one filled for more movies.\n"
        f"For \"list\", \"all\" or \"every\" questions use limit {MAX_LIMIT}.\n"
        "Examples:\n"
        "Which Fast and Furious movie made the most money? -> {\"query\": {\"franchise\": \"Fast & Furious\", "
        "\"sort_by\": \"worldwide_gross_usd\", \"limit\": 5}}\n"
        "Which movie earned the most in India? -> {\"query\": {\"sort_by\": \"india_net_collection\", \"order\": \"desc\", \"limit\": 5}}\n"
        "Ranbir Kapoor's movies by worldwide collection -> {\"query\": {\"person\": \"Ranbir Kapoor\", \"role\": \"cast\", "
        "\"sort_by\": \"worldwide_gross_collection\"}}\n"
        "How much did Ramayana make in its first 3 days? -> {\"query\": {\"title\": \"Ramayana\", \"days_field\": "
        "\"india_net_collection_day_wise\", \"days_from\": 1, \"days_to\": 3}}\n"
        "Who played Ravana in Ramayana? -> {\"query\": null}"
    )
    return [ChatMessage("system", system), ChatMessage("user", question)]


def _int(value, low: int, high: int) -> int | None:
    """A whole number within [low, high], or None. Called by: parse_query()"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if low <= n <= high else None


def _text(value, limit: int = 80) -> str | None:
    """A short plain string, or None. Called by: parse_query()"""
    if not isinstance(value, str):
        return None
    value = re.sub(r"[\x00-\x1f%_\\]", "", value).strip()[:limit]  # no LIKE wildcards from the model
    return value or None


def parse_query(reply: str, fields: list[dict]) -> MovieQuery | None:
    """The model's JSON reply as a MovieQuery, keeping only valid parts; None when the model said
    the table doesn't help, the reply isn't JSON, or nothing usable is left.

    Called by: application/movie_questions.py  MovieQuestions.source(); tests
    """
    m = re.search(r"\{.*\}", reply, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    q = data.get("query") if isinstance(data, dict) else None
    if not isinstance(q, dict):
        return None
    sortable = {f["id"] for f in fields if f.get("type") in ("money", "number")} | set(BUILTIN_SORTS)
    daywise = {f["id"] for f in fields if f.get("type") == "daywise"}
    role = q.get("role") if q.get("role") in ROLES else None
    query = MovieQuery(
        title=_text(q.get("title")), franchise=_text(q.get("franchise"), 60), year=_int(q.get("year"), 1870, 2100),
        year_from=_int(q.get("year_from"), 1870, 2100), year_to=_int(q.get("year_to"), 1870, 2100),
        language=_text(q.get("language"), 40), genre=_text(q.get("genre"), 40), person=_text(q.get("person")),
        role=role, sort_by=q.get("sort_by") if q.get("sort_by") in sortable else None,
        order="asc" if q.get("order") == "asc" else "desc", limit=_int(q.get("limit"), 1, MAX_LIMIT) or 10,
        days_field=q.get("days_field") if q.get("days_field") in daywise else None,
        days_from=_int(q.get("days_from"), 1, 1000), days_to=_int(q.get("days_to"), 1, 1000),
    )
    if query == MovieQuery(order=query.order, limit=query.limit):
        return None  # nothing to look up
    return query


def describe_query(q: MovieQuery, labels: dict[str, str]) -> str:
    """"Movies with Ranbir Kapoor (cast), sorted by India net collection, highest first": the
    heading of the results source, so the answer can say what was looked up.

    Called by: application/movie_questions.py  MovieQuestions.source(); tests
    """
    parts = []
    if q.title:
        parts.append(f'titled like "{q.title}"')
    if q.franchise:
        parts.append(f"of {q.franchise}")
    if q.person:
        parts.append(f"with {q.person}" + (f" ({q.role})" if q.role else ""))
    if q.year:
        parts.append(f"from {q.year}")
    elif q.year_from or q.year_to:
        parts.append(f"from {q.year_from or '…'} to {q.year_to or '…'}")
    if q.language:
        parts.append(f"in {q.language}")
    if q.genre:
        parts.append(f"genre {q.genre}")
    text = "Movies " + (", ".join(parts) if parts else "(all)")
    if q.sort_by:
        name = labels.get(q.sort_by) or BUILTIN_SORTS.get(q.sort_by, q.sort_by)
        text += f", sorted by {name}, {'highest' if q.order == 'desc' else 'lowest'} first"
    if q.days_field:
        text += f"; adding up {labels.get(q.days_field, q.days_field)}" + (
            f" rows {q.days_from or 1} to {q.days_to or 'last'}" if q.days_from or q.days_to else "")
    return text
