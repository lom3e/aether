"""Completing an OAuth authorization: exchange the code, verify the account live, persist the connection.

Shared by every way a flow can end (the loopback listener, the legacy HTTP callback). No HTML and no HTTP here: it returns a plain
result so the caller decides how to tell the user. Tokens never leave this function except into the encrypted connection store.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aether.connections.models import Connection, ConnectionStatus
from aether.connections.oauth import OAUTH_SPECS, OAuthManager, OAuthStateData

logger = logging.getLogger(__name__)


@dataclass
class FinishResult:
    ok: bool
    provider: str
    account_name: str = ""
    code: str = ""  # machine-readable reason when not ok: exchange_failed | verification_failed
    message: str = ""


def _verify(prov: str, tokens: dict[str, Any], ws: Any, ws_id: str) -> tuple[bool, str, str]:
    if prov == "google_calendar":
        from aether.connections.google_calendar import GoogleCalendarConnector

        c = GoogleCalendarConnector(auth_metadata=tokens, workspace_id=ws_id, store=ws.connections.store if ws else None)
        valid, message = c.verify(tokens, live_check=True)
        return valid, message, tokens.get("email") or "Google User"
    if prov == "gmail":
        from aether.connections.gmail import GmailConnector

        valid, message = GmailConnector(auth_metadata=tokens, workspace_id=ws_id).verify(tokens, live_check=True)
        return valid, message, tokens.get("email") or "Gmail"
    if prov == "github":
        from aether.connections.github import GitHubConnector

        valid, message = GitHubConnector(auth_metadata=tokens).verify(tokens, live_check=True)
        return valid, message, tokens.get("account_name") or f"@{tokens.get('login', 'github-user')}"
    if prov == "slack":
        from aether.connections.slack import SlackConnector

        valid, message = SlackConnector(auth_metadata=tokens).verify(tokens, live_check=True)
        return valid, message, tokens.get("account_name") or f"Slack ({tokens.get('team', 'Workspace')})"
    if prov == "notion":
        from aether.connections.notion import NotionConnector

        valid, message = NotionConnector(auth_metadata=tokens).verify(tokens, live_check=True)
        return valid, message, tokens.get("account_name") or f"Notion ({tokens.get('workspace_name', 'Workspace')})"
    return True, "Verified", tokens.get("account_name") or f"{OAUTH_SPECS.get(prov, {}).get('name', prov)} account"


def finish_oauth(ws: Any, prov: str, code: str, state_data: OAuthStateData) -> FinishResult:
    ws_id = getattr(state_data, "workspace_id", None) or getattr(ws, "id", "")
    try:
        tokens = OAuthManager.exchange_code(prov, code, state_data)
    except Exception as exc:  # noqa: BLE001 - reported to the user, never raised through the listener thread
        msg = str(exc)
        logger.error("Token exchange failed (%s): %s", prov, type(exc).__name__)
        if ws is not None:
            try:
                ws.connections.record_operation_failure(ws_id, prov, "oauth_exchange", msg, is_auth_error=True)
            except Exception:  # noqa: BLE001
                pass
        return FinishResult(False, prov, code="exchange_failed", message=msg)

    try:
        valid, message, account = _verify(prov, tokens, ws, ws_id)
    except Exception as exc:  # noqa: BLE001
        valid, message, account = False, f"{type(exc).__name__}: {exc}", ""

    return _persist(ws, ws_id, prov, tokens, valid, message, account)


def finish_with_tokens(ws: Any, prov: str, tokens: dict[str, Any], ws_id: str) -> FinishResult:
    """Same ending for flows that already hold the tokens (device flow): verify live, persist."""
    try:
        valid, message, account = _verify(prov, tokens, ws, ws_id)
    except Exception as exc:  # noqa: BLE001
        valid, message, account = False, f"{type(exc).__name__}: {exc}", ""
    return _persist(ws, ws_id, prov, tokens, valid, message, account)


def _persist(ws: Any, ws_id: str, prov: str, tokens: dict[str, Any], valid: bool, message: str, account: str) -> FinishResult:
    now = datetime.now(timezone.utc).isoformat()
    if ws is not None:
        existing = ws.connections.get_connection(ws_id, prov)
        conn = Connection(
            id=existing.id if existing else f"conn-{uuid.uuid4().hex[:10]}",
            workspace_id=ws_id,
            provider=prov,
            account_name=account or (existing.account_name if existing else prov),
            status=ConnectionStatus.VERIFIED if valid else ConnectionStatus.VERIFICATION_FAILED,
            scopes=existing.scopes if existing else ws.connections.get_default_capabilities(prov),
            capabilities=ws.connections.get_default_capabilities(prov),
            auth_metadata=tokens,
            last_verified_at=now if valid else None,
            last_verification_error=None if valid else message,
            verification_method=f"{prov}_oauth",
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        ws.connections.save_connection(conn)
        try:
            if ws.activity:
                from aether.activity.models import ActivityCategory, ActivityStatus

                name = OAUTH_SPECS.get(prov, {}).get("name", prov)
                ws.activity.log(
                    workspace_id=ws_id, title=f"Verified: {name}" if valid else f"Verification Failed: {name}",
                    description=f"{name} authorization {'verified' if valid else 'failed'}: {message}",
                    category=ActivityCategory.CONNECTION, status=ActivityStatus.COMPLETED if valid else ActivityStatus.FAILED,
                    link_view="connections", link_id=conn.id,
                )
        except Exception:  # noqa: BLE001
            pass
    if not valid:
        return FinishResult(False, prov, account_name=account, code="verification_failed", message=message)
    return FinishResult(True, prov, account_name=account, message=message)
