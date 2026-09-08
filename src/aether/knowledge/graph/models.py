"""
Domain models for the Knowledge Graph Foundation (Phase B Slice 2).
Defines node and relation taxonomy, GraphNode, GraphEdge, and Subgraph structures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid

from aether.memory.models import MemoryProvenance


class KnowledgeNodeType(StrEnum):
    """
    Controlled taxonomy of entity and concept node types in the Knowledge Graph.
    """
    AGENT = "agent"
    TEAM = "team"
    PERSON = "person"
    PROJECT = "project"
    MISSION = "mission"
    EXECUTION = "execution"
    DELIVERABLE = "deliverable"
    DECISION = "decision"
    PROCESS = "process"
    FACT = "fact"
    OUTCOME = "outcome"
    LESSON = "lesson"
    ORGANIZATION = "organization"

    @classmethod
    def from_str(cls, val: str) -> KnowledgeNodeType:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.FACT


class KnowledgeRelationType(StrEnum):
    """
    Controlled taxonomy of directed relation types between Knowledge Graph nodes.
    """
    AGENT_MEMBER_OF_TEAM = "agent_member_of_team"
    AGENT_CONTRIBUTED_TO = "agent_contributed_to"
    AGENT_VERIFIED = "agent_verified"
    MISSION_BELONGS_TO_PROJECT = "mission_belongs_to_project"
    EXECUTION_OF_MISSION = "execution_of_mission"
    MEMORY_ABOUT = "memory_about"
    DECISION_AFFECTS = "decision_affects"
    LESSON_FROM = "lesson_from"
    OUTCOME_OF = "outcome_of"
    DELIVERABLE_FROM = "deliverable_from"
    PERSON_RELATED_TO_PROJECT = "person_related_to_project"
    PROCESS_USED_BY = "process_used_by"
    PROJECT_RELATED_TO_WORKSPACE = "project_related_to_workspace"
    CREATED_BY = "created_by"
    DERIVED_FROM = "derived_from"
    APPLIES_TO = "applies_to"
    RELATES_TO = "relates_to"

    @classmethod
    def from_str(cls, val: str) -> KnowledgeRelationType:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.RELATES_TO


@dataclass(slots=True)
class GraphNode:
    """
    A persistent, scoped node representing an entity or concept in the Knowledge Graph.
    """
    id: str
    workspace_id: str
    node_type: KnowledgeNodeType
    canonical_key: str
    label: str
    summary: str | None = None
    source_memory_ids: list[str] = field(default_factory=list)
    provenance: MemoryProvenance = field(default_factory=lambda: MemoryProvenance(source_entity="system"))
    properties: dict[str, Any] = field(default_factory=dict)
    is_archived: bool = False
    is_deleted: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "node_type": self.node_type.value if isinstance(self.node_type, KnowledgeNodeType) else str(self.node_type),
            "canonical_key": self.canonical_key,
            "label": self.label,
            "summary": self.summary,
            "source_memory_ids": list(self.source_memory_ids),
            "provenance": self.provenance.to_dict() if hasattr(self.provenance, "to_dict") else dict(self.provenance or {}),
            "properties": dict(self.properties),
            "is_archived": self.is_archived,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphNode:
        prov_raw = data.get("provenance") or {}
        prov_obj = MemoryProvenance.from_dict(prov_raw) if isinstance(prov_raw, dict) else prov_raw

        return cls(
            id=data["id"],
            workspace_id=data["workspace_id"],
            node_type=KnowledgeNodeType.from_str(data["node_type"]),
            canonical_key=data["canonical_key"],
            label=data["label"],
            summary=data.get("summary"),
            source_memory_ids=list(data.get("source_memory_ids") or []),
            provenance=prov_obj,
            properties=dict(data.get("properties") or {}),
            is_archived=bool(data.get("is_archived", False)),
            is_deleted=bool(data.get("is_deleted", False)),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class GraphEdge:
    """
    A persistent, directed relationship between two nodes in the Knowledge Graph.
    """
    id: str
    workspace_id: str
    source_node_id: str
    target_node_id: str
    relation_type: KnowledgeRelationType
    weight: float = 1.0
    confidence: float = 1.0
    provenance: MemoryProvenance = field(default_factory=lambda: MemoryProvenance(source_entity="system"))
    source_memory_ids: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relation_type": self.relation_type.value if isinstance(self.relation_type, KnowledgeRelationType) else str(self.relation_type),
            "weight": self.weight,
            "confidence": self.confidence,
            "provenance": self.provenance.to_dict() if hasattr(self.provenance, "to_dict") else dict(self.provenance or {}),
            "source_memory_ids": list(self.source_memory_ids),
            "properties": dict(self.properties),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphEdge:
        prov_raw = data.get("provenance") or {}
        prov_obj = MemoryProvenance.from_dict(prov_raw) if isinstance(prov_raw, dict) else prov_raw

        return cls(
            id=data["id"],
            workspace_id=data["workspace_id"],
            source_node_id=data["source_node_id"],
            target_node_id=data["target_node_id"],
            relation_type=KnowledgeRelationType.from_str(data["relation_type"]),
            weight=float(data.get("weight", 1.0)),
            confidence=float(data.get("confidence", 1.0)),
            provenance=prov_obj,
            source_memory_ids=list(data.get("source_memory_ids") or []),
            properties=dict(data.get("properties") or {}),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class Subgraph:
    """
    A bounded subgraph containing a localized set of nodes and their connecting edges.
    """
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    seed_node_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "seed_node_ids": list(self.seed_node_ids),
        }
