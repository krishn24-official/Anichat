"""Tests for knowledge from the admin form: movie records and free entries (no network)."""

import pytest

from anichat.application.added_data import AddedDataService, AddedStore, RecordSync
from anichat.domain.added import parse_submission
from anichat.domain.chunking import chunk_document
from anichat.domain.records import format_value, parse_fields, record_document, tmdb_record
from anichat.infrastructure.document_store import DocumentStore, parse_markdown
from anichat.domain.documents import to_markdown
from scripts.add_movie import best_match

FIELDS = parse_fields([
    {"id": "india_net", "label": "India net collection", "type": "money", "group": "Box office", "currency": "INR",
     "unit": "crore", "order": 0},
    {"id": "budget_usd", "label": "Budget (USD)", "type": "money", "group": "Box office", "currency": "USD", "unit": "", "order": 1},
    {"id": "india_net_daywise", "label": "India net collection (day-wise)", "type": "daywise", "group": "Box office",
     "currency": "INR", "unit": "crore", "order": 2},
    {"id": "ott_platform", "label": "OTT platform", "type": "list", "group": "Streaming", "order": 3},
    {"id": "verdict", "label": "Box office verdict", "type": "text", "group": "Box office", "order": 4, "archived": True},
])

STREE = {
    "id": "tmdb-1", "type": "movie", "tmdb_id": 1, "title": "Stree 2", "original_title": "", "year": 2024,
    "release_date": "2024-08-15", "runtime": 147, "genres": ["Comedy", "Horror"], "language": "Hindi",
    "overview": "The town of Chanderi is haunted again.", "tagline": "", "directors": ["Amar Kaushik"],
    "writers": ["Niren Bhatt"], "producers": [], "music": ["Sachin–Jigar"],
    "cast": [{"name": "Rajkummar Rao", "character": "Vicky"}, {"name": "Shraddha Kapoor", "character": "Stree"},
             {"name": "Pankaj Tripathi", "character": "Rudra"}],
    "values": {"india_net": 597.99, "budget_usd": 7000000, "ott_platform": ["Prime Video"], "verdict": "All-time blockbuster",
               "india_net_daywise": [{"label": "Day 1 [1st Thursday]", "value": 55.4}, {"label": "Day 2", "value": 35.3}]},
    "notes": "Biggest Hindi horror comedy.", "sources": ["https://www.sacnilk.com/x"], "version": 3,
}


def test_values_are_shown_like_the_form_shows_them():
    assert format_value(FIELDS["india_net"], 597.99) == "₹597.99 crore"
    assert format_value(FIELDS["india_net"], 600.0) == "₹600 crore"
    assert format_value(FIELDS["budget_usd"], 140000000) == "$140,000,000"
    assert format_value(FIELDS["ott_platform"], ["Prime Video", "JioHotstar"]) == "Prime Video, JioHotstar"


def test_a_record_becomes_a_document_with_its_numbers_cast_and_day_wise_table():
    doc = record_document(STREE, FIELDS)
    assert doc.title == "Stree 2 (2024)" and doc.kind == "movie" and doc.series == "movies" and doc.revision_id == 3
    assert doc.facts["India net collection"] == "₹597.99 crore" and doc.facts["OTT platform"] == "Prime Video"
    assert doc.facts["Box office verdict"] == "All-time blockbuster"  # archived field: its value is kept
    assert doc.facts["starring"] == "Rajkummar Rao, Shraddha Kapoor, Pankaj Tripathi"
    assert doc.body.startswith("Stree 2 (2024) is a 2024 Hindi film directed by Amar Kaushik, starring Rajkummar Rao, "
                               "Shraddha Kapoor and Pankaj Tripathi.")
    assert "- Shraddha Kapoor as Stree" in doc.body and "## Streaming\n\n- OTT platform: Prime Video" in doc.body
    assert "## India net collection (day-wise)\n\n- Day 1 [1st Thursday]: ₹55.4 crore" in doc.body
    assert "## Notes\n\nBiggest Hindi horror comedy." in doc.body
    chunks = chunk_document(parse_markdown(to_markdown(doc)))
    assert any("₹597.99 crore" in c.text for c in chunks) and any("Shraddha Kapoor as Stree" in c.text for c in chunks)
    assert "**OTT platform:** Prime Video" in to_markdown(doc)


