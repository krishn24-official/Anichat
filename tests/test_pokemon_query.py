"""Tests for list / ranking / counting questions answered from the Pokémon table (no network)."""

from anichat.application.pokemon_questions import PokemonQuestions, results_text
from anichat.domain.llm import ModelReply
from anichat.domain.pokemon_query import PokemonQuery, StatRange, describe_query, looks_pokemon_table, parse_query
from anichat.infrastructure.pokemon_db import PokemonDB


def row(number, name, t1, t2="", gen=1, speed=50, total=400, form="", legendary=False, matchups=None, final=True):
    return {"number": number, "name": name, "species": name, "form": form, "generation": gen, "type1": t1, "type2": t2,
            "category": "", "legendary": legendary, "mythical": False, "baby": False, "stage": 1, "fully_evolved": final,
            "evolves_from": "", "egg_groups": "", "hp": 50, "attack": 50, "defense": 50, "sp_attack": 50, "sp_defense": 50,
            "speed": speed, "total": total, "height_m": 1.0, "weight_kg": 10.0, "abilities": "Blaze", "hidden_ability": "",
            "matchups": matchups or {}}


ROWS = [
    row(4, "Charmander", "fire", speed=65, final=False, matchups={"water": 2.0, "rock": 2.0, "grass": 0.5}),
    row(6, "Charizard", "fire", "flying", speed=100, total=534, matchups={"rock": 4.0, "water": 2.0, "ground": 0.0}),
    row(6, "Charizard Mega X", "fire", "dragon", speed=100, total=634, form="Charizard Mega X"),
    row(130, "Gyarados", "water", "flying", speed=81, matchups={"electric": 4.0, "rock": 2.0, "ground": 0.0}),
    row(721, "Volcanion", "fire", "water", gen=6, speed=70, legendary=True, matchups={"ground": 2.0, "rock": 2.0}),
    row(894, "Regieleki", "electric", gen=8, speed=200, legendary=True, matchups={"ground": 2.0}),
]


def db(tmp_path):
    d = PokemonDB(tmp_path / "pokemon.sqlite")
    assert d.rebuild(ROWS) == 6
    return d


def test_only_list_ranking_and_counting_questions_go_to_the_table():
    for q in ("All Fire types from generation 1", "Which Pokémon are Fire/Water dual types?", "Fastest Pokémon?",
              "How many Water types are there in each generation?", "List Pokémon weak to Ice"):
        assert looks_pokemon_table(q), q
    for q in ("What is Charizard weak to?", "Who was Ash's first Pokémon?", "Which movie earned the most?"):
        assert not looks_pokemon_table(q), q


def test_the_plan_keeps_only_known_types_stats_and_options():
    q = parse_query('{"query": {"types": ["Fire", "Water", "Plasma"], "generation": "6", "status": "god", '
                    '"stat_ranges": [{"stat": "speed", "min": 60}, {"stat": "drop table", "min": 1}], "limit": 500}}')
    assert q == PokemonQuery(types=("fire", "water"), generation=6, stat_ranges=(StatRange("speed", 60.0),), limit=30)
    assert parse_query('{"query": null}') is None and parse_query("not json") is None
    assert parse_query('{"query": {"types": ["plasma"]}}') is None  # nothing usable left


def test_the_table_filters_types_matchups_stats_and_forms(tmp_path):
    d = db(tmp_path)
    names = lambda q: [r["name"] for r in d.run(q)[0]]  # noqa: E731
    assert names(PokemonQuery(types=("fire",))) == ["Charmander", "Charizard", "Volcanion"]  # no Mega form
    assert names(PokemonQuery(types=("fire",), include_forms=True))[-1] == "Volcanion"
    assert names(PokemonQuery(types=("fire", "water"))) == ["Volcanion"]
    assert names(PokemonQuery(types=("fire",), single_type=True)) == ["Charmander"]
    assert names(PokemonQuery(weak_to="rock", weak_x4=True)) == ["Charizard"]
    assert names(PokemonQuery(immune_to="ground")) == ["Charizard", "Gyarados"]
    assert names(PokemonQuery(sort_by="speed", limit=2)) == ["Regieleki", "Charizard"]
    assert names(PokemonQuery(status="regular", stat_ranges=(StatRange("speed", 80),))) == ["Charizard", "Gyarados"]
    assert names(PokemonQuery(fully_evolved=False)) == ["Charmander"]
    assert names(PokemonQuery(generation_from=6)) == ["Volcanion", "Regieleki"]


def test_counts_by_generation_type_and_combination(tmp_path):
    d = db(tmp_path)
    gens, _ = d.run(PokemonQuery(count_by="generation"))
    assert [(g["group"], g["count"]) for g in gens] == [(1, 3), (6, 1), (8, 1)]
    assert gens[0]["names"] == "Charmander, Charizard, Gyarados"  # small groups name their Pokémon
    types, _ = d.run(PokemonQuery(count_by="type"))
    assert (types[0]["group"], types[0]["count"]) == ("fire", 3) and ("flying", 2) in [(t["group"], t["count"]) for t in types]
    combos, _ = d.run(PokemonQuery(single_type=False, count_by="type_combination"))
    assert {"group": "fire/water", "count": 1, "names": "Volcanion"} in combos and all("/" in c["group"] for c in combos)
    # Order of types doesn't matter: a Water/Flying and a Flying/Water Pokémon share a typing.
    d.rebuild(ROWS + [row(931, "Squawkabilly", "flying", "water")])
    combos, _ = d.run(PokemonQuery(single_type=False, count_by="type_combination"))
    assert {"group": "flying/water", "count": 2, "names": "Gyarados, Squawkabilly"} in combos
    unique, _ = d.run(PokemonQuery(single_type=False, count_by="type_combination", count_equals=1))
    assert [u["group"] for u in unique] == ["fire/flying", "fire/water"]


def test_results_read_like_a_source(tmp_path):
    q = PokemonQuery(types=("fire",), sort_by="speed")
    rows, total = db(tmp_path).run(q)
    text = results_text(q, rows, total)
    assert text.startswith("Pokémon table › Pokémon of type Fire, sorted by speed, highest first")
    assert "#0006 Charizard | Fire/Flying | Gen I | HP 50" in text and "weak to Rock x4, Water" in text
    assert "#0721 Volcanion | Fire/Water | Gen VI | legendary" in text
    assert describe_query(PokemonQuery(types=("water",), count_by="generation")) == \
        "Pokémon of type Water, counted by generation"


class FakeModel:
    name = "fake"

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def complete(self, messages):
        self.calls += 1
        return ModelReply(self.reply, "fake")


def test_the_table_becomes_a_source_only_for_its_questions(tmp_path):
    d = db(tmp_path)
    chunk, _ = PokemonQuestions(d, FakeModel('{"query": {"types": ["fire"], "generation": 1}}')).source(
        "All Fire types from generation 1", None)
    assert chunk is not None and chunk.title == "Pokémon table" and "Charmander" in chunk.text
    quiet = FakeModel('{"query": {"types": ["fire"]}}')
    assert PokemonQuestions(d, quiet).source("What is Charizard weak to?", None)[0] is None
    assert PokemonQuestions(d, quiet).source("All Fire types from generation 1", "naruto")[0] is None
    assert quiet.calls == 0
