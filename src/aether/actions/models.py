"""
Domain models for Aether Action Layer (Phase C).
Defines operational capabilities, execution tiers (ANSWER/DO/ACT), and safety gates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class ActionTier(StrEnum):
    """
    Tri-level action hierarchy:
    - ANSWER: Informational, analytical, zero mutation.
    - DO: Local/safe mutation within workspace boundaries (e.g. creating documents, local note).
    - ACT: External or sensitive mutation (e.g. creating calendar event, sending email, mutating remote state).
    """
    ANSWER = "answer"
    DO = "do"
    ACT = "act"

    @classmethod
    def from_str(cls, val: str) -> ActionTier:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.DO


class ActionPermissionLevel(StrEnum):
    READ_ONLY = "read_only"
    LOCAL_MUTATION = "local_mutation"
    EXTERNAL_MUTATION = "external_mutation"
    SENSITIVE_MUTATION = "sensitive_mutation"

    @classmethod
    def from_str(cls, val: str) -> ActionPermissionLevel:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.LOCAL_MUTATION


class ActionExecutionStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

    @classmethod
    def from_str(cls, val: str) -> ActionExecutionStatus:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.SUCCESS


def mask_secret_value(val: Any) -> Any:
    """Masks secret strings, preserving length hints only if safe."""
    if isinstance(val, str):
        clean = val.strip()
        if not clean:
            return ""
        if len(clean) > 8:
            return f"{clean[:3]}...{clean[-3:]}"
        return "••••••••"
    return val


def sanitize_payload(payload: Any) -> Any:
    """Recursively scrubs secret keys from payloads for safe logging and display."""
    secret_terms = ("token", "secret", "password", "key", "webhook", "pat", "authorization", "bearer", "credential")
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for k, v in payload.items():
            k_lower = str(k).lower()
            if any(term in k_lower for term in secret_terms):
                sanitized[k] = mask_secret_value(v)
            elif isinstance(v, (dict, list)):
                sanitized[k] = sanitize_payload(v)
            else:
                sanitized[k] = v
        return sanitized
    elif isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]
    return payload


@dataclass(slots=True)
class ActionDefinition:
    """Specification of an invocable action capability."""
    id: str
    name: str
    description: str
    tier: ActionTier = ActionTier.DO
    permission_level: ActionPermissionLevel = ActionPermissionLevel.LOCAL_MUTATION
    requires_confirmation: bool = False
    provider: str = "core"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    def is_external_or_sensitive(self) -> bool:
        """Returns True if the action modifies external state or requires sensitive handling."""
        return (
            self.tier == ActionTier.ACT
            or self.permission_level in (
                ActionPermissionLevel.EXTERNAL_MUTATION,
                ActionPermissionLevel.SENSITIVE_MUTATION,
            )
        )

    def is_mutation(self) -> bool:
        """Returns True if the action is not purely read-only."""
        return self.permission_level != ActionPermissionLevel.READ_ONLY

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tier": self.tier.value if isinstance(self.tier, ActionTier) else str(self.tier),
            "permission_level": self.permission_level.value if isinstance(self.permission_level, ActionPermissionLevel) else str(self.permission_level),
            "requires_confirmation": self.requires_confirmation,
            "provider": self.provider,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionDefinition:
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            description=data.get("description", ""),
            tier=ActionTier.from_str(data.get("tier", "do")),
            permission_level=ActionPermissionLevel.from_str(data.get("permission_level", "local_mutation")),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            provider=data.get("provider", "core"),
            input_schema=dict(data.get("input_schema") or {}),
            output_schema=dict(data.get("output_schema") or {}),
        )


@dataclass(slots=True)
class ActionExecution:
    """Record of an action invocation with state, safety confirmation, and audit logs."""
    id: str
    action_id: str
    workspace_id: str
    status: ActionExecutionStatus = ActionExecutionStatus.RUNNING
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    approved_by: str | None = None
    rejection_reason: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provider: str = ""

    def to_dict(self, mask_secrets: bool = True) -> dict[str, Any]:
        inp = sanitize_payload(self.input_data) if mask_secrets else self.input_data
        out = sanitize_payload(self.output_data) if mask_secrets else self.output_data
        meta = sanitize_payload(self.metadata) if mask_secrets else self.metadata
        return {
            "id": self.id,
            "action_id": self.action_id,
            "workspace_id": self.workspace_id,
            "provider": self.provider,
            "status": self.status.value if isinstance(self.status, ActionExecutionStatus) else str(self.status),
            "input_data": inp,
            "output_data": out,
            "error_message": self.error_message,
            "approved_by": self.approved_by,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "metadata": meta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionExecution:
        return cls(
            id=data.get("id") or f"ax-{uuid.uuid4().hex[:12]}",
            action_id=data["action_id"],
            workspace_id=data.get("workspace_id", "default"),
            provider=data.get("provider", ""),
            status=ActionExecutionStatus.from_str(data.get("status", "running")),
            input_data=dict(data.get("input_data") or {}),
            output_data=dict(data.get("output_data") or {}),
            error_message=data.get("error_message"),
            approved_by=data.get("approved_by"),
            rejection_reason=data.get("rejection_reason"),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            completed_at=data.get("completed_at"),
            metadata=dict(data.get("metadata") or {}),
        )
