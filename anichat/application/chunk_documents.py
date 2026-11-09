"""Stage 3 use case: chunk every document of a series and save the chunks."""

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Protocol

from anichat.domain.chunking import Chunk, SourceDocument, children_by_parent, chunk_document, killers_by_victim


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
        docs = list(self._reader.iter_documents(series))
        # How many pages link to each page: used to pick "Kira" -> Light Yagami (linked from almost
        # every page) over minor characters also called Kira.
        links = Counter(m for d in docs for m in set(d.meta.get("mentions") or []))
        # "Killed by" facts gathered from the killers' pages, shown on the victims' cards.
        killers = killers_by_victim(docs)
        children = children_by_parent(docs)
        for doc in docs:
            if not all(doc.meta.get(k) for k in REQUIRED):
                report.skipped.append(str(doc.meta.get("title", "<untitled>")))
                continue
            derived = {"killed by": killers.get(doc.meta["title"]), "children": children.get(doc.meta["title"])}
            facts = doc.meta.get("facts") or {}
            extra = {k: "; ".join(v) for k, v in derived.items() if v and not facts.get(k)}
            if extra:
                doc = SourceDocument({**doc.meta, "facts": {**facts, **extra}}, doc.body)
            chunks = chunk_document(doc, importance=links.get(doc.meta["title"], 0))
            kind = doc.meta["kind"]
            report.documents[kind] = report.documents.get(kind, 0) + 1
            report.chunks[kind] = report.chunks.get(kind, 0) + len(chunks)
            report.sizes += [len(c.text) for c in chunks]
            all_chunks += chunks
        self._writer.save(series, all_chunks)
        return report, all_chunks
