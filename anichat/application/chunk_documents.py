"""Stage 3 use case: chunk every document of a series and save the chunks."""

from dataclasses import dataclass, field
from typing import Iterable, Protocol

from anichat.domain.chunking import Chunk, SourceDocument, chunk_document


class DocumentReader(Protocol):
    """Implemented by: infrastructure/document_store.py  DocumentStore.iter_documents()"""

    def iter_documents(self, series: str) -> Iterable[SourceDocument]: ...


class ChunkWriter(Protocol):
    """Implemented by: infrastructure/chunk_store.py  ChunkStore"""

    def save(self, series: str, chunks: list[Chunk]) -> None: ...


@dataclass
class ChunkReport:
    """Created by ChunkDocumentsService.chunk(); printed by scripts/chunk.py."""

    series: str
    documents: dict[str, int] = field(default_factory=dict)  # per kind
    chunks: dict[str, int] = field(default_factory=dict)  # per kind
    sizes: list[int] = field(default_factory=list)  # characters per chunk (for the size summary)
    skipped: list[str] = field(default_factory=list)  # documents missing required metadata


REQUIRED = ("series", "kind", "title", "display_title")


class ChunkDocumentsService:
    """Chunks the documents of a series.

    Created by: scripts/chunk.py  main()
    Tested by:  tests/test_chunking.py
    """

    def __init__(self, reader: DocumentReader, writer: ChunkWriter):
        self._reader = reader
        self._writer = writer

    def chunk(self, series: str) -> tuple[ChunkReport, list[Chunk]]:
        """Chunk all documents and save them together (replacing the previous chunks).

        Called by: scripts/chunk.py  main()
        Returns the report and the chunks (the script prints a few as samples).
        """
        report, all_chunks = ChunkReport(series=series), []
        for doc in self._reader.iter_documents(series):
            if not all(doc.meta.get(k) for k in REQUIRED):
                report.skipped.append(str(doc.meta.get("title", "<untitled>")))
                continue
            chunks = chunk_document(doc)
            kind = doc.meta["kind"]
            report.documents[kind] = report.documents.get(kind, 0) + 1
            report.chunks[kind] = report.chunks.get(kind, 0) + len(chunks)
            report.sizes += [len(c.text) for c in chunks]
            all_chunks += chunks
        self._writer.save(series, all_chunks)
        return report, all_chunks
