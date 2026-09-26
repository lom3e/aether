"""
Notion Connector for Aether (Macro-pass P1.1 - Strada A).
Provides real Notion integration via official REST API v1 (/v1/users/me, /v1/search, /v1/pages)
with strict credential protection, rate limit handling, and normalized error reporting.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

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

logger = logging.getLogger(__name__)


class NotionConnector(BaseConnector):
    """
    Real Notion integration connector using Notion REST API v1 (2022-06-28).
    """

    API_BASE = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"

    def __init__(self, auth_metadata: dict[str, Any] | None = None) -> None:
        self._auth_metadata = dict(auth_metadata or {})

    @property
    def provider(self) -> str:
        return "notion"

    @property
    def capabilities(self) -> list[str]:
        return [
            "notion.get_me",
            "notion.search",
            "notion.get_page",
            "notion.create_page",
        ]

    @property
    def credential_requirements(self) -> list[CredentialRequirement]:
        return [
            CredentialRequirement(
                key="token",
                label="Internal Integration Secret",
                description="Notion secret starting with 'secret_' or 'ntn_'.",
                required=True,
                secret=True,
            ),
            CredentialRequirement(
                key="default_database_id",
                label="Default Database ID",
                description="Optional default database ID for creating pages or queries.",
                required=False,
                secret=False,
            ),
        ]

    def _get_token(self, params: dict[str, Any] | None = None) -> str | None:
        explicit = None
        if params and "token" in params:
            explicit = str(params["token"]).strip()
        if not explicit:
            explicit = str(self._auth_metadata.get("token") or self._auth_metadata.get("api_key") or "").strip()
        return explicit or None

    def _build_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Notion-Version": self.NOTION_VERSION,
            "Content-Type": "application/json",
            "User-Agent": "Aether/1.0",
        }

    def _http_request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        token: str | None = None,
        timeout: float = 10.0,
    ) -> Any:
        tok = token or self._get_token()
        if not tok:
            raise ConnectorConfigurationError("Notion integration token is required.", provider=self.provider)

        url = path if path.startswith("http") else f"{self.API_BASE}/{path.lstrip('/')}"
        headers = self._build_headers(tok)
        body = json.dumps(data).encode("utf-8") if data is not None else None

        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_bytes = resp.read()
                if not resp_bytes:
                    return {}
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_msg = ""
            try:
                err_payload = json.loads(exc.read().decode("utf-8"))
                err_msg = err_payload.get("message", "")
            except Exception:
                pass

            if exc.code in (401, 403):
                raise ConnectorAuthError(
                    f"Notion authentication failed (HTTP {exc.code}): {err_msg or 'Invalid or unauthorized token.'}",
                    provider=self.provider,
                ) from None
            elif exc.code == 404:
                raise ConnectorNotFoundError(
                    f"Notion resource not found (HTTP 404): {err_msg or 'Target page or database not found.'}",
                    provider=self.provider,
                ) from None
            elif exc.code == 429:
                raise ConnectorError(
                    f"Notion API rate limit exceeded (HTTP 429): {err_msg or 'Please retry after a brief delay.'}",
                    provider=self.provider,
                ) from None
            else:
                raise ConnectorError(
                    f"Notion API request failed with status {exc.code}: {err_msg or exc.reason}",
                    provider=self.provider,
                ) from None
        except (TimeoutError, socket.timeout) as exc:
            raise ConnectorError(f"Notion connection timed out: {exc}", provider=self.provider) from None
        except socket.gaierror as exc:
            raise ConnectorError(f"Notion DNS resolution failed: {exc}", provider=self.provider) from None
        except urllib.error.URLError as exc:
            raise ConnectorError(f"Notion network error: {exc}", provider=self.provider) from None
        except Exception as exc:
            raise ConnectorError(f"Unexpected Notion error: {exc}", provider=self.provider) from None

    def verify(self, auth_metadata: dict[str, Any] | None = None, live_check: bool = False) -> tuple[bool, str]:
        meta = auth_metadata or self._auth_metadata
        token = str(meta.get("token") or meta.get("api_key") or "").strip()

        if not token:
            return False, "Notion Integration Token is required."

        if not (token.startswith("secret_") or token.startswith("ntn_")):
            return False, "Invalid Notion token format. Must be an integration secret starting with 'secret_' or 'ntn_'."

        if live_check or meta.get("live_check"):
            try:
                user_data = self._http_request("GET", "/users/me", token=token, timeout=7.0)
                name = user_data.get("name") or user_data.get("bot", {}).get("owner", {}).get("user", {}).get("name") or "Aether Integration"
                bot_info = user_data.get("bot", {})
                workspace_name = bot_info.get("workspace_name")
                if workspace_name:
                    return True, f"Notion bot '{name}' verified in workspace '{workspace_name}'."
                return True, f"Notion integration verified for '{name}'."
            except ConnectorAuthError as exc:
                return False, f"Notion authentication failed: {exc.message}"
            except ConnectorError as exc:
                return False, f"Notion verification failed: {exc.message}"
            except Exception as exc:
                return False, f"Notion API unreachable: {exc}"

        return True, "Notion integration token format verified."

    def get_health(self) -> ConnectorHealth:
        tok = self._get_token()
        if not tok:
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.NOT_CONFIGURED,
                message="Notion integration token is not configured.",
            )
        valid, msg = self.verify(live_check=True)
        return ConnectorHealth(
            healthy=valid,
            status=ConnectionStatus.VERIFIED if valid else ConnectionStatus.VERIFICATION_FAILED,
            message=msg,
        )

    def get_me(self, token: str | None = None) -> dict[str, Any]:
        """Fetch bot identity from Notion (GET /v1/users/me)."""
        return self._http_request("GET", "/users/me", token=token)

    def search(
        self,
        query: str = "",
        filter_type: str | None = None,
        page_size: int = 10,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Search workspace pages and databases (POST /v1/search)."""
        payload: dict[str, Any] = {"page_size": min(page_size, 100)}
        if query:
            payload["query"] = query
        if filter_type in ("page", "database"):
            payload["filter"] = {"value": filter_type, "property": "object"}
        return self._http_request("POST", "/search", data=payload, token=token)

    def get_page(self, page_id: str, token: str | None = None) -> dict[str, Any]:
        """Retrieve a specific page by ID (GET /v1/pages/{page_id})."""
        clean_id = page_id.replace("-", "").strip()
        if not clean_id:
            raise ConnectorError("page_id is required.", provider=self.provider)
        return self._http_request("GET", f"/pages/{clean_id}", token=token)

    def create_page(
        self,
        title: str,
        parent_page_id: str | None = None,
        parent_database_id: str | None = None,
        content: str | None = None,
        properties: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Create a new page in a database or under a parent page (POST /v1/pages)."""
        parent_db = parent_database_id or self._auth_metadata.get("default_database_id")
        
        parent: dict[str, Any] = {}
        props: dict[str, Any] = dict(properties or {})

        if parent_db:
            clean_db = str(parent_db).replace("-", "").strip()
            parent = {"database_id": clean_db}
            if "title" not in props and "Name" not in props:
                props["Name"] = {"title": [{"text": {"content": title}}]}
        elif parent_page_id:
            clean_pid = str(parent_page_id).replace("-", "").strip()
            parent = {"page_id": clean_pid}
            if "title" not in props:
                props["title"] = [{"text": {"content": title}}]
        else:
            raise ConnectorError(
                "Either parent_database_id or parent_page_id must be provided to create a Notion page.",
                provider=self.provider,
            )

        payload: dict[str, Any] = {
            "parent": parent,
            "properties": props,
        }

        if content:
            payload["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    },
                }
            ]

        return self._http_request("POST", "/pages", data=payload, token=token)

    def execute(self, operation: str, params: dict[str, Any]) -> ConnectorResult:
        clean_op = operation.lower().strip()
        tok = self._get_token(params)

        try:
            if clean_op in ("notion.get_me", "get_me", "me"):
                data = self.get_me(token=tok)
                return ConnectorResult(success=True, operation=operation, provider=self.provider, data=data)

            elif clean_op in ("notion.search", "search"):
                query = str(params.get("query") or "").strip()
                filter_type = params.get("filter_type")
                page_size = int(params.get("page_size", 10))
                data = self.search(query=query, filter_type=filter_type, page_size=page_size, token=tok)
                return ConnectorResult(success=True, operation=operation, provider=self.provider, data=data)

            elif clean_op in ("notion.get_page", "get_page"):
                page_id = str(params.get("page_id") or params.get("id") or "").strip()
                data = self.get_page(page_id=page_id, token=tok)
                return ConnectorResult(success=True, operation=operation, provider=self.provider, data=data)

            elif clean_op in ("notion.create_page", "create_page"):
                title = str(params.get("title") or "Untitled Page").strip()
                parent_page_id = params.get("parent_page_id")
                parent_database_id = params.get("parent_database_id")
                content = params.get("content") or params.get("body")
                properties = params.get("properties")
                data = self.create_page(
                    title=title,
                    parent_page_id=parent_page_id,
                    parent_database_id=parent_database_id,
                    content=content,
                    properties=properties,
                    token=tok,
                )
                return ConnectorResult(success=True, operation=operation, provider=self.provider, data=data)

            else:
                raise ConnectorError(f"Unsupported Notion operation: '{operation}'", provider=self.provider)

        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError(f"Notion operation '{operation}' failed: {exc}", provider=self.provider) from None
