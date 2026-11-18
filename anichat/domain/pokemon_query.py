"""Questions about many Pokémon at once ("all Fire types from Generation I", "Fire/Water dual
types", "fastest Pokémon", "weak to Ice", "how many Water types per generation"), answered from
the Pokémon table (infrastructure/pokemon_db.py). Pure Python, no I/O.

Like domain/movie_query.py: the chat model turns the question into a PokemonQuery (JSON with
known keys and values only, never SQL), the table answers it exactly, and the rows become one
more source for the answer.
"""

import json
import re
from dataclasses import dataclass, field

from anichat.domain.llm import ChatMessage

TYPES = ("normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison", "ground", "flying",
         "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy")
STATS = ("hp", "attack", "defense", "sp_attack", "sp_defense", "speed", "total", "height_m", "weight_kg", "number")
STATUSES = ("legendary", "mythical", "baby", "regular")  # regular: none of the other three
COUNT_BY = ("type", "type_combination", "generation")
MAX_LIMIT = 100

# A question that may need the table: about several Pokémon, types, generations, stats or matchups.
_POKEMON_WORDS = re.compile(
    r"\b(pok[eé]mon|pok[eé]dex|gen(?:eration)?s?\s*(?:[1-9]|i{1,3}|iv|v|vi{0,3}|ix)\b|legendar(?:y|ies)|mythical|"
    rf"(?:{'|'.join(TYPES)})[- ]?types?|dual[- ]types?|mono[- ]?types?|pure (?:{'|'.join(TYPES)})|"
    r"base stats?|stat total|sp(?:ecial)?\.? ?(?:attack|defen[cs]e)|weak (?:to|against)|resists?|immune|"
    r"type combinations?|evolutions?)\b", re.I)
_MANY = re.compile(
    r"\b(all|every|list|which|how many|most|least|highest|lowest|top|fastest|slowest|strongest|weakest|best|"
    r"heaviest|lightest|tallest|shortest|biggest|smallest|over|under|above|below|more than|less than|count|"
    r"combinations?|each|per|rank\w*|compare|types)\b", re.I)


def looks_pokemon_table(question: str) -> bool:
    """Whether the question may need the Pokémon table: it talks Pokémon (types, generations,
    stats, matchups) and about several of them or a ranking.

    Called by: application/pokemon_questions.py  PokemonQuestions.source(); tests
    """
    return bool(_POKEMON_WORDS.search(question) and _MANY.search(question))


@dataclass(frozen=True)
class StatRange:
    """A base stat (or size) between two values: speed >= 100."""

    stat: str
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class PokemonQuery:
    """What to look up in the Pokémon table. Every part is optional; parse_query() keeps only
    known values, which become bound SQL parameters (never SQL text).

    Created by: parse_query()
    Used by:    infrastructure/pokemon_db.py  PokemonDB.run()
    """

    types: tuple[str, ...] = ()  # has all of these types: ("fire",) or ("fire", "water")
    single_type: bool | None = None  # True: pure (no second type); False: dual types only
    exclude_types: tuple[str, ...] = ()
    generation: int | None = None
    generation_from: int | None = None
    generation_to: int | None = None
    status: str | None = None  # one of STATUSES
    fully_evolved: bool | None = None
    weak_to: str | None = None  # takes x2 or more from this type...
    weak_x4: bool = False  # ...and only x4
    resists: str | None = None  # takes x0.5 or less (immunity included)
    immune_to: str | None = None
    name: str | None = None  # part of a name: "chu"
    ability: str | None = None
    egg_group: str | None = None
    stat_ranges: tuple[StatRange, ...] = field(default_factory=tuple)
    include_forms: bool = False  # Mega, Alolan, Galarian... rows too
    sort_by: str | None = None  # one of STATS
    order: str = "desc"
    limit: int = 30
    count_by: str | None = None  # one of COUNT_BY: counts instead of a list
    count_equals: int | None = None  # with count_by: only groups of exactly this size (1 = unique typings)


