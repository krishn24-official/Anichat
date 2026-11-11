"""Turning MediaWiki markup into clean text with structure. Pure Python, no I/O.

Order matters (see parse_page): noise -> file links -> wiki links -> templates
(innermost first) -> tables -> HTML, then split into sections. Links are resolved
before templates so a link's "|" is never mistaken for a template parameter.
"""

import re
from dataclasses import dataclass, field

# Infobox templates: their parameters become the page's structured facts. Every wiki names
# them differently ({{Human3}}, {{Shinigami2}}, {{Objects}}...), so besides these known names,
# any template with INFOBOX_MIN_FIELDS named fields is a candidate (unless it is a navigation/notice
# template); the one with the most fields wins (see _render_templates).
INFOBOX_TEMPLATES = {"episode", "chapter infobox", "character", "ability", "location", "story arc"}
INFOBOX_MIN_FIELDS = 3
NOT_INFOBOX = {"parenttab", "tabs", "for", "for2", "quote", "quotebox", "quote box", "stub", "toc limit", "cropwh"}
# Infobox parameters that are layout, not facts.
SKIP_FACTS = {"image", "caption", "name", "next", "previous", "cover", "image2", "gallery"}
# Sections that are only media, navigation or citations.
SKIP_SECTIONS = {
    "gallery", "references", "navigation", "site navigation", "credits", "music",
    "external links", "see also", "sources", "notes and references",
}
# Templates whose text is kept: name -> how many leading positional arguments to keep.
KEEP_FIRST_ARG = {"ruby", "small", "w", "translation", "color", "tooltip"}
# Templates that wrap a block of content (lists of battles...): keep the longest parameter.
# Not kept: "tabs" (a navigation bar: its longest value is a tab name like "Relationships")
# and "quotebox"/"quote" (the epigraph at the top of character pages, which would otherwise
# become the first line of the intro and of the profile card).
KEEP_CONTENT = ("scroll box", "battle scroll box")
# Link targets that are not worth recording as mentions.
NON_ENTITY_PREFIXES = ("file:", "image:", "category:", "chapter ", "episode ", "volume ", "template:", "wikipedia:")

_TEMPLATE = re.compile(r"\{\{([^{}]*)\}\}")  # innermost template: no braces inside
_LINK = re.compile(r"\[\[([^\[\]|#]*)(?:#[^\[\]|]*)?(?:\|([^\[\]]*))?\]\]")
_HEADING = re.compile(r"^(={2,6})\s*(.*?)\s*\1\s*$", re.M)


@dataclass
class ParsedPage:
    """A page's content after cleaning.

    Created by: parse_page()
    Used by:    domain/documents.py  build_document()
    """

    infobox: dict[str, str] = field(default_factory=dict)  # cleaned facts, e.g. {"air_date": "April 6, 2019"}
    lead: str = ""  # text before the first heading
    sections: list[tuple[int, str, str]] = field(default_factory=list)  # (level 2-6, heading, text)
    mentions: list[str] = field(default_factory=list)  # linked page titles (characters, places, ...)


