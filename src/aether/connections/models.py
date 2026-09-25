"""
Domain models for Aether Connections (Phase C).
Defines connected external tools, integrations (Calendar, Email, GitHub, etc.), and synced entities.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class ConnectionStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    VERIFICATION_REQUIRED = "verification_required"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    DISCONNECTED = "disconnected"

    # Backward compatibility aliases
    CONNECTED = "verified"
    NEEDS_AUTH = "verification_required"
    AUTH_FAILED = "verification_failed"
    ERROR = "verification_failed"

    @classmethod
    def _missing_(cls, val: object) -> ConnectionStatus | None:
        if isinstance(val, str):
            return cls.from_str(val)
        return None

    @classmethod
    def from_str(cls, val: str) -> ConnectionStatus:
        if not val:
            return cls.DISCONNECTED
        norm = val.lower().strip()
        if norm in ("verified", "connected"):
            return cls.VERIFIED
        if norm in ("configured", "saved"):
            return cls.CONFIGURED
        if norm in ("verification_required", "needs_auth", "needs_attention"):
            return cls.VERIFICATION_REQUIRED
        if norm in ("verification_failed", "auth_failed", "error", "failed"):
            return cls.VERIFICATION_FAILED
        if norm in ("not_configured", "unconfigured"):
            return cls.NOT_CONFIGURED
        if norm in ("disconnected", "disabled"):
            return cls.DISCONNECTED
        return cls.DISCONNECTED


@dataclass(slots=True)
class Connection:
    """Represents an integrated tool or service connected to Aether."""
    id: str
    workspace_id: str
    provider: str
    account_name: str
    status: ConnectionStatus = ConnectionStatus.CONFIGURED
    scopes: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    auth_metadata: dict[str, Any] = field(default_factory=dict)
    last_synced_at: str | None = None
    last_verified_at: str | None = None
    last_verification_error: str | None = None
    last_successful_operation: str | None = None
    verification_method: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_verified(self) -> bool:
        return self.status in (ConnectionStatus.VERIFIED, ConnectionStatus.CONNECTED)

    @property
    def is_configured(self) -> bool:
        return self.status in (
            ConnectionStatus.CONFIGURED,
            ConnectionStatus.VERIFIED,
            ConnectionStatus.CONNECTED,
            ConnectionStatus.VERIFICATION_REQUIRED,
            ConnectionStatus.VERIFICATION_FAILED,
        )

    def to_dict(self, mask_secrets: bool = False) -> dict[str, Any]:
        meta = dict(self.auth_metadata or {})
        if mask_secrets:
            masked = {}
            for k, v in meta.items():
                if any(secret_word in k.lower() for secret_word in ("token", "secret", "password", "key", "webhook", "pat")):
                    if isinstance(v, str) and len(v) > 6:
                        masked[k] = f"{v[:4]}...{v[-3:]}"
                    elif isinstance(v, str) and v:
                        masked[k] = "••••••••"
                    else:
                        masked[k] = v
                else:
                    masked[k] = v
            meta = masked

        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "provider": self.provider,
            "account_name": self.account_name,
            "status": self.status.value if isinstance(self.status, ConnectionStatus) else str(self.status),
            "scopes": self.scopes,
            "capabilities": self.capabilities,
            "auth_metadata": meta,
            "last_synced_at": self.last_synced_at,
            "last_verified_at": self.last_verified_at,
            "last_verification_error": self.last_verification_error,
            "last_successful_operation": self.last_successful_operation,
            "verification_method": self.verification_method,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Connection:
        return cls(
            id=data.get("id") or f"conn-{uuid.uuid4().hex[:12]}",
            workspace_id=data.get("workspace_id", "default"),
            provider=data["provider"],
            account_name=data.get("account_name", "Primary Account"),
            status=ConnectionStatus.from_str(data.get("status", "configured")),
            scopes=list(data.get("scopes") or []),
            capabilities=list(data.get("capabilities") or []),
            auth_metadata=dict(data.get("auth_metadata") or {}),
            last_synced_at=data.get("last_synced_at"),
            last_verified_at=data.get("last_verified_at"),
            last_verification_error=data.get("last_verification_error"),
            last_successful_operation=data.get("last_successful_operation"),
            verification_method=data.get("verification_method"),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class CalendarEvent:
    """Real calendar event entity synced/managed via Connection Layer."""
    id: str
    workspace_id: str
    connection_id: str
    title: str
    start_time: str
    end_time: str | None = None
    description: str = ""
    location: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "connection_id": self.connection_id,
            "title": self.title,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "description": self.description,
            "location": self.location,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalendarEvent:
        return cls(
            id=data.get("id") or f"evt-{uuid.uuid4().hex[:12]}",
            workspace_id=data.get("workspace_id", "default"),
            connection_id=data.get("connection_id", "local-cal"),
            title=data.get("title", "Untitled Event"),
            start_time=data.get("start_time") or datetime.now(timezone.utc).isoformat(),
            end_time=data.get("end_time"),
            description=data.get("description", ""),
            location=data.get("location", ""),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )
