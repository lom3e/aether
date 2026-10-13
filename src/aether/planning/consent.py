"""
Persistent consent record.

Intent (what the user said), proposal (what Aether plans), consent (who agreed, when, to exactly what),
authority (the token derived from an accepted proposal) and policy decision (what the workspace rules allow)
are five different things. This module is the "consent" one: an immutable record that lets anyone reconstruct
*who* authorised *what*, *when*, *through which channel*, for *which proposal version and content*, within
*which scope*, and whether it was later revoked.

A consent is bound to the proposal's content digest: if the proposal is edited after consent, the digest no
longer matches and the consent stops being valid.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def proposal_digest(proposal: Any) -> str:
    """Stable SHA-256 of everything a person agrees to when accepting a proposal."""
    def _plain(x: Any) -> Any:
        return x.to_dict() if hasattr(x, "to_dict") else x

    payload = {
        "id": getattr(proposal, "id", None),
        "version": getattr(proposal, "version", None),
        "workspace_id": getattr(proposal, "workspace_id", None),
        "objective": getattr(proposal, "objective", None),
        "steps": [_plain(s) for s in (getattr(proposal, "proposed_steps", None) or [])],
        "constraints": list(getattr(proposal, "constraints", None) or []),
        "approvals": [_plain(a) for a in (getattr(proposal, "required_approvals", None) or [])],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def scope_from_constraints(constraints: list[str]) -> dict[str, Any]:
    """The machine-readable scope a consent covers, derived from the proposal's constraints."""
    scope: dict[str, Any] = {"allow": [], "allow_paths": [], "deny": [], "mission_ids": [], "constraints": list(constraints or [])}
    for c in constraints or []:
        text = str(c).strip()
        low = text.lower()
        if low.startswith("allow:") or low.startswith("scope:"):
            scope["allow"] += [a.strip() for a in text.split(":", 1)[1].split(",") if a.strip()]
        elif low.startswith("allow_path:"):
            scope["allow_paths"].append(text.split(":", 1)[1].strip())
        elif low.startswith(("prohibit:", "deny:", "disallow:", "blocked:")):
            scope["deny"].append(text.split(":", 1)[1].strip())
        elif low.startswith(("mission_id:", "bind_mission:")):
            scope["mission_ids"].append(text.split(":", 1)[1].strip())
    return scope


@dataclass
class ConsentRecord:
    id: str
    workspace_id: str
    proposal_id: str
    proposal_version: int
    actor: str                 # who: "user", "user:session", "system_autonomous", "legacy_unknown"
    actor_kind: str            # human | policy_autonomous | legacy
    channel: str               # ui | api | cli | policy | migration
    content_digest: str
    scope: dict[str, Any] = field(default_factory=dict)
    policy_code: str | None = None      # the policy verdict that allowed an autonomous consent
    mission_id: str | None = None
    granted_at: str = field(default_factory=_now)
    revoked_at: str | None = None
    revoke_reason: str | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "workspace_id": self.workspace_id, "proposal_id": self.proposal_id,
            "proposal_version": self.proposal_version, "actor": self.actor, "actor_kind": self.actor_kind,
            "channel": self.channel, "content_digest": self.content_digest, "scope": self.scope,
            "policy_code": self.policy_code, "mission_id": self.mission_id, "granted_at": self.granted_at,
            "revoked_at": self.revoked_at, "revoke_reason": self.revoke_reason,
        }
