"""Tests for stage 2: wikitext cleaning and document building (pure, no files)."""

from anichat.domain.documents import build_document, to_markdown
from anichat.domain.entities import RawPage
from anichat.domain.wikitext import parse_page

EPISODE = """{{Episode
|title = Cruelty
|image = <gallery>
Episode 01.png|Episode
</gallery>
|air_date = April 6, 2019
|chapters = [[Chapter 1|1]]
|Next = [[Episode 2]]
}}
{{nihongo|'''Cruelty'''|{{Ruby|残|ざん}}{{Ruby|酷|こく}}|Zankoku}} is the 1st episode of the [[Kimetsu no Yaiba (Anime)|Kimetsu no Yaiba]] TV anime series.<ref>Source</ref>

==Synopsis==
[[File:Tanjiro.png|thumb|[[Tanjiro Kamado|Tanjiro]] in the snow]]
It is the Taisho Period. [[Tanjiro Kamado|Tanjiro]] lives with his family. He meets [[Giyu Tomioka]].
* First point
** Nested point

==Gallery==
Lots of images.
===Screenshots===
More images.

==Battles==
{{Battle scroll box|content=* Tanjiro vs. Giyu}}

{{Anime Navigation}}
"""


def page(text=EPISODE, kind="episode", title="Episode 1"):
    return RawPage("demon_slayer", kind, title, "https://w/wiki/Episode_1", 7, text, "now")


def test_infobox_becomes_facts_and_inline_templates_keep_text():
    parsed = parse_page(EPISODE)
    assert parsed.infobox == {"title": "Cruelty", "air_date": "April 6, 2019", "chapters": "1"}
    assert parsed.lead == "Cruelty (残酷, Zankoku) is the 1st episode of the Kimetsu no Yaiba TV anime series."


def test_noise_is_removed_and_links_become_text_and_mentions():
    parsed = parse_page(EPISODE)
    synopsis = dict((h, t) for _, h, t in parsed.sections)["Synopsis"]
    assert synopsis.startswith("It is the Taisho Period. Tanjiro lives with his family.")
    assert "thumb" not in synopsis and "png" not in synopsis  # image + caption gone
    assert "- First point" in synopsis and "- Nested point" in synopsis
    assert parsed.mentions[:2] == ["Kimetsu no Yaiba (Anime)", "Tanjiro Kamado"]


def test_media_sections_are_dropped_but_content_boxes_kept():
    headings = [h for _, h, _ in parse_page(EPISODE).sections]
    assert "Gallery" not in headings and "Screenshots" not in headings
    assert dict((h, t) for _, h, t in parse_page(EPISODE).sections)["Battles"] == "- Tanjiro vs. Giyu"


def test_document_metadata_and_markdown():
    long_page = EPISODE + "\n==Plot==\n" + "Tanjiro carries charcoal down the mountain. " * 10
    doc = build_document(page(long_page), "Demon Slayer: Kimetsu no Yaiba")
    assert doc.number == 1 and doc.display_title == "Episode 1: Cruelty"
    md = to_markdown(doc)
    assert md.startswith("---\nseries: \"demon_slayer\"")
    assert "# Episode 1: Cruelty" in md and "CC BY-SA" in md and "## Synopsis" in md


def test_stubs_are_skipped():
    assert build_document(page("{{Stub}}\nShort page."), "Demon Slayer") is None


def test_tab_labels_keep_content_and_empty_tabs_disappear():
    text = "==Forms==\n<tabber>Sekido = Anger clone with a staff.\n|-|Karaku = Joy clone with a fan.\n</tabber>\n" \
           "==Demonstrations==\n<tabber>Anime = <gallery>a.png</gallery>\n|-|Manga = <gallery>b.png</gallery>\n</tabber>\n"
    sections = dict((h, t) for _, h, t in parse_page(text).sections)
    assert sections["Forms"] == "**Sekido**\nAnger clone with a staff.\n\n**Karaku**\nJoy clone with a fan."
    assert sections["Demonstrations"] == ""  # only galleries: nothing left, so the section is skipped


def test_interlanguage_links_and_multiline_facts():
    text = "{{Episode\n|animation_direction = Akira Matsushima\nYuka Shiojima\n}}\nStory text.\n[[ca:Episodi 1]]\n[[ru:Эпизод 1]]"
    parsed = parse_page(text)
    assert parsed.infobox["animation_direction"] == "Akira Matsushima; Yuka Shiojima"
    assert parsed.lead == "Story text." and parsed.mentions == []


def test_intro_comes_before_facts_and_trivia_facts_are_hidden():
    text = ("{{Character\n|rank = Upper Rank Three\n|height = 173 cm\n}}\n"
            "Akaza is a demon who held the position of Upper Rank Three. " * 4 + "\n==History==\n" + "Long ago. " * 30)
    md = to_markdown(build_document(page(text, "character", "Akaza"), "Demon Slayer"))
    body = md.split("\n---\n", 1)[1]
    assert body.index("Akaza is a demon") < body.index("## Facts") < body.index("## History")
    assert "**Rank:** Upper Rank Three" in body and "173 cm" not in body
    assert '"height": "173 cm"' in md  # still in the metadata
