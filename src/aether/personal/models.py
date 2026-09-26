"""
Domain models for Personal Aether Agent (Phase C).
Defines intent classification, conversational steps, sessions, and overview aggregates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class IntentTier(StrEnum):
    ANSWER = "answer"      # Read-only information / analysis
    DO = "do"              # Safe local mutation
    ACT = "act"            # Sensitive / external mutation (requires user approval)
    DELEGATE = "delegate"  # Multi-agent mission / workforce delegation

    @classmethod
    def from_str(cls, val: str) -> IntentTier:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.ANSWER


@dataclass(slots=True)
class UserIntent:
    """Classified user intent with target action or mission details."""
    raw_prompt: str
    tier: IntentTier
    summary: str
    action_id: str | None = None
    action_args: dict[str, Any] = field(default_factory=dict)
    delegation_goal: str | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_prompt": self.raw_prompt,
            "tier": self.tier.value if isinstance(self.tier, IntentTier) else str(self.tier),
            "summary": self.summary,
            "action_id": self.action_id,
            "action_args": self.action_args,
            "delegation_goal": self.delegation_goal,
            "confidence": self.confidence,
        }


class StepStatusStr(str):
    """Smart status string providing seamless compatibility between waiting_approval and pending_approval."""
    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            s1 = str(self).lower().strip()
            s2 = str(other).lower().strip()
            if s1 == s2:
                return True
            if s1 in ("waiting_approval", "pending_approval") and s2 in ("waiting_approval", "pending_approval"):
                return True
            if s1 in ("completed", "succeeded", "success") and s2 in ("completed", "succeeded", "success"):
                return True
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(str(self))


@dataclass(slots=True)
class PersonalStep:
    """A clear, human-readable execution step shown in the progress stepper."""
    id: str
    title: str
    status: str = "completed"  # pending, running, completed, failed, waiting_approval / pending_approval
    category: str = "general"   # understanding, knowledge, action, delegation, response
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.status, StepStatusStr):
            object.__setattr__(self, "status", StepStatusStr(self.status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "category": self.category,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PersonalStep:
        return cls(
            id=data.get("id") or f"step-{uuid.uuid4().hex[:8]}",
            title=data.get("title", ""),
            status=data.get("status", "completed"),
            category=data.get("category", "general"),
            details=dict(data.get("details") or {}),
        )


@dataclass(slots=True)
class PersonalMessage:
    """A conversational exchange item with structured steps and action/mission links."""
    id: str
    session_id: str
    workspace_id: str
    role: str  # user, assistant, system
    content: str
    tier: IntentTier = IntentTier.ANSWER
    steps: list[PersonalStep] = field(default_factory=list)
    action_execution_id: str | None = None
    mission_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
            "role": self.role,
            "content": self.content,
            "tier": self.tier.value if isinstance(self.tier, IntentTier) else str(self.tier),
            "steps": [s.to_dict() for s in self.steps],
            "action_execution_id": self.action_execution_id,
            "mission_id": self.mission_id,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PersonalMessage:
        return cls(
            id=data.get("id") or f"msg-{uuid.uuid4().hex[:12]}",
            session_id=data.get("session_id", "default"),
            workspace_id=data.get("workspace_id", "default"),
            role=data.get("role", "assistant"),
            content=data.get("content", ""),
            tier=IntentTier.from_str(data.get("tier", "answer")),
            steps=[PersonalStep.from_dict(s) for s in (data.get("steps") or [])],
            action_execution_id=data.get("action_execution_id"),
            mission_id=data.get("mission_id"),
            metadata=dict(data.get("metadata") or {}),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class PersonalSession:
    """Conversational session between user and Personal Aether."""
    id: str
    workspace_id: str
    title: str = "New Conversation"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    messages: list[PersonalMessage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
        }


@dataclass(slots=True)
class PendingApproval:
    """Card item requiring user confirmation before executing an ACT action."""
    execution_id: str
    action_id: str
    action_name: str
    description: str
    tier: str
    input_data: dict[str, Any]
    created_at: str
    human_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "action_id": self.action_id,
            "action_name": self.action_name,
            "description": self.description,
            "human_summary": self.human_summary or self.description,
            "tier": self.tier,
            "input_data": self.input_data,
            "created_at": self.created_at,
        }


class PersonalTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def from_str(cls, val: str) -> PersonalTaskStatus:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.PENDING


@dataclass(slots=True)
class PersonalTask:
    """A real-world persistent background task coordinated by Personal Aether."""
    id: str
    session_id: str
    workspace_id: str
    title: str
    status: PersonalTaskStatus = PersonalTaskStatus.PENDING
    tier: IntentTier = IntentTier.DELEGATE
    progress_percent: int = 0
    current_step: str = "Initiated"
    result_summary: str | None = None
    mission_id: str | None = None
    action_execution_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def deliverable_path(self) -> str | None:
        return self.metadata.get("deliverable_path")

    @property
    def progress_pct(self) -> float:
        return float(self.progress_percent)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "status": self.status.value if isinstance(self.status, PersonalTaskStatus) else str(self.status),
            "tier": self.tier.value if isinstance(self.tier, IntentTier) else str(self.tier),
            "progress_percent": self.progress_percent,
            "progress_pct": self.progress_pct,
            "current_step": self.current_step,
            "result_summary": self.result_summary,
            "deliverable_path": self.deliverable_path,
            "mission_id": self.mission_id,
            "action_execution_id": self.action_execution_id,
            "error": self.error,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PersonalTask:
        return cls(
            id=data.get("id") or f"ptask-{uuid.uuid4().hex[:10]}",
            session_id=data.get("session_id", "default"),
            workspace_id=data.get("workspace_id", "default"),
            title=data.get("title", "Untitled Task"),
            status=PersonalTaskStatus.from_str(data.get("status", "pending")),
            tier=IntentTier.from_str(data.get("tier", "delegate")),
            progress_percent=int(data.get("progress_percent", 0)),
            current_step=data.get("current_step", "Initiated"),
            result_summary=data.get("result_summary"),
            mission_id=data.get("mission_id"),
            action_execution_id=data.get("action_execution_id"),
            error=data.get("error"),
            metadata=dict(data.get("metadata") or {}),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


class CompanionSurfaceMode(StrEnum):
    ORB = "orb"
    COMPACT = "compact"
    EXPANDED = "expanded"
    COCKPIT = "cockpit"


@dataclass(slots=True)
class DesktopAppContext:
    """Active desktop window, application, and clipboard context for on-demand inspection."""
    app_name: str = "Desktop"
    window_title: str = ""
    selected_text: str = ""
    clipboard_text: str = ""
    screen_summary: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "window_title": self.window_title,
            "selected_text": self.selected_text,
            "clipboard_text": self.clipboard_text,
            "screen_summary": self.screen_summary,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DesktopAppContext:
        return cls(
            app_name=data.get("app_name", "Desktop"),
            window_title=data.get("window_title", ""),
            selected_text=data.get("selected_text", ""),
            clipboard_text=data.get("clipboard_text", ""),
            screen_summary=data.get("screen_summary", ""),
            timestamp=data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class CompanionDeliverable:
    """Artifact, document, or code deliverable immediately accessible in Companion."""
    id: str
    title: str
    source: str
    file_path: str
    file_type: str
    file_size_bytes: int = 0
    summary: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "file_size_bytes": self.file_size_bytes,
            "summary": self.summary,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompanionDeliverable:
        return cls(
            id=data.get("id") or f"deliv-{uuid.uuid4().hex[:8]}",
            title=data.get("title", "Deliverable"),
            source=data.get("source", "workspace"),
            file_path=data.get("file_path", ""),
            file_type=data.get("file_type", "document"),
            file_size_bytes=int(data.get("file_size_bytes", 0)),
            summary=data.get("summary", ""),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )

