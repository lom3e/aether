"""Helpers that give a browser test a clean slate on the shared (session-scoped) test server."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


def _call(base_url: str, token: str | None, method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(base_url + path, method=method, data=json.dumps(body or {}).encode() if method != "GET" else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except (urllib.error.URLError, ValueError, OSError):
        return None


def clear_pending_work(base_url: str, token: str | None) -> None:
    """Rejects pending action approvals and revokes open proposals left by earlier tests (their text is user data)."""
    ws = _call(base_url, token, "GET", "/api/workspace") or {}
    name = ws.get("name")
    if not name:
        return
    overview = _call(base_url, token, "GET", f"/api/personal/overview?workspace_id={urllib.parse.quote(name)}") or {}
    for item in overview.get("pending_approvals") or []:
        ident = item.get("execution_id") or item.get("id")
        if ident:
            _call(base_url, token, "POST", f"/api/actions/executions/{ident}/reject", {"reason": "test cleanup"})
    for proposal in _call(base_url, token, "GET", "/api/personal/proposals?limit=200") or []:
        if proposal.get("status") in ("draft", "ready_for_acceptance", "needs_clarification"):
            _call(base_url, token, "POST", f"/api/personal/proposals/{proposal['id']}/revoke", {"reason": "test cleanup"})
