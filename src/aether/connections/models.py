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
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    NEEDS_AUTH = "needs_auth"

    @classmethod
    def from_str(cls, val: str) -> ConnectionStatus:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.DISCONNECTED


@dataclass(slots=True)
class Connection:
    """Represents an integrated tool or service connected to Aether."""
    id: str
    workspace_id: str
    provider: str
    account_name: str
    status: ConnectionStatus = ConnectionStatus.CONNECTED
    scopes: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    auth_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "provider": self.provider,
            "account_name": self.account_name,
            "status": self.status.value if isinstance(self.status, ConnectionStatus) else str(self.status),
            "scopes": self.scopes,
            "capabilities": self.capabilities,
            "auth_metadata": self.auth_metadata,
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
            status=ConnectionStatus.from_str(data.get("status", "connected")),
            scopes=list(data.get("scopes") or []),
            capabilities=list(data.get("capabilities") or []),
            auth_metadata=dict(data.get("auth_metadata") or {}),
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
