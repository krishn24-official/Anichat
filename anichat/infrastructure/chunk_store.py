"""ChunkWriter that keeps all chunks of a series in data/chunks/<series>.jsonl
(one JSON object per line: easy to inspect, and stage 4 streams it into the index).
"""

import json
from dataclasses import asdict
from pathlib import Path

from anichat.domain.chunking import Chunk


class ChunkStore:
    """Implements application/chunk_documents.py ChunkWriter.

    Created by: scripts/chunk.py  main()
    Used by:    application/chunk_documents.py  ChunkDocumentsService.chunk()
                stage 4 (indexing) will read it back with iter_chunks()
    """

    def __init__(self, root: Path):
        self._root = Path(root)

    def path(self, series: str) -> Path:
        """Where a series' chunks live. Called by: save(), iter_chunks(), scripts/chunk.py"""
        return self._root / f"{series}.jsonl"

    def save(self, series: str, chunks: list[Chunk]) -> None:
        """Write all chunks, replacing the previous file.

        Called by: ChunkDocumentsService.chunk()
        """
        self._root.mkdir(parents=True, exist_ok=True)
        with self.path(series).open("w", encoding="utf-8") as fh:
            for chunk in chunks:
                fh.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")

    def iter_chunks(self, series: str):
        """Yield the saved chunks of a series.

        Called by: stage 4 (indexing), not written yet
        """
        with self.path(series).open(encoding="utf-8") as fh:
            for line in fh:
                yield Chunk(**json.loads(line))
