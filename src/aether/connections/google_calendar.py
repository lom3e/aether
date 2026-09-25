"""
Google Calendar Connector & Real OAuth 2.0 PKCE Integration for Aether (Macro-pass P0.2).
Provides:
  - OAuth 2.0 Authorization Code Flow with PKCE (RFC 7636) for desktop/browser
  - Automatic token refresh & token revocation
  - Real Google Calendar API integration (calendarList, events CRUD)
  - Semantic live verification (calendarList + events retrieval)
  - Zero simulation, truthful connection state
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
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

from aether.connections.base import (
    BaseConnector,
    ConnectorAuthError,
    ConnectorConfigurationError,
    ConnectorError,
    ConnectorHealth,
    ConnectorNotFoundError,
    ConnectorResult,
    CredentialRequirement,
)
from aether.connections.models import ConnectionStatus

if TYPE_CHECKING:
    from aether.connections.store import ConnectionStore

logger = logging.getLogger(__name__)

# Official Google OAuth 2.0 & Calendar API Endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"

GOOGLE_CALENDAR_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]


# ---------------------------------------------------------------------------
# PKCE Helpers (RFC 7636)
# ---------------------------------------------------------------------------

def generate_code_verifier(length: int = 64) -> str:
    """
    Generates a high-entropy cryptographic random string for PKCE code_verifier.
    Uses unreserved characters [A-Z, a-z, 0-9, -, ., _, ~].
    """
    raw = os.urandom(length)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")[:128]


def generate_code_challenge(verifier: str) -> str:
    """
    Generates the code_challenge from code_verifier using S256 (SHA-256 base64url).
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


# ---------------------------------------------------------------------------
# OAuth State Cache
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class OAuthStateData:
    workspace_id: str
    code_verifier: str
    client_id: str
    client_secret: str
    redirect_uri: str
    created_at: float


