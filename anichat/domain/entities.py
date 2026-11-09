"""Core data shapes of AniChat. Pure Python: no I/O, no frameworks.

Stage 1 (collection) only needs RawPage; later stages add documents and chunks.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RawPage:
    """One wiki page exactly as fetched (stage 1 output, the input of stage 2).

    Created by:  infrastructure/fandom_client.py  FandomClient.fetch_page()
    Saved by:    infrastructure/raw_store.py      RawStore.save()
    Read by:     stage 2 (document building), not written yet
    """

    series: str  # our id for the series, e.g. "demon_slayer"
    kind: str  # what the page describes: "episode", "character", ...
    title: str  # wiki page title, e.g. "Tanjiro Kamado"
    url: str  # human-readable page link (kept for attribution: fandom is CC BY-SA)
    revision_id: int  # wiki revision fetched, so a later re-fetch can tell if it changed
    wikitext: str  # raw MediaWiki markup; cleaned in stage 2
    fetched_at: str  # ISO timestamp (UTC)
    # Facts kept outside the wikitext (Naruto wiki: Semantic MediaWiki holds the infobox data),
    # already renamed to our fact names, e.g. {"parents": "Minato Namikaze; Kushina Uzumaki"}.
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class CollectReport:
    """What a collection run did, per kind.

    Created by:  application/collect.py  CollectService.collect()
    Printed by:  scripts/collect.py      main()
    """

    series: str
    listed: dict[str, int] = field(default_factory=dict)  # pages found in each category
    fetched: dict[str, int] = field(default_factory=dict)  # newly downloaded
    cached: dict[str, int] = field(default_factory=dict)  # already on disk, skipped
    failed: dict[str, list[str]] = field(default_factory=dict)  # titles that could not be fetched
