"""
Aether Learning & Correction Loop Domain Models (Phase B — Slice 4).

Defines LearningEvent, Correction, DistilledLesson, and controlled taxonomy enums
for observable outcomes, verification states, and scoping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class LearningEventType(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    CORRECTION = "correction"
    QUALITY_GATE_REWORK = "quality_gate_rework"
    HUMAN_FEEDBACK = "human_feedback"
    HUMAN_APPROVAL = "human_approval"
    REGRESSION = "regression"
    LESSON_CREATED = "lesson_created"

    @classmethod
    def from_str(cls, val: str) -> LearningEventType:
        val_clean = str(val).strip().lower()
        for member in cls:
            if member.value == val_clean or member.name.lower() == val_clean:
                return member
        return cls.CORRECTION


class LearningVerificationStatus(StrEnum):
    OBSERVED = "observed"
    PROPOSED = "proposed"
    VERIFIED = "verified"
    REJECTED = "rejected"

    @classmethod
    def from_str(cls, val: str) -> LearningVerificationStatus:
        val_clean = str(val).strip().lower()
        for member in cls:
            if member.value == val_clean or member.name.lower() == val_clean:
                return member
        return cls.OBSERVED


class LearningScope(StrEnum):
    AGENT = "agent"
    TEAM = "team"
    PROJECT = "project"
    PROCESS = "process"
    WORKSPACE = "workspace"

    @classmethod
    def from_str(cls, val: str) -> LearningScope:
        val_clean = str(val).strip().lower()
        for member in cls:
            if member.value == val_clean or member.name.lower() == val_clean:
                return member
        return cls.WORKSPACE


@dataclass(slots=True)
class LearningEvent:
    id: str
    workspace_id: str
    event_type: LearningEventType
    observed_behavior: str
    expected_behavior: str
    correction: str
    evidence: dict[str, Any] = field(default_factory=dict)
    verification_status: LearningVerificationStatus = LearningVerificationStatus.OBSERVED
    mission_id: str | None = None
    execution_id: str | None = None
    milestone_id: str | None = None
    agent_name: str | None = None
    team_name: str | None = None
    source_memory_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "event_type": self.event_type.value if isinstance(self.event_type, LearningEventType) else str(self.event_type),
            "observed_behavior": self.observed_behavior,
            "expected_behavior": self.expected_behavior,
            "correction": self.correction,
            "evidence": self.evidence,
            "verification_status": self.verification_status.value if isinstance(self.verification_status, LearningVerificationStatus) else str(self.verification_status),
            "mission_id": self.mission_id,
            "execution_id": self.execution_id,
            "milestone_id": self.milestone_id,
            "agent_name": self.agent_name,
            "team_name": self.team_name,
            "source_memory_ids": list(self.source_memory_ids),
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearningEvent:
        return cls(
            id=data.get("id") or f"le-{uuid.uuid4().hex[:12]}",
            workspace_id=data.get("workspace_id", "default"),
            event_type=LearningEventType.from_str(data.get("event_type", "correction")),
            observed_behavior=data.get("observed_behavior", ""),
            expected_behavior=data.get("expected_behavior", ""),
            correction=data.get("correction", ""),
            evidence=data.get("evidence") or {},
            verification_status=LearningVerificationStatus.from_str(data.get("verification_status", "observed")),
            mission_id=data.get("mission_id"),
            execution_id=data.get("execution_id"),
            milestone_id=data.get("milestone_id"),
            agent_name=data.get("agent_name"),
            team_name=data.get("team_name"),
            source_memory_ids=list(data.get("source_memory_ids") or []),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            metadata=data.get("metadata") or {},
        )


@dataclass(slots=True)
class Correction:
    id: str
    workspace_id: str
    target_scope: LearningScope
    target_identifier: str
    problem: str
    correction: str
    rationale: str
    evidence: dict[str, Any] = field(default_factory=dict)
    source_mission_id: str | None = None
    source_execution_id: str | None = None
    verification_status: LearningVerificationStatus = LearningVerificationStatus.PROPOSED
    verified_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "target_scope": self.target_scope.value if isinstance(self.target_scope, LearningScope) else str(self.target_scope),
            "target_identifier": self.target_identifier,
            "problem": self.problem,
            "correction": self.correction,
            "rationale": self.rationale,
            "evidence": self.evidence,
            "source_mission_id": self.source_mission_id,
            "source_execution_id": self.source_execution_id,
            "verification_status": self.verification_status.value if isinstance(self.verification_status, LearningVerificationStatus) else str(self.verification_status),
            "verified_at": self.verified_at,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Correction:
        return cls(
            id=data.get("id") or f"corr-{uuid.uuid4().hex[:12]}",
            workspace_id=data.get("workspace_id", "default"),
            target_scope=LearningScope.from_str(data.get("target_scope", "workspace")),
            target_identifier=data.get("target_identifier", "workspace"),
            problem=data.get("problem", ""),
            correction=data.get("correction", ""),
            rationale=data.get("rationale", ""),
            evidence=data.get("evidence") or {},
            source_mission_id=data.get("source_mission_id"),
            source_execution_id=data.get("source_execution_id"),
            verification_status=LearningVerificationStatus.from_str(data.get("verification_status", "proposed")),
            verified_at=data.get("verified_at"),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            metadata=data.get("metadata") or {},
        )


@dataclass(slots=True)
class DistilledLesson:
    id: str
    workspace_id: str
    title: str
    lesson_text: str
    scope: LearningScope
    target_identifier: str
    source_mission_id: str | None = None
    source_execution_id: str | None = None
    source_correction_id: str | None = None
    quality_gate_rule: str | None = None
    verification_status: LearningVerificationStatus = LearningVerificationStatus.VERIFIED
    memory_id: str | None = None
    node_id: str | None = None
    is_regression: bool = False
    regression_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "lesson_text": self.lesson_text,
            "scope": self.scope.value if isinstance(self.scope, LearningScope) else str(self.scope),
            "target_identifier": self.target_identifier,
            "source_mission_id": self.source_mission_id,
            "source_execution_id": self.source_execution_id,
            "source_correction_id": self.source_correction_id,
            "quality_gate_rule": self.quality_gate_rule,
            "verification_status": self.verification_status.value if isinstance(self.verification_status, LearningVerificationStatus) else str(self.verification_status),
            "memory_id": self.memory_id,
            "node_id": self.node_id,
            "is_regression": self.is_regression,
            "regression_count": self.regression_count,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DistilledLesson:
        return cls(
            id=data.get("id") or f"lsn-{uuid.uuid4().hex[:12]}",
            workspace_id=data.get("workspace_id", "default"),
            title=data.get("title", ""),
            lesson_text=data.get("lesson_text", ""),
            scope=LearningScope.from_str(data.get("scope", "workspace")),
            target_identifier=data.get("target_identifier", "workspace"),
            source_mission_id=data.get("source_mission_id"),
            source_execution_id=data.get("source_execution_id"),
            source_correction_id=data.get("source_correction_id"),
            quality_gate_rule=data.get("quality_gate_rule"),
            verification_status=LearningVerificationStatus.from_str(data.get("verification_status", "verified")),
            memory_id=data.get("memory_id"),
            node_id=data.get("node_id"),
            is_regression=bool(data.get("is_regression", False)),
            regression_count=int(data.get("regression_count", 0)),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            metadata=data.get("metadata") or {},
        )