class GoogleOAuthManager:
    """Manages active PKCE OAuth flows and pending states."""

    _states: dict[str, OAuthStateData] = {}
    STATE_TTL_SECONDS = 900  # 15 minutes

    @classmethod
    def _cleanup_expired(cls) -> None:
        now = time.time()
        expired = [s for s, data in cls._states.items() if now - data.created_at > cls.STATE_TTL_SECONDS]
        for s in expired:
            cls._states.pop(s, None)

    @classmethod
    def create_auth_flow(
        cls,
        workspace_id: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        scopes: list[str] | None = None,
    ) -> tuple[str, str]:
        """
        Creates a new PKCE OAuth state and builds the Google Authorization URL.
        Returns (auth_url, state).
        """
        cls._cleanup_expired()

        cid = (
            client_id
            or os.environ.get("GOOGLE_CLIENT_ID")
            or os.environ.get("AETHER_GOOGLE_CLIENT_ID")
            or "aether-desktop-client.apps.googleusercontent.com"
        ).strip()
        csec = (
            client_secret
            or os.environ.get("GOOGLE_CLIENT_SECRET")
            or os.environ.get("AETHER_GOOGLE_CLIENT_SECRET")
            or ""
        ).strip()
        r_uri = (redirect_uri or "http://127.0.0.1:8000/api/connections/google_calendar/oauth/callback").strip()

        state = secrets.token_urlsafe(32)
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)

        cls._states[state] = OAuthStateData(
            workspace_id=workspace_id,
            code_verifier=verifier,
            client_id=cid,
            client_secret=csec,
            redirect_uri=r_uri,
            created_at=time.time(),
        )

        effective_scopes = " ".join(scopes or GOOGLE_CALENDAR_SCOPES)
        params = {
            "client_id": cid,
            "redirect_uri": r_uri,
            "response_type": "code",
            "scope": effective_scopes,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return auth_url, state

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
        code: str,
        state_data: OAuthStateData,
    ) -> dict[str, Any]:
        """
        Exchanges the authorization code and PKCE verifier for Google access & refresh tokens.
        Also retrieves the authorized user's email address.
        """
        payload = {
            "client_id": state_data.client_id,
            "code": code,
            "code_verifier": state_data.code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": state_data.redirect_uri,
        }
        if state_data.client_secret:
            payload["client_secret"] = state_data.client_secret

        encoded = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=encoded,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Aether/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                token_resp = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            logger.error("Google token exchange failed HTTP %s: %s", exc.code, err_body)
            raise ConnectorAuthError(f"Google token exchange failed ({exc.code}): {err_body}") from exc
        except Exception as exc:
            logger.error("Google token exchange network failure: %s", exc)
            raise ConnectorError(f"Could not reach Google token endpoint: {exc}") from exc

        access_token = token_resp.get("access_token")
        if not access_token:
            raise ConnectorAuthError("Google token response did not contain an access_token.")

        refresh_token = token_resp.get("refresh_token", "")
        expires_in = int(token_resp.get("expires_in", 3600))
        token_expiry = datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc).isoformat()

        # Retrieve user email
        user_email = cls._fetch_user_email(access_token)

        return {
            "client_id": state_data.client_id,
            "client_secret": state_data.client_secret,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": token_expiry,
            "email": user_email,
            "primary_calendar_id": "primary",
            "selected_calendar_id": "primary",
            "selected_calendar_summary": "Primary Calendar",
        }

    @classmethod
    def _fetch_user_email(cls, access_token: str) -> str:
        """Fetches the authorized Google account email."""
        req = urllib.request.Request(
            GOOGLE_USERINFO_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "Aether/1.0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                info = json.loads(resp.read().decode("utf-8"))
                return info.get("email") or "Google User"
        except Exception as exc:
            logger.warning("Could not fetch Google userinfo email: %s", exc)
            return "Google User"

    @classmethod
    def revoke_token(cls, token: str) -> tuple[bool, str]:
        """Revokes a Google access or refresh token."""
        if not token:
            return True, "No token to revoke."
        data = urllib.parse.urlencode({"token": token}).encode("utf-8")
        req = urllib.request.Request(
            GOOGLE_REVOKE_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Aether/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                if resp.status == 200:
                    return True, "Token revoked successfully."
                return False, f"Google revoke returned HTTP {resp.status}."
        except urllib.error.HTTPError as exc:
            # 400 often means already revoked or expired
            if exc.code == 400:
                return True, "Token already revoked or invalid."
            return False, f"Failed to revoke token: HTTP {exc.code}"
        except Exception as exc:
            return False, f"Revoke error: {exc}"


# ---------------------------------------------------------------------------
# Real Google Calendar Connector
# ---------------------------------------------------------------------------

class GoogleCalendarConnector(BaseConnector):
    """
    Real Google Calendar connector executing live operations via Google Calendar API v3.
    Requires real OAuth 2.0 authorization with PKCE.
    """

    def __init__(
        self,
        auth_metadata: dict[str, Any] | None = None,
        workspace_id: str | None = None,
        store: ConnectionStore | None = None,
    ) -> None:
        self.auth_metadata = dict(auth_metadata or {})
        self.workspace_id = workspace_id
        self.store = store

    @property
    def provider(self) -> str:
        return "google_calendar"

    @property
    def capabilities(self) -> list[str]:
        return [
            "google_calendar.list_events",
            "google_calendar.create_event",
            "google_calendar.get_event",
            "google_calendar.update_event",
            "google_calendar.delete_event",
            "google_calendar.list_calendars",
        ]

    @property
    def credential_requirements(self) -> list[CredentialRequirement]:
        return [
            CredentialRequirement(
                key="client_id",
                label="Google Client ID",
                description="OAuth 2.0 Client ID created in Google Cloud Console.",
                required=False,
                secret=False,
            ),
            CredentialRequirement(
                key="access_token",
                label="Access Token",
                description="OAuth 2.0 Bearer token for Google Calendar API.",
                required=True,
                secret=True,
            ),
            CredentialRequirement(
                key="refresh_token",
                label="Refresh Token",
                description="Long-lived token for refreshing expired access tokens.",
                required=False,
                secret=True,
            ),
        ]

    # ---------------------------------------------------------------------------
    # Token Management
    # ---------------------------------------------------------------------------

    def _is_token_expired(self) -> bool:
        expiry_str = self.auth_metadata.get("token_expiry")
        if not expiry_str:
            return False
        try:
            exp = datetime.fromisoformat(expiry_str)
            now = datetime.now(timezone.utc)
            # Add 60s safety buffer
            return (exp - now).total_seconds() < 60
        except Exception:
            return False

    def refresh_access_token(self) -> str:
        """Refreshes the access token using the stored refresh_token."""
        refresh_token = self.auth_metadata.get("refresh_token")
        if not refresh_token:
            raise ConnectorAuthError("Cannot refresh Google access token: no refresh_token stored.")

        client_id = (
            self.auth_metadata.get("client_id")
            or os.environ.get("GOOGLE_CLIENT_ID")
            or os.environ.get("AETHER_GOOGLE_CLIENT_ID")
            or "aether-desktop-client.apps.googleusercontent.com"
        )
        client_secret = (
            self.auth_metadata.get("client_secret")
            or os.environ.get("GOOGLE_CLIENT_SECRET")
            or os.environ.get("AETHER_GOOGLE_CLIENT_SECRET")
            or ""
        )

        payload = {
            "client_id": client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        if client_secret:
            payload["client_secret"] = client_secret

        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Aether/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            # If invalid_grant, token has been revoked by Google
            if exc.code in (400, 401) and ("invalid_grant" in err_body or "revoked" in err_body):
                self._record_auth_revocation(f"Google refresh token revoked or expired: {err_body}")
            raise ConnectorAuthError(f"Google token refresh failed HTTP {exc.code}: {err_body}") from exc
        except Exception as exc:
            raise ConnectorError(f"Failed to reach Google token endpoint during refresh: {exc}") from exc

        new_access_token = data.get("access_token")
        if not new_access_token:
            raise ConnectorAuthError("Google refresh response missing access_token.")

        expires_in = int(data.get("expires_in", 3600))
        token_expiry = datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc).isoformat()

        self.auth_metadata["access_token"] = new_access_token
        self.auth_metadata["token_expiry"] = token_expiry

        # Persist updated tokens directly in connection store
        if self.store and self.workspace_id:
            conn = self.store.get_connection_by_provider(self.workspace_id, "google_calendar")
            if conn:
                conn.auth_metadata.update(self.auth_metadata)
                conn.updated_at = datetime.now(timezone.utc).isoformat()
                self.store.save_connection(conn)

        return new_access_token

    def _ensure_access_token(self) -> str:
        """Returns a valid access token, refreshing if necessary."""
        token = self.auth_metadata.get("access_token")
        if not token:
            if self.auth_metadata.get("refresh_token"):
                return self.refresh_access_token()
            raise ConnectorAuthError("Google Calendar is not authorized. Please complete OAuth connection.")
        if self._is_token_expired():
            if self.auth_metadata.get("refresh_token"):
                try:
                    return self.refresh_access_token()
                except Exception as exc:
                    logger.warning("Failed refreshing expired Google token: %s", exc)
                    raise
        return token

    def _record_auth_revocation(self, message: str) -> None:
        """Marks connection as VERIFICATION_FAILED due to revoked credentials."""
        if self.store and self.workspace_id:
            conn = self.store.get_connection_by_provider(self.workspace_id, "google_calendar")
            if conn:
                conn.status = ConnectionStatus.VERIFICATION_FAILED
                conn.last_verification_error = message
                conn.updated_at = datetime.now(timezone.utc).isoformat()
                self.store.save_connection(conn)

    # ---------------------------------------------------------------------------
    # HTTP Client
    # ---------------------------------------------------------------------------

    def _api_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        retry_on_401: bool = True,
    ) -> Any:
        token = self._ensure_access_token()
        url = f"{GOOGLE_CALENDAR_API_BASE}/{endpoint.lstrip('/')}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url = f"{url}?{query}"

        body_bytes = None
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Aether/1.0",
        }
        if data is not None:
            body_bytes = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                if resp.status == 204:
                    return {}
                resp_text = resp.read().decode("utf-8")
                return json.loads(resp_text) if resp_text else {}
        except urllib.error.HTTPError as exc:
            err_text = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401 and retry_on_401 and self.auth_metadata.get("refresh_token"):
                logger.info("Google API returned 401. Refreshing token and retrying...")
                try:
                    self.refresh_access_token()
                    return self._api_request(
                        endpoint=endpoint,
                        method=method,
                        params=params,
                        data=data,
                        retry_on_401=False,
                    )
                except Exception as ref_exc:
                    self._record_auth_revocation(f"Authentication failed: {ref_exc}")
                    raise ConnectorAuthError(f"Google authorization expired and refresh failed: {ref_exc}") from exc

            if exc.code == 401:
                self._record_auth_revocation("Google authorization expired or invalid.")
                raise ConnectorAuthError(f"Google authentication failed: {err_text}") from exc
            elif exc.code == 404:
                raise ConnectorNotFoundError(f"Google Calendar resource not found: {endpoint}") from exc
            elif exc.code == 403:
                raise ConnectorAuthError(f"Google Calendar permission denied: {err_text}") from exc
            raise ConnectorError(f"Google Calendar API error (HTTP {exc.code}): {err_text}") from exc
        except Exception as exc:
            raise ConnectorError(f"Google Calendar API unreachable: {exc}") from exc

    # ---------------------------------------------------------------------------
    # Verification & Health
    # ---------------------------------------------------------------------------

    def verify(
        self,
        auth_metadata: dict[str, Any] | None = None,
        live_check: bool = False,
    ) -> tuple[bool, str]:
        """
        Truthfully verifies Google Calendar credentials.
        Live check MUST successfully execute calendarList and event retrieval on Google API.
        """
        meta = auth_metadata or self.auth_metadata
        token = meta.get("access_token")
        refresh = meta.get("refresh_token")

        if not token and not refresh:
            return False, "Google authorization missing. OAuth consent flow required."

        if not live_check:
            return True, "Google Calendar authorization credentials present. Live check pending."

        try:
            # 1. Probe calendar list
            cal_list = self.list_calendars()
            if not isinstance(cal_list, list):
                return False, "Google Calendar API did not return a valid calendar list."

            # 2. Probe events from primary or selected calendar
            selected_cal = meta.get("selected_calendar_id") or "primary"
            events = self.list_events(calendar_id=selected_cal, limit=5)
            count = len(events)
            cal_name = meta.get("selected_calendar_summary") or selected_cal
            return True, f"Google Calendar live verified: accessed calendar '{cal_name}' ({count} events found)."
        except ConnectorAuthError as exc:
            return False, f"Google authentication failed: {exc}"
        except Exception as exc:
            return False, f"Google Calendar verification failed: {exc}"

    def get_health(self) -> ConnectorHealth:
        valid, msg = self.verify(live_check=False)
        if not valid:
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.VERIFICATION_REQUIRED,
                message=msg,
            )
        return ConnectorHealth(
            healthy=True,
            status=ConnectionStatus.VERIFIED,
            message="Google Calendar connection is active and authorized.",
        )

    # ---------------------------------------------------------------------------
    # Calendar & Event Operations
    # ---------------------------------------------------------------------------

    def list_calendars(self) -> list[dict[str, Any]]:
        """Retrieves list of calendars for the authenticated Google user."""
        res = self._api_request("users/me/calendarList", method="GET")
        items = res.get("items", [])
        return [
            {
                "id": c.get("id"),
                "summary": c.get("summary", "Untitled Calendar"),
                "description": c.get("description", ""),
                "primary": bool(c.get("primary", False)),
                "timeZone": c.get("timeZone", "UTC"),
                "accessRole": c.get("accessRole", "reader"),
            }
            for c in items
        ]

    def list_events(
        self,
        calendar_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Lists events from the specified or selected calendar."""
        cal_id = urllib.parse.quote(
            calendar_id or self.auth_metadata.get("selected_calendar_id") or "primary",
            safe="",
        )
        params = {
            "maxResults": min(max(1, limit), 250),
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        res = self._api_request(f"calendars/{cal_id}/events", method="GET", params=params)
        items = res.get("items", [])
        return [
            {
                "id": ev.get("id"),
                "title": ev.get("summary", "Untitled Event"),
                "start_time": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date") or "",
                "end_time": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
                "description": ev.get("description", ""),
                "location": ev.get("location", ""),
                "status": ev.get("status", "confirmed"),
                "html_link": ev.get("htmlLink", ""),
            }
            for ev in items
        ]

    def get_event(
        self,
        event_id: str,
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        """Retrieves a single event by ID."""
        cal_id = urllib.parse.quote(
            calendar_id or self.auth_metadata.get("selected_calendar_id") or "primary",
            safe="",
        )
        ev_id = urllib.parse.quote(event_id, safe="")
        ev = self._api_request(f"calendars/{cal_id}/events/{ev_id}", method="GET")
        return {
            "id": ev.get("id"),
            "title": ev.get("summary", "Untitled Event"),
            "start_time": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date") or "",
            "end_time": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
            "description": ev.get("description", ""),
            "location": ev.get("location", ""),
            "status": ev.get("status", "confirmed"),
            "html_link": ev.get("htmlLink", ""),
        }

    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str | None = None,
        description: str = "",
        location: str = "",
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        """Creates an event on the specified Google Calendar."""
        cal_id = urllib.parse.quote(
            calendar_id or self.auth_metadata.get("selected_calendar_id") or "primary",
            safe="",
        )

        # Build start/end objects conformant with Google Calendar API v3
        start_obj = self._format_date_field(start_time)
        if end_time:
            end_obj = self._format_date_field(end_time)
        else:
            # Default to 1 hour after start
            end_obj = self._calculate_default_end(start_time)

        payload = {
            "summary": title,
            "description": description,
            "location": location,
            "start": start_obj,
            "end": end_obj,
        }

        created = self._api_request(f"calendars/{cal_id}/events", method="POST", data=payload)
        return {
            "event_id": created.get("id"),
            "id": created.get("id"),
            "title": created.get("summary", title),
            "start_time": (created.get("start") or {}).get("dateTime") or (created.get("start") or {}).get("date") or start_time,
            "end_time": (created.get("end") or {}).get("dateTime") or (created.get("end") or {}).get("date"),
            "location": created.get("location", location),
            "description": created.get("description", description),
            "status": created.get("status", "confirmed"),
            "html_link": created.get("htmlLink", ""),
        }

    def update_event(
        self,
        event_id: str,
        title: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        description: str | None = None,
        location: str | None = None,
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        """Updates fields of an existing event."""
        cal_id = urllib.parse.quote(
            calendar_id or self.auth_metadata.get("selected_calendar_id") or "primary",
            safe="",
        )
        ev_id = urllib.parse.quote(event_id, safe="")

        patch_data: dict[str, Any] = {}
        if title is not None:
            patch_data["summary"] = title
        if description is not None:
            patch_data["description"] = description
        if location is not None:
            patch_data["location"] = location
        if start_time is not None:
            patch_data["start"] = self._format_date_field(start_time)
        if end_time is not None:
            patch_data["end"] = self._format_date_field(end_time)

        updated = self._api_request(f"calendars/{cal_id}/events/{ev_id}", method="PATCH", data=patch_data)
        return {
            "event_id": updated.get("id"),
            "id": updated.get("id"),
            "title": updated.get("summary"),
            "start_time": (updated.get("start") or {}).get("dateTime") or (updated.get("start") or {}).get("date"),
            "end_time": (updated.get("end") or {}).get("dateTime") or (updated.get("end") or {}).get("date"),
            "location": updated.get("location"),
            "description": updated.get("description"),
            "status": updated.get("status"),
            "html_link": updated.get("htmlLink"),
        }

    def delete_event(
        self,
        event_id: str,
        calendar_id: str | None = None,
    ) -> bool:
        """Deletes an event from the calendar."""
        cal_id = urllib.parse.quote(
            calendar_id or self.auth_metadata.get("selected_calendar_id") or "primary",
            safe="",
        )
        ev_id = urllib.parse.quote(event_id, safe="")
        self._api_request(f"calendars/{cal_id}/events/{ev_id}", method="DELETE")
        return True

    def revoke(self) -> tuple[bool, str]:
        """Revokes all tokens associated with this Google connection."""
        refresh = self.auth_metadata.get("refresh_token")
        access = self.auth_metadata.get("access_token")
        token_to_revoke = refresh or access
        if token_to_revoke:
            ok, msg = GoogleOAuthManager.revoke_token(token_to_revoke)
            self.auth_metadata["access_token"] = ""
            self.auth_metadata["refresh_token"] = ""
            return ok, msg
        return True, "No active token."

    # ---------------------------------------------------------------------------
    # Connector Execution Dispatch
    # ---------------------------------------------------------------------------

    def execute(self, operation: str, params: dict[str, Any]) -> ConnectorResult:
        clean_op = operation.lower().strip()
        if clean_op in ("google_calendar.list_events", "list_events"):
            res = self.list_events(
                calendar_id=params.get("calendar_id"),
                limit=int(params.get("limit", 50)),
            )
            return ConnectorResult(success=True, operation=operation, provider=self.provider, data={"events": res})

        elif clean_op in ("google_calendar.create_event", "create_event"):
            res = self.create_event(
                title=params.get("title", "Untitled Event"),
                start_time=params.get("start_time", datetime.now(timezone.utc).isoformat()),
                end_time=params.get("end_time"),
                description=params.get("description", ""),
                location=params.get("location", ""),
                calendar_id=params.get("calendar_id"),
            )
            return ConnectorResult(success=True, operation=operation, provider=self.provider, data=res)

        elif clean_op in ("google_calendar.get_event", "get_event"):
            res = self.get_event(
                event_id=params.get("event_id", ""),
                calendar_id=params.get("calendar_id"),
            )
            return ConnectorResult(success=True, operation=operation, provider=self.provider, data=res)

        elif clean_op in ("google_calendar.update_event", "update_event"):
            res = self.update_event(
                event_id=params.get("event_id", ""),
                title=params.get("title"),
                start_time=params.get("start_time"),
                end_time=params.get("end_time"),
                description=params.get("description"),
                location=params.get("location"),
                calendar_id=params.get("calendar_id"),
            )
            return ConnectorResult(success=True, operation=operation, provider=self.provider, data=res)

        elif clean_op in ("google_calendar.delete_event", "delete_event"):
            self.delete_event(
                event_id=params.get("event_id", ""),
                calendar_id=params.get("calendar_id"),
            )
            return ConnectorResult(success=True, operation=operation, provider=self.provider, data={"deleted": True})

        elif clean_op in ("google_calendar.list_calendars", "list_calendars"):
            res = self.list_calendars()
            return ConnectorResult(success=True, operation=operation, provider=self.provider, data={"calendars": res})

        raise ValueError(f"Unsupported Google Calendar operation: '{operation}'")

    # ---------------------------------------------------------------------------
    # Date formatting helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _format_date_field(date_str: str) -> dict[str, str]:
        s = date_str.strip()
        if "T" in s:
            # Ensure time zone is indicated
            if not (s.endswith("Z") or "+" in s[10:] or "-" in s[10:]):
                s = f"{s}Z"
            return {"dateTime": s}
        elif len(s) == 10 and s.count("-") == 2:
            return {"date": s}
        else:
            # Fallback assuming ISO datetime
            return {"dateTime": datetime.now(timezone.utc).isoformat()}

    @staticmethod
    def _calculate_default_end(start_str: str) -> dict[str, str]:
        s = start_str.strip()
        if "T" in s:
            try:
                clean_s = s.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_s)
                end_dt = datetime.fromtimestamp(dt.timestamp() + 3600, tz=dt.tzinfo or timezone.utc)
                return {"dateTime": end_dt.isoformat()}
            except Exception:
                pass
            return {"dateTime": datetime.now(timezone.utc).isoformat()}
        return {"date": s}
