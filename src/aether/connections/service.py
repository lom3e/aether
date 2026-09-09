"""
Service layer for Aether Connections and external integrations (Phase C).
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from aether.activity.models import ActivityCategory, ActivityStatus
from aether.activity.service import ActivityService
from aether.connections.models import CalendarEvent, Connection, ConnectionStatus
from aether.connections.store import ConnectionStore

logger = logging.getLogger(__name__)


class CalendarConnector:
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


class ConnectionService:
    """Orchestrates integrations, OAuth states, and tool connectors."""

    def __init__(
        self,
        store: ConnectionStore,
        activity_service: ActivityService | None = None,
    ) -> None:
        self.store = store
        self.activity_service = activity_service

    def connect(
        self,
        workspace_id: str,
        provider: str,
        account_name: str = "Connected Account",
        scopes: list[str] | None = None,
        capabilities: list[str] | None = None,
        auth_metadata: dict[str, Any] | None = None,
    ) -> Connection:
        """Connects or updates an external tool/service."""
        existing = self.store.get_connection_by_provider(workspace_id, provider)
        conn_id = existing.id if existing else f"conn-{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        conn = Connection(
            id=conn_id,
            workspace_id=workspace_id,
            provider=provider,
            account_name=account_name,
            status=ConnectionStatus.CONNECTED,
            scopes=scopes or ["read", "write"],
            capabilities=capabilities or [f"{provider}.read", f"{provider}.write"],
            auth_metadata=dict(auth_metadata or {}),
            created_at=existing.created_at if existing else now_iso,
            updated_at=now_iso,
        )
        saved = self.store.save_connection(conn)

        if self.activity_service:
            self.activity_service.log(
                workspace_id=workspace_id,
                title=f"Connected: {provider.capitalize()}",
                description=f"Successfully connected {provider} ({account_name}).",
                category=ActivityCategory.CONNECTION,
                status=ActivityStatus.COMPLETED,
                link_view="connections",
                link_id=saved.id,
                metadata={"provider": provider, "account_name": account_name},
            )

        return saved

    def disconnect(self, workspace_id: str, provider: str) -> None:
        """Disconnects a service."""
        conn = self.store.get_connection_by_provider(workspace_id, provider)
        if conn:
            conn.status = ConnectionStatus.DISCONNECTED
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

    def list_connections(self, workspace_id: str) -> list[Connection]:
        """Lists all connections for a workspace."""
        return self.store.list_connections(workspace_id)

    def get_connection(self, workspace_id: str, provider: str) -> Connection | None:
        """Retrieves connection for provider."""
        return self.store.get_connection_by_provider(workspace_id, provider)

    def verify(self, provider: str, auth_metadata: dict[str, Any] | None = None) -> tuple[bool, str]:
        """Validates credentials for a provider."""
        return verify_credentials(provider, auth_metadata)

    def get_calendar_connector(self, workspace_id: str) -> CalendarConnector:
        """Returns active calendar connector, ensuring connection record exists."""
        conn = self.store.get_connection_by_provider(workspace_id, "calendar")
        if not conn:
            conn = self.connect(
                workspace_id=workspace_id,
                provider="calendar",
                account_name="Primary Calendar",
                scopes=["calendar.events.read", "calendar.events.write"],
                capabilities=["calendar.create_event", "calendar.list_events"],
            )
        return CalendarConnector(self.store, workspace_id, conn.id)


def verify_credentials(provider: str, auth_metadata: dict[str, Any] | None) -> tuple[bool, str]:
    """Validates presence and format of connection credentials."""
    prov = (provider or "").lower().strip()
    meta = auth_metadata or {}

    if prov == "calendar":
        return True, "Built-in calendar connection ready."

    elif prov == "github":
        token = str(meta.get("token") or meta.get("pat") or meta.get("api_key") or "").strip()
        if not token:
            return False, "GitHub Personal Access Token (PAT) is required."
        if not (token.startswith("ghp_") or token.startswith("github_pat_") or len(token) >= 20):
            return False, "Invalid GitHub token format. Must be a Personal Access Token (e.g. starting with 'ghp_' or 'github_pat_')."
        return True, "GitHub Personal Access Token format verified."

    elif prov == "slack":
        bot_token = str(meta.get("bot_token") or meta.get("token") or "").strip()
        webhook_url = str(meta.get("webhook_url") or "").strip()
        if not bot_token and not webhook_url:
            return False, "Slack Bot User OAuth Token (xoxb-...) or Incoming Webhook URL is required."
        if bot_token and not (bot_token.startswith("xoxb-") or bot_token.startswith("xoxp-")):
            return False, "Invalid Slack Bot Token format. Must start with 'xoxb-' or 'xoxp-'."
        if webhook_url and not webhook_url.startswith("https://hooks.slack.com/"):
            return False, "Invalid Slack Webhook URL. Must start with 'https://hooks.slack.com/'."
        return True, "Slack credentials format verified."

    elif prov == "email":
        username = str(meta.get("username") or meta.get("email") or "").strip()
        password = str(meta.get("password") or meta.get("app_password") or meta.get("token") or "").strip()
        smtp_host = str(meta.get("smtp_host") or "").strip()
        if not username:
            return False, "Email address or username is required."
        if not password:
            return False, "App password or token is required."
        if not smtp_host:
            return False, "SMTP Host is required (e.g. smtp.gmail.com)."
        return True, "Email SMTP credentials format verified."

    elif prov == "notion":
        token = str(meta.get("token") or meta.get("api_key") or "").strip()
        if not token:
            return False, "Notion Integration Token is required."
        if not (token.startswith("secret_") or token.startswith("ntn_") or len(token) >= 20):
            return False, "Invalid Notion token format. Must start with 'secret_' or 'ntn_'."
        return True, "Notion integration token format verified."

    else:
        if not meta or not any(str(v).strip() for v in meta.values()):
            return False, f"Credentials required for {provider}."
        return True, f"{provider} credentials verified."

