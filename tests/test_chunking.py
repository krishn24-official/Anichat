"""Tests for stage 3 chunking (pure functions, no files)."""

from anichat.domain.chunking import MAX_CHARS, SourceDocument, chunk_document, split_text
from anichat.infrastructure.document_store import parse_markdown

META = {
    "series": "demon_slayer", "series_title": "Demon Slayer", "kind": "character",
    "title": "Tanjiro Kamado", "display_title": "Tanjiro Kamado", "number": None,
    "source": "https://w/wiki/Tanjiro_Kamado", "mentions": ["Nezuko Kamado", "Giyu Tomioka", "Demon Slayer Corps"],
}
BODY = """# Tanjiro Kamado

*Demon Slayer* · Source: [Tanjiro Kamado](https://w/wiki/Tanjiro_Kamado) (CC BY-SA 3.0)

Tanjiro is a kind boy who protects his sister Nezuko.

## Abilities

### Breathing Style

""" + "Tanjiro uses Water Breathing taught by Sakonji. " * 60 + """

### Equipment

A black Nichirin sword.

## Relationships

Giyu Tomioka spared Nezuko.
"""


def test_chunks_follow_headings_and_carry_their_location():
    chunks = chunk_document(SourceDocument(META, BODY))
    assert chunks[1].text.startswith("Demon Slayer › Tanjiro Kamado\n\nTanjiro is a kind boy")  # [0] is the profile card
    assert "Source:" not in chunks[1].text  # credit line is metadata, not content
    breathing = [c for c in chunks if c.section == "Abilities › Breathing Style"]
    assert len(breathing) >= 2  # long section split
    assert all(c.text.startswith("Demon Slayer › Tanjiro Kamado › Abilities › Breathing Style") for c in breathing)
    assert all(len(c.text) <= MAX_CHARS for c in chunks)  # location line included in the budget


def test_tiny_sections_merge_into_the_previous_chunk_and_ids_are_stable():
    chunks = chunk_document(SourceDocument(META, BODY))
    assert not any(c.section.endswith("Equipment") for c in chunks)  # merged...
    assert any("Equipment: A black Nichirin sword." in c.text for c in chunks)  # ...with its label
    assert [c.id for c in chunks] == [c.id for c in chunk_document(SourceDocument(META, BODY))]
    assert chunks[1].id == "demon_slayer:character:Tanjiro Kamado:0"


def test_mentions_are_per_chunk_including_first_names():
    chunks = chunk_document(SourceDocument(META, BODY))
    assert "Nezuko Kamado" in chunks[1].mentions  # "Nezuko" in the intro
    assert "Giyu Tomioka" not in chunks[1].mentions
    assert "Demon Slayer Corps" not in chunks[1].mentions  # three-word name: full name only


def test_split_text_overlaps_and_respects_the_limit():
    text = " ".join(f"Sentence {i} is here." for i in range(300))
    parts = split_text(text, target=400, limit=500)
    assert all(len(p) <= 500 for p in parts) and len(parts) > 5
    assert parts[1].split(". ")[0] in parts[0]  # one sentence of overlap
    assert split_text("short") == ["short"]


def test_front_matter_round_trip_and_hand_written_values():
    doc = parse_markdown('---\nseries: "demon_slayer"\nnumber: 5\nkind: character\n---\n\n# Body')
    assert doc.meta == {"series": "demon_slayer", "number": 5, "kind": "character"}  # plain YAML value accepted
    assert doc.body == "# Body"


def test_entity_pages_get_a_short_profile_card():
    meta = {**META, "facts": {"affiliation": "Demon Slayer Corps", "height": "165 cm"}}
    chunks = chunk_document(SourceDocument(meta, BODY))
    card = chunks[0]
    assert card.id == "demon_slayer:character:Tanjiro Kamado:card" and card.section == "Profile"
    assert card.text.startswith("Demon Slayer › Tanjiro Kamado › Profile\n\nTanjiro is a kind boy")
    assert "Affiliation: Demon Slayer Corps" in card.text and "165 cm" not in card.text
    chapter = chunk_document(SourceDocument({**META, "kind": "chapter"}, BODY))
    assert not any(c.id.endswith(":card") for c in chapter)  # only entity pages get cards


def test_people_killed_lists_become_killed_by_facts_on_the_victims():
    from anichat.domain.chunking import SourceDocument, killers_by_victim

    def doc(title, body):
        return SourceDocument({"title": title}, body)

    mikasa = doc("Mikasa Ackerman", "Intro.\n\n## People killed\n\n- Floch Forster\n- Eren Yeager\n- One robber\n\n"
                                    "### Failed attempts\n\n- Reiner Braun\n\n## Trivia\n\n- Eren Yeager")
    docs = [mikasa, doc("Eren Yeager", "x"), doc("Floch Forster", "x"), doc("Reiner Braun", "x")]
    assert killers_by_victim(docs) == {"Floch Forster": ["Mikasa Ackerman"], "Eren Yeager": ["Mikasa Ackerman"]}


def test_parents_facts_give_the_parents_a_children_fact():
    from anichat.domain.chunking import SourceDocument, children_by_parent

    naruto = SourceDocument({"title": "Naruto Uzumaki", "facts": {"parents": "Minato Namikaze; Kushina Uzumaki"}}, "x")
    assert children_by_parent([naruto]) == {"Minato Namikaze": ["Naruto Uzumaki"], "Kushina Uzumaki": ["Naruto Uzumaki"]}
