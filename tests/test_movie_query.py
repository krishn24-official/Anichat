"""Tests for questions answered from the movies table (no network: a fake chat model)."""

from anichat.application.movie_questions import MovieQuestions, results_text
from anichat.domain.llm import ModelReply
from anichat.domain.movie_query import MovieQuery, describe_query, looks_structured, parse_query
from anichat.infrastructure.movie_db import MovieDB

FIELDS = [
    {"id": "india_net_collection", "label": "India net collection", "type": "money", "currency": "INR", "unit": "crore"},
    {"id": "worldwide_gross_collection", "label": "Worldwide gross collection", "type": "money", "currency": "INR", "unit": "crore"},
    {"id": "india_net_collection_day_wise", "label": "India net collection (day-wise)", "type": "daywise",
     "currency": "INR", "unit": "crore"},
    {"id": "ott_platform", "label": "OTT platform", "type": "list"},
]


def movie(id, title, year, net, cast, directors, days=None, deleted=False):
    values = {"india_net_collection": net, "ott_platform": ["Prime Video"]}
    if days:
        values["india_net_collection_day_wise"] = [{"label": f"Day {i}", "value": v} for i, v in enumerate(days, 1)]
    return {"id": id, "title": title, "year": year, "release_date": f"{year}-08-15", "runtime": 150, "language": "Hindi",
            "genres": ["Action"], "collection": "Ramayana Collection" if "Ramayana" in title else "",
            "companies": ["T-Series Films"] if title == "Animal" else ["Maddock Films"], "cast": [{"name": n, "character": c} for n, c in cast], "directors": directors,
            "writers": [], "producers": [], "music": [], "values": values, "deleted": deleted}


RECORDS = [
    movie("m1", "Ramayana: Rise of a Legend", 2026, 440, [("Ranbir Kapoor", "Rama"), ("Yash", "Ravana")], ["Nitesh Tiwari"],
          days=[64.85, 48.05, 69.8]),
    movie("m2", "Animal", 2023, 553.87, [("Ranbir Kapoor", "Ranvijay")], ["Sandeep Reddy Vanga"]),
    movie("m3", "Stree 2", 2024, 597.99, [("Rajkummar Rao", "Vicky")], ["Amar Kaushik"]),
    movie("m4", "Deleted Film", 2024, 9999, [("Ranbir Kapoor", "x")], [], deleted=True),
]


def db(tmp_path):
    d = MovieDB(tmp_path / "movies.sqlite")
    assert d.rebuild(RECORDS, FIELDS) == 3  # the deleted one is left out
    return d


def test_only_questions_about_many_movies_or_numbers_go_to_the_table():
    for q in ("Which movie earned the most?", "Top 5 Hindi films of 2024", "Ranbir Kapoor's movies by collection",
              "How much did Ramayana make in days 1 to 3?", "What was the opening day collection of Animal?",
              "How much did Ramayana collect in its first 3 days?", "Its 10-day total?"):
        assert looks_structured(q), q
    for q in ("Who played Ravana in Ramayana?", "What is Ramayana about?", "Who is Naruto?"):
        assert not looks_structured(q), q


def test_the_models_plan_keeps_only_known_fields_and_options():
    q = parse_query('Sure! {"query": {"sort_by": "india_net_collection", "order": "asc", "limit": 99, "role": "hero", '
                    '"person": "Ranbir%", "year": "2024"}}', FIELDS)
    assert q == MovieQuery(sort_by="india_net_collection", order="asc", limit=10, person="Ranbir", year=2024)
    assert parse_query('{"query": {"sort_by": "box_office; DROP TABLE movies"}}', FIELDS) is None  # unknown field: nothing left
    assert parse_query('{"query": null}', FIELDS) is None
    assert parse_query("I think the answer is Stree 2", FIELDS) is None
    assert parse_query('{"query": {"days_field": "ott_platform"}}', FIELDS) is None  # not a day-wise field


