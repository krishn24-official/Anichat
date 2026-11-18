"""Use case: answer list / ranking / counting questions about Pokémon from the Pokémon table.

    question -> looks like one? -> model plans a PokemonQuery (JSON) -> PokemonDB runs it
             -> the rows become one more source (a Chunk) for the answer, cited like any other
"""

import time

from anichat.application.llm_fallback import AllModelsUnavailable
from anichat.domain.chunking import Chunk
from anichat.domain.llm import ChatModel, ModelUnavailable
from anichat.domain.pokedex import SERIES
from anichat.domain.pokemon_query import PokemonQuery, describe_query, looks_pokemon_table, parse_query, planner_messages
from anichat.infrastructure.pokemon_db import PokemonDB

ROMAN = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX")


class PokemonQuestions:
    """Created by: anichat/container.py  answer_service()
    Used by:    application/answer.py  AnswerService._context()
    """

    def __init__(self, db: PokemonDB, model: ChatModel):
        self._db = db
        self._model = model

    def source(self, question: str, series: str | None) -> tuple[Chunk | None, float]:
        """The Pokémon table's answer as a source chunk (None when the question isn't that kind, the
        table isn't built, or nothing matches), and the seconds it took.

        Called by: application/answer.py  AnswerService._context()
        """
        if series not in (None, SERIES) or not self._db.exists() or not looks_pokemon_table(question):
            return None, 0.0
        started = time.perf_counter()
        try:
            reply = self._model.complete(planner_messages(question))
        except (AllModelsUnavailable, ModelUnavailable):
            return None, time.perf_counter() - started
        query = parse_query(reply.text)
        if query is None:
            return None, time.perf_counter() - started
        rows, total = self._db.run(query)
        if not rows:
            return None, time.perf_counter() - started
        chunk = Chunk(id=f"{SERIES}:table", text=results_text(query, rows, total), series=SERIES, kind="table",
                      title="Pokémon table", display_title="Pokémon table (Pokédex data)", section=describe_query(query),
                      number=None, source="https://pokeapi.co/")
        return chunk, time.perf_counter() - started


def results_text(query: PokemonQuery, rows: list[dict], total: int) -> str:
    """The rows as a list the answer model can read and cite.

    Called by: PokemonQuestions.source(); tests
    """
    head = f"Pokémon table › {describe_query(query)}"
    if query.count_by:
        label = {"generation": lambda g: f"Generation {ROMAN[g] if isinstance(g, int) and g < 10 else g}",
                 "type": lambda g: str(g).capitalize(), "type_combination": lambda g: "/".join(x.capitalize() for x in str(g).split("/"))}
        lines = [head, f"{total} group(s), {sum(r['count'] for r in rows)} in all:"]
        lines += [f"- {label[query.count_by](r['group'])}: {r['count']}" + (f" ({r['names']})" if r.get("names") else "")
                  for r in rows]
        return "\n".join(lines)
    lines = [head, f"{total} Pokémon match" + (f"; the first {len(rows)} are listed" if total > len(rows) else "") + ":"]
    for r in rows:
        types = r["type1"].capitalize() + (f"/{r['type2'].capitalize()}" if r["type2"] else "")
        status = ", ".join(s for s in ("legendary", "mythical", "baby") if r[s])
        weak = ", ".join(f"{t.capitalize()}{' x4' if m >= 4 else ''}" for t, m in r["weak"])
        lines.append(
            f"#{r['number']:04d} {r['name']} | {types} | Gen {ROMAN[r['generation']] if r['generation'] else '?'}"
            + (f" | {status}" if status else "")
            + f" | HP {r['hp']} Atk {r['attack']} Def {r['defense']} SpA {r['sp_attack']} SpD {r['sp_defense']} "
              f"Spe {r['speed']} (total {r['total']})"
            + (f" | {r['height_m']:g} m, {r['weight_kg']:g} kg" if query.sort_by in ("height_m", "weight_kg") else "")
            + (f" | weak to {weak}" if weak else ""))
    return "\n".join(lines)
