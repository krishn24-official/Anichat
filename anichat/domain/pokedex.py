"""Pokédex pages from PokéAPI data (pokeapi.co): one Document per Pokémon species with its national
number, types, weaknesses, abilities, stats, evolution chain and Pokédex descriptions.
Pure Python, no I/O: scripts/add_pokedex.py fetches the data and saves the documents.

Weaknesses aren't in the data: they are worked out from the type chart for the Pokémon's own
type combination (a Grass/Poison type takes x4 from nothing, x2 from Fire, Ice, Flying, Psychic).
"""

import re

from anichat.domain.documents import Document

SERIES = "pokemon"
SERIES_TITLE = "Pokémon"
LICENSE = "PokéAPI (pokeapi.co); Pokémon names and descriptions © Nintendo / Game Freak / The Pokémon Company"
STATS = (("hp", "HP"), ("attack", "Attack"), ("defense", "Defense"), ("special-attack", "Sp. Atk"),
         ("special-defense", "Sp. Def"), ("speed", "Speed"))
GENERATIONS = {"generation-i": "Generation I", "generation-ii": "Generation II", "generation-iii": "Generation III",
               "generation-iv": "Generation IV", "generation-v": "Generation V", "generation-vi": "Generation VI",
               "generation-vii": "Generation VII", "generation-viii": "Generation VIII", "generation-ix": "Generation IX"}
MAX_ENTRIES = 6  # different Pokédex descriptions kept per Pokémon


def type_chart(types: list[dict]) -> dict[str, dict[str, float]]:
    """PokéAPI's /type/<name> answers -> attacking type -> defending type -> damage multiplier
    (only the non-1 ones are listed).

    Called by: scripts/add_pokedex.py; tests
    """
    chart: dict[str, dict[str, float]] = {}
    for t in types:
        rel = t["damage_relations"]
        row = chart.setdefault(t["name"], {})
        for key, mult in (("double_damage_to", 2.0), ("half_damage_to", 0.5), ("no_damage_to", 0.0)):
            for target in rel.get(key, []):
                row[target["name"]] = mult
    return chart


def defenses(defending: list[str], chart: dict[str, dict[str, float]]) -> dict[float, list[str]]:
    """How much each attacking type hurts this type combination: {4.0: [...], 2.0: [...], 0.5: [...],
    0.25: [...], 0.0: [...]} (x1 left out). Called by: pokemon_document(); tests
    """
    by_mult: dict[float, list[str]] = {}
    for attacker, row in sorted(chart.items()):
        mult = 1.0
        for d in defending:
            mult *= row.get(d, 1.0)
        if mult != 1.0:
            by_mult.setdefault(mult, []).append(attacker)
    return by_mult


def title_case(name: str) -> str:
    """"mr-mime" -> "Mr Mime" (only when no English name is given). Called by: pokemon_document()"""
    return " ".join(w.capitalize() for w in name.split("-"))


def _english(items: list[dict], key: str) -> str:
    """The English entry of a PokéAPI translated list. Called by: pokemon_document()"""
    return next((i[key] for i in items if i.get("language", {}).get("name") == "en"), "")


def _clean(text: str) -> str:
    """Pokédex text with its game line breaks and form feeds turned into spaces. Called by: pokemon_document()"""
    return re.sub(r"\s+", " ", text.replace("\f", " ").replace("­", "")).strip()


def evolution_lines(chain: dict, names: dict[str, str]) -> list[str]:
    """An evolution chain as lines: "Pichu → Pikachu (high friendship)", "Pikachu → Raichu (Thunder Stone)".

    `names`: species id-name -> English name. Called by: pokemon_document(); tests
    """
    lines = []

    def how(details: list[dict]) -> str:
        if not details:
            return ""
        d = details[0]
        parts = []
        if d.get("min_level"):
            parts.append(f"level {d['min_level']}")
        if d.get("item"):
            parts.append(title_case(d["item"]["name"]))
        if d.get("held_item"):
            parts.append(f"holding {title_case(d['held_item']['name'])}")
        if d.get("min_happiness"):
            parts.append("high friendship")
        if d.get("known_move"):
            parts.append(f"knowing {title_case(d['known_move']['name'])}")
        if d.get("time_of_day"):
            parts.append(f"at {d['time_of_day']}")
        trigger = (d.get("trigger") or {}).get("name", "")
        if trigger == "trade":
            parts.append("trade")
        return f" ({', '.join(parts)})" if parts else ""

    def walk(node: dict) -> None:
        here = names.get(node["species"]["name"], title_case(node["species"]["name"]))
        for nxt in node.get("evolves_to", []):
            lines.append(f"{here} → {names.get(nxt['species']['name'], title_case(nxt['species']['name']))}"
                         f"{how(nxt.get('evolution_details', []))}")
            walk(nxt)

    walk(chain)
    return lines


