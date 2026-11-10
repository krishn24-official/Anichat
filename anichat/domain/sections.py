"""Splitting one wiki page into several pages, one per section. Pure Python, no I/O.

Some wikis have no page per chapter: Bleach keeps each volume's chapters as sections of the
volume page ("=== 116. White Tower Rocks ==="). Split into "Chapter 116" pages, the rest of
the pipeline (numbers, exact "chapter 116" lookups, display titles) works as for any wiki.
"""

import re
from dataclasses import replace

from anichat.domain.entities import RawPage

_HEADING = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$", re.M)
_TAGS = re.compile(r"<[^>]+>")
# "116. White Tower Rocks", "-100. Turn Back The Pendulum 9" (Bleach's prequel chapters)
CHAPTER_HEADING = r"(-?\d+)\.\s*(.+)"


def split_sections(page: RawPage, heading: str = CHAPTER_HEADING, kind: str = "chapter") -> list[RawPage]:
    """One page per section whose heading matches `heading` (groups: number, name). Each gets
    the title "Chapter <number>", a small infobox (number, name, the source page as volume) and
    the section's text, up to the next heading of the same or a higher level.

    Called by: application/collect.py  CollectService.collect() (sources with split_sections)
    """
    headings = list(_HEADING.finditer(page.wikitext))
    pages = []
    for i, h in enumerate(headings):
        text = _TAGS.sub("", h.group(2)).strip()
        m = re.fullmatch(heading, text)
        if not m:
            continue
        level = len(h.group(1))
        end = next((n.start() for n in headings[i + 1:] if len(n.group(1)) <= level), len(page.wikitext))
        body = page.wikitext[h.end():end].strip()
        number, name = m.group(1), m.group(2).strip()
        infobox = (f"{{{{Chapter\n|chapter = {number}\n|chapter title = {name}\n"
                   f"|volume = {page.title}\n}}}}\n")
        anchor = text.replace(" ", "_")
        pages.append(replace(page, kind=kind, title=f"Chapter {number}", url=f"{page.url}#{anchor}",
                             wikitext=infobox + body))
    return pages
