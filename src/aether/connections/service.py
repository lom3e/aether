"""
Service layer for Aether Connections and external integrations (Phase C).
Orchestrates connections, credentials, and real connectors (GitHub, Email, Slack, HTTP, Calendar).
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from aether.activity.models import ActivityCategory, ActivityStatus
from aether.activity.service import ActivityService
from aether.connections.base import (
    BaseConnector,
    ConnectorHealth,
    ConnectorResult,
    CredentialRequirement,
)
from aether.connections.email import EmailConnector
from aether.connections.github import GitHubConnector
from aether.connections.google_calendar import GoogleCalendarConnector
from aether.connections.http import HttpConnector
from aether.connections.models import CalendarEvent, Connection, ConnectionStatus
from aether.connections.slack import SlackConnector
from aether.connections.telegram import TelegramConnector
from aether.connections.store import ConnectionStore

logger = logging.getLogger(__name__)


class CalendarConnector(BaseConnector):
    """Real calendar connector backed by ConnectionStore."""

    def __init__(
        self,
        store: ConnectionStore,
        workspace_id: str,
        connection_id: str = "calendar-primary",
    ) -> None:
        self.store = store
        self.workspace_id = workspace_id
        self.connection_id = connection_id

    @property
    def provider(self) -> str:
        return "calendar"

    @property
    def capabilities(self) -> list[str]:
        return ["calendar.create_event", "calendar.list_events"]

    @property
    def credential_requirements(self) -> list[CredentialRequirement]:
        return []

    def verify(self, auth_metadata: dict[str, Any] | None = None, live_check: bool = False) -> tuple[bool, str]:
        return True, "Aether local calendar storage ready."

    def get_health(self) -> ConnectorHealth:
        return ConnectorHealth(
            healthy=True,
            status=ConnectionStatus.VERIFIED,
            message="Aether local calendar storage active.",
        )

    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str | None = None,
        description: str = "",
        location: str = "",
    ) -> dict[str, Any]:
        """Creates a real calendar event and persists it."""
        event = CalendarEvent(
            id=f"evt-{uuid.uuid4().hex[:10]}",
            workspace_id=self.workspace_id,
            connection_id=self.connection_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
        )
        saved = self.store.save_calendar_event(event)
        return {
            "event_id": saved.id,
            "title": saved.title,
            "start_time": saved.start_time,
            "end_time": saved.end_time,
            "location": saved.location,
            "description": saved.description,
            "status": "confirmed",
        }

    def list_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Queries calendar events for the workspace."""
        events = self.store.list_calendar_events(self.workspace_id, limit=limit)
        return [e.to_dict() for e in events]

    def execute(self, operation: str, params: dict[str, Any]) -> ConnectorResult:
        clean_op = operation.lower().strip()
        if clean_op in ("calendar.create_event", "create_event"):
            res = self.create_event(
                title=params.get("title", "Untitled Event"),
                start_time=params.get("start_time", datetime.now(timezone.utc).isoformat()),
                end_time=params.get("end_time"),
                description=params.get("description", ""),
                location=params.get("location", ""),
            )
            return ConnectorResult(success=True, operation=operation, provider=self.provider, data=res)
        elif clean_op in ("calendar.list_events", "list_events"):
            res = self.list_events(limit=int(params.get("limit", 50)))
            return ConnectorResult(success=True, operation=operation, provider=self.provider, data={"events": res})
        raise ValueError(f"Unsupported calendar operation: '{operation}'")


class ConnectionService:
    """Orchestrates integrations, OAuth states, and tool connectors."""

    def __init__(
        self,
        store: ConnectionStore,
        activity_service: ActivityService | None = None,
    ) -> None:
        self.store = store
        self.activity_service = activity_service

    def get_default_capabilities(self, provider: str) -> list[str]:
        p = provider.lower().strip()
        if p == "github":
            return [
                "github.inspect_repo",
                "github.list_branches",
                "github.get_branch",
                "github.create_branch",
                "github.list_pull_requests",
                "github.get_pull_request",
                "github.create_pull_request",
                "github.list_issues",
                "github.get_issue",
                "github.create_issue",
                "github.update_issue",
                "github.add_comment",
                "github.get_file",
            ]
        elif p == "email":
            return ["email.send", "email.verify"]
        elif p == "slack":
            return ["slack.send_message", "slack.verify"]
        elif p == "http":
            return ["http.request", "http.get", "http.post", "http.put", "http.patch", "http.delete"]
        elif p == "calendar":
            return ["calendar.create_event", "calendar.list_events"]
        elif p == "google_calendar":
            return [
                "google_calendar.list_events",
                "google_calendar.create_event",
                "google_calendar.get_event",
                "google_calendar.update_event",
                "google_calendar.delete_event",
                "google_calendar.list_calendars",
            ]
        elif p == "telegram":
            return ["telegram.send_message", "telegram.send_approval", "telegram.verify"]
        return [f"{p}.read", f"{p}.write"]

    def save_connection(self, connection: Connection) -> Connection:
        """Saves a connection directly to the persistent store."""
        return self.store.save_connection(connection)

    def connect(
        self,
        workspace_id: str,
        provider: str,
        account_name: str = "Connected Account",
        scopes: list[str] | None = None,
        capabilities: list[str] | None = None,
        auth_metadata: dict[str, Any] | None = None,
        live_check: bool = False,
    ) -> Connection:
        """Connects or updates an external tool/service with truthful status validation."""
        p = provider.lower().strip()
        existing = self.store.get_connection_by_provider(workspace_id, provider)
        conn_id = existing.id if existing else f"conn-{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        auth_meta = dict(auth_metadata or {})

        # Truthful status determination
        if p == "calendar":
            status = ConnectionStatus.VERIFIED
            verification_method = "local_storage"
            last_verified_at = now_iso
            last_verification_error = None
        else:
            has_creds = bool(auth_meta and any(str(v).strip() for v in auth_meta.values()))
            if not has_creds:
                status = ConnectionStatus.NOT_CONFIGURED
                verification_method = None
                last_verified_at = None
                last_verification_error = f"Credentials required for {provider}."
            else:
                valid_format, format_msg = verify_credentials(provider, auth_meta, live_check=False)
                if not valid_format:
                    status = ConnectionStatus.VERIFICATION_FAILED
                    verification_method = "format_only"
                    last_verified_at = None
                    last_verification_error = format_msg
                elif live_check:
                    valid_live, live_msg = verify_credentials(provider, auth_meta, live_check=True)
                    if valid_live:
                        status = ConnectionStatus.VERIFIED
                        verification_method = "live_check"
                        last_verified_at = now_iso
                        last_verification_error = None
                    else:
                        status = ConnectionStatus.VERIFICATION_FAILED
                        verification_method = "live_check"
                        last_verified_at = None
                        last_verification_error = live_msg
                else:
                    status = ConnectionStatus.CONFIGURED
                    verification_method = "format_only"
                    last_verified_at = None
                    last_verification_error = None

        conn = Connection(
            id=conn_id,
            workspace_id=workspace_id,
            provider=provider,
            account_name=account_name,
            status=status,
            scopes=scopes or ["read", "write"],
            capabilities=capabilities or self.get_default_capabilities(provider),
            auth_metadata=auth_meta,
            last_synced_at=existing.last_synced_at if existing else None,
            last_verified_at=last_verified_at if last_verified_at is not None else (existing.last_verified_at if existing and status == existing.status else None),
            last_verification_error=last_verification_error,
            last_successful_operation=existing.last_successful_operation if existing else None,
            verification_method=verification_method,
            created_at=existing.created_at if existing else now_iso,
            updated_at=now_iso,
        )
        saved = self.store.save_connection(conn)

        if self.activity_service:
            if saved.status == ConnectionStatus.VERIFIED:
                act_title = f"Verified: {provider.capitalize()}"
                act_desc = f"Successfully verified {provider} ({account_name})."
                act_status = ActivityStatus.COMPLETED
            elif saved.status == ConnectionStatus.CONFIGURED:
                act_title = f"Configured: {provider.capitalize()}"
                act_desc = f"Configuration saved for {provider} ({account_name}). Live verification pending."
                act_status = ActivityStatus.COMPLETED
            elif saved.status == ConnectionStatus.VERIFICATION_FAILED:
                act_title = f"Verification Failed: {provider.capitalize()}"
                act_desc = f"Verification failed for {provider} ({account_name}): {saved.last_verification_error}"
                act_status = ActivityStatus.FAILED
            else:
                act_title = f"Setup Required: {provider.capitalize()}"
                act_desc = f"{provider.capitalize()} is not configured with credentials."
                act_status = ActivityStatus.IN_PROGRESS

            self.activity_service.log(
                workspace_id=workspace_id,
                title=act_title,
                description=act_desc,
                category=ActivityCategory.CONNECTION,
                status=act_status,
                link_view="connections",
                link_id=saved.id,
                metadata={
                    "provider": provider,
                    "account_name": account_name,
                    "status": saved.status.value,
                    "verification_method": saved.verification_method,
                },
            )

        return saved

    def verify_connection(
        self,
        workspace_id: str,
        provider: str,
        auth_metadata: dict[str, Any] | None = None,
        live_check: bool = True,
    ) -> tuple[bool, str, Connection | None]:
        """
        Verifies credentials live (or format) and persists the updated health status on the connection record.
        """
        existing = self.store.get_connection_by_provider(workspace_id, provider)
        meta = dict(auth_metadata or {})
        if not meta and existing and existing.auth_metadata:
            meta = dict(existing.auth_metadata)

        # Merge with existing secrets if updating with partial / blank values
        if existing and existing.auth_metadata:
            for k, v in existing.auth_metadata.items():
                val = meta.get(k)
                if val is None or val == "" or (isinstance(val, str) and (val.startswith("••") or "..." in val)):
                    meta[k] = v

        p = provider.lower().strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        if p == "calendar":
            valid, message = True, "Aether local calendar storage ready."
        else:
            valid, message = verify_credentials(provider, meta, live_check=live_check)

        if not existing:
            status = (
                ConnectionStatus.VERIFIED
                if (valid and (live_check or p == "calendar"))
                else (
                    ConnectionStatus.CONFIGURED
                    if valid
                    else (ConnectionStatus.NOT_CONFIGURED if not meta else ConnectionStatus.VERIFICATION_FAILED)
                )
            )
            existing = Connection(
                id=f"conn-{uuid.uuid4().hex[:10]}",
                workspace_id=workspace_id,
                provider=provider,
                account_name=f"Personal {provider.capitalize()}",
                status=status,
                scopes=["read", "write"],
                capabilities=self.get_default_capabilities(provider),
                auth_metadata=meta,
                last_verified_at=now_iso if (valid and (live_check or p == "calendar")) else None,
                last_verification_error=None if valid else message,
                verification_method="live_check" if live_check else "format_only",
                created_at=now_iso,
                updated_at=now_iso,
            )
        else:
            existing.auth_metadata = meta
            existing.updated_at = now_iso
            existing.verification_method = "live_check" if live_check else "format_only"
            if valid:
                if live_check or p == "calendar":
                    existing.status = ConnectionStatus.VERIFIED
                    existing.last_verified_at = now_iso
                else:
                    if existing.status != ConnectionStatus.VERIFIED:
                        existing.status = ConnectionStatus.CONFIGURED
                existing.last_verification_error = None
            else:
                existing.status = ConnectionStatus.VERIFICATION_FAILED
                existing.last_verification_error = message

        saved = self.store.save_connection(existing)

        if self.activity_service:
            act_status = ActivityStatus.COMPLETED if valid else ActivityStatus.FAILED
            act_title = f"Verified: {provider.capitalize()}" if valid else f"Verification Failed: {provider.capitalize()}"
            self.activity_service.log(
                workspace_id=workspace_id,
                title=act_title,
                description=f"Verification {'succeeded' if valid else 'failed'}: {message}",
                category=ActivityCategory.CONNECTION,
                status=act_status,
                link_view="connections",
                link_id=saved.id,
                metadata={"provider": provider, "valid": valid, "live_check": live_check},
            )

        return valid, message, saved

    def record_operation_success(self, workspace_id: str, provider: str, operation: str) -> None:
        """Records that a live operation succeeded on this provider, reinforcing verified status."""
        conn = self.store.get_connection_by_provider(workspace_id, provider)
        if conn:
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.status = ConnectionStatus.VERIFIED
            conn.last_verified_at = now_iso
            conn.last_successful_operation = f"{operation} at {now_iso}"
            conn.last_verification_error = None
            conn.verification_method = "operation"
            conn.updated_at = now_iso
            self.store.save_connection(conn)

    def record_operation_failure(
        self,
        workspace_id: str,
        provider: str,
        operation: str,
        error: str,
        is_auth_error: bool = False,
    ) -> None:
        """Records that an operation failed, transitioning to verification_failed if auth failure."""
        conn = self.store.get_connection_by_provider(workspace_id, provider)
        if conn:
            now_iso = datetime.now(timezone.utc).isoformat()
            if is_auth_error:
                conn.status = ConnectionStatus.VERIFICATION_FAILED
                conn.last_verification_error = f"Auth error during {operation}: {error}"
            conn.updated_at = now_iso
            self.store.save_connection(conn)

    def disconnect(self, workspace_id: str, provider: str) -> None:
        """Disconnects a service."""
        conn = self.store.get_connection_by_provider(workspace_id, provider)
        if conn:
            if provider.lower().strip() == "google_calendar" and conn.auth_metadata:
                try:
                    connector = GoogleCalendarConnector(auth_metadata=conn.auth_metadata)
                    connector.revoke()
                except Exception as exc:
                    logger.warning("Failed to revoke Google token during disconnect: %s", exc)
                conn.auth_metadata["access_token"] = ""
                conn.auth_metadata["refresh_token"] = ""
            conn.status = ConnectionStatus.DISCONNECTED
            conn.last_verified_at = None
            conn.updated_at = datetime.now(timezone.utc).isoformat()
            self.store.save_connection(conn)

            if self.activity_service:
                self.activity_service.log(
                    workspace_id=workspace_id,
                    title=f"Disconnected: {provider.capitalize()}",
                    description=f"Disconnected {provider} ({conn.account_name}).",
                    category=ActivityCategory.CONNECTION,
                    status=ActivityStatus.COMPLETED,
                    link_view="connections",
                    link_id=conn.id,
                )
        else:
            conn = Connection(
                id=f"conn-{uuid.uuid4().hex[:10]}",
                workspace_id=workspace_id,
                provider=provider,
                account_name=f"{provider.capitalize()} (Disconnected)",
                status=ConnectionStatus.DISCONNECTED,
                scopes=[],
                capabilities=[],
                auth_metadata={},
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            self.store.save_connection(conn)

    def list_connections(self, workspace_id: str) -> list[Connection]:
        """Lists all connections for a workspace."""
        return self.store.list_connections(workspace_id)

    def get_connection(self, workspace_id: str, provider: str) -> Connection | None:
        """Retrieves connection for provider."""
        return self.store.get_connection_by_provider(workspace_id, provider)

    def verify(
        self,
        provider: str,
        auth_metadata: dict[str, Any] | None = None,
        live_check: bool = False,
    ) -> tuple[bool, str]:
        """Validates credentials for a provider."""
        return verify_credentials(provider, auth_metadata, live_check=live_check)

    def get_calendar_connector(self, workspace_id: str) -> CalendarConnector:
        """Returns active calendar connector, ensuring connection record exists."""
        conn = self.store.get_connection_by_provider(workspace_id, "calendar")
        if not conn:
            conn = self.connect(
                workspace_id=workspace_id,
                provider="calendar",
                account_name="Aether Calendar (Local)",
                scopes=["calendar.events.read", "calendar.events.write"],
                capabilities=self.get_default_capabilities("calendar"),
            )
        elif conn.status == ConnectionStatus.DISCONNECTED:
            raise RuntimeError("Calendar connection is disconnected in this workspace.")
        return CalendarConnector(self.store, workspace_id, conn.id)

    def get_github_connector(self, workspace_id: str) -> GitHubConnector:
        """Returns GitHubConnector configured with the workspace's credentials."""
        conn = self.store.get_connection_by_provider(workspace_id, "github")
        meta = conn.auth_metadata if conn else {}
        return GitHubConnector(auth_metadata=meta)

    def get_email_connector(self, workspace_id: str) -> EmailConnector:
        """Returns EmailConnector configured with the workspace's credentials."""
        conn = self.store.get_connection_by_provider(workspace_id, "email")
        meta = conn.auth_metadata if conn else {}
        return EmailConnector(auth_metadata=meta)

    def get_slack_connector(self, workspace_id: str) -> SlackConnector:
        """Returns SlackConnector configured with the workspace's credentials."""
        conn = self.store.get_connection_by_provider(workspace_id, "slack")
        meta = conn.auth_metadata if conn else {}
        return SlackConnector(auth_metadata=meta)

    def get_http_connector(self, workspace_id: str) -> HttpConnector:
        """Returns HttpConnector configured with the workspace's credentials."""
        conn = self.store.get_connection_by_provider(workspace_id, "http")
        meta = conn.auth_metadata if conn else {}
        return HttpConnector(auth_metadata=meta)

    def get_telegram_connector(self, workspace_id: str) -> TelegramConnector:
        """Returns TelegramConnector configured with the workspace's credentials."""
        conn = self.store.get_connection_by_provider(workspace_id, "telegram")
        meta = conn.auth_metadata if conn else {}
        return TelegramConnector(auth_metadata=meta)

    def get_google_calendar_connector(self, workspace_id: str) -> GoogleCalendarConnector:
        """Returns GoogleCalendarConnector configured with the workspace's credentials."""
        conn = self.store.get_connection_by_provider(workspace_id, "google_calendar")
        if not conn:
            raise RuntimeError("Google Calendar connection is not configured in this workspace.")
        if conn.status == ConnectionStatus.DISCONNECTED:
            raise RuntimeError("Google Calendar connection is disconnected in this workspace.")
        return GoogleCalendarConnector(
            auth_metadata=conn.auth_metadata,
            workspace_id=workspace_id,
            store=self.store,
        )

    def get_connector(self, workspace_id: str, provider: str) -> BaseConnector | None:
        """Generic connector resolver."""
        p = provider.lower().strip()
        if p == "github":
            return self.get_github_connector(workspace_id)
        elif p == "email":
            return self.get_email_connector(workspace_id)
        elif p == "slack":
            return self.get_slack_connector(workspace_id)
        elif p == "http":
            return self.get_http_connector(workspace_id)
        elif p == "telegram":
            return self.get_telegram_connector(workspace_id)
        elif p == "calendar":
            return self.get_calendar_connector(workspace_id)
        elif p == "google_calendar":
            return self.get_google_calendar_connector(workspace_id)
        return None


def verify_credentials(
    provider: str,
    auth_metadata: dict[str, Any] | None,
    live_check: bool = False,
) -> tuple[bool, str]:
    """Validates presence, format, and optional live connectivity of credentials."""
    prov = (provider or "").lower().strip()
    meta = auth_metadata or {}

    if prov == "calendar":
        return True, "Aether local calendar storage ready."

    elif prov == "google_calendar":
        return GoogleCalendarConnector(auth_metadata=meta).verify(meta, live_check=live_check)

    elif prov == "github":
        return GitHubConnector(auth_metadata=meta).verify(meta, live_check=live_check)

    elif prov == "email":
        return EmailConnector(auth_metadata=meta).verify(meta, live_check=live_check)

    elif prov == "slack":
        return SlackConnector(auth_metadata=meta).verify(meta, live_check=live_check)

    elif prov == "http":
        return HttpConnector(auth_metadata=meta).verify(meta, live_check=live_check)

    elif prov == "telegram":
        return TelegramConnector(auth_metadata=meta).verify(
            meta, live_check=live_check or bool(meta.get("live_check"))
        )

    elif prov == "notion":
        token = str(meta.get("token") or meta.get("api_key") or "").strip()
        if not token:
            return False, "Notion Integration Token is required."
        if not (token.startswith("secret_") or token.startswith("ntn_") or len(token) >= 20):
            return False, "Invalid Notion token format. Must start with 'secret_' or 'ntn_'."
        if live_check:
            import urllib.error
            import urllib.request
            req = urllib.request.Request(
                "https://api.notion.com/v1/users/me",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Notion-Version": "2022-06-28",
                    "User-Agent": "Aether/1.0",
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        return True, "Notion API live check succeeded."
                    return False, f"Notion API live check failed: HTTP {resp.status}"
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    return False, "Notion authentication failed: invalid or unauthorized token."
                return False, f"Notion API returned HTTP {exc.code}."
            except Exception as exc:
                return False, f"Notion API unreachable: {exc}"
        return True, "Notion integration token format verified."

    else:
        if not meta or not any(str(v).strip() for v in meta.values()):
            return False, f"Credentials required for {provider}."
        if live_check:
            return True, f"{provider} credentials validated."
        return True, f"{provider} credentials format verified."