def planner_messages(question: str) -> list[ChatMessage]:
    """The prompt that turns a question into a PokemonQuery (as JSON) or {"query": null}.

    Called by: application/pokemon_questions.py  PokemonQuestions.source()
    """
    system = (
        "You turn a question about Pokémon into a JSON query for a Pokémon table (every species, numbers 1-1025, "
        "generations 1-9), or decide it isn't one.\n"
        "Answer with JSON only: {\"query\": {...}} or {\"query\": null}.\n"
        "Use null for questions about one Pokémon's details, the anime, or a story.\n"
        "Keys (all optional):\n"
        f"- types: list of 1-2 types the Pokémon must have, from: {', '.join(TYPES)}\n"
        "- single_type: true = only one type (pure/mono), false = dual types only\n"
        "- exclude_types: list of types it must not have\n"
        "- generation, generation_from, generation_to: 1-9\n"
        f"- status: one of {', '.join(STATUSES)} (regular = not legendary, mythical or baby)\n"
        "- fully_evolved: true/false\n"
        "- weak_to: a type it takes 2x or more from; weak_x4: true for 4x only; resists: a type it takes half or less "
        "from; immune_to: a type it takes no damage from\n"
        "- name, ability, egg_group: text\n"
        f"- stat_ranges: list of {{\"stat\", \"min\", \"max\"}} with stat one of {', '.join(STATS[:-1])}\n"
        "- include_forms: true to include Mega/regional/other forms (default false)\n"
        f"- sort_by: one of {', '.join(STATS)}; order: \"desc\" (highest first) or \"asc\"\n"
        f"- limit: 1-{MAX_LIMIT} (use {MAX_LIMIT} for \"all\"/\"list\"/\"every\")\n"
        f"- count_by: one of {', '.join(COUNT_BY)}: counts instead of a list (\"how many per ...\"); "
        "type_combination counts a pure type as itself, so for dual types add single_type: false; "
        "count_equals: only groups of exactly that size (1 = held by just one Pokémon)\n"
        "Examples:\n"
        "All Fire types from Generation 1 -> {\"query\": {\"types\": [\"fire\"], \"generation\": 1, \"sort_by\": \"number\", "
        "\"order\": \"asc\", \"limit\": 100}}\n"
        "Fire and Water dual types -> {\"query\": {\"types\": [\"fire\", \"water\"], \"limit\": 100}}\n"
        "Fastest non-legendary Pokémon -> {\"query\": {\"status\": \"regular\", \"sort_by\": \"speed\", \"limit\": 10}}\n"
        "Pokémon with 4x weakness to Ice -> {\"query\": {\"weak_to\": \"ice\", \"weak_x4\": true, \"limit\": 100}}\n"
        "How many Water types are there in each generation? -> {\"query\": {\"types\": [\"water\"], \"count_by\": \"generation\"}}\n"
        "Most common dual type combinations -> {\"query\": {\"single_type\": false, \"count_by\": \"type_combination\"}}\n"
        "Which Pokémon have a typing no other Pokémon has? -> {\"query\": {\"single_type\": false, "
        "\"count_by\": \"type_combination\", \"count_equals\": 1}}\n"
        "What is Charizard weak to? -> {\"query\": null}"
    )
    return [ChatMessage("system", system), ChatMessage("user", question)]


def _int(value, low: int, high: int) -> int | None:
    """A whole number within [low, high], or None. Called by: parse_query()"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if low <= n <= high else None


def _num(value) -> float | None:
    """A number, or None. Called by: parse_query()"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _type(value) -> str | None:
    """A known type ("Fire" -> "fire"), or None. Called by: parse_query()"""
    v = str(value or "").strip().lower()
    return v if v in TYPES else None


def _text(value, limit: int = 40) -> str | None:
    """A short plain string without LIKE wildcards, or None. Called by: parse_query()"""
    if not isinstance(value, str):
        return None
    value = re.sub(r"[\x00-\x1f%_\\]", "", value).strip()[:limit]
    return value or None


def _bool(value) -> bool | None:
    """true/false, or None. Called by: parse_query()"""
    return value if isinstance(value, bool) else None


