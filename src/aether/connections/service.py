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
from aether.connections.http import HttpConnector
from aether.connections.models import CalendarEvent, Connection, ConnectionStatus
from aether.connections.slack import SlackConnector
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

    def verify(self, auth_metadata: dict[str, Any] | None = None) -> tuple[bool, str]:
        return True, "Built-in calendar connection ready."

    def get_health(self) -> ConnectorHealth:
        return ConnectorHealth(
            healthy=True,
            status=ConnectionStatus.CONNECTED,
            message="Built-in calendar connection active.",
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
            capabilities=capabilities or self.get_default_capabilities(provider),
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
        elif p == "calendar":
            return self.get_calendar_connector(workspace_id)
        return None


def verify_credentials(provider: str, auth_metadata: dict[str, Any] | None) -> tuple[bool, str]:
    """Validates presence and format of connection credentials using connector implementations."""
    prov = (provider or "").lower().strip()
    meta = auth_metadata or {}

    if prov == "calendar":
        return True, "Built-in calendar connection ready."

    elif prov == "github":
        return GitHubConnector(auth_metadata=meta).verify(meta)

    elif prov == "email":
        return EmailConnector(auth_metadata=meta).verify(meta)

    elif prov == "slack":
        return SlackConnector(auth_metadata=meta).verify(meta)

    elif prov == "http":
        return HttpConnector(auth_metadata=meta).verify(meta)

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
