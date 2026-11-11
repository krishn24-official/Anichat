"""DocumentWriter that keeps one Markdown file per document under
data/documents/<series>/<kind>/<page>.md (easy to open and review by hand).
"""

import json
import shutil
from pathlib import Path

from anichat.domain.chunking import SourceDocument
from anichat.domain.documents import Document, to_markdown
from anichat.infrastructure.raw_store import safe_filename


def parse_markdown(text: str) -> SourceDocument:
    """Split a document file into its front matter (one `key: <json>` per line, as written
    by domain/documents.py to_markdown()) and its Markdown body.

    Called by: DocumentStore.iter_documents()
    """
    meta = {}
    if text.startswith("---\n"):
        header, _, body = text[4:].partition("\n---\n")
        for line in header.splitlines():
            key, _, value = line.partition(":")
            try:
                meta[key.strip()] = json.loads(value)
            except json.JSONDecodeError:
                meta[key.strip()] = value.strip()  # hand-written plain YAML value
    else:
        body = text
    return SourceDocument(meta=meta, body=body.strip())


class DocumentStore:
    """Implements application/build_documents.py DocumentWriter.

    Created by: scripts/build_documents.py  main()
    Used by:    application/build_documents.py  BuildDocumentsService.build()
    """

    def __init__(self, root: Path, *also_read: Path):
        """`also_read`: more folders with the same layout whose documents iter_documents() also
        yields (data/added/: TMDb movies and admin-form entries, which a wiki rebuild must not delete)."""
        self._root = Path(root)
        self._also = [Path(p) for p in also_read]

    def clear(self, series: str) -> None:
        """Delete the series' previous documents before a rebuild.

        Called by: BuildDocumentsService.build()
        """
        shutil.rmtree(self._root / series, ignore_errors=True)

    def iter_documents(self, series: str):
        """Yield every document of a series as a SourceDocument (front matter + body).
        Hand-written .md files placed in the same folders are read too, as long as they
        have the same front matter (at least: series, kind, title, display_title).

        Called by: application/chunk_documents.py  ChunkDocumentsService.chunk()
        """
        for root in (self._root, *self._also):
            for path in sorted((root / series).glob("*/*.md")):
                yield parse_markdown(path.read_text(encoding="utf-8"))

    def save(self, doc: Document) -> None:
        """Write the document as Markdown.

        Called by: BuildDocumentsService.build()
        """
        path = self._root / doc.series / doc.kind / f"{safe_filename(doc.title)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_markdown(doc), encoding="utf-8")