def chain_species(node: dict, names: dict[str, str]) -> list[str]:
    """Every species in an evolution chain, by English name. Called by: pokemon_document()"""
    out = [names.get(node["species"]["name"], title_case(node["species"]["name"]))]
    for nxt in node.get("evolves_to", []):
        out += chain_species(nxt, names)
    return out


def pokemon_document(species: dict, pokemon: dict, chain: dict | None, chart: dict[str, dict[str, float]],
                     names: dict[str, str], varieties: list[dict], abilities_en: dict[str, str]) -> Document:
    """One Pokémon species (PokéAPI /pokemon-species and its default /pokemon, its evolution chain,
    its other varieties' /pokemon) as a Document.

    `names`: species id-name -> English name (for the evolution chain); `abilities_en`: ability
    id-name -> English name. Called by: scripts/add_pokedex.py
    """
    number = species["id"]
    name = _english(species.get("names", []), "name") or title_case(species["name"])
    # "Nidoran♀" and "Nidoran♂" must stay two pages (file names drop the symbols).
    name = name.replace("♀", " (female)").replace("♂", " (male)")
    genus = _english(species.get("genera", []), "genus")  # "Mouse Pokémon"
    types = [t["type"]["name"] for t in sorted(pokemon["types"], key=lambda t: t["slot"])]
    type_text = "/".join(t.capitalize() for t in types)
    generation = GENERATIONS.get((species.get("generation") or {}).get("name", ""), "")
    rank = "Mythical" if species.get("is_mythical") else "Legendary" if species.get("is_legendary") else ""
    abilities = [a for a in sorted(pokemon["abilities"], key=lambda a: a["slot"])]
    ability_names = [abilities_en.get(a["ability"]["name"], title_case(a["ability"]["name"])) for a in abilities if not a["is_hidden"]]
    hidden = [abilities_en.get(a["ability"]["name"], title_case(a["ability"]["name"])) for a in abilities if a["is_hidden"]]
    stats = {s["stat"]["name"]: s["base_stat"] for s in pokemon["stats"]}
    damage = defenses(types, chart)
    cap = lambda ts: ", ".join(t.capitalize() for t in ts)  # noqa: E731
    evolutions = evolution_lines(chain["chain"], names) if chain else []
    previous = names.get((species.get("evolves_from_species") or {}).get("name", ""), "")

    facts = {
        "national pokédex number": f"#{number:04d}",
        "type": type_text,
        "category": genus,
        "generation": generation,
        "status": rank,
        "abilities": ", ".join(ability_names),
        "hidden ability": ", ".join(hidden),
        "weak to (x4)": cap(damage.get(4.0, [])),
        "weak to (x2)": cap(damage.get(2.0, [])),
        "resists (x0.5)": cap(damage.get(0.5, [])),
        "resists (x0.25)": cap(damage.get(0.25, [])),
        "immune to": cap(damage.get(0.0, [])),
        "evolves from": previous,
        "size": f"{pokemon['height'] / 10:g} m, {pokemon['weight'] / 10:g} kg",  # not "height": that is character trivia
        "base stat total": str(sum(stats.values())),
        "egg groups": cap(g["name"] for g in species.get("egg_groups", [])),
    }
    facts = {k: v for k, v in facts.items() if v}

    weak = damage.get(4.0, []) + damage.get(2.0, [])
    intro = (f"{name} (Pokédex #{number:04d}) is a{'n' if type_text[0] in 'AEIOU' else ''} {type_text}-type "
             f"{(rank + ' ') if rank else ''}Pokémon{', the ' + genus if genus else ''}"
             f"{', introduced in ' + generation if generation else ''}.")
    intro += f" It is weak to {cap(weak)}." if weak else ""
    entries = list(dict.fromkeys(_clean(f["flavor_text"]) for f in species.get("flavor_text_entries", [])
                                 if f.get("language", {}).get("name") == "en"))
    parts = [intro + (" " + entries[0] if entries else "")]
    parts.append("## Base stats\n\n" + "\n".join(f"- {label}: {stats.get(key, '?')}" for key, label in STATS)
                 + f"\n- Total: {sum(stats.values())}")
    matchup = [f"- {label}: {cap(damage[m])}" for m, label in ((4.0, "Takes 4x damage from"), (2.0, "Takes 2x damage from"),
               (0.5, "Takes ½ damage from"), (0.25, "Takes ¼ damage from"), (0.0, "Takes no damage from")) if damage.get(m)]
    if matchup:
        parts.append("## Type matchups (defending)\n\n" + "\n".join(matchup))
    if evolutions:
        parts.append("## Evolution\n\n" + "\n".join(f"- {line}" for line in evolutions))
    if len(entries) > 1:
        parts.append("## Pokédex entries\n\n" + "\n".join(f"- {e}" for e in entries[1:MAX_ENTRIES]))
    forms = []
    for v in varieties:
        vtypes = "/".join(t["type"]["name"].capitalize() for t in sorted(v["types"], key=lambda t: t["slot"]))
        forms.append(f"- {title_case(v['name'])}: {vtypes}")
    if forms:
        parts.append("## Other forms\n\n" + "\n".join(forms))

    return Document(series=SERIES, series_title=SERIES_TITLE, kind="pokemon", title=name,
                    display_title=f"{name} (#{number:04d})", source_url=f"https://pokeapi.co/api/v2/pokemon-species/{number}/",
                    revision_id=0, number=number, facts=facts,
                    mentions=[n for n in chain_species(chain["chain"], names) if n != name] if chain else [],
                    body="\n\n".join(parts), license=LICENSE)