def _strip_noise(text: str) -> str:
    """Remove comments, <ref> citations, galleries and __MAGIC__ words.

    Called by: parse_page()
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", text, flags=re.S | re.I)
    text = re.sub(r"<(gallery|imagemap)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)  # media blocks
    text = re.sub(r"<tabber[^>]*>(.*?)</tabber>", _tab_labels, text, flags=re.S | re.I)  # <tabber widths="400">
    return re.sub(r"__[A-Z]+__", "", text)


def _tab_labels(m: re.Match) -> str:
    """<tabber>Anime = ...|-|Manga = ...</tabber> -> bold labels "**Anime**" before each tab's
    content (tabs left empty, e.g. image galleries, are dropped later in _finish()).

    Called by: _strip_noise() (as the re.sub replacement for each <tabber> block)
    """
    # Labels never contain markup: in '<p style="...">' the "=" is an HTML attribute, not a tab.
    body = re.sub(r"(?:^|\|-\|)\s*([^=\n|{}\[\]<>]{1,40}?)\s*=", r"\n**\1**\n", m.group(1), flags=re.M)
    return "\n" + body + "\n"


def _remove_file_links(text: str) -> str:
    """Drop [[File:...]] / [[Image:...]] including captions that contain nested links.

    Called by: parse_page()
    """
    out, i = [], 0
    pattern = re.compile(r"\[\[(?:File|Image):", re.I)
    while (m := pattern.search(text, i)):
        out.append(text[i:m.start()])
        depth, j = 0, m.start()
        while j < len(text):  # walk to the matching "]]", counting nested [[ ]]
            if text.startswith("[[", j):
                depth, j = depth + 1, j + 2
            elif text.startswith("]]", j):
                depth, j = depth - 1, j + 2
                if depth == 0:
                    break
            else:
                j += 1
        i = j
    out.append(text[i:])
    return "".join(out)


def _resolve_links(text: str, mentions: list[str]) -> str:
    """[[Target|Label]] -> Label, [[Target]] -> Target; records entity targets in `mentions`.

    Called by: parse_page()
    """
    def replace(m: re.Match) -> str:
        target, label = m.group(1).strip(), m.group(2)
        if re.match(r"^[a-z]{2,3}(?:-[a-z]+)?:", target):  # interlanguage link ("ru:Эпизод 1"): drop
            return ""
        if target and not target.lower().startswith(NON_ENTITY_PREFIXES) and target not in mentions:
            mentions.append(target)
        if target.lower().startswith("category:"):
            return ""
        return (label if label is not None else target).strip()

    return _LINK.sub(replace, text)


def _split_params(body: str) -> tuple[str, list[str], dict[str, str]]:
    """Template body "Name|a|key=b" -> ("name", ["a"], {"key": "b"}).

    Called by: _render_templates()
    """
    parts = body.split("|")
    name = parts[0].strip().lower().removeprefix("template:")
    positional, named = [], {}
    for p in parts[1:]:
        key, sep, value = p.partition("=")
        if sep and re.fullmatch(r"[\w ōū\-().]+", key.strip()):  # keys like "Number (in vol.)"
            named[key.strip().lower()] = value.strip()
        else:
            positional.append(p.strip())
    return name, positional, named


def _render_templates(text: str, infobox: dict[str, str]) -> str:
    """Replace templates innermost-first: keep the text of inline ones, capture the
    infobox's parameters into `infobox`, drop navigation/maintenance ones.

    Called by: parse_page()
    """
    # Infobox candidates as (known name?, field count, facts). The best one wins after rendering:
    # a known infobox name first, else the most fields. Not simply the first: a hatnote such as
    # {{Disambiguation|this=...|for=...|see=...}} above the real infobox also has 3 named fields.
    candidates: list[tuple[bool, int, dict[str, str]]] = []

    def render(m: re.Match) -> str:
        name, positional, named = _split_params(m.group(1))
        # "... box" infoboxes too (JoJo's {{Chapter box}}): a {{Characters}} list on the same page
        # has more fields, and would otherwise win.
        known = name in INFOBOX_TEMPLATES or "infobox" in name or name.endswith(" box")
        if (known or len(named) >= INFOBOX_MIN_FIELDS) and name not in NOT_INFOBOX and not name.startswith(KEEP_CONTENT):
            facts = {}
            for key, value in named.items():
                value = re.sub(r"^\s*[*#]+\s*", "", value, flags=re.M)  # list items ("* Face to Face")
                value = _plain(re.sub(r"\s*\n\s*", "; ", value))  # multi-line values -> one line
                value = re.sub(r"\s*;(?:\s*;)*\s*", "; ", value).strip("; ")  # "a ; ; b" -> "a; b"
                if key not in SKIP_FACTS and value:
                    facts[key] = value
            candidates.append((known, len(named), facts))
            return ""
        if name == "nihongo":  # {{Nihongo|English|Japanese|Romaji}} -> English (Japanese, Romaji)
            english, extra = (positional + ["", "", ""])[0], [p for p in positional[1:3] if p]
            return f"{english} ({', '.join(extra)})" if extra else english
        if name in KEEP_FIRST_ARG:
            return positional[0] if positional else ""
        if name.startswith(KEEP_CONTENT):
            values = positional + list(named.values())
            return "\n" + max(values, key=len) + "\n" if values else ""
        return ""  # navigation boxes, references, maintenance tags...

    for _ in range(10):  # templates nest; each pass resolves the innermost level
        new = _TEMPLATE.sub(render, text)
        if new == text:
            break
        text = new
    if candidates:
        infobox.update(max(candidates, key=lambda c: (c[0], c[1]))[2])
    # Wiki typos: a template missing one opening brace ("{ref|ob = 10}}") is never matched above.
    return re.sub(r"(?<!\{)\{[^{}\n]{1,200}\}\}", "", text)


def _convert_tables(text: str, infobox: dict[str, str] | None = None) -> str:
    """{| wikitable |} -> one line per row, cells separated by " | ".
    A table at the very top of a page without an infobox template, made of "label | value"
    rows, is the page's infobox written by hand (Solo Leveling chapters): its rows become facts.

    Called by: parse_page()
    """
    def convert(m: re.Match) -> str:
        rows = _table_rows(m.group(1))
        pairs = [r for r in rows if len(r) == 2]
        at_top = not text[:m.start()].strip()
        if infobox is not None and not infobox and at_top and len(pairs) >= 3 and len(pairs) >= len(rows) - 1:
            for label, value in pairs:
                key, value = _plain(label).lower(), _plain(value)
                if key not in SKIP_FACTS and value:
                    infobox[key] = value
            return ""
        return "\n" + "\n".join("- " + " | ".join(r) for r in rows if any(r)) + "\n"

    return re.sub(r"\{\|.*?\n(.*?)\n\|\}", convert, text, flags=re.S)


def _table_rows(body: str) -> list[list[str]]:
    """Cells of each row of a wikitable body. Called by: _convert_tables()"""
    rows, current = [], []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("|-") or line.startswith("|+"):
            if current:
                rows.append(current)
            current = []
        elif line.startswith(("|", "!")):
            cells = re.split(r"\|\||!!", line[1:])
            # "style=... | value": keep what follows the attribute part
            current += [c.split("|")[-1].strip() for c in cells if c.strip()]
    if current:
        rows.append(current)
    return rows


def _plain(text: str) -> str:
    """Inline cleanup shared by body text and infobox values: bold/italic quotes,
    HTML tags, <br> as a separator, extra spaces.

    Called by: _render_templates() (infobox values), _finish()
    """
    text = re.sub(r"<br\s*/?>", "; ", text, flags=re.I)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    # Links broken in the source ("[[Woble Hui Guo Rou|Woble]", "[[Kite#Gender"): keep the label.
    text = re.sub(r"\[\[(?:[^\[\]|]*\|)?", "", text).replace("]]", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip(" ;\n")


def _finish(text: str) -> str:
    """Final body cleanup: wiki list markers -> "- ", tidy blank lines.

    Called by: parse_page()
    """
    lines = []
    for line in text.splitlines():
        if re.fullmatch(r"\s*(\{\||\|\}|\|-\|?)\s*", line):  # stray table / tab markers
            continue
        line = _plain(line)
        if re.match(r"^[*#]+", line) and not re.fullmatch(r"\*\*[^*]+\*\*", line):  # list item, not a bold label
            line = "- " + line.lstrip("*#: ").strip()
        elif line.startswith((":", ";")):
            line = line.lstrip(":; ").strip()
        lines.append(line)
    # Drop tab labels with nothing under them ("**Anime**" over a removed gallery).
    content = [i for i, l in enumerate(lines) if l.strip()]
    is_label = lambda l: re.fullmatch(r"\*\*[^*]+\*\*", l.strip()) is not None  # noqa: E731
    empty_labels = {
        i for n, i in enumerate(content)
        if is_label(lines[i]) and (n + 1 == len(content) or is_label(lines[content[n + 1]]))
    }
    text = "\n".join(l for i, l in enumerate(lines) if i not in empty_labels)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_page(wikitext: str, title: str = "") -> ParsedPage:
    """Clean a page and split it into infobox facts, lead text and sections.
    Media, navigation and citation sections are dropped.

    Called by: domain/documents.py  build_document()
    """
    page = ParsedPage()
    # Magic words for the page's own name ("'''{{PAGENAME}}''' is the main protagonist").
    wikitext = re.sub(r"\{\{\s*(?:BASE)?PAGENAMEE?\s*\}\}", title.split(" (")[0], wikitext)
    # Template parameters left in a page ("{{Character/{{{1|Article}}}": a template name built
    # from a parameter) take their default, so the template around them still parses.
    wikitext = re.sub(r"\{\{\{[^{}|]*\|([^{}]*)\}\}\}", r"\1", wikitext)
    wikitext = re.sub(r"\{\{\{[^{}|]*\}\}\}", "", wikitext)
    text = _strip_noise(wikitext)
    text = _remove_file_links(text)
    text = _resolve_links(text, page.mentions)
    text = _render_templates(text, page.infobox)
    text = _convert_tables(text, page.infobox)
    # Image file names are not facts ("lnimagey1 = Airi Sakura LN visual.png").
    for key in [k for k, v in page.infobox.items() if re.search(r"\.(?:png|jpe?g|gif|webp|svg)$", v, re.I)]:
        del page.infobox[key]

    headings = list(_HEADING.finditer(text))
    page.lead = _finish(text[: headings[0].start()] if headings else text)
    if not page.lead and page.infobox.get("intro"):  # You-Zitsu keeps the intro in the infobox
        page.lead = page.infobox.pop("intro")
    skipping_level = None
    for i, h in enumerate(headings):
        level, heading = len(h.group(1)), _plain(h.group(2))
        if skipping_level is not None and level > skipping_level:
            continue  # inside a skipped section (e.g. Gallery's sub-sections)
        skipping_level = level if heading.lower() in SKIP_SECTIONS else None
        if skipping_level is not None:
            continue
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        page.sections.append((level, heading, _finish(text[h.end():end])))
    return page
