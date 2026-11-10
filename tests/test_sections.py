"""Tests for splitting a volume page into chapter pages (pure)."""

from anichat.domain.documents import build_document
from anichat.domain.entities import RawPage
from anichat.domain.sections import split_sections

VOLUME = """{{VolumeInfobox
|title = WHITE TOWER ROCKS
|volume = 14
}}
'''WHITE TOWER ROCKS''' is the fourteenth volume.
==Publisher's summary==
Ichigo races to save Rukia.
==Chapters==
===116. White Tower Rocks===
Ichigo and Yoruichi arrive at the Senzaikyū. Byakuya stands in their way.
===<span id="CH117">117. Remnant 2 [Deny the Shadow]</span>===
Byakuya remembers his promise to his late wife Hisana. FILLER
==Author's Notes==
Kubo comments on the cover.
""".replace("FILLER", "He fights Ichigo on the hill. " * 15)


def page(text):
    return RawPage("bleach", "chapter", "WHITE TOWER ROCKS", "https://bleach.fandom.com/wiki/WHITE_TOWER_ROCKS", 1,
                   text, "now")


def test_each_chapter_section_becomes_a_numbered_chapter_page():
    parts = split_sections(page(VOLUME))
    assert [p.title for p in parts] == ["Chapter 116", "Chapter 117"]
    assert "Byakuya stands" in parts[0].wikitext and "Hisana" not in parts[0].wikitext
    assert "Author" not in parts[1].wikitext  # a higher-level heading ends the section
    assert parts[1].url.endswith("#117._Remnant_2_[Deny_the_Shadow]")

    doc = build_document(parts[1], "Bleach")
    assert doc.number == 117 and doc.display_title == "Chapter 117: Remnant 2 [Deny the Shadow]"
    assert doc.facts["volume"] == "WHITE TOWER ROCKS"