def chain_position(node: dict, species: str, stage: int = 1) -> tuple[int, bool] | None:
    """Where a species sits in its evolution chain: (stage, 1 = first; whether it evolves no
    further). None if it isn't in the chain. Called by: pokemon_rows(); tests
    """
    if node["species"]["name"] == species:
        return stage, not node.get("evolves_to")
    for nxt in node.get("evolves_to", []):
        found = chain_position(nxt, species, stage + 1)
        if found:
            return found
    return None


def pokemon_rows(species: dict, pokemon: dict, chain: dict | None, chart: dict[str, dict[str, float]],
                 names: dict[str, str], varieties: list[dict], abilities_en: dict[str, str]) -> list[dict]:
    """The species as rows of the Pokémon table (infrastructure/pokemon_db.py): its default form,
    then its other forms (Mega, Alolan...) flagged with "form". Each row: number, name, types,
    generation, status, stage, stats, abilities, size, and its defending matchups {type: multiplier}.

    Called by: scripts/add_pokedex.py; tests
    """
    name = (_english(species.get("names", []), "name") or title_case(species["name"]))
    name = name.replace("♀", " (female)").replace("♂", " (male)")
    gen_key = (species.get("generation") or {}).get("name", "")
    generation = list(GENERATIONS).index(gen_key) + 1 if gen_key in GENERATIONS else None
    stage, final = (chain_position(chain["chain"], species["name"]) if chain else None) or (1, True)
    base = {
        "number": species["id"], "species": name, "generation": generation,
        "category": _english(species.get("genera", []), "genus"),
        "legendary": bool(species.get("is_legendary")), "mythical": bool(species.get("is_mythical")),
        "baby": bool(species.get("is_baby")), "stage": stage, "fully_evolved": final,
        "evolves_from": names.get((species.get("evolves_from_species") or {}).get("name", ""), ""),
        "egg_groups": ", ".join(title_case(g["name"]) for g in species.get("egg_groups", [])),
    }
    rows = []
    for p, form in [(pokemon, "")] + [(v, title_case(v["name"])) for v in varieties]:
        types = [t["type"]["name"] for t in sorted(p["types"], key=lambda t: t["slot"])]
        stats = {s["stat"]["name"]: s["base_stat"] for s in p["stats"]}
        abilities = sorted(p["abilities"], key=lambda a: a["slot"])
        en = lambda a: abilities_en.get(a["ability"]["name"], title_case(a["ability"]["name"]))  # noqa: E731
        matchups = {}
        for mult, attackers in defenses(types, chart).items():
            for a in attackers:
                matchups[a] = mult
        rows.append({
            **base, "name": form or name, "form": form,
            "type1": types[0], "type2": types[1] if len(types) > 1 else "",
            "hp": stats.get("hp", 0), "attack": stats.get("attack", 0), "defense": stats.get("defense", 0),
            "sp_attack": stats.get("special-attack", 0), "sp_defense": stats.get("special-defense", 0),
            "speed": stats.get("speed", 0), "total": sum(stats.values()),
            "height_m": p["height"] / 10, "weight_kg": p["weight"] / 10,
            "abilities": ", ".join(en(a) for a in abilities if not a["is_hidden"]),
            "hidden_ability": ", ".join(en(a) for a in abilities if a["is_hidden"]),
            "matchups": matchups,
        })
    return rows
