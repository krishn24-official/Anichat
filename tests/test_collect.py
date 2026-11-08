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
