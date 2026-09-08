"""
Domain models for Unified Workforce Intelligence context retrieval (Phase B Macro Slice 3).
Combines Workforce Memory documents and Knowledge Graph topology into unified evidence items.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from aether.memory.models import MemoryProvenance


class EvidenceSourceType(StrEnum):
    """
    Source origin of unified operational intelligence evidence.
    """
    MEMORY = "memory"
    GRAPH_NODE = "graph_node"
    GRAPH_EDGE = "graph_edge"
    HYBRID = "hybrid"

    @classmethod
    def from_str(cls, val: str) -> EvidenceSourceType:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.MEMORY


@dataclass(slots=True)
class UnifiedEvidence:
    """
    A single unified evidence item combining semantic memory and graph relational context.
    """
    id: str
    source_type: EvidenceSourceType
    title: str
    summary: str
    score: float
    confidence: float = 1.0
    category: str | None = None
    node_type: str | None = None
    provenance: MemoryProvenance = field(default_factory=lambda: MemoryProvenance(source_entity="system"))
    source_memory_ids: list[str] = field(default_factory=list)
    source_node_ids: list[str] = field(default_factory=list)
    relations_summary: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type.value if isinstance(self.source_type, EvidenceSourceType) else str(self.source_type),
            "title": self.title,
            "summary": self.summary,
            "score": round(self.score, 3),
            "confidence": round(self.confidence, 3),
            "category": self.category,
            "node_type": self.node_type,
            "provenance": self.provenance.to_dict() if hasattr(self.provenance, "to_dict") else dict(self.provenance or {}),
            "source_memory_ids": list(self.source_memory_ids),
            "source_node_ids": list(self.source_node_ids),
            "relations_summary": list(self.relations_summary),
            "properties": dict(self.properties),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnifiedEvidence:
        prov_raw = data.get("provenance") or {}
        prov_obj = MemoryProvenance.from_dict(prov_raw) if isinstance(prov_raw, dict) else prov_raw

        return cls(
            id=data["id"],
            source_type=EvidenceSourceType.from_str(data.get("source_type", "memory")),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            score=float(data.get("score", 0.0)),
            confidence=float(data.get("confidence", 1.0)),
            category=data.get("category"),
            node_type=data.get("node_type"),
            provenance=prov_obj,
            source_memory_ids=list(data.get("source_memory_ids") or []),
            source_node_ids=list(data.get("source_node_ids") or []),
            relations_summary=list(data.get("relations_summary") or []),
            properties=dict(data.get("properties") or {}),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class UnifiedIntelligenceResult:
    """
    Result payload of unified intelligence retrieval for an agent task.
    """
    workspace_id: str
    task_instruction: str
    evidence: list[UnifiedEvidence] = field(default_factory=list)
    total_memories_found: int = 0
    total_nodes_found: int = 0
    deduplicated_count: int = 0
    injected_char_count: int = 0
    formatted_context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "task_instruction": self.task_instruction,
            "evidence": [e.to_dict() for e in self.evidence],
            "total_memories_found": self.total_memories_found,
            "total_nodes_found": self.total_nodes_found,
            "deduplicated_count": self.deduplicated_count,
            "injected_char_count": self.injected_char_count,
            "formatted_context": self.formatted_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UnifiedIntelligenceResult:
        return cls(
            workspace_id=data["workspace_id"],
            task_instruction=data.get("task_instruction", ""),
            evidence=[UnifiedEvidence.from_dict(e) for e in data.get("evidence", [])],
            total_memories_found=int(data.get("total_memories_found", 0)),
            total_nodes_found=int(data.get("total_nodes_found", 0)),
            deduplicated_count=int(data.get("deduplicated_count", 0)),
            injected_char_count=int(data.get("injected_char_count", 0)),
            formatted_context=data.get("formatted_context"),
        )
