"""Tests for Pokédex pages built from PokéAPI data (no network)."""

from anichat.domain.pokedex import defenses, evolution_lines, pokemon_document, type_chart


def t(name, double=(), half=(), none=()):
    """A PokéAPI /type answer with only the attacking relations used here."""
    rel = {"double_damage_to": [{"name": n} for n in double], "half_damage_to": [{"name": n} for n in half],
           "no_damage_to": [{"name": n} for n in none]}
    return {"name": name, "damage_relations": rel}


CHART = type_chart([
    t("rock", double=["fire", "flying", "ice", "bug"], half=["fighting", "ground", "steel"]),
    t("electric", double=["water", "flying"], half=["electric", "grass", "dragon"], none=["ground"]),
    t("ground", double=["fire", "electric", "poison", "rock", "steel"], half=["grass", "bug"], none=["flying"]),
    t("water", double=["fire", "ground", "rock"], half=["water", "grass", "dragon"]),
    t("grass", double=["water", "ground", "rock"], half=["fire", "grass", "poison", "flying", "bug", "dragon", "steel"]),
])


def test_dual_types_multiply_and_immunities_win():
    charizard = defenses(["fire", "flying"], CHART)
    assert charizard[4.0] == ["rock"] and charizard[2.0] == ["electric", "water"]
    assert charizard[0.0] == ["ground"] and charizard[0.25] == ["grass"]
    assert "ground" not in defenses(["water"], CHART).get(0.0, [])


def test_evolution_chain_with_conditions():
    chain = {"species": {"name": "pichu"}, "evolves_to": [
        {"species": {"name": "pikachu"}, "evolution_details": [{"min_happiness": 220, "trigger": {"name": "level-up"}}],
         "evolves_to": [{"species": {"name": "raichu"}, "evolution_details": [{"item": {"name": "thunder-stone"},
                                                                               "trigger": {"name": "use-item"}}],
                         "evolves_to": []}]}]}
    names = {"pichu": "Pichu", "pikachu": "Pikachu", "raichu": "Raichu"}
    assert evolution_lines(chain, names) == ["Pichu → Pikachu (high friendship)", "Pikachu → Raichu (Thunder Stone)"]


def test_a_pokemon_page_has_number_types_weaknesses_and_entries():
    species = {"id": 25, "name": "pikachu", "names": [{"language": {"name": "en"}, "name": "Pikachu"}],
               "genera": [{"language": {"name": "en"}, "genus": "Mouse Pokémon"}], "generation": {"name": "generation-i"},
               "is_legendary": False, "is_mythical": False, "evolves_from_species": {"name": "pichu"},
               "egg_groups": [{"name": "field"}, {"name": "fairy"}],
               "flavor_text_entries": [{"language": {"name": "en"}, "flavor_text": "When several of\nthese POKéMON gather,"},
                                       {"language": {"name": "en"}, "flavor_text": "When several of\nthese POKéMON gather,"}]}
    pokemon = {"types": [{"slot": 1, "type": {"name": "electric"}}], "height": 4, "weight": 60,
               "abilities": [{"slot": 1, "is_hidden": False, "ability": {"name": "static"}},
                             {"slot": 3, "is_hidden": True, "ability": {"name": "lightning-rod"}}],
               "stats": [{"stat": {"name": n}, "base_stat": v} for n, v in
                         (("hp", 35), ("attack", 55), ("defense", 40), ("special-attack", 50), ("special-defense", 50), ("speed", 90))]}
    doc = pokemon_document(species, pokemon, None, CHART, {"pichu": "Pichu"}, [], {"static": "Static", "lightning-rod": "Lightning Rod"})
    assert doc.title == "Pikachu" and doc.display_title == "Pikachu (#0025)" and doc.number == 25 and doc.kind == "pokemon"
    assert doc.facts["type"] == "Electric" and doc.facts["weak to (x2)"] == "Ground" and doc.facts["hidden ability"] == "Lightning Rod"
    assert doc.facts["evolves from"] == "Pichu" and doc.facts["size"] == "0.4 m, 6 kg" and doc.facts["base stat total"] == "320"
    assert doc.body.startswith("Pikachu (Pokédex #0025) is an Electric-type Pokémon, the Mouse Pokémon, introduced in "
                               "Generation I. It is weak to Ground. When several of these POKéMON gather,")
    assert "## Pokédex entries" not in doc.body  # the repeated entry is shown once
