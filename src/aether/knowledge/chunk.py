"""KnowledgeChunk — the atomic unit of stored knowledge."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class KnowledgeScope(str, Enum):
    """
    Scope boundaries for indexed knowledge resources.
    """
    WORKSPACE = "workspace"
    PROJECT = "project"
    SYSTEM = "system"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        try:
            return str(value).strip().lower() in {s.value for s in cls}
        except Exception:
            return False

    @classmethod
    def normalize(cls, value: str | None) -> str:
        if not value or not str(value).strip():
            return cls.WORKSPACE.value
        val = str(value).strip().lower()
        if val in {s.value for s in cls}:
            return val
        return cls.WORKSPACE.value


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
    scope:
        Knowledge scope ('workspace', 'project', or 'system').
    project_id:
        Optional project ID when scope is 'project'.
    created_at:
        UTC timestamp when the chunk was ingested.
    """

    content: str
    source: str
    chunk_index: int = 0
    id: str = field(default_factory=lambda: uuid4().hex)
    metadata: dict = field(default_factory=dict)
    scope: str = KnowledgeScope.WORKSPACE.value
    project_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        preview = self.content[:60].replace("\n", " ")
        proj = f", project_id={self.project_id!r}" if self.project_id else ""
        return (
            f"KnowledgeChunk(source={self.source!r}, "
            f"chunk_index={self.chunk_index}, scope={self.scope!r}{proj}, preview={preview!r})"
        )
