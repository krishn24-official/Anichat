"""Build the Pokédex: one page per Pokémon species from PokéAPI (pokeapi.co, free, no key), with
national number, types, weaknesses, abilities, base stats, evolution chain and Pokédex entries.

    python -m scripts.add_pokedex                 # all species (~1,025): ~3,000 requests the first time
    python -m scripts.add_pokedex --limit 151     # only the first 151 (Kanto)

Every API answer is cached under data/raw/pokeapi/, so running again (e.g. after changing the page
layout in domain/pokedex.py) downloads nothing. The Pokémon table (data/pokemon.sqlite: lists,
rankings and counts by type, generation, stats, matchups) is rebuilt too. Pages go to data/added/pokemon/pokemon/ and are
chunked with the Pokémon wiki's anime pages (series "pokemon"): run scripts/chunk.py and
scripts/index.py (or scripts/embed.py on a GPU) for "pokemon" afterwards.
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from anichat.domain.pokedex import pokemon_document, pokemon_rows, type_chart
from anichat.infrastructure.document_store import DocumentStore
from anichat.infrastructure.pokemon_db import PokemonDB

DATA = Path(__file__).resolve().parents[1] / "data"
CACHE = DATA / "raw" / "pokeapi"
API = "https://pokeapi.co/api/v2"
WORKERS = 6  # polite: PokéAPI is free and run by volunteers
STANDARD_TYPES = 18  # type ids 1-18 (Normal ... Fairy); later ids are special ("unknown", "shadow", "stellar")


class PokeApi:
    """PokéAPI with a file cache. Created by: main()"""

    def __init__(self):
        self._http = httpx.Client(timeout=30, headers={"User-Agent": "AniChat/0.1 (personal project)"})

    def get(self, path: str) -> dict:
        """One API answer (path like "pokemon/25"), from the cache when fetched before.

        Called by: main() and its helpers
        """
        path = path.replace(API, "").strip("/")
        file = CACHE / (path.replace("/", "_").replace("?", "_") + ".json")
        if file.exists():
            return json.loads(file.read_text(encoding="utf-8"))
        for attempt in range(4):
            try:
                r = self._http.get(f"{API}/{path}")
                if r.status_code == 200:
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text(r.text, encoding="utf-8")
                    return r.json()
                if r.status_code == 404:
                    raise LookupError(f"PokéAPI has no {path}")
            except httpx.HTTPError:
                pass
            time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"PokéAPI keeps failing for {path}")

    def close(self) -> None:
        """Called by: main()"""
        self._http.close()


def main(limit: int | None) -> None:
    """Fetch everything needed, then write one document per species.

    Called by: this file's __main__ block (command line)
    """
    api = PokeApi()
    started = time.time()
    try:
        with ThreadPoolExecutor(WORKERS) as pool:
            chart = type_chart(list(pool.map(api.get, [f"type/{i}" for i in range(1, STANDARD_TYPES + 1)])))
            count = api.get("pokemon-species?limit=1")["count"]
            ids = list(range(1, min(count, limit or count) + 1))
            species = list(pool.map(lambda i: api.get(f"pokemon-species/{i}"), ids))
            print(f"{len(species)} species ({time.time() - started:.0f}s)")
            defaults = {s["id"]: next(v["pokemon"]["name"] for v in s["varieties"] if v["is_default"]) for s in species}
            pokemon = dict(zip(defaults, pool.map(lambda n: api.get(f"pokemon/{n}"), defaults.values())))
            others = {s["id"]: [v["pokemon"]["name"] for v in s["varieties"] if not v["is_default"]] for s in species}
            other_names = [n for names in others.values() for n in names]
            other_data = dict(zip(other_names, pool.map(lambda n: api.get(f"pokemon/{n}"), other_names)))
            chain_urls = sorted({s["evolution_chain"]["url"] for s in species if s.get("evolution_chain")})
            chains = dict(zip(chain_urls, pool.map(api.get, chain_urls)))
            ability_ids = sorted({a["ability"]["name"] for p in pokemon.values() for a in p["abilities"]})
            abilities = dict(zip(ability_ids, pool.map(lambda n: api.get(f"ability/{n}"), ability_ids)))
            print(f"{len(other_names)} other forms, {len(chains)} evolution chains, {len(abilities)} abilities "
                  f"({time.time() - started:.0f}s)")
    finally:
        api.close()

    names = {s["name"]: next((n["name"] for n in s["names"] if n["language"]["name"] == "en"), s["name"]) for s in species}
    abilities_en = {k: next((n["name"] for n in v["names"] if n["language"]["name"] == "en"), k) for k, v in abilities.items()}
    store = DocumentStore(DATA / "added")
    rows = []
    for s in species:
        chain = chains.get((s.get("evolution_chain") or {}).get("url", ""))
        forms = [other_data[n] for n in others[s["id"]]]
        store.save(pokemon_document(s, pokemon[s["id"]], chain, chart, names, forms, abilities_en))
        rows += pokemon_rows(s, pokemon[s["id"]], chain, chart, names, forms, abilities_en)
    print(f"{len(species)} Pokédex pages saved under {DATA / 'added' / 'pokemon'} ({time.time() - started:.0f}s)")
    if not limit:  # a partial table would answer "how many" questions wrongly
        count = PokemonDB(DATA / "pokemon.sqlite").rebuild(rows)
        print(f"{count} rows (species and their forms) in data/pokemon.sqlite")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="only the first N species (by national number)")
    main(parser.parse_args().limit)
