"""What a skill may do (one permission vocabulary) and which connection it needs (so the UI can tell the truth).

Permission ids are `namespace.action` (the same shape as `SkillPermission.identifier`). `risk` is shown to the user:
read = looks only, write = changes local things, sensitive = reaches outside or runs code (these go through approval in the executor).
"""
from __future__ import annotations

from typing import Any, Callable

PERMISSIONS: dict[str, str] = {
    "web.read": "read",
    "files.read": "read",
    "files.write": "write",
    "knowledge.read": "read",
    "shell.run": "sensitive",
    "mail.read": "read",
    "mail.draft": "write",
    "mail.send": "sensitive",
    "github.read": "read",
    "github.write": "sensitive",
    "slack.send": "sensitive",
    "mcp.call": "sensitive",
}

# skill -> the connection it needs. `available: False` = no such connector exists yet (the UI says so instead of pretending).
REQUIREMENTS: dict[str, dict[str, Any]] = {
    "gmail_integration": {"connection": "gmail", "available": False},
    "github_tools": {"connection": "github", "available": True},
    "slack_notifications": {"connection": "slack", "available": True},
}


def permission_details(ids: list[str]) -> list[dict[str, str]]:
    return [{"id": i, "risk": PERMISSIONS.get(i, "sensitive")} for i in ids]  # an unknown permission is treated as sensitive


def readiness(skill_name: str, connection_status: Callable[[str], str | None]) -> dict[str, Any] | None:
    """None when the skill needs no connection. Otherwise {connection, state}: ready | not_connected | needs_reauth | unavailable."""
    req = REQUIREMENTS.get(skill_name)
    if not req:
        return None
    if not req["available"]:
        return {"connection": req["connection"], "state": "unavailable"}
    status = connection_status(req["connection"])
    if status == "verified":
        state = "ready"
    elif status in ("verification_required", "verification_failed"):
        state = "needs_reauth"
    else:
        state = "not_connected"
    return {"connection": req["connection"], "state": state}


_SECRET_HINTS = ("token", "key", "secret", "password", "passwd", "credential")
MASK = "••••••••"


def is_secret_field(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _SECRET_HINTS)
