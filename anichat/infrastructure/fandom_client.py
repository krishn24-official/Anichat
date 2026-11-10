"""WikiClient for fandom wikis, using the MediaWiki API (https://<wiki>/api.php).

Polite by design: a few requests at a time, retries with back-off on rate limits
and server errors, and a descriptive User-Agent.
"""

import asyncio
import urllib.parse
from datetime import datetime, timezone

import httpx

from anichat.domain.entities import RawPage
from anichat.domain.series import ALL_ARTICLES

USER_AGENT = "AniChat/0.1 (personal, non-commercial anime knowledge project)"
CONCURRENCY = 4  # simultaneous requests per run
RETRIES = 4


class FandomClient:
    """Implements domain/ports.py WikiClient.

    Created by: scripts/collect.py  main()
    Used by:    application/collect.py  CollectService.collect()
    Use as an async context manager so the HTTP connection is closed afterwards.
    """

    def __init__(self, concurrency: int = CONCURRENCY):
        self._sem = asyncio.Semaphore(concurrency)
        self._http = httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._http.aclose()

    async def _api(self, host: str, params: dict) -> dict:
        """One MediaWiki API call with retries; {} if it keeps failing.

        Called by: category_pages(), fetch_page()
        """
        for attempt in range(RETRIES):
            try:
                async with self._sem:
                    r = await self._http.get(f"https://{host}/api.php", params={**params, "format": "json"})
                if r.status_code == 200:
                    return r.json()
                if r.status_code not in (429, 500, 502, 503, 504):  # a real error: retrying won't help
                    return {}
            except httpx.HTTPError:
                pass  # network hiccup: retry
            await asyncio.sleep(2 * (attempt + 1))
        return {}

    async def _members(self, host: str, category: str, member_type: str) -> list[str]:
        """All member titles of one category of one type ("page" or "subcat"), following
        the API's pagination.

        Called by: category_pages()
        """
        titles, cont = [], {}
        while True:
            data = await self._api(host, {
                "action": "query", "list": "categorymembers", "cmtitle": f"Category:{category}",
                "cmtype": member_type, "cmnamespace": 14 if member_type == "subcat" else 0,
                "cmlimit": 500, **cont,
            })
            titles += [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
            if "continue" not in data:
                return titles
            cont = data["continue"]

    async def category_pages(self, host: str, category: str, include_subcategories: bool) -> list[str]:
        """Article titles in a category, plus those of its direct sub-categories when asked.
        Duplicates (a page in several sub-categories) are removed; order is kept.

        Called by: application/collect.py  CollectService.collect()
        """
        if category == ALL_ARTICLES:
            return await self._all_articles(host)
        titles = await self._members(host, category, "page")
        if include_subcategories:
            for sub in await self._members(host, category, "subcat"):
                titles += await self._members(host, sub.removeprefix("Category:"), "page")
        return list(dict.fromkeys(titles))

    async def _all_articles(self, host: str) -> list[str]:
        """Every article of the wiki (main namespace, redirects excluded). Small wikis leave many
        pages uncategorised (Solo Leveling: Beru, Antares), so they are collected this way.

        Called by: category_pages() for the ALL_ARTICLES category
        """
        titles, cont = [], {}
        while True:
            data = await self._api(host, {"action": "query", "list": "allpages", "apnamespace": 0,
                                          "apfilterredir": "nonredirects", "aplimit": 500, **cont})
            titles += [p["title"] for p in data.get("query", {}).get("allpages", [])]
            if "continue" not in data:
                return titles
            cont = data["continue"]

    async def redirects_to(self, host: str, titles: list[str]) -> dict[str, list[str]]:
        """Redirect titles pointing at each page, 50 pages per request ("Nagato" -> ["Pain",
        "Pein", "Akatsuki Leader", ...]). Wikis create a redirect for every name a character goes by.

        Called by: application/collect.py  CollectService._add_aliases()
        """
        found: dict[str, list[str]] = {}
        for i in range(0, len(titles), 50):
            cont: dict = {}
            while True:
                data = await self._api(host, {"action": "query", "prop": "redirects", "rdlimit": "max",
                                              "titles": "|".join(titles[i:i + 50]), **cont})
                for page in data.get("query", {}).get("pages", {}).values():
                    found.setdefault(page.get("title", ""), []).extend(r["title"] for r in page.get("redirects", []))
                if "continue" not in data:
                    break
                cont = data["continue"]
        return found

    async def page_properties(self, host: str, title: str) -> dict[str, list[str]]:
        """A page's Semantic MediaWiki properties, values as plain titles/text. Wikis like
        naruto.fandom.com keep the infobox data there instead of in the page's wikitext.

        Called by: application/collect.py  CollectService._add_properties()
        """
        data = await self._api(host, {"action": "browsebysubject", "subject": title.replace(" ", "_")})
        out: dict[str, list[str]] = {}
        for prop in data.get("query", {}).get("data", []):
            values = []
            for item in prop.get("dataitem", []):
                value = str(item.get("item", ""))
                if "##_" in value:  # internal sub-object or query id, not a value
                    continue
                values.append(value.split("#", 1)[0].replace("_", " ").strip())
            if values and not prop["property"].startswith("_"):
                out[prop["property"]] = [v for v in dict.fromkeys(values) if v]
        return out

    async def fetch_page(self, host: str, series: str, kind: str, title: str) -> RawPage | None:
        """Download one page's wikitext (redirects followed). None if missing or failing.

        Called by: application/collect.py  CollectService.collect()
        """
        data = await self._api(host, {"action": "parse", "page": title, "prop": "wikitext|revid", "redirects": 1})
        parsed = data.get("parse")
        if not parsed:
            return None
        final_title = parsed.get("title", title)
        return RawPage(
            series=series,
            kind=kind,
            title=final_title,
            url=f"https://{host}/wiki/{urllib.parse.quote(final_title.replace(' ', '_'))}",
            revision_id=int(parsed.get("revid") or 0),
            wikitext=(parsed.get("wikitext") or {}).get("*", ""),
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