def test_the_table_ranks_filters_and_adds_up_days(tmp_path):
    d = db(tmp_path)
    rows, total, _ = d.run(MovieQuery(sort_by="india_net_collection", limit=2))
    assert [r["title"] for r in rows] == ["Stree 2", "Animal"] and total == 3
    rows, total, _ = d.run(MovieQuery(person="ranbir", role="cast", sort_by="india_net_collection"))
    assert [r["title"] for r in rows] == ["Animal", "Ramayana: Rise of a Legend"] and total == 2
    assert rows[1]["person_roles"] == ["Ranbir Kapoor: cast (Rama)"]
    rows, _, _ = d.run(MovieQuery(title="ramayana", days_field="india_net_collection_day_wise", days_from=2, days_to=3))
    assert rows[0]["days_sum"] == 117.85 and [label for label, _ in rows[0]["days"]] == ["Day 2", "Day 3"]
    rows, total, _ = d.run(MovieQuery(year_from=2024, sort_by="year", order="asc"))
    assert [r["title"] for r in rows] == ["Stree 2", "Ramayana: Rise of a Legend"] and total == 2


def test_results_read_like_a_source(tmp_path):
    q = MovieQuery(person="Ranbir Kapoor", role="cast", sort_by="india_net_collection")
    rows, total, _ = db(tmp_path).run(q)
    text = results_text(q, rows, total, FIELDS)
    assert text.startswith("Movies table › Movies with Ranbir Kapoor (cast), sorted by India net collection, highest first")
    assert "1. Animal (2023) | India net collection: ₹553.87 crore | Ranbir Kapoor: cast (Ranvijay)" in text
    assert "OTT platform: Prime Video" in text and "directed by Nitesh Tiwari" in text
    assert describe_query(MovieQuery(year=2024), {}) == "Movies from 2024"


class FakeModel:
    name = "fake"

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def complete(self, messages):
        self.calls += 1
        return ModelReply(self.reply, "fake")


def test_the_table_becomes_the_first_source_only_when_it_helps(tmp_path):
    d = db(tmp_path)
    plan = FakeModel('{"query": {"sort_by": "india_net_collection", "limit": 3}}')
    chunk, seconds = MovieQuestions(d, plan).source("Which movie earned the most in India?", None)
    assert chunk is not None and chunk.title == "Movies table" and "1. Stree 2 (2024)" in chunk.text and seconds >= 0
    # Not that kind of question, another series, or no table yet: the model isn't even asked.
    quiet = FakeModel('{"query": {"sort_by": "india_net_collection"}}')
    assert MovieQuestions(d, quiet).source("Who played Ravana?", None)[0] is None
    assert MovieQuestions(d, quiet).source("Which movie earned the most?", "naruto")[0] is None
    assert MovieQuestions(MovieDB(tmp_path / "none.sqlite"), quiet).source("Which movie earned the most?", None)[0] is None
    assert quiet.calls == 0
    assert MovieQuestions(d, FakeModel('{"query": null}')).source("Which movie is the best?", None)[0] is None


def test_a_franchise_matches_series_studio_or_title_and_an_empty_sort_field_still_lists(tmp_path):
    from anichat.infrastructure.movie_db import franchise_words

    d = db(tmp_path)
    assert franchise_words("The Fast & Furious movies") == ["fast", "furious"]
    rows, total, note = d.run(MovieQuery(franchise="Maddock Films", sort_by="india_net_collection"))
    assert [r["title"] for r in rows] == ["Stree 2", "Ramayana: Rise of a Legend"] and total == 2 and note == ""
    rows, total, _ = d.run(MovieQuery(franchise="ramayana series"))
    assert [r["title"] for r in rows] == ["Ramayana: Rise of a Legend"]
    # Nobody has a worldwide gross: the matches are still listed, with a note saying why unsorted.
    rows, total, note = d.run(MovieQuery(franchise="maddock", sort_by="worldwide_gross_collection"))
    assert total == 2 and "none of them has a value" in note
    filled = {f["id"]: f["filled"] for f in d.fields()}
    assert filled["india_net_collection"] == 3 and filled["worldwide_gross_collection"] == 0 and filled["india_net_collection_day_wise"] == 1
