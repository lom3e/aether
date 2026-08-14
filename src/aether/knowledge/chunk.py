"""KnowledgeChunk — the atomic unit of stored knowledge."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class KnowledgeChunk:
    """
    A single chunk of indexed knowledge.

    Attributes
    ----------
    content:
        The text content of this chunk.
    source:
        The original file or URL this chunk was extracted from.
    chunk_index:
        The zero-based position of this chunk within its source document.
    id:
        Unique identifier for this chunk (auto-generated UUID hex).
    metadata:
        Optional arbitrary metadata (e.g., page number, section title).
    created_at:
        UTC timestamp when the chunk was ingested.
    """

    content: str
    source: str
    chunk_index: int = 0
    id: str = field(default_factory=lambda: uuid4().hex)
    metadata: dict = field(default_factory=dict)
    scope: str = "workspace"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        preview = self.content[:60].replace("\n", " ")
        return (
            f"KnowledgeChunk(source={self.source!r}, "
            f"chunk_index={self.chunk_index}, preview={preview!r})"
        )
