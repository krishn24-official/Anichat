"""Which wiki and which page categories make up each series. Pure configuration.

To add a series: add an entry to SERIES. Category names come from the wiki
(e.g. https://kimetsu-no-yaiba.fandom.com/wiki/Category:Episodes).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CategorySource:
    """One kind of page and the wiki category listing those pages.

    Used by: application/collect.py  CollectService.collect()
    """

    kind: str  # our name for the page type, also the folder name under data/raw/<series>/
    category: str  # wiki category title, without the "Category:" prefix
    include_subcategories: bool = False  # e.g. Characters -> Demons, Hashira, ...


@dataclass(frozen=True)
class SeriesSource:
    """Where a series' knowledge comes from.

    Used by: application/collect.py  CollectService.collect()
             scripts/collect.py      (lists the valid --series choices)
    """

    id: str  # our id, e.g. "demon_slayer"
    title: str  # display name
    wiki_host: str  # fandom wiki host name
    categories: tuple[CategorySource, ...]


SERIES: dict[str, SeriesSource] = {
    "demon_slayer": SeriesSource(
        id="demon_slayer",
        title="Demon Slayer: Kimetsu no Yaiba",
        wiki_host="kimetsu-no-yaiba.fandom.com",
        categories=(
            CategorySource("episode", "Episodes"),
            CategorySource("chapter", "Chapters"),
            CategorySource("character", "Characters", include_subcategories=True),
            CategorySource("arc", "Story Arcs"),
            CategorySource("breathing_style", "Breathing Styles"),
            CategorySource("location", "Locations"),
        ),
    ),
}
