"""Stage 1 use case: download every wiki page of a series and keep it raw on disk.

Raw means untouched wikitext. Cleaning and structuring happen in stage 2, so if
that logic changes we rebuild from these files instead of downloading again.
"""

import asyncio
import re
from dataclasses import replace
from datetime import datetime, timezone

from anichat.domain.entities import CollectReport
from anichat.domain.ports import RawStore, WikiClient
from anichat.domain.sections import split_sections
from anichat.domain.series import CategorySource, SeriesSource
from anichat.domain.wikitext import parse_page

NUMBERED_KINDS = ("episode", "chapter")  # their redirects are only other spellings of a number
ALIAS_FACT = "also called"  # fact name for redirect titles; shown on the profile card as an alias


class CollectService:
    """Collects all pages of a series, skipping ones already saved.

    Created by: scripts/collect.py  main()   (wires FandomClient + RawStore)
    Tested by:  tests/test_collect.py
    """

    def __init__(self, wiki: WikiClient, store: RawStore):
        self._wiki = wiki
        self._store = store
        self._links: dict[tuple[str, str], set[str]] = {}  # (host, category) -> titles its pages link to

    async def _linked(self, series: SeriesSource, category: str) -> set[str]:
        """Titles linked from the pages of `category` (read once per run, shared by sources).

        Called by: _list() for sources with linked_from
        """
        key = (series.wiki_host, category)
        if key not in self._links:
            pages = await self._wiki.category_pages(series.wiki_host, category, False)
            self._links[key] = await self._wiki.links_from(series.wiki_host, pages)
        return self._links[key]

    async def _list(self, series: SeriesSource, source: CategorySource, claimed: dict[str, str]) -> list[str]:
        """The titles one source contributes: its category (or explicit titles), minus excluded
        titles and categories, minus titles an earlier source already claimed.

        Called by: collect(), wanted()
        """
        titles = list(source.titles) or await self._wiki.category_pages(
            series.wiki_host, source.category, source.include_subcategories)
        # Excluded titles are dropped first, so they stay free for a later source: One Punch Man's
        # "Episodes" category feeds both "episode" (Episode N) and "ova" (OVA N).
        if source.exclude_titles:
            titles = [t for t in titles if not re.search(source.exclude_titles, t, re.I)]
        for category in source.exclude_categories:
            unwanted = set(await self._wiki.category_pages(series.wiki_host, category, True))
            titles = [t for t in titles if t not in unwanted]
        if source.linked_from:
            linked = await self._linked(series, source.linked_from)
            titles = [t for t in titles if t in linked]
        # A page in two kinds' categories (Attack on Titan: "Eren Yeager" is in Characters and
        # Titans) is kept once, under the first kind listed in SERIES, not indexed twice.
        return [t for t in titles if claimed.setdefault(t, source.kind) == source.kind]

    async def wanted(self, series: SeriesSource) -> dict[str, set[str] | None]:
        """kind -> titles the current configuration collects (no pages are downloaded). Saved
        pages missing here were collected under older rules. None = can't tell without
        downloading (a kind made by splitting pages into sections: keep all).

        Called by: scripts/prune.py  main()
        """
        claimed: dict[str, str] = {}
        result: dict[str, set[str] | None] = {}
        for source in series.categories:
            titles = await self._list(series, source, claimed)
            if source.split_sections:
                result[source.kind] = None
            elif result.get(source.kind, set()) is not None:
                result.setdefault(source.kind, set()).update(titles)
        return result

    async def collect(self, series: SeriesSource, kinds: list[str] | None = None, refresh: bool = False) -> CollectReport:
        """Fetch every page in the series' categories and save it.

        series:  which wiki/categories to read (domain/series.py SERIES)
        kinds:   limit to some kinds, e.g. ["episode"]; None = all
        refresh: re-download pages that are already saved

        Called by: scripts/collect.py  main()
        Returns a CollectReport (counts per kind, failures).
        """
        report = CollectReport(series=series.id)
        manifest_kinds = {}
        claimed: dict[str, str] = {}  # title -> kind of the first category that listed it
        for source in series.categories:
            if kinds and source.kind not in kinds:
                continue
            titles = await self._list(series, source, claimed)
            # A kind may come from several categories (Death Note: manga + anime characters):
            # counts add up, and a page already saved (from another category) is not fetched twice.
            report.listed[source.kind] = report.listed.get(source.kind, 0) + len(titles)
            # Split pages are saved under other titles, so "already saved" can't be told: always fetched.
            todo = [t for t in titles if refresh or source.split_sections or not self._store.has(series.id, source.kind, t)]
            report.cached[source.kind] = report.cached.get(source.kind, 0) + len(titles) - len(todo)

            pages = await asyncio.gather(
                *(self._wiki.fetch_page(series.wiki_host, series.id, source.kind, t) for t in todo)
            )
            failed = [t for t, page in zip(todo, pages) if page is None]
            # Infobox filter (Naruto's "Episodes" also lists Shippuden and Boruto episodes): other
            # series' pages are not saved and not counted. They are downloaded again on each run,
            # because only saved pages are remembered; collection runs rarely, so that is fine.
            other = [p for p in pages if p and not source.accepts(parse_page(p.wikitext).infobox)]
            for page in pages:
                if page and page not in other:
                    # A volume page holding its chapters as sections (Bleach) is saved as chapters.
                    for part in split_sections(page, source.split_sections) if source.split_sections else [page]:
                        self._store.save(part)
            report.listed[source.kind] -= len(other)
            report.fetched[source.kind] = report.fetched.get(source.kind, 0) + len(todo) - len(failed) - len(other)
            report.failed[source.kind] = report.failed.get(source.kind, []) + failed
            if source.properties:
                await self._add_properties(series, source, titles, refresh)
            if source.kind not in NUMBERED_KINDS:
                await self._add_aliases(series, source, titles, refresh)
            manifest_kinds[f"{source.kind}:{source.category}"] = {"kind": source.kind, "category": source.category,
                                                                  "pages": len(titles), "failed": failed}

        self._store.write_manifest(series.id, {
            "series": series.id,
            "title": series.title,
            "source": f"https://{series.wiki_host}",
            "license": "CC BY-SA 3.0 (fandom wiki content) - keep attribution with any reuse",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "kinds": manifest_kinds,
        })
        return report

    async def _add_properties(self, series: SeriesSource, source, titles: list[str], refresh: bool) -> None:
        """Store the source's Semantic MediaWiki properties (renamed to our fact names) on each
        saved page that does not have them yet. Naruto's character pages show an empty
        {{Infobox}}: parents, clan, rank... only exist there.

        Called by: collect()
        """
        wanted = dict(source.properties)  # wiki property -> our fact name
        pages = [p for p in (self._store.load(series.id, source.kind, t) for t in titles)
                 if p and (refresh or not p.properties)]
        found = await asyncio.gather(*(self._wiki.page_properties(series.wiki_host, p.title) for p in pages))
        for page, props in zip(pages, found):
            facts = {wanted[k]: "; ".join(v) for k, v in props.items() if k in wanted and v}
            if facts:
                self._store.save(replace(page, properties=facts))

    async def _add_aliases(self, series: SeriesSource, source, titles: list[str], refresh: bool) -> None:
        """Store the titles of redirects to each entity page as its other names ("Pain" and
        "Pein" redirect to "Nagato", "Tobi" to "Obito Uchiha"), so a question using such a
        name finds the page. Sub-pages and non-Latin titles (Japanese spellings) are skipped.

        Called by: collect()
        """
        pages = [p for p in (self._store.load(series.id, source.kind, t) for t in titles)
                 if p and (refresh or ALIAS_FACT not in p.properties)]
        if not pages:
            return
        found = await self._wiki.redirects_to(series.wiki_host, [p.title for p in pages])
        for page in pages:
            names = [r for r in found.get(page.title, []) if "/" not in r and r.isascii() and r != page.title]
            # Saved even when empty, so the page is not asked about again on the next run.
            self._store.save(replace(page, properties={**page.properties, ALIAS_FACT: "; ".join(names)}))
