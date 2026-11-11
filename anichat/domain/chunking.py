"""Stage 3: split documents into chunks for embedding. Pure Python, no I/O.

A chunk is the unit that gets embedded (stage 4) and retrieved (stage 5). Rules:
- split by heading first, so a chunk stays about one topic;
- long sections are split by paragraph, then sentence, with one sentence of overlap;
- tiny sections are merged into the previous chunk of the same document;
- every chunk starts with its location ("Series › Page › Section › Subsection"),
  so it is understandable on its own and the embedding knows what it is about.

Sizes are in characters (~4 characters per token for English text): the target
keeps chunks well inside bge-small's 512-token input limit.
"""

import hashlib
import re
from dataclasses import dataclass, field

TARGET_CHARS = 1600  # ~400 tokens
MAX_CHARS = 2000  # ~500 tokens: never exceed (beyond the model limit text is ignored)
MIN_CHARS = 300  # smaller sections are merged into the previous chunk
OVERLAP_SENTENCES = 1
SEPARATOR = " › "

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")


@dataclass(frozen=True)
class SourceDocument:
    """A stage 2 document read back from disk: metadata + Markdown body.

    Created by: infrastructure/document_store.py  DocumentStore.iter_documents()
    Used by:    chunk_document()
    """

    meta: dict  # front matter: series, kind, title, display_title, number, source, mentions, facts...
    body: str  # Markdown, starting with "# <display title>"


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece of knowledge.

    Created by: chunk_document()
    Saved by:   infrastructure/chunk_store.py  ChunkStore.save()
    Read by:    stage 4 (embedding + indexing), not written yet
    """

    id: str  # stable across rebuilds while the content doesn't move: <series>:<kind>:<page>:<n>
    text: str  # what gets embedded and shown to the LLM (starts with the location line)
    series: str
    kind: str
    title: str
    display_title: str
    section: str  # "Abilities › Breathing Style", "" for the page intro
    number: int | None
    source: str
    mentions: list[str] = field(default_factory=list)  # page's linked entities that appear in this chunk
    importance: int = 0  # profile cards: how many pages of the series link to this page


def _sections(body: str) -> list[tuple[list[str], str]]:
    """Markdown body -> [(heading path, text)], e.g. (["Abilities", "Breathing Style"], "...").
    The "# Title" line and the source credit line are page-level, not content.

    Called by: chunk_document()
    """
    matches = list(_HEADING.finditer(body))
    bounds = [(m.start(), m.end(), len(m.group(1)), m.group(2)) for m in matches] + [(len(body), len(body), 0, "")]
    sections, path = [([], body[: bounds[0][0]])], []
    for i, (_, end, level, heading) in enumerate(bounds[:-1]):
        path = [] if level == 1 else path[: level - 2] + [heading]  # "#" is the page title
        sections.append((list(path), body[end: bounds[i + 1][0]]))

    out = []
    for heading_path, text in sections:
        # Drop the "*Series* · Source: [...]" credit line: the source URL is chunk metadata.
        lines = [l for l in text.strip().splitlines() if not (l.startswith("*") and "Source:" in l)]
        text = "\n".join(lines).strip()
        if text:
            out.append((heading_path, text))
    return out


def split_text(text: str, target: int = TARGET_CHARS, limit: int = MAX_CHARS, overlap: int = OVERLAP_SENTENCES) -> list[str]:
    """Split text into pieces of about `target` characters (never above `limit`):
    paragraphs first, sentences when a paragraph is too long, words as a last resort.
    Consecutive pieces share `overlap` sentences.

    Called by: chunk_document()
    """
    if len(text) <= limit:
        return [text]
    units = []  # sentences, keeping paragraph breaks as their own marker
    for paragraph in re.split(r"\n\s*\n", text):
        units += [s.strip() for s in _SENTENCE_END.split(paragraph) if s.strip()] + ["\n"]
    pieces, current = [], []

    def flush():
        joined = " ".join(u for u in current if u != "\n").strip()
        if joined:
            pieces.append(joined)

    for unit in units:
        if unit == "\n":
            if current and len(" ".join(current)) >= target:
                flush()
                current[:] = current[-overlap:] if overlap else []
            continue
        while len(unit) > limit:  # one enormous "sentence": cut at a word boundary
            cut = unit.rfind(" ", 0, limit) or limit
            pieces.append(unit[:cut])
            unit = unit[cut:].strip()
        if current and len(" ".join(current + [unit])) > target:
            flush()
            current[:] = current[-overlap:] if overlap else []
            if len(" ".join(current + [unit])) > limit:  # overlap + a long sentence won't fit
                current.clear()
        current.append(unit)
    flush()
    return pieces


def _chunk_id(meta: dict, n: int) -> str:
    """Stable id: same page + position -> same id, so re-indexing replaces instead of duplicating.

    Called by: chunk_document()
    """
    key = f"{meta['series']}:{meta['kind']}:{meta['title']}:{n}"
    return key if len(key) <= 120 else key[:100] + ":" + hashlib.sha1(key.encode()).hexdigest()[:12]


def chunk_document(doc: SourceDocument, importance: int = 0) -> list[Chunk]:
    """All chunks of one document, in reading order. `importance` (how many pages link
    here) is stored on the profile card, to pick the main entity when a name is ambiguous.

    Called by: application/chunk_documents.py  ChunkDocumentsService.chunk()
    """
    meta = doc.meta
    page = f"{meta.get('series_title', meta['series'])}{SEPARATOR}{meta['display_title']}"

    # 1. Pieces per section, merging tiny sections into the previous piece.
    pieces: list[tuple[str, str]] = []  # (section path, text)
    for heading_path, text in _sections(doc.body):
        section = SEPARATOR.join(heading_path)
        if pieces and len(text) < MIN_CHARS:
            prev_section, prev_text = pieces[-1]
            label = f"{heading_path[-1]}: " if heading_path else ""
            merged = f"{prev_text}\n\n{label}{text}"
            prev_location = len(page) + len(SEPARATOR) + len(prev_section) + 2
            if prev_location + len(merged) <= MAX_CHARS:  # the location line counts too
                pieces[-1] = (prev_section, merged)
                continue
        # The location line is part of the chunk: take it out of the size budget.
        location_chars = len(page) + len(SEPARATOR) + len(section) + 2
        pieces += [(section, part) for part in
                   split_text(text, TARGET_CHARS - location_chars, MAX_CHARS - location_chars)]

    # 2. Chunks with their location line and metadata (plus a profile card for entity pages).
    chunks = []
    card = _profile_card(meta, page, pieces, importance)
    if card:
        chunks.append(card)
    for n, (section, text) in enumerate(pieces):
        location = page + (SEPARATOR + section if section else "")
        lowered = text.lower()
        chunks.append(Chunk(
            id=_chunk_id(meta, n),
            text=f"{location}\n\n{text}",
            series=meta["series"],
            kind=meta["kind"],
            title=meta["title"],
            display_title=meta["display_title"],
            section=section,
            number=meta.get("number"),
            source=meta.get("source", ""),
            mentions=[m for m in meta.get("mentions", []) if _mentioned(m, lowered)],
        ))
    return chunks


# Entity kinds (not episodes/chapters) get a profile card: a short "who/what is X" chunk.
CARD_KINDS = {"character", "breathing_style", "location", "arc", "titan", "death_note", "organization", "technique", "object", "concept", "event", "jutsu", "clan", "devil_fruit", "movie", "ova", "ability", "race", "page", "magic", "transformation", "devil", "quirk", "angel", "mecha", "stand", "added"}
CARD_FACTS = ("alias", "affiliation", "occupation", "rank", "race", "species", "status", "relatives", "user", "creator",
              "killed by", "parents", "children", "clan", "classification", "quirk")
# Wiki sections listing whom a character killed ("People killed" on Attack on Titan pages).
KILL_SECTIONS = ("people killed", "killed", "victims", "kills")


def children_by_parent(docs: list[SourceDocument]) -> dict[str, list[str]]:
    """Reverse of the "parents" facts: parent page title -> children ("Minato Namikaze" ->
    ["Naruto Uzumaki"]), so "Who is Minato's son?" finds it on Minato's own card too.

    Called by: application/chunk_documents.py  ChunkDocumentsService.chunk()
    """
    found: dict[str, list[str]] = {}
    for doc in docs:
        for parent in ((doc.meta.get("facts") or {}).get("parents") or "").split(";"):
            if parent.strip():
                found.setdefault(parent.strip(), []).append(doc.meta.get("title"))
    return found


def killers_by_victim(docs: list[SourceDocument]) -> dict[str, list[str]]:
    """Reverse of the "People killed" lists: victim page title -> the pages that list them.
    "Who killed Eren?" is answered on Mikasa's page, not Eren's; this puts "Killed by: Mikasa
    Ackerman" on Eren's profile card. Only list items naming a page of the series count, and
    sub-sections ("Failed attempts") are not part of the list.

    Called by: application/chunk_documents.py  ChunkDocumentsService.chunk()
    """
    titles = {d.meta.get("title"): d.meta.get("title") for d in docs}
    titles.update({t.split(" (")[0]: t for t in list(titles) if t})  # "L" -> "L (character)"
    found: dict[str, list[str]] = {}
    for doc in docs:
        in_list = False
        for line in doc.body.splitlines():
            if line.startswith("#"):
                in_list = line.lstrip("# ").strip().lower() in KILL_SECTIONS and line.startswith("## ")
                continue
            if in_list and line.startswith("- "):
                name = re.sub(r"\s*\(.*?\)\s*$", "", line[2:]).strip()  # "Eren Yeager (indirectly)"
                victim = titles.get(name)
                killer = doc.meta.get("title")
                if victim and victim != killer and killer not in found.setdefault(victim, []):
                    found[victim].append(killer)
    return found
# Each wiki names the alias field differently ("aka" on the Death Note wiki): all are shown as "Alias".
ALIAS_FACTS = ("alias", "aliases", "aka", "also known as", "nickname", "nicknames", "epithet", "epithets",
               "also called",  # "also called": redirect titles (application/collect.py _add_aliases)
               "romaji")  # the Japanese name in Latin letters: "Shin" (Li Xin), "Uzumaki Naruto"
CARD_SENTENCES = 2


def _profile_card(meta: dict, page: str, pieces: list[tuple[str, str]], importance: int = 0) -> Chunk | None:
    """A short "who/what is this" chunk for entity pages: name, the intro's first sentences
    and key facts. Long intros bury a defining phrase ("held the position of Upper Rank
    Three") among history; a short card makes "Who is Upper Rank Three?" find the page.

    Called by: chunk_document()
    """
    if meta.get("kind") not in CARD_KINDS:
        return None
    intro = next((text for section, text in pieces if section == ""), "")
    # First real paragraph: skip stray short lines left at the top of some pages.
    paragraph = next((p for p in intro.split("\n\n") if len(p) >= 40), "")
    sentences = _SENTENCE_END.split(paragraph)[:CARD_SENTENCES]
    facts = meta.get("facts") or {}
    aliases = "; ".join(facts[k] for k in ALIAS_FACTS if facts.get(k))
    fact_lines = ([f"Alias: {aliases}"] if aliases else []) + [
        f"{k.replace('_', ' ').capitalize()}: {facts[k]}" for k in CARD_FACTS if k != "alias" and facts.get(k)
    ]
    if not sentences or not sentences[0]:
        return None
    text = f"{page} › Profile\n\n" + " ".join(sentences) + ("\n" + "\n".join(fact_lines) if fact_lines else "")
    return Chunk(
        id=f"{meta['series']}:{meta['kind']}:{meta['title']}:card",
        text=text[:MAX_CHARS],
        series=meta["series"],
        kind=meta["kind"],
        title=meta["title"],
        display_title=meta["display_title"],
        section="Profile",
        number=meta.get("number"),
        source=meta.get("source", ""),
        mentions=[m for m in meta.get("mentions", []) if _mentioned(m, text.lower())],
        importance=importance,
    )


GENERIC_WORDS = {"demon", "demons", "mount", "the", "upper", "lower", "village", "kimetsu", "infinity", "final"}


def _mentioned(name: str, lowered_text: str) -> bool:
    """Whether a linked entity appears in a chunk: its full name ("Tanjiro Kamado"),
    or for two-word names its first word ("Tanjiro"), unless that word is generic
    ("Demon Slayer" must not match every "demon").

    Called by: chunk_document()
    """
    base = name.split(" (")[0].lower()  # "Kimetsu no Yaiba (Anime)" -> "kimetsu no yaiba"
    if re.search(rf"\b{re.escape(base)}\b", lowered_text):
        return True
    words = base.split()
    return len(words) == 2 and words[0] not in GENERIC_WORDS and len(words[0]) > 3 \
        and re.search(rf"\b{re.escape(words[0])}\b", lowered_text) is not None
