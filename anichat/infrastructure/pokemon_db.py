"""The Pokémon table: every species (and, flagged, its other forms) with types, generation, status,
evolution stage, base stats, size, abilities and defending matchups, in SQLite
(data/pokemon.sqlite). Rebuilt by scripts/add_pokedex.py from the PokéAPI cache.

Tables:
    pokemon(id, number, name, species, form, generation, type1, type2, category, legendary, mythical,
            baby, stage, fully_evolved, evolves_from, egg_groups, hp, attack, defense, sp_attack,
            sp_defense, speed, total, height_m, weight_kg, abilities, hidden_ability)
    matchups(pokemon_id, attacking, multiplier)    only multipliers other than 1
"""

import sqlite3
from pathlib import Path

from anichat.domain.pokemon_query import STATS, PokemonQuery

COLUMNS = ("number", "name", "species", "form", "generation", "type1", "type2", "category", "legendary", "mythical",
           "baby", "stage", "fully_evolved", "evolves_from", "egg_groups", "hp", "attack", "defense", "sp_attack",
           "sp_defense", "speed", "total", "height_m", "weight_kg", "abilities", "hidden_ability")
SCHEMA = f"""
CREATE TABLE pokemon (id INTEGER PRIMARY KEY, {', '.join(COLUMNS)});
CREATE TABLE matchups (pokemon_id INTEGER, attacking TEXT, multiplier REAL);
CREATE INDEX matchup_type ON matchups (attacking, multiplier);
"""
NAMED_GROUP = 10  # counted groups this small also list their Pokémon


class PokemonDB:
    """Created by: scripts/add_pokedex.py (rebuild), anichat/container.py (queries)
    Used by:    application/pokemon_questions.py  PokemonQuestions
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def exists(self) -> bool:
        """Whether the table has been built. Called by: PokemonQuestions"""
        return self.path.exists()

    def rebuild(self, rows: list[dict]) -> int:
        """Replace the table with these rows (domain/pokedex.py pokemon_rows), swapped in whole.

        Called by: scripts/add_pokedex.py  main()
        """
        tmp = self.path.with_suffix(".tmp")
        tmp.unlink(missing_ok=True)
        db = sqlite3.connect(tmp)
        try:
            db.executescript(SCHEMA)
            for i, row in enumerate(rows, 1):
                db.execute(f"INSERT INTO pokemon VALUES (?, {', '.join('?' * len(COLUMNS))})", [i, *(row[c] for c in COLUMNS)])
                db.executemany("INSERT INTO matchups VALUES (?, ?, ?)", [(i, t, m) for t, m in row["matchups"].items()])
            db.commit()
        finally:
            db.close()
        tmp.replace(self.path)
        return len(rows)

    def run(self, q: PokemonQuery) -> tuple[list[dict], int]:
        """The rows matching the query (at most q.limit, sorted as asked) and how many match, or with
        count_by: [{"group", "count"}] and the number of groups.

        Only whitelisted SQL is built; values from the question are bound parameters.
        Called by: application/pokemon_questions.py  PokemonQuestions.source()
        """
        where, params = [], []
        if not q.include_forms:
            where.append("p.form = ''")
        for t in q.types:
            where.append("(p.type1 = ? OR p.type2 = ?)")
            params += [t, t]
        if q.single_type is True:
            where.append("p.type2 = ''")
        elif q.single_type is False:
            where.append("p.type2 != ''")
        for t in q.exclude_types:
            where.append("p.type1 != ? AND p.type2 != ?")
            params += [t, t]
        if q.generation:
            where.append("p.generation = ?")
            params.append(q.generation)
        if q.generation_from:
            where.append("p.generation >= ?")
            params.append(q.generation_from)
        if q.generation_to:
            where.append("p.generation <= ?")
            params.append(q.generation_to)
        if q.status == "regular":
            where.append("NOT p.legendary AND NOT p.mythical AND NOT p.baby")
        elif q.status:
            where.append(f"p.{q.status}")  # a column name from STATUSES (checked by parse_query)
        if q.fully_evolved is not None:
            where.append("p.fully_evolved = ?")
            params.append(int(q.fully_evolved))
        for attacking, condition in ((q.weak_to, "m.multiplier >= 4" if q.weak_x4 else "m.multiplier >= 2"),
                                     (q.resists, "m.multiplier <= 0.5"), (q.immune_to, "m.multiplier = 0")):
            if attacking:
                where.append(f"EXISTS (SELECT 1 FROM matchups m WHERE m.pokemon_id = p.id AND m.attacking = ? AND {condition})")
                params.append(attacking)
        for column, value in (("p.name", q.name), ("p.abilities || ', ' || p.hidden_ability", q.ability),
                              ("p.egg_groups", q.egg_group)):
            if value:
                where.append(f"lower({column}) LIKE ?")
                params.append(f"%{value.lower()}%")
        for r in q.stat_ranges:  # stat names come from STATS (checked by parse_query)
            if r.min is not None:
                where.append(f"p.{r.stat} >= ?")
                params.append(r.min)
            if r.max is not None:
                where.append(f"p.{r.stat} <= ?")
                params.append(r.max)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            if q.count_by:
                # A typing ignores order: Steel/Ground (Steelix) and Ground/Steel (Excadrill) are one.
                group = {"generation": "p.generation", "type_combination":
                         "CASE WHEN p.type2 = '' THEN p.type1 WHEN p.type1 < p.type2 THEN p.type1 || '/' || p.type2 "
                         "ELSE p.type2 || '/' || p.type1 END"}.get(q.count_by)
                having = "HAVING count(*) = ?" if q.count_equals else ""
                extra = [q.count_equals] if q.count_equals else []
                if q.count_by == "type":  # each Pokémon counts once for each of its types
                    sql = (f"SELECT t AS grp, count(*) AS n, group_concat(name, ', ') AS names FROM ("
                           f"SELECT p.type1 AS t, p.name FROM pokemon p {clause} UNION ALL SELECT p.type2, p.name "
                           f"FROM pokemon p {clause}{' AND' if clause else ' WHERE'} p.type2 != '') "
                           f"GROUP BY t {having} ORDER BY n DESC")
                    rows = db.execute(sql, params + params + extra).fetchall()
                else:
                    rows = db.execute(f"SELECT {group} AS grp, count(*) AS n, group_concat(p.name, ', ') AS names "
                                      f"FROM pokemon p {clause} GROUP BY grp {having} "
                                      f"ORDER BY {'grp' if q.count_by == 'generation' else 'n DESC, grp'}",
                                      params + extra).fetchall()
                # Small groups name their Pokémon ("Fire/Water: Volcanion"); big ones only count.
                groups = [{"group": r["grp"], "count": r["n"], "names": r["names"] if r["n"] <= NAMED_GROUP else ""}
                          for r in rows]
                return groups, len(groups)
            sort = f"p.{q.sort_by}" if q.sort_by in STATS else "p.number"
            order = "DESC" if (q.sort_by and q.order == "desc") else "ASC"
            total = db.execute(f"SELECT count(*) FROM pokemon p {clause}", params).fetchone()[0]
            rows = [dict(r) for r in db.execute(f"SELECT p.* FROM pokemon p {clause} ORDER BY {sort} {order}, p.number, p.id "
                                                "LIMIT ?", [*params, q.limit])]
            for row in rows:
                row["weak"] = [(r["attacking"], r["multiplier"]) for r in db.execute(
                    "SELECT attacking, multiplier FROM matchups WHERE pokemon_id = ? AND multiplier >= 2 "
                    "ORDER BY multiplier DESC, attacking", (row["id"],))]
            return rows, total
        finally:
            db.close()
