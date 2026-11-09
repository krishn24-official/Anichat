"""Tests for the exact name/alias/title lookup (pure)."""

from anichat.domain.chunking import Chunk
from anichat.domain.entities_lookup import build_phrase_index, card_phrases, lookup


def card(title, text):
    return Chunk(f"ds:character:{title}:card", f"Series › {title} › Profile\n\n{text}", "demon_slayer",
                 "character", title, title, "Profile", None, "u", [])


AKAZA = card("Akaza", "Akaza is a demon affiliated with the Twelve Kizuki, who held the position of Upper Rank Three.\n"
                      "Alias: Hakuji (Human)\nAffiliation: Twelve Kizuki")
TENGEN = card("Tengen Uzui", "Tengen Uzui is a Demon Slayer.\nOccupation: Shinobi (Formerly) ; Sound Hashira (Formerly)")
DOMA = card("Doma", "Doma is a demon of the Twelve Kizuki, Upper Rank Two.\nAffiliation: Twelve Kizuki")
GYOKKO = card("Gyokko", "Gyokko is a demon of the Twelve Kizuki, Upper Rank Five.\nAffiliation: Twelve Kizuki")


def test_phrases_come_from_names_aliases_occupations_and_titles():
    assert {"akaza", "hakuji", "upper rank three", "twelve kizuki"} <= card_phrases(AKAZA)
    assert {"tengen uzui", "tengen", "sound hashira", "shinobi"} <= card_phrases(TENGEN)
    assert "formerly" not in card_phrases(TENGEN)


def test_lookup_finds_distinctive_titles_and_ignores_shared_ones():
    index = build_phrase_index([AKAZA, TENGEN, DOMA, GYOKKO])
    assert "twelve kizuki" not in index  # on three pages: identifies no one
    assert [c.title for c in lookup("Who is Upper Rank Three?", index)] == ["Akaza"]
    assert [c.title for c in lookup("Who is the sound hashira?", index)] == ["Tengen Uzui"]
    assert lookup("Who are the Twelve Kizuki?", index) == []


def test_aliases_from_any_field_name_without_bracketed_qualifiers():
    from anichat.domain.chunking import SourceDocument, chunk_document

    meta = {"series": "death_note", "series_title": "Death Note", "kind": "character", "title": "Light Yagami",
            "display_title": "Light Yagami", "source": "u", "mentions": [],
            "facts": {"aka": "[The First] Kira; L-Kira; God (by Teru Mikami)", "species": "Human"}}
    body = "# Light Yagami\n\nLight Yagami is the main protagonist of the Death Note series and a top student."
    card = chunk_document(SourceDocument(meta, body))[0]
    assert "Alias: [The First] Kira; L-Kira" in card.text
    assert {"kira", "l-kira"} <= card_phrases(card) and "god" not in card_phrases(card)  # too short to identify anyone
    assert [c.title for c in lookup("Who is Kira?", build_phrase_index([card]))] == ["Light Yagami"]


def test_an_ambiguous_name_resolves_to_the_most_linked_page():
    from dataclasses import replace

    def kira(title, importance):
        return replace(card(title, f"{title} is a person.\nAlias: Kira"), importance=importance)

    index = build_phrase_index([kira("Light Yagami", 300), kira("Kyosuke Higuchi", 40), kira("Minoru Tanaka", 3)])
    assert [c.title for c in lookup("Who is Kira?", index)] == ["Light Yagami"]


def test_the_page_named_by_the_phrase_beats_a_more_linked_alias():
    from dataclasses import replace

    eren = replace(card("Eren Yeager", "Eren Yeager is the protagonist.\nAlias: Founding Titan; Attack Titan"), importance=300)
    founding = replace(card("Founding Titan", "The Founding Titan is one of the Nine Titans."), importance=90)
    index = build_phrase_index([eren, founding])
    assert lookup("What is the Founding Titan?", index, limit=1)[0].title == "Founding Titan"


def test_what_the_first_sentence_says_an_entity_is_identifies_it():
    hiruzen = card("Hiruzen Sarutobi", "Hiruzen Sarutobi was the Third Hokage of Konohagakure.")
    konohamaru = card("Konohamaru Sarutobi", "Konohamaru is a shinobi. He is the grandson of the Third Hokage.")
    asuma = card("Asuma Sarutobi", "Asuma is a jōnin, the son of the Third Hokage.")
    index = build_phrase_index([hiruzen, konohamaru, asuma])
    assert [c.title for c in lookup("Who is the Third Hokage?", index)] == ["Hiruzen Sarutobi"]


def test_a_qualified_title_does_not_beat_the_main_holder_of_a_name():
    from dataclasses import replace

    obito = replace(card("Obito Uchiha", "Obito Uchiha was a shinobi.\nAlias: Tobi; Masked Man"), importance=120)
    zetsu = replace(card("Tobi (Zetsu)", "Tobi was a White Zetsu."), importance=15)
    assert lookup("Who is Tobi?", build_phrase_index([obito, zetsu]), limit=1)[0].title == "Obito Uchiha"
