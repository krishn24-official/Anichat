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
