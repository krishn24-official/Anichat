"""Stage 2 use case: turn every collected raw page of a series into a Markdown document.

Works only from the files stage 1 saved (no network), so it can be re-run freely
while the cleaning rules in domain/wikitext.py are improved.
"""

from dataclasses import dataclass, field
from typing import Iterable, Protocol

from anichat.domain.documents import Document, build_document
from anichat.domain.entities import RawPage
from anichat.domain.series import SeriesSource


class RawPageReader(Protocol):
    """Implemented by: infrastructure/raw_store.py  RawStore.iter_pages()"""

    def iter_pages(self, series: str) -> Iterable[RawPage]: ...


class DocumentWriter(Protocol):
    """Implemented by: infrastructure/document_store.py  DocumentStore"""

    def clear(self, series: str) -> None: ...

    def save(self, doc: Document) -> None: ...


@dataclass
class BuildReport:
    """Per-kind counts of a build. Created by BuildDocumentsService.build(), printed by
    scripts/build_documents.py."""

    series: str
    built: dict[str, int] = field(default_factory=dict)
    stubs: dict[str, list[str]] = field(default_factory=dict)  # pages skipped as too short
    chars: dict[str, int] = field(default_factory=dict)  # total body characters per kind


class BuildDocumentsService:
    """Builds the documents of a series.

    Created by: scripts/build_documents.py  main()
    Tested by:  tests/test_documents.py
    """

    def __init__(self, reader: RawPageReader, writer: DocumentWriter):
        self._reader = reader
        self._writer = writer

    def build(self, series: SeriesSource) -> BuildReport:
        """Rebuild all documents of the series from scratch (old ones are removed first,
        so documents of pages that became stubs don't linger).

        Called by: scripts/build_documents.py  main()
        """
        report = BuildReport(series=series.id)
        self._writer.clear(series.id)
        for page in self._reader.iter_pages(series.id):
            doc = build_document(page, series.title)
            if doc is None:
                report.stubs.setdefault(page.kind, []).append(page.title)
                continue
            self._writer.save(doc)
            report.built[page.kind] = report.built.get(page.kind, 0) + 1
            report.chars[page.kind] = report.chars.get(page.kind, 0) + len(doc.body)
        return report