def parse_query(reply: str) -> PokemonQuery | None:
    """The model's JSON reply as a PokemonQuery, keeping only valid parts; None when the model said
    the table doesn't help, the reply isn't JSON, or nothing usable is left.

    Called by: application/pokemon_questions.py  PokemonQuestions.source(); tests
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
    as_list = lambda v: v if isinstance(v, list) else [v] if v else []  # noqa: E731
    types = tuple(dict.fromkeys(t for t in map(_type, as_list(q.get("types"))) if t))[:2]
    ranges = []
    for r in as_list(q.get("stat_ranges"))[:6]:
        if isinstance(r, dict) and r.get("stat") in STATS[:-1] and (_num(r.get("min")) is not None or _num(r.get("max")) is not None):
            ranges.append(StatRange(r["stat"], _num(r.get("min")), _num(r.get("max"))))
    query = PokemonQuery(
        types=types, single_type=_bool(q.get("single_type")),
        exclude_types=tuple(t for t in map(_type, as_list(q.get("exclude_types"))) if t)[:6],
        generation=_int(q.get("generation"), 1, 9), generation_from=_int(q.get("generation_from"), 1, 9),
        generation_to=_int(q.get("generation_to"), 1, 9), status=q.get("status") if q.get("status") in STATUSES else None,
        fully_evolved=_bool(q.get("fully_evolved")), weak_to=_type(q.get("weak_to")), weak_x4=q.get("weak_x4") is True,
        resists=_type(q.get("resists")), immune_to=_type(q.get("immune_to")), name=_text(q.get("name")),
        ability=_text(q.get("ability")), egg_group=_text(q.get("egg_group")), stat_ranges=tuple(ranges),
        include_forms=q.get("include_forms") is True, sort_by=q.get("sort_by") if q.get("sort_by") in STATS else None,
        order="asc" if q.get("order") == "asc" else "desc", limit=_int(q.get("limit"), 1, MAX_LIMIT) or 30,
        count_by=q.get("count_by") if q.get("count_by") in COUNT_BY else None,
        count_equals=_int(q.get("count_equals"), 1, 1000) if q.get("count_by") in COUNT_BY else None,
    )
    empty = PokemonQuery(order=query.order, limit=query.limit, include_forms=query.include_forms)
    if query == empty and not query.sort_by:
        return None  # nothing to look up
    return query


def describe_query(q: PokemonQuery) -> str:
    """"Pokémon of type Fire/Water from Generation 1, sorted by speed, highest first": the heading
    of the results source. Called by: application/pokemon_questions.py; tests
    """
    parts = []
    if q.types:
        parts.append(f"of type {'/'.join(t.capitalize() for t in q.types)}"
                     + (" only (no second type)" if q.single_type else " with a second type" if q.single_type is False else ""))
    elif q.single_type is not None:
        parts.append("with one type" if q.single_type else "with two types")
    if q.exclude_types:
        parts.append("not " + "/".join(t.capitalize() for t in q.exclude_types))
    if q.generation:
        parts.append(f"from Generation {q.generation}")
    elif q.generation_from or q.generation_to:
        parts.append(f"from Generation {q.generation_from or 1} to {q.generation_to or 9}")
    if q.status:
        parts.append(f"{q.status}")
    if q.fully_evolved is not None:
        parts.append("fully evolved" if q.fully_evolved else "not fully evolved")
    if q.weak_to:
        parts.append(f"taking {'4x' if q.weak_x4 else '2x or more'} damage from {q.weak_to.capitalize()}")
    if q.resists:
        parts.append(f"resisting {q.resists.capitalize()}")
    if q.immune_to:
        parts.append(f"immune to {q.immune_to.capitalize()}")
    for label, value in (("named like", q.name), ("with ability", q.ability), ("in egg group", q.egg_group)):
        if value:
            parts.append(f'{label} "{value}"')
    for r in q.stat_ranges:
        parts.append(f"{r.stat}" + (f" ≥ {r.min:g}" if r.min is not None else "") + (f" ≤ {r.max:g}" if r.max is not None else ""))
    text = "Pokémon " + (", ".join(parts) if parts else "(all)") + (" (forms included)" if q.include_forms else "")
    if q.count_by:
        text += f", counted by {q.count_by.replace('_', ' ')}"
        text += " (type order ignored)" if q.count_by == "type_combination" else ""
        text += f", only groups of exactly {q.count_equals}" if q.count_equals else ""
    elif q.sort_by:
        text += f", sorted by {q.sort_by.replace('_', ' ')}, {'highest' if q.order == 'desc' else 'lowest'} first"
    return text
