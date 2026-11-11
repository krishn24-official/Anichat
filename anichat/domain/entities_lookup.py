"""Exact entity lookup by name, alias or title. Pure Python, no I/O.

Embeddings miss questions that name an entity only by a title ("Who is Upper Rank
Three?" -> Akaza): the phrase appears in dozens of story chunks. Like chapter numbers,
such references are looked up exactly instead: every profile card contributes its
distinctive phrases (name, aliases, titles in its first sentences), and a question
containing one gets that card added to its results.
"""

import re
import unicodedata
from collections import defaultdict

from anichat.domain.chunking import Chunk

MAX_ENTITIES_PER_PHRASE = 5  # a phrase shared by more pages ("Twelve Kizuki") identifies no one
UNAMBIGUOUS = 2  # up to this many pages: all are candidates; more: only the most-linked one
MIN_PHRASE_CHARS = 4
# Capitalised multi-word phrases: "Upper Rank Three", "Sound Hashira", "Demon King".
_TITLE = re.compile(r"\b[A-Z][a-z]+(?:\s+(?:of\s+the\s+|of\s+)?[A-Z][a-z]+){1,3}\b")
_ALIAS_LINE = re.compile(r"^Alias: (.+)$", re.M)
_ROLE_LINE = re.compile(r"^(?:Occupation|Rank|Affiliation): (.+)$", re.M)
# "Hiruzen Sarutobi was the Third Hokage of Konohagakure": what the first sentence says the
# entity *is* names it, even if other cards mention the phrase ("grandson of the Third Hokage").
# 'nicknamed "Mob"' / 'known as "Ace"': a quoted nickname in the first sentence names the entity
# even when it is shorter than MIN_PHRASE_CHARS.
_NICKNAMED = re.compile(r'\b(?:nicknamed|known as|called)\s+["“]([^"”]{3,30})["”]')
_DEFINED_AS = re.compile(r"\b(?:is|was)\s+the\s+(?:former\s+)?((?:[A-Z0-9][\w'’-]*\s+){0,3}[A-Z][\w'’-]*)")


def _split_values(value: str) -> list[str]:
    """"[The First] Kira; L-Kira (by Teru)" -> ["Kira", "L-Kira", "by Teru"]. Called by: _phrases()"""
    value = re.sub(r"\[[^\]]*\]", "", value)
    parts = (p.strip() for p in re.split(r"[;,]|\(|\)", value))
    return [p for p in parts if p and p.lower() not in ("formerly", "human", "demon")]


def _phrases(card: Chunk, series_title: str = "") -> tuple[set[str], set[str], set[str]]:
    """(identity phrases, name parts, role phrases), lower-cased.
    Identity = names and aliases: "Kira" identifies a person even if minor pages share it.
    Name parts = a character's first and last name ("Shin" of "Shin Shou"): like identity, but a
    name part shared by many pages loses to the page whose alias it is ("Shin" -> Li Xin).
    Role = occupation/rank/affiliation and titles from the description: "Twelve Kizuki" is a
    group, so it only identifies someone when at most UNAMBIGUOUS pages share it.

    Called by: card_phrases(), build_phrase_index()
    """
    body = card.text.split("\n\n", 1)[-1]
    name = card.title.split(" (")[0]
    identity = {card.title, name}
    name_parts: set[str] = set()
    if len(name.split()) > 1 and card.kind == "character":
        # First and last name ("Tengen"; "Jinwoo" in the Korean order "Sung Jinwoo"). Not for jutsu
        # or arcs: "Naruto Cannon" does not make "Naruto" a name. A surname shared by many pages
        # ("Uzumaki") is dropped or resolved to the most linked page by build_phrase_index/lookup.
        name_parts = {name.split()[0], name.split()[-1]}
    for value in _ALIAS_LINE.findall(body):
        identity.update(_split_values(value))
    first_sentence = re.split(r"(?<=[.!?])\s", body.strip(), maxsplit=1)[0]
    identity.update(_DEFINED_AS.findall(first_sentence))
    nicknames = {n.lower() for n in _NICKNAMED.findall(first_sentence)}
    roles = set(_TITLE.findall(body))
    for value in _ROLE_LINE.findall(body):
        roles.update(_split_values(value))
    ignore = {series_title.lower(), "kimetsu no yaiba"}

    def clean(phrases: set[str]) -> set[str]:
        # "Ane is the Amanto..." -> "amanto", not "the amanto" (which would outrank the page
        # titled "Amanto" for "What are the Amanto?" by being longer).
        lowered = {re.sub(r"^the\s+", "", p.lower()) for p in phrases}
        return {p for p in lowered if (len(p) >= MIN_PHRASE_CHARS or p in nicknames) and p not in ignore}

    identity = clean(identity)
    return identity, clean(name_parts) - identity, clean(roles) - identity - clean(name_parts)


