"""RawStore that keeps one JSON file per page under data/raw/<series>/<kind>/.

Plain files on purpose: easy to open and inspect while building stage 2, and
small (one series is a few MB).
"""

import json
import re
from dataclasses import asdict
from pathlib import Path

from anichat.domain.entities import RawPage


def safe_filename(title: str) -> str:
    """A filesystem-safe name for a page title ("Tanjiro Kamado" -> "tanjiro_kamado").

    Called by: RawStore._path()
    """
    name = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return name or "untitled"


class RawStore:
    """Implements domain/ports.py RawStore.

    Created by: scripts/collect.py  main()
    Used by:    application/collect.py  CollectService.collect()
    """

    def __init__(self, root: Path):
        self._root = Path(root)

    def _path(self, series: str, kind: str, title: str) -> Path:
        """Where a page's JSON lives. Called by: has(), save()"""
        return self._root / series / kind / f"{safe_filename(title)}.json"

    def has(self, series: str, kind: str, title: str) -> bool:
        """Whether this page was already collected (so it is not downloaded again).

        Called by: application/collect.py  CollectService.collect()
        """
        return self._path(series, kind, title).exists()

    def load(self, series: str, kind: str, title: str) -> RawPage | None:
        """A saved page, or None. Called by: application/collect.py  CollectService._add_properties()"""
        path = self._path(series, kind, title)
        return RawPage(**json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None

    def save(self, page: RawPage) -> None:
        """Write the page as pretty JSON (overwrites an older copy).

        Called by: application/collect.py  CollectService.collect()
        """
        path = self._path(page.series, page.kind, page.title)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(page), ensure_ascii=False, indent=1), encoding="utf-8")

    def iter_pages(self, series: str):
        """Yield every saved RawPage of a series (all kinds), in a stable order.

        Called by: application/build_documents.py  BuildDocumentsService.build()
        """
        for path in sorted((self._root / series).glob("*/*.json")):
            yield RawPage(**json.loads(path.read_text(encoding="utf-8")))

    def write_manifest(self, series: str, manifest: dict) -> None:
        """Write data/raw/<series>/manifest.json: source, license and what was collected.

        Called by: application/collect.py  CollectService.collect()
        """
        path = self._root / series / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
