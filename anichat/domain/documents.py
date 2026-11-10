"""Stage 2 output: one Markdown document per wiki page. Pure Python, no I/O.

A document = YAML front matter (metadata used for filtering later: series, kind,
episode/chapter number, mentioned characters...) + a readable Markdown body.
Stage 3 splits the body by heading into chunks and copies the metadata onto each.
"""

import json
import re
from dataclasses import dataclass, field

from anichat.domain.entities import RawPage
from anichat.domain.wikitext import parse_page

MIN_BODY_CHARS = 300  # pages shorter than this are stubs: nothing worth retrieving
LICENSE = "CC BY-SA 3.0"
MAX_MENTIONS = 40
# Infobox facts kept in the metadata but left out of the text: they rarely answer a question
# and they drown out what a page is about in its embedding.
TRIVIA_FACTS = {
    "height", "weight", "hair_color", "eye_color", "allrelatives", "image_size", "blood_type",
    "birthday_image", "anime_debut", "manga_debut", "game_debut", "japanese_va", "english_va",
}


@dataclass
class Document:
    """A cleaned page ready to be chunked.

    Created by: build_document()
    Saved by:   infrastructure/document_store.py  DocumentStore.save()
    Read by:    stage 3 (chunking), not written yet
    """

    series: str
    series_title: str
    kind: str
    title: str  # wiki page title, e.g. "Episode 1"
    display_title: str  # e.g. "Episode 1: Cruelty"
    source_url: str
    revision_id: int
    number: int | None = None  # episode / chapter number
    facts: dict[str, str] = field(default_factory=dict)
    mentions: list[str] = field(default_factory=list)
    body: str = ""


# Where each wiki keeps the number; "overall" first (per-season/per-volume numbers restart at 1).
NUMBER_FACTS = {
    "episode": ("number (overall)", "number", "episode", "#", "ep number", "episodenumber", "episode number"),
    "chapter": ("number (overall)", "chapter", "number", "chapter number", "#"),
}


def _number(kind: str, title: str, facts: dict[str, str]) -> int | None:
    """Episode/chapter number from the title ("Episode 12" -> 12) or, on wikis that name
    these pages by their title ("Bomb"), from the infobox (chapter = 30). None otherwise.

    Called by: build_document()
    """
    if kind not in NUMBER_FACTS:
        return None
    # "Episode 12", also with a qualifier: "Episode 1 (2011)" (Hunter x Hunter's two anime)
    m = re.fullmatch(r"(?:Episode|Chapter)\s+(\d+)(?:\s*\(.*\))?", title.strip(), re.I)
    if m:
        return int(m.group(1))
    for key in NUMBER_FACTS[kind]:
        m = re.match(r"\s*(\d{1,4})\b", facts.get(key, ""))
        if m:
            return int(m.group(1))
    return None


def _display_title(kind: str, title: str, facts: dict[str, str], number: int | None) -> str:
    """Episodes/chapters show both number and name: "Episode 1: Cruelty" (page "Episode 1",
    infobox title "Cruelty") or "Chapter 30: Bomb" (page "Bomb", infobox chapter 30).

    Called by: build_document()
    """
    if kind not in NUMBER_FACTS:
        return title
    label = f"{kind.capitalize()} {number}" if number is not None else None
    if label and re.match(rf"{label}:", title, re.I):
        return title  # already "Chapter 1: The Two Alchemists"
    numbered_page = label and re.fullmatch(rf"{label}(?:\s*\(.*\))?", title, re.I)  # "Episode 1 (2011)"
    if label and not numbered_page:
        return f"{label}: {title}"  # page named by its title
    name = facts.get("title") or facts.get("chapter title") or facts.get("ep title") or facts.get("episode title") or facts.get("english")
    if name and name.lower() != title.lower():
        return f"{label or title}: {name}"
    return label or title


def _other_names(redirects: str, title: str) -> str:
    """Redirect titles -> other names: bracketed qualifiers dropped ("Haku (Naruto)" -> "Haku";
    left in, "Naruto" would become an alias of every such page), duplicates and the page's own
    name removed, case-insensitively.

    Called by: build_document()
    """
    seen = {title.split(" (")[0].lower()}
    names = []
    for name in redirects.split(";"):
        name = re.sub(r"\s*\(.*?\)", "", name).strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return "; ".join(names)


def build_document(page: RawPage, series_title: str) -> Document | None:
    """Clean one raw page into a Document; None for stubs.

    Called by: application/build_documents.py  BuildDocumentsService.build()
    """
    if re.search(r"\{\{\s*disambig", page.wikitext[:500], re.I):
        return None  # "Episode 1 may refer to...": a list of links, no content
    parsed = parse_page(page.wikitext, page.title)
    # Facts from Semantic MediaWiki and redirects (page.properties) fill what the infobox lacks.
    facts = {**page.properties, **parsed.infobox}
    if facts.get("also called"):
        facts["also called"] = _other_names(facts["also called"], page.title)

    parts = [parsed.lead] if parsed.lead else []
    for level, heading, text in parsed.sections:
        if text:
            parts.append(f"{'#' * level} {heading}\n\n{text}")
    body = "\n\n".join(parts).strip()
    if len(body) < MIN_BODY_CHARS:
        return None

    number = _number(page.kind, page.title, facts)
    return Document(
        series=page.series,
        series_title=series_title,
        kind=page.kind,
        title=page.title,
        display_title=_display_title(page.kind, page.title, facts, number),
        source_url=page.url,
        revision_id=page.revision_id,
        number=number,
        facts={k: v for k, v in facts.items() if v},
        mentions=parsed.mentions[:MAX_MENTIONS],
        body=body,
    )


def to_markdown(doc: Document) -> str:
    """Render a Document as Markdown with YAML front matter (values written as JSON,
    which is valid YAML, so quotes and colons in titles are always safe).

    Called by: infrastructure/document_store.py  DocumentStore.save()
    """
    meta = {
        "series": doc.series,
        "series_title": doc.series_title,
        "kind": doc.kind,
        "title": doc.title,
        "display_title": doc.display_title,
        "number": doc.number,
        "source": doc.source_url,
        "revision": doc.revision_id,
        "license": LICENSE,
        "facts": doc.facts,
        "mentions": doc.mentions,
    }
    front = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in meta.items())
    shown = {k: v for k, v in doc.facts.items() if k not in TRIVIA_FACTS}
    facts = "\n".join(f"- **{k.replace('_', ' ').capitalize()}:** {v}" for k, v in shown.items())
    header = f"# {doc.display_title}\n\n*{doc.series_title}* · Source: [{doc.title}]({doc.source_url}) ({LICENSE})"
    # Intro first, then facts: the intro ("Akaza ... held the position of Upper Rank Three")
    # becomes its own chunk, so its embedding is about who/what the page is, not hair colour.
    intro, sep, rest = doc.body.partition("\n## ")
    if intro.startswith("## "):  # no intro paragraph: the body starts with a section
        intro, rest, sep = "", doc.body[3:], "\n## "
    facts_block = f"## Facts\n\n{facts}\n\n" if facts else ""
    body = (f"{intro.strip()}\n\n" if intro.strip() else "") + facts_block + (f"## {rest}" if sep else "")
    return f"---\n{front}\n---\n\n{header}\n\n{body.strip()}\n"