_LONG_VOWELS = (("ō", "o"), ("ū", "u"), ("ā", "a"), ("ē", "e"), ("ī", "i"))


def spellings(phrase: str) -> set[str]:
    """The phrase as people type it without macrons: "tōru" -> {"tōru", "toru", "tooru", "touru"}
    (other accents are dropped: "pokémon" -> "pokemon").

    Called by: build_phrase_index()
    """
    if phrase.isascii():
        return {phrase}

    def plain(text: str) -> str:
        return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))

    doubled, ou = phrase, phrase
    for long, short in _LONG_VOWELS:
        doubled = doubled.replace(long, short * 2)
        ou = ou.replace(long, "ou" if long == "ō" else short * 2)
    return {phrase, plain(phrase), plain(doubled), plain(ou)}


def card_phrases(card: Chunk, series_title: str = "") -> set[str]:
    """All lower-cased phrases that may identify the card's entity (identity + role).

    Called by: tests; see _phrases() for the three kinds
    """
    identity, name_parts, roles = _phrases(card, series_title)
    return identity | name_parts | roles


class PhraseIndex(dict):
    """phrase -> cards, remembering which phrases are only roles/titles (not anyone's name).

    Created by: build_phrase_index(); read by: lookup()
    """

    def __init__(self, *args, roles_only: set[str] | None = None):
        super().__init__(*args)
        self.roles_only = roles_only or set()


def build_phrase_index(cards: list[Chunk], series_title: str = "") -> dict[str, list[Chunk]]:
    """phrase -> the cards it may identify. Identity phrases are kept when shared by up to
    MAX_ENTITIES_PER_PHRASE pages (lookup() then picks the most linked); role phrases only
    when shared by at most UNAMBIGUOUS pages.

    Called by: application/retrieve.py  RetrievalService._phrases() (built once, on first use,
               from the cards returned by VectorIndex.profile_cards())
    """
    identity_index: dict[str, list[Chunk]] = defaultdict(list)
    alias_index: dict[str, list[Chunk]] = defaultdict(list)  # identity without name parts
    role_index: dict[str, list[Chunk]] = defaultdict(list)
    for card in cards:
        identity, name_parts, roles = _phrases(card, series_title)
        for p in {v for p in identity for v in spellings(p)}:
            identity_index[p].append(card)
            alias_index[p].append(card)
        for p in {v for p in name_parts for v in spellings(p)} - identity:
            identity_index[p].append(card)
        for p in {v for p in roles for v in spellings(p)} - identity - name_parts:
            role_index[p].append(card)
    index = PhraseIndex({p: cs for p, cs in role_index.items() if len(cs) <= UNAMBIGUOUS})
    index.roles_only = set(index) - set(identity_index)
    for p, cs in identity_index.items():
        if len(cs) <= MAX_ENTITIES_PER_PHRASE:
            index[p] = cs + [c for c in index.get(p, []) if c not in cs]
        else:
            # Too common as a first/last name ("Cell": Cell Jr., Perfect Cell, Cell Max...), but the
            # page titled exactly by it is still that phrase's entity.
            exact = [c for c in cs if p in spellings(c.title.lower())]
            if len(exact) == 1:
                index[p] = exact
            elif 1 <= len(alias_index[p]) <= UNAMBIGUOUS:
                # Common as a first/last name ("Shin Shou", "Chou Shin"), but the alias of one or two
                # pages ("Shin": Li Xin's Japanese name): those pages are what it names.
                index[p] = alias_index[p]
    return index


def lookup(question: str, phrase_index: dict[str, list[Chunk]], limit: int = 2) -> list[Chunk]:
    """Cards whose phrases appear in the question, names/aliases before roles and longest phrase
    first ("upper rank three" beats "three"), each card once.

    Called by: application/retrieve.py  RetrievalService.retrieve()
    """
    q = question.lower()
    found: list[Chunk] = []
    # Names and aliases before roles/titles ("Who trained Tanjiro before the Final Selection?":
    # Tanjiro, not a minor page that mentions the Final Selection), each longest first.
    roles_only = getattr(phrase_index, "roles_only", set())
    for phrase in sorted(phrase_index, key=lambda p: (p in roles_only, -len(p))):
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", q):
            # The page titled exactly by the phrase first ("Founding Titan" -> that page, not Eren,
            # whose aliases include it), then the most linked. A qualified title doesn't count:
            # "Tobi (Zetsu)" is not the main "Tobi" (Obito Uchiha, most linked, is).
            candidates = sorted(phrase_index[phrase], reverse=True,
                                key=lambda c: (phrase in spellings(c.title.lower()), c.importance))
            if len(candidates) > UNAMBIGUOUS:  # "Kira": 4 pages -> the main one (most linked)
                candidates = candidates[:1]
            for card in candidates:
                if card.id not in {c.id for c in found}:
                    found.append(card)
        if len(found) >= limit:
            break
    return found[:limit]
