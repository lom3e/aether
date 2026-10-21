"""
Unified OAuth 2.0 & Official Authorization Engine for Aether Connections.
Supports Google Calendar, GitHub, Slack, and Notion with:
  - Truthful developer setup detection (ready_for_user_connect vs requires_developer_setup)
  - Seamless 1-Click user authorization flows
  - Secure state management with 15-minute TTL
  - Token exchange & live credential verification
  - Automatic persistence to SecretStore and ConnectionStore
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any, TYPE_CHECKING
import urllib.error
import urllib.parse
import urllib.request

if TYPE_CHECKING:
    from aether.connections.store import ConnectionStore

logger = logging.getLogger(__name__)

GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"

# Standard OAuth Endpoints & Configuration
OAUTH_SPECS: dict[str, dict[str, Any]] = {
    "google_calendar": {
        "name": "Google Calendar",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.readonly",
        ],
        "default_client_id": None,
        "env_client_id": ["GOOGLE_CLIENT_ID", "AETHER_GOOGLE_CLIENT_ID"],
        "env_client_secret": ["GOOGLE_CLIENT_SECRET", "AETHER_GOOGLE_CLIENT_SECRET"],
        "setup_url": "https://console.cloud.google.com/apis/credentials",
        "uses_pkce": True,
        "requires_secret": False,  # Google Desktop client uses PKCE without required secret
    },
    "github": {
        "name": "GitHub",
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": ["repo", "read:user"],
        "default_client_id": None,
        "env_client_id": ["GITHUB_CLIENT_ID", "AETHER_GITHUB_CLIENT_ID"],
        "env_client_secret": ["GITHUB_CLIENT_SECRET", "AETHER_GITHUB_CLIENT_SECRET"],
        "setup_url": "https://github.com/settings/applications/new",
        "uses_pkce": False,
        "requires_secret": True,
    },
    "slack": {
        "name": "Slack",
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes": ["chat:write", "channels:read", "groups:read"],
        "default_client_id": None,
        "env_client_id": ["SLACK_CLIENT_ID", "AETHER_SLACK_CLIENT_ID"],
        "env_client_secret": ["SLACK_CLIENT_SECRET", "AETHER_SLACK_CLIENT_SECRET"],
        "setup_url": "https://api.slack.com/apps/new",
        "uses_pkce": False,
        "requires_secret": True,
    },
    "notion": {
        "name": "Notion",
        "auth_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "scopes": [],
        "default_client_id": None,
        "env_client_id": ["NOTION_CLIENT_ID", "AETHER_NOTION_CLIENT_ID"],
        "env_client_secret": ["NOTION_CLIENT_SECRET", "AETHER_NOTION_CLIENT_SECRET"],
        "setup_url": "https://www.notion.so/my-integrations",
        "uses_pkce": False,
        "requires_secret": True,
    },
}


def _bundled_clients() -> dict[str, dict[str, str]]:
    """Public client ids shipped with the app: oauth_clients.json (committed, ids only) overlaid with the optional
    oauth_clients.local.json (git-ignored, added at build time, may carry the desktop client secret). Missing/invalid = none."""
    from pathlib import Path

    merged: dict[str, dict[str, str]] = {}
    for name in ("oauth_clients.json", "oauth_clients.local.json"):
        try:
            raw = json.loads((Path(__file__).with_name(name)).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for key, value in raw.items():
            if isinstance(value, dict):
                merged.setdefault(key, {}).update({k: v for k, v in value.items() if v})
    return merged


@dataclass(slots=True)
class OAuthStateData:
    workspace_id: str
    provider: str
    code_verifier: str
    client_id: str
    client_secret: str
    redirect_uri: str
    created_at: float
    extra: dict[str, Any] = field(default_factory=dict)


def github_tokens(access_token: str, client_id: str, client_secret: str = "", scope: str = "", token_type: str = "bearer") -> dict[str, Any]:
    """The connection record for a GitHub access token (web flow or device flow): who it belongs to, plus the token."""
    user_login = "github-user"
    user_email = ""
    try:
        u_req = urllib.request.Request(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json", "User-Agent": "Aether/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(u_req, timeout=10.0) as u_resp:
            u_data = json.loads(u_resp.read().decode("utf-8"))
            user_login = u_data.get("login") or user_login
            user_email = u_data.get("email") or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch GitHub user info: %s", type(exc).__name__)
    out = {
        "token": access_token, "login": user_login, "email": user_email, "account_name": f"@{user_login}",
        "scope": scope, "token_type": token_type, "client_id": client_id,
    }
    if client_secret:
        out["client_secret"] = client_secret
    return out


def generate_code_verifier(length: int = 64) -> str:
    """Generates a high-entropy cryptographic random string for PKCE."""
    raw = os.urandom(length)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")[:128]


def generate_code_challenge(verifier: str) -> str:
    """Generates the code_challenge from code_verifier using S256."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class OAuthManager:
    """Centralized manager for OAuth 2.0 and official application authorizations."""

    _states: dict[str, OAuthStateData] = {}
    STATE_TTL_SECONDS = 900  # 15 minutes

    @classmethod
    def _cleanup_expired(cls) -> None:
        now = time.time()
        expired = [s for s, data in cls._states.items() if now - data.created_at > cls.STATE_TTL_SECONDS]
        for s in expired:
            cls._states.pop(s, None)

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        return list(OAUTH_SPECS.keys())

    @classmethod
    def resolve_credentials(
        cls,
        provider: str,
        workspace_id: str,
        store: ConnectionStore | None = None,
    ) -> tuple[str, str]:
        """
        Resolves (client_id, client_secret) for a provider in workspace.
        Checks:
          1. Existing Connection auth_metadata (with secret_store resolution)
          2. Environment variables
          3. Default client ID (for PKCE-enabled desktop clients like Google)
        """
        spec = OAUTH_SPECS.get(provider)
        if not spec:
            return "", ""

        client_id = ""
        client_secret = ""

        # 1. Check persistent connection metadata
        if store:
            conn = store.get_connection_by_provider(workspace_id, provider)
            if conn and conn.auth_metadata:
                meta = conn.auth_metadata
                client_id = str(meta.get("client_id") or meta.get(f"{provider}_client_id") or "").strip()
                client_secret = str(meta.get("client_secret") or meta.get(f"{provider}_client_secret") or "").strip()

        # 2. Check environment variables
        if not client_id:
            for env_key in spec.get("env_client_id", []):
                val = os.environ.get(env_key, "").strip()
                if val:
                    client_id = val
                    break

        if not client_secret:
            for env_key in spec.get("env_client_secret", []):
                val = os.environ.get(env_key, "").strip()
                if val:
                    client_secret = val
                    break

        # 3. Client ids shipped with the app (one-click connect), then the spec default
        bundled = _bundled_clients().get(provider, {})
        if not client_id and str(bundled.get("client_id") or "").strip():
            client_id = str(bundled["client_id"]).strip()
            if not client_secret:
                client_secret = str(bundled.get("client_secret") or "").strip()
        if not client_id and spec.get("default_client_id"):
            client_id = spec["default_client_id"]

        return client_id, client_secret

    @classmethod
    def get_provider_status(
        cls,
        provider: str,
        workspace_id: str,
        base_url: str = "http://127.0.0.1:8000",
        store: ConnectionStore | None = None,
    ) -> dict[str, Any]:
        """Returns readiness and developer setup status for an OAuth provider."""
        spec = OAUTH_SPECS.get(provider)
        if not spec:
            return {
                "provider": provider,
                "supports_oauth": False,
                "ready_for_user_connect": False,
                "requires_developer_setup": False,
            }

        client_id, client_secret = cls.resolve_credentials(provider, workspace_id, store)
        requires_secret = spec.get("requires_secret", True)

        has_client_id = bool(client_id)
        has_client_secret = bool(client_secret)

        if requires_secret:
            ready = has_client_id and has_client_secret
        else:
            ready = has_client_id

        redirect_uri = f"{base_url.rstrip('/')}/api/connections/{provider}/oauth/callback"

        return {
            "provider": provider,
            "name": spec["name"],
            "supports_oauth": True,
            "ready_for_user_connect": ready,
            "requires_developer_setup": not ready,
            "redirect_uri": redirect_uri,
            "setup_url": spec["setup_url"],
            "has_client_id": has_client_id,
            "has_client_secret": has_client_secret,
            "client_id_preview": f"{client_id[:6]}...{client_id[-4:]}" if len(client_id) > 12 else (client_id if client_id else None),
        }

    @classmethod
    def get_all_providers_status(
        cls,
        workspace_id: str,
        base_url: str = "http://127.0.0.1:8000",
        store: ConnectionStore | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Returns readiness status for all supported OAuth providers."""
        return {
            p: cls.get_provider_status(p, workspace_id, base_url, store)
            for p in cls.get_supported_providers()
        }

    @classmethod
    def save_developer_config(
        cls,
        provider: str,
        workspace_id: str,
        client_id: str,
        client_secret: str,
        store: ConnectionStore,
    ) -> dict[str, Any]:
        """Saves developer OAuth App credentials for a provider in the workspace."""
        from aether.connections.models import Connection, ConnectionStatus
        now_iso = datetime.now(timezone.utc).isoformat()

        existing = store.get_connection_by_provider(workspace_id, provider)
        auth_meta = dict(existing.auth_metadata or {}) if existing else {}

        cid_clean = (client_id or "").strip()
        if cid_clean:
            auth_meta["client_id"] = cid_clean
        elif not existing:
            auth_meta["client_id"] = ""

        csec_clean = (client_secret or "").strip()
        if csec_clean and not csec_clean.startswith("••"):
            auth_meta["client_secret"] = csec_clean
        elif not existing:
            auth_meta["client_secret"] = csec_clean

        status = existing.status if existing else ConnectionStatus.NOT_CONFIGURED
        conn = Connection(
            id=existing.id if existing else f"conn-{secrets.token_hex(6)}",
            workspace_id=workspace_id,
            provider=provider,
            account_name=existing.account_name if existing else f"{OAUTH_SPECS.get(provider, {}).get('name', provider.capitalize())}",
            status=status,
            scopes=existing.scopes if existing else OAUTH_SPECS.get(provider, {}).get("scopes", []),
            capabilities=existing.capabilities if existing else [],
            auth_metadata=auth_meta,
            created_at=existing.created_at if existing else now_iso,
            updated_at=now_iso,
        )
        store.save_connection(conn)
        return {
            "success": True,
            "provider": provider,
            "client_id": auth_meta.get("client_id", ""),
            "has_client_secret": bool(str(auth_meta.get("client_secret") or "").strip()),
        }

    @classmethod
    def create_auth_flow(
        cls,
        provider: str,
        workspace_id: str,
        redirect_uri: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        scopes: list[str] | None = None,
        store: ConnectionStore | None = None,
    ) -> tuple[str, str, str]:
        """
        Creates an authorization URL and records pending OAuth state.
        Returns (auth_url, state, redirect_uri).
        """
        cls._cleanup_expired()
        spec = OAUTH_SPECS.get(provider)
        if not spec:
            raise ValueError(f"Provider '{provider}' does not support OAuth authorization.")

        res_cid, res_csec = cls.resolve_credentials(provider, workspace_id, store)
        cid = (client_id or res_cid).strip()
        csec = (client_secret or res_csec).strip()

        if not cid:
            raise ValueError(
                f"OAuth Client ID is required for {spec['name']}. Please complete the initial developer setup first."
            )
        if spec.get("requires_secret", True) and not csec:
            raise ValueError(
                f"OAuth Client Secret is required for {spec['name']}. Please complete the initial developer setup first."
            )

        # Legacy callers (manual redirect) may omit it; the one-click flow always passes its own loopback URI.
        r_uri = (redirect_uri or f"http://127.0.0.1:8000/api/connections/{provider}/oauth/callback").strip()
        state = secrets.token_urlsafe(32)
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)

        cls._states[state] = OAuthStateData(
            workspace_id=workspace_id,
            provider=provider,
            code_verifier=verifier,
            client_id=cid,
            client_secret=csec,
            redirect_uri=r_uri,
            created_at=time.time(),
        )

        effective_scopes = scopes or spec.get("scopes", [])

        if provider == "google_calendar":
            params = {
                "client_id": cid,
                "redirect_uri": r_uri,
                "response_type": "code",
                "scope": " ".join(effective_scopes),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
            }
            auth_url = f"{spec['auth_url']}?{urllib.parse.urlencode(params)}"

        elif provider == "github":
            params = {
                "client_id": cid,
                "redirect_uri": r_uri,
                "scope": ",".join(effective_scopes) if effective_scopes else "repo,read:user",
                "state": state,
                "allow_signup": "true",
            }
            auth_url = f"{spec['auth_url']}?{urllib.parse.urlencode(params)}"

        elif provider == "slack":
            params = {
                "client_id": cid,
                "redirect_uri": r_uri,
                "scope": ",".join(effective_scopes) if effective_scopes else "chat:write,channels:read,groups:read",
                "state": state,
            }
            auth_url = f"{spec['auth_url']}?{urllib.parse.urlencode(params)}"

        elif provider == "notion":
            params = {
                "client_id": cid,
                "redirect_uri": r_uri,
                "response_type": "code",
                "owner": "user",
                "state": state,
            }
            auth_url = f"{spec['auth_url']}?{urllib.parse.urlencode(params)}"

        elif spec.get("exchange") == "standard":
            params = {
                "client_id": cid, "redirect_uri": r_uri, "response_type": "code", "scope": " ".join(effective_scopes), "state": state,
                "code_challenge": challenge, "code_challenge_method": "S256",
            }
            auth_url = f"{spec['auth_url']}?{urllib.parse.urlencode(params)}"

        else:
            raise ValueError(f"Unsupported OAuth provider: {provider}")

        return auth_url, state, r_uri

    @classmethod
    def validate_and_consume_state(cls, state: str) -> OAuthStateData | None:
        """Validates and retrieves the state data, consuming it to prevent replay."""
        cls._cleanup_expired()
        data = cls._states.pop(state, None)
        if not data:
            return None
        if time.time() - data.created_at > cls.STATE_TTL_SECONDS:
            return None
        return data

    @classmethod
    def exchange_code(
        cls,
        provider: str,
        code: str,
        state_data: OAuthStateData,
    ) -> dict[str, Any]:
        """
        Exchanges authorization code for provider access tokens and retrieves user identity.
        """
        spec = OAUTH_SPECS.get(provider)
        if not spec:
            raise ValueError(f"Unknown provider '{provider}'")

        if provider == "google_calendar":
            from aether.connections.google_calendar import GoogleOAuthManager, OAuthStateData as GState
            g_state = GState(
                workspace_id=state_data.workspace_id,
                code_verifier=state_data.code_verifier,
                client_id=state_data.client_id,
                client_secret=state_data.client_secret,
                redirect_uri=state_data.redirect_uri,
                created_at=state_data.created_at,
            )
            return GoogleOAuthManager.exchange_code(code, g_state)

        elif provider == "github":
            # GitHub OAuth Code Exchange
            payload = {
                "client_id": state_data.client_id,
                "client_secret": state_data.client_secret,
                "code": code,
                "redirect_uri": state_data.redirect_uri,
            }
            req = urllib.request.Request(
                spec["token_url"],
                data=urllib.parse.urlencode(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "User-Agent": "Aether/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if "error" in data:
                desc = data.get("error_description") or data.get("error")
                raise RuntimeError(f"GitHub OAuth error: {desc}")

            access_token = data.get("access_token")
            if not access_token:
                raise RuntimeError("GitHub OAuth exchange did not return an access token.")

            return github_tokens(access_token, state_data.client_id, state_data.client_secret, data.get("scope", ""), data.get("token_type", "bearer"))

        elif provider == "slack":
            # Slack OAuth v2 Access Code Exchange
            payload = {
                "client_id": state_data.client_id,
                "client_secret": state_data.client_secret,
                "code": code,
                "redirect_uri": state_data.redirect_uri,
            }
            req = urllib.request.Request(
                spec["token_url"],
                data=urllib.parse.urlencode(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Aether/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if not data.get("ok"):
                err = data.get("error", "oauth_failed")
                raise RuntimeError(f"Slack OAuth error: {err}")

            access_token = data.get("access_token")
            team_info = data.get("team") or {}
            team_name = team_info.get("name") or "Slack Workspace"
            bot_user_id = data.get("bot_user_id") or ""

            return {
                "bot_token": access_token,
                "token": access_token,
                "team": team_name,
                "team_id": team_info.get("id"),
                "account_name": f"Slack ({team_name})",
                "bot_user_id": bot_user_id,
                "client_id": state_data.client_id,
                "client_secret": state_data.client_secret,
            }

        elif provider == "notion":
            # Notion OAuth Code Exchange
            basic = base64.b64encode(f"{state_data.client_id}:{state_data.client_secret}".encode("utf-8")).decode("ascii")
            body = json.dumps({
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": state_data.redirect_uri,
            }).encode("utf-8")

            req = urllib.request.Request(
                spec["token_url"],
                data=body,
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/json",
                    "Notion-Version": "2022-06-28",
                    "User-Agent": "Aether/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if "error" in data:
                raise RuntimeError(f"Notion OAuth error: {data.get('error')}")

            access_token = data.get("access_token")
            workspace_name = data.get("workspace_name") or "Notion Workspace"

            return {
                "token": access_token,
                "workspace_name": workspace_name,
                "workspace_id": data.get("workspace_id"),
                "bot_id": data.get("bot_id"),
                "account_name": f"Notion ({workspace_name})",
                "client_id": state_data.client_id,
                "client_secret": state_data.client_secret,
            }

        if spec.get("exchange") == "standard":
            payload = {"grant_type": "authorization_code", "code": code, "redirect_uri": state_data.redirect_uri,
                       "client_id": state_data.client_id, "code_verifier": state_data.code_verifier}
            if state_data.client_secret:
                payload["client_secret"] = state_data.client_secret
            req = urllib.request.Request(spec["token_url"], data=urllib.parse.urlencode(payload).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "Aether/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as http_err:  # providers explain a refusal in the body
                try:
                    data = json.loads(http_err.read().decode("utf-8"))
                except Exception:  # noqa: BLE001
                    data = {"error": f"HTTP {http_err.code}"}
            if "error" in data or not data.get("access_token"):
                raise RuntimeError(f"{spec['name']} OAuth error: {data.get('error_description') or data.get('error') or 'no access token'}")
            out = {"access_token": data["access_token"], "token": data["access_token"], "refresh_token": data.get("refresh_token", ""),
                   "token_type": data.get("token_type", "bearer"), "scope": data.get("scope", ""), "account_name": data.get("account_name") or spec["name"],
                   "client_id": state_data.client_id}
            if data.get("expires_in"):
                out["expires_at"] = time.time() + float(data["expires_in"])
            return out

        raise ValueError(f"Exchange not implemented for {provider}")
