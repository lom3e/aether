"""
Domain models for Workforce Intelligence and Persistent Memory (Phase B).
Defines memory taxonomy (8 categories), provenance tracking, and scoped memory entities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class MemoryCategory(StrEnum):
    """
    Taxonomy of 8 structured memory categories defined in Master Roadmap Layer 5.1.
    """
    FACT = "fact"                # Verified truths about user, organization, or environment
    PREFERENCE = "preference"    # Explicit styles, formats, constraints, and instructions
    DECISION = "decision"        # Prior strategic, architectural, or procedural decisions
    PROCESS = "process"          # Standard operating procedures, pipelines, and workflows
    PERSON = "person"            # Key contacts, stakeholders, clients, and role assignments
    PROJECT = "project"          # Ongoing repositories, campaigns, deadlines, and initiatives
    OUTCOME = "outcome"          # Historical metrics, prior deliverables, and benchmarks
    LESSON = "lesson"            # Operational rules synthesized from corrections and reworks

    @classmethod
    def from_str(cls, val: str) -> MemoryCategory:
        try:
            return cls(val.lower().strip())
        except ValueError:
            # Fallback to FACT if unrecognized
            return cls.FACT


@dataclass(slots=True)
class MemoryProvenance:
    """
    Audit trail detailing origin, author, and verification grounds of a memory.
    Strictly factual and verifiable. Zero internal chain-of-thought or reasoning.
    """
    source_entity: str           # "quality_gate", "mission_execution", "deliverable", "user_instruction", "manual", "agent_task"
    source_mission_id: str | None = None
    source_execution_id: str | None = None
    source_milestone_id: str | None = None
    source_deliverable_id: str | None = None
    source_id: str | None = None
    author_agent: str | None = None      # e.g. "QualityGate Reviewer", "@User", "ResearchLead"
    verification_status: str = "verified" # "verified", "inferred", "user_stated", "unverified"
    evidence: dict[str, Any] = field(default_factory=dict) # Sanitized evidence (e.g. quality score, checksum)
    evidence_excerpt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_entity": self.source_entity,
            "source_mission_id": self.source_mission_id,
            "source_execution_id": self.source_execution_id,
            "source_milestone_id": self.source_milestone_id,
            "source_deliverable_id": self.source_deliverable_id,
            "source_id": self.source_id,
            "author_agent": self.author_agent,
            "verification_status": self.verification_status,
            "evidence": self.evidence,
            "evidence_excerpt": self.evidence_excerpt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryProvenance:
        return cls(
            source_entity=data.get("source_entity", "manual"),
            source_mission_id=data.get("source_mission_id"),
            source_execution_id=data.get("source_execution_id"),
            source_milestone_id=data.get("source_milestone_id"),
            source_deliverable_id=data.get("source_deliverable_id"),
            source_id=data.get("source_id"),
            author_agent=data.get("author_agent"),
            verification_status=data.get("verification_status", "verified"),
            evidence=data.get("evidence") or {},
            evidence_excerpt=data.get("evidence_excerpt"),
        )


@dataclass(slots=True)
class WorkforceMemory:
    """
    A persistent, scoped unit of workforce intelligence.
    Supports multi-tenant isolation, category-based filtering, and auditable provenance.
    """
    id: str
    workspace_id: str
    category: MemoryCategory
    summary: str
    content: str
    provenance: MemoryProvenance
    team_name: str | None = None
    agent_name: str | None = None
    mission_id: str | None = None
    execution_id: str | None = None
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
    is_archived: bool = False
    is_deleted: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(
        cls,
        workspace_id: str,
        category: MemoryCategory | str,
        summary: str,
        content: str,
        provenance: MemoryProvenance | dict[str, Any] | None = None,
        team_name: str | None = None,
        agent_name: str | None = None,
        mission_id: str | None = None,
        execution_id: str | None = None,
        confidence: float = 1.0,
        tags: list[str] | None = None,
        memory_id: str | None = None,
    ) -> WorkforceMemory:
        cat_enum = category if isinstance(category, MemoryCategory) else MemoryCategory.from_str(str(category))
        clean_summary = str(summary).strip()
        clean_content = str(content).strip()
        if not clean_summary:
            clean_summary = clean_content[:60] + "..." if len(clean_content) > 60 else clean_content

        prov_obj = (
            provenance
            if isinstance(provenance, MemoryProvenance)
            else (MemoryProvenance.from_dict(provenance) if isinstance(provenance, dict) else MemoryProvenance(source_entity="manual"))
        )

        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=memory_id or f"mem_{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            category=cat_enum,
            summary=clean_summary,
            content=clean_content,
            provenance=prov_obj,
            team_name=team_name,
            agent_name=agent_name,
            mission_id=mission_id,
            execution_id=execution_id,
            confidence=max(0.0, min(1.0, float(confidence))),
            tags=list(tags or []),
            is_archived=False,
            is_deleted=False,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "category": self.category.value if isinstance(self.category, MemoryCategory) else str(self.category),
            "summary": self.summary,
            "content": self.content,
            "provenance": self.provenance.to_dict(),
            "team_name": self.team_name,
            "agent_name": self.agent_name,
            "mission_id": self.mission_id,
            "execution_id": self.execution_id,
            "confidence": self.confidence,
            "tags": list(self.tags),
            "is_archived": self.is_archived,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkforceMemory:
        cat_raw = data.get("category", "fact")
        category = MemoryCategory.from_str(cat_raw)

        prov_raw = data.get("provenance") or {}
        provenance = MemoryProvenance.from_dict(prov_raw) if isinstance(prov_raw, dict) else MemoryProvenance(source_entity="manual")

        raw_tags = data.get("tags") or []
        tags = list(raw_tags) if isinstance(raw_tags, (list, tuple)) else []

        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=data.get("id") or f"mem_{uuid.uuid4().hex[:12]}",
            workspace_id=data.get("workspace_id", "default"),
            category=category,
            summary=data.get("summary", ""),
            content=data.get("content", ""),
            provenance=provenance,
            team_name=data.get("team_name"),
            agent_name=data.get("agent_name"),
            mission_id=data.get("mission_id"),
            execution_id=data.get("execution_id"),
            confidence=float(data.get("confidence", 1.0)),
            tags=tags,
            is_archived=bool(data.get("is_archived", False)),
            is_deleted=bool(data.get("is_deleted", False)),
            created_at=data.get("created_at") or now,
            updated_at=data.get("updated_at") or now,
        )
