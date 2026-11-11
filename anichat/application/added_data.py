"""Use cases: knowledge from the admin form, outside the wiki pipeline.
- RecordSync: movie records (editable at any time) -> documents of the "movies" series.
- AddedDataService: free entries (facts about anime, series, anything) -> documents of kind "added".
Documents go to data/added/<series>/<kind>/ and are chunked with the series' wiki documents
(scripts/chunk.py reads both folders).
"""

import json
from dataclasses import asdict
from pathlib import Path

from anichat.domain.added import MOVIES, added_document, parse_submission
from anichat.domain.documents import Document
from anichat.domain.records import Field, record_document
from anichat.infrastructure.document_store import DocumentStore
from anichat.infrastructure.raw_store import safe_filename

LEDGER = "_added.json"  # per series: every added Document, so later entries can merge into it
RECORD_TITLES = "_records.json"  # movies: record id -> its page title (to remove the old page on a rename)


class AddedStore:
    """The added documents of each series: a JSON ledger (source of truth, merged into by later
    entries) plus the Markdown files the chunker reads.

    Created by: scripts/sync_submissions.py, tests
    Used by:    AddedDataService, RecordSync
    """

    def __init__(self, root: Path):
        self._root = Path(root)
        self._markdown = DocumentStore(self._root)

    def _ledger(self, series: str) -> dict[str, dict]:
        """"kind:title" -> Document fields, for one series. Called by: get(), save(), remove()"""
        path = self._root / series / LEDGER
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _write_ledger(self, series: str, ledger: dict[str, dict]) -> None:
        """Called by: save(), remove()"""
        path = self._root / series / LEDGER
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")

    def get(self, series: str, kind: str, title: str) -> Document | None:
        """An earlier added document, or None. Called by: AddedDataService"""
        found = self._ledger(series).get(f"{kind}:{title}")
        return Document(**found) if found else None

    def save(self, doc: Document) -> None:
        """Write the document to the ledger and as Markdown. Called by: AddedDataService, RecordSync"""
        ledger = self._ledger(doc.series)
        ledger[f"{doc.kind}:{doc.title}"] = asdict(doc)
        self._write_ledger(doc.series, ledger)
        self._markdown.save(doc)

    def remove(self, series: str, kind: str, title: str) -> None:
        """Delete a document (ledger entry and Markdown file). Called by: RecordSync"""
        ledger = self._ledger(series)
        if ledger.pop(f"{kind}:{title}", None) is not None:
            self._write_ledger(series, ledger)
        (self._root / series / kind / f"{safe_filename(title)}.md").unlink(missing_ok=True)

    def record_titles(self) -> dict[str, str]:
        """Movie record id -> the page title it was last saved under. Called by: RecordSync"""
        path = self._root / MOVIES / RECORD_TITLES
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def set_record_titles(self, titles: dict[str, str]) -> None:
        """Called by: RecordSync"""
        path = self._root / MOVIES / RECORD_TITLES
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(titles, ensure_ascii=False, indent=1), encoding="utf-8")


class RecordSync:
    """Brings movie records up to date: rebuilds the document of every record whose version the
    laptop hasn't indexed yet, and removes deleted ones.

    Created by: scripts/sync_submissions.py  main()
    """

    def __init__(self, store: AddedStore, series_title: str = "Movies"):
        self._store = store
        self._series_title = series_title

    def changed(self, records: list[dict], synced: dict[str, int]) -> list[dict]:
        """Records edited since the laptop last indexed them. Called by: sync(); scripts (--list)"""
        return [r for r in records if synced.get(r["id"]) != r.get("version")]

    def sync(self, records: list[dict], fields: dict[str, Field], synced: dict[str, int]) -> list[tuple[dict, str]]:
        """Rebuild the changed records' documents. Returns (record, what happened) for each.

        Called by: scripts/sync_submissions.py  main()
        """
        titles = self._store.record_titles()
        done = []
        for record in self.changed(records, synced):
            old_title = titles.get(record["id"])
            if record.get("deleted"):
                if old_title:
                    self._store.remove(MOVIES, "movie", old_title)
                titles.pop(record["id"], None)
                done.append((record, "removed"))
                continue
            doc = record_document(record, fields, self._series_title)
            if old_title and old_title != doc.title:  # renamed (title or year changed)
                self._store.remove(MOVIES, "movie", old_title)
            self._store.save(doc)
            titles[record["id"]] = doc.title
            done.append((record, "updated" if old_title else "added"))
        self._store.set_record_titles(titles)
        return done


class AddedDataService:
    """Free entries from the admin form ("Other entries").

    Created by: scripts/sync_submissions.py, tests
    """

    def __init__(self, store: AddedStore, series_titles: dict[str, str]):
        self._store = store
        self._titles = series_titles

    def apply(self, raw: dict) -> tuple[Document, str]:
        """Process one entry: validate it, then add it as (or merge it into) a document. Returns the
        document and a short message for the form's list. Raises ValueError with the reason when
        it can't be added.

        Called by: scripts/sync_submissions.py  main()
        """
        sub = parse_submission(raw)
        if sub.series not in self._titles:
            raise ValueError(f"unknown series {sub.series!r}: use one of the ids in anichat/domain/series.py")
        existing = self._store.get(sub.series, "added", sub.title)
        doc = added_document(sub, self._titles[sub.series], existing)
        self._store.save(doc)
        return doc, f"{doc.title}: {'updated' if existing else 'added'} in {sub.series} ({len(doc.facts)} facts)"
