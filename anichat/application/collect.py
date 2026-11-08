"""Stage 1 use case: download every wiki page of a series and keep it raw on disk.

Raw means untouched wikitext. Cleaning and structuring happen in stage 2, so if
that logic changes we rebuild from these files instead of downloading again.
"""

import asyncio
from datetime import datetime, timezone

from anichat.domain.entities import CollectReport
from anichat.domain.ports import RawStore, WikiClient
from anichat.domain.series import SeriesSource


class CollectService:
    """Collects all pages of a series, skipping ones already saved.

    Created by: scripts/collect.py  main()   (wires FandomClient + RawStore)
    Tested by:  tests/test_collect.py
    """

    def __init__(self, wiki: WikiClient, store: RawStore):
        self._wiki = wiki
        self._store = store

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
        for source in series.categories:
            if kinds and source.kind not in kinds:
                continue
            titles = await self._wiki.category_pages(series.wiki_host, source.category, source.include_subcategories)
            report.listed[source.kind] = len(titles)
            todo = [t for t in titles if refresh or not self._store.has(series.id, source.kind, t)]
            report.cached[source.kind] = len(titles) - len(todo)

            pages = await asyncio.gather(
                *(self._wiki.fetch_page(series.wiki_host, series.id, source.kind, t) for t in todo)
            )
            failed = [t for t, page in zip(todo, pages) if page is None]
            for page in pages:
                if page:
                    self._store.save(page)
            report.fetched[source.kind] = len(todo) - len(failed)
            report.failed[source.kind] = failed
            manifest_kinds[source.kind] = {"category": source.category, "pages": len(titles), "failed": failed}

        self._store.write_manifest(series.id, {
            "series": series.id,
            "title": series.title,
            "source": f"https://{series.wiki_host}",
            "license": "CC BY-SA 3.0 (fandom wiki content) - keep attribution with any reuse",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "kinds": manifest_kinds,
        })
        return report