def test_sync_adds_edits_renames_and_removes_movies(tmp_path):
    store = AddedStore(tmp_path)
    sync = RecordSync(store)
    done = sync.sync([STREE], FIELDS, synced={})
    assert [what for _, what in done] == ["added"]
    assert (tmp_path / "movies" / "movie" / "stree_2_2024.md").exists()

    # Nothing changed since: nothing to do.
    assert sync.sync([STREE], FIELDS, synced={"tmdb-1": 3}) == []

    # A re-release changes the collection and an actor is added: the same page is rebuilt.
    edited = {**STREE, "version": 4, "values": {**STREE["values"], "india_net": 627.5},
              "cast": STREE["cast"] + [{"name": "Abhishek Banerjee", "character": "Jana"}]}
    assert [what for _, what in sync.sync([edited], FIELDS, synced={"tmdb-1": 3})] == ["updated"]
    page = store.get("movies", "movie", "Stree 2 (2024)")
    assert page.facts["India net collection"] == "₹627.5 crore" and "Abhishek Banerjee as Jana" in page.body

    # The year was wrong: the page moves to its new title.
    renamed = {**edited, "version": 5, "year": 2025}
    sync.sync([renamed], FIELDS, synced={"tmdb-1": 4})
    assert store.get("movies", "movie", "Stree 2 (2024)") is None and store.get("movies", "movie", "Stree 2 (2025)")
    assert not (tmp_path / "movies" / "movie" / "stree_2_2024.md").exists()

    # Deleted in the form: gone.
    assert [what for _, what in sync.sync([{**renamed, "version": 6, "deleted": True}], FIELDS, synced={"tmdb-1": 5})] == ["removed"]
    assert store.get("movies", "movie", "Stree 2 (2025)") is None
    assert list(DocumentStore(tmp_path).iter_documents("movies")) == []


def test_a_tmdb_movie_becomes_a_record_like_the_form_makes():
    movie = {"id": 1726, "title": "Iron Man", "original_title": "Iron Man", "release_date": "2008-04-30", "runtime": 126,
             "budget": 140000000, "revenue": 585174222, "original_language": "en",
             "spoken_languages": [{"iso_639_1": "en", "english_name": "English"}], "genres": [{"name": "Action"}],
             "credits": {"cast": [{"name": "Robert Downey Jr.", "character": "Tony Stark"}],
                         "crew": [{"name": "Jon Favreau", "job": "Director"}, {"name": "Jon Favreau", "job": "Director"}]}}
    r = tmdb_record(movie, {"budget_usd"})
    assert r["id"] == "tmdb-1726" and r["year"] == 2008 and r["language"] == "English" and r["original_title"] == ""
    assert r["directors"] == ["Jon Favreau"] and r["values"] == {"budget_usd": 140000000}  # no worldwide_gross_usd field
    assert record_document({**r, "version": 1}, FIELDS).facts["Budget (USD)"] == "$140,000,000"
    assert best_match([{"title": "Iron Man 2", "popularity": 90}, {"title": "Iron Man", "popularity": 50}], "iron man")["title"] == "Iron Man"


def test_free_entries_are_validated():
    sub = parse_submission({"id": "a1", "type": "anime", "series": "Naruto", "title": " Naruto Uzumaki ",
                            "facts": {"Hindi dub ": "Sonal Kaushal", "empty": " "}})
    assert sub.series == "naruto" and sub.facts == {"hindi dub": "Sonal Kaushal"}
    for bad, reason in [({"type": "song", "title": "x", "notes": "y"}, "unknown type"),
                        ({"type": "anime", "title": "", "notes": "y"}, "missing title"),
                        ({"type": "anime", "title": "Naruto", "notes": "y"}, "missing series"),
                        ({"type": "anime", "title": "Naruto", "series": "naruto"}, "nothing to add")]:
        with pytest.raises(ValueError, match=reason):
            parse_submission(bad)


def test_entries_for_a_series_merge_and_are_chunked_with_its_wiki_pages(tmp_path):
    svc = AddedDataService(AddedStore(tmp_path / "added"), {"naruto": "Naruto"})
    svc.apply({"id": "1", "type": "anime", "series": "naruto", "title": "Naruto Uzumaki",
               "facts": {"favourite food": "Ichiraku ramen"}, "notes": "Naruto's favourite food is ramen."})
    doc, message = svc.apply({"id": "2", "type": "anime", "series": "naruto", "title": "Naruto Uzumaki",
                              "facts": {"dream": "Become Hokage"}})
    assert doc.kind == "added" and set(doc.facts) == {"favourite food", "dream"} and "updated" in message
    with pytest.raises(ValueError, match="unknown series"):
        svc.apply({"id": "3", "type": "anime", "series": "pokemon", "title": "Pikachu", "notes": "x"})
    wiki = tmp_path / "documents" / "naruto" / "character"
    wiki.mkdir(parents=True)
    wiki.joinpath("naruto_uzumaki.md").write_text('---\nseries: "naruto"\nkind: "character"\ntitle: "Naruto Uzumaki"\n'
                                                  'display_title: "Naruto Uzumaki"\n---\n\nWiki text.', encoding="utf-8")
    docs = list(DocumentStore(tmp_path / "documents", tmp_path / "added").iter_documents("naruto"))
    assert sorted(d.meta["kind"] for d in docs) == ["added", "character"]
    assert any("Ichiraku ramen" in c.text for d in docs if d.meta["kind"] == "added" for c in chunk_document(d))
    assert len({c.id for d in docs for c in chunk_document(d)}) == sum(len(chunk_document(d)) for d in docs)
