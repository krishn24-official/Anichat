"""Tests for stage 1 collection, using in-memory fakes (no network, no disk)."""

import asyncio

from anichat.application.collect import CollectService
from anichat.domain.entities import RawPage
from anichat.domain.series import CategorySource, SeriesSource
from anichat.infrastructure.raw_store import safe_filename

SERIES = SeriesSource("demo", "Demo", "demo.fandom.com", (CategorySource("episode", "Episodes"),))


class FakeWiki:
    """Stands in for FandomClient: two episodes, one of which cannot be fetched."""

    async def category_pages(self, host, category, include_subcategories):
        return ["Episode 1", "Episode 2"]

    async def fetch_page(self, host, series, kind, title):
        if title == "Episode 2":
            return None
        return RawPage(series, kind, title, "https://demo/wiki/Episode_1", 1, "text", "now")


class FakeStore:
    """Stands in for RawStore: remembers saved titles."""

    def __init__(self, existing=()):
        self.saved = set(existing)
        self.manifest = None

    def has(self, series, kind, title):
        return title in self.saved

    def save(self, page):
        self.saved.add(page.title)

    def write_manifest(self, series, manifest):
        self.manifest = manifest


def test_collects_new_pages_reports_failures_and_writes_a_manifest():
    store = FakeStore()
    report = asyncio.run(CollectService(FakeWiki(), store).collect(SERIES))
    assert report.listed == {"episode": 2} and report.fetched == {"episode": 1}
    assert report.failed == {"episode": ["Episode 2"]}
    assert store.saved == {"Episode 1"}
    assert "CC BY-SA" in store.manifest["license"]


def test_skips_pages_already_saved_unless_refreshing():
    store = FakeStore(existing={"Episode 1"})
    report = asyncio.run(CollectService(FakeWiki(), store).collect(SERIES))
    assert report.cached == {"episode": 1} and report.fetched == {"episode": 0}
    report = asyncio.run(CollectService(FakeWiki(), store).collect(SERIES, refresh=True))
    assert report.fetched == {"episode": 1}


def test_safe_filenames():
    assert safe_filename("Tanjiro Kamado") == "tanjiro_kamado"
    assert safe_filename("Episode 1: Cruelty") == "episode_1_cruelty"
    assert safe_filename("???") == "untitled"


def test_infobox_filters_split_a_shared_wiki_and_sequels_search_the_shared_pages():
    from anichat.domain.series import SERIES, search_scope

    naruto_ep = SERIES["naruto"].categories[0]
    shippuden_ch = SERIES["naruto_shippuden"].categories[1]
    assert naruto_ep.accepts({"episode": "1", "shippuden": "No", "boruto": "No", "boruto anime": "No"})
    assert not naruto_ep.accepts({"episode": "1", "shippuden": "Yes", "boruto": "No", "boruto anime": "No"})
    assert not naruto_ep.accepts({"episode": "1", "shippuden": "No", "boruto": "Yes", "boruto anime": "Yes"})
    assert shippuden_ch.accepts({"chapter": "245", "boruto": "No"})
    assert not shippuden_ch.accepts({"chapter": "12", "boruto": "No"})
    assert search_scope("naruto_shippuden") == ("naruto_shippuden", "naruto")
    assert search_scope("death_note") == "death_note"


def test_redirect_titles_are_stored_as_other_names_of_entity_pages():
    class Wiki(FakeWiki):
        async def category_pages(self, host, category, include_subcategories):
            return ["Nagato"]

        async def redirects_to(self, host, titles):
            return {"Nagato": ["Pain", "Pein/original", "ペイン", "Akatsuki Leader"]}

    class Store(FakeStore):
        pages = {}

        def save(self, page):
            super().save(page)
            self.pages[page.title] = page

        def load(self, series, kind, title):
            return self.pages.get(title)

    store = Store()
    series = SeriesSource("demo", "Demo", "demo.fandom.com", (CategorySource("character", "Characters"),))
    asyncio.run(CollectService(Wiki(), store).collect(series))
    assert store.pages["Nagato"].properties == {"also called": "Pain; Akatsuki Leader"}
