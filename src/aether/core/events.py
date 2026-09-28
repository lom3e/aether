"""
Cross-Surface Event Envelope (Phase P3.1).

Defines the canonical wire envelope for events that cross architectural boundaries:
- Backend runtime
- Desktop Main App
- Ambient Companion
- Notification Fabric
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass(slots=True)
class CrossSurfaceEventEnvelope:
    """Canonical envelope schema for events shared across backend, app, companion, and notifications."""
    event_id: str
    event_type: str
    workspace_id: str
    entity_type: str | None
    entity_id: str | None
    occurred_at: str
    version: int
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serializes the envelope, including legacy 'type' and 'data' for client compatibility."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "workspace_id": self.workspace_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "occurred_at": self.occurred_at,
            "version": self.version,
            "payload": self.payload,
            # Backward-compatibility legacy fields:
            "type": self.event_type,
            "data": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrossSurfaceEventEnvelope:
        now_iso = datetime.now(timezone.utc).isoformat()
        evt_type = data.get("event_type") or data.get("type") or "message"
        payload = data.get("payload") if "payload" in data else data.get("data")
        if payload is None:
            payload = {}
        elif not isinstance(payload, dict):
            payload = {"value": payload}

        return cls(
            event_id=data.get("event_id") or f"evt-{uuid.uuid4().hex[:12]}",
            event_type=evt_type,
            workspace_id=data.get("workspace_id") or "default",
            entity_type=data.get("entity_type"),
            entity_id=data.get("entity_id") or payload.get("id"),
            occurred_at=data.get("occurred_at") or now_iso,
            version=int(data.get("version", 1)),
            payload=payload,
        )

    @classmethod
    def wrap(
        cls,
        workspace_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> CrossSurfaceEventEnvelope:
        now_iso = datetime.now(timezone.utc).isoformat()
        body = payload if payload is not None else (data or {})
        body_dict = body if isinstance(body, dict) else {"value": body}
        eid = entity_id or body_dict.get("id") or body_dict.get("execution_id") or body_dict.get("target_id")
        etype = entity_type or body_dict.get("target_type") or body_dict.get("type")
        return cls(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            event_type=event_type,
            workspace_id=workspace_id,
            entity_type=str(etype) if etype else None,
            entity_id=str(eid) if eid else None,
            occurred_at=now_iso,
            version=1,
            payload=body_dict,
        )

    @staticmethod
    def unwrap_payload(envelope_dict: dict[str, Any]) -> dict[str, Any]:
        """Extracts the underlying payload from an envelope or legacy dictionary."""
        if "payload" in envelope_dict and isinstance(envelope_dict["payload"], dict):
            return envelope_dict["payload"]
        if "data" in envelope_dict and isinstance(envelope_dict["data"], dict):
            return envelope_dict["data"]
        return envelope_dict
