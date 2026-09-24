"""
Generic Provider-Neutral HTTP Connector for Aether (Phase C & Sprint 1).
Supports GET, POST, PUT, PATCH, DELETE with auth abstractions (Bearer, API Key, Basic),
timeout handling, response normalization, and workspace security enforcement.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import logging
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
    ConnectorResult,
    CredentialRequirement,
)
from aether.connections.models import ConnectionStatus

logger = logging.getLogger(__name__)


class HttpConnector(BaseConnector):
    """
    Provider-neutral HTTP connector for external API communication.
    """

    SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}

    def __init__(self, auth_metadata: dict[str, Any] | None = None) -> None:
        self._auth_metadata = dict(auth_metadata or {})

    @property
    def provider(self) -> str:
        return "http"

    @property
    def capabilities(self) -> list[str]:
        return [
            "http.request",
            "http.get",
            "http.post",
            "http.put",
            "http.patch",
            "http.delete",
        ]

    @property
    def credential_requirements(self) -> list[CredentialRequirement]:
        return [
            CredentialRequirement(
                key="base_url",
                label="Base URL",
                description="Optional default base URL for API endpoints.",
                required=False,
                secret=False,
            ),
            CredentialRequirement(
                key="auth_type",
                label="Authentication Type",
                description="bearer, api_key, basic, or none.",
                required=False,
                secret=False,
                options=["none", "bearer", "api_key", "basic"],
                default="none",
            ),
            CredentialRequirement(
                key="token",
                label="Bearer Token / API Key",
                description="Bearer token or API key for authentication.",
                required=False,
                secret=True,
            ),
            CredentialRequirement(
                key="header_name",
                label="API Key Header Name",
                description="Header name if using api_key auth (e.g. X-API-Key).",
                required=False,
                secret=False,
                default="X-API-Key",
            ),
            CredentialRequirement(
                key="username",
                label="Basic Auth Username",
                description="Username for Basic auth.",
                required=False,
                secret=False,
            ),
            CredentialRequirement(
                key="password",
                label="Basic Auth Password",
                description="Password for Basic auth.",
                required=False,
                secret=True,
            ),
        ]

    def verify(self, auth_metadata: dict[str, Any] | None = None) -> tuple[bool, str]:
        meta = auth_metadata or self._auth_metadata
        base_url = str(meta.get("base_url") or "").strip()
        auth_type = str(meta.get("auth_type") or "none").strip().lower()

        if base_url:
            parsed = urllib.parse.urlparse(base_url)
            if parsed.scheme not in ("http", "https"):
                return False, f"Invalid base URL scheme: '{parsed.scheme}'. Must be http or https."

        if auth_type == "bearer":
            token = str(meta.get("token") or meta.get("bearer_token") or "").strip()
            if not token:
                return False, "Bearer token is required when auth_type is 'bearer'."

        elif auth_type == "api_key":
            key = str(meta.get("token") or meta.get("api_key") or "").strip()
            if not key:
                return False, "API key is required when auth_type is 'api_key'."

        elif auth_type == "basic":
            user = str(meta.get("username") or "").strip()
            password = str(meta.get("password") or "").strip()
            if not user or not password:
                return False, "Username and password required for Basic auth."

        return True, "HTTP connector configuration verified."

    def get_health(self) -> ConnectorHealth:
        valid, msg = self.verify()
        return ConnectorHealth(
            healthy=valid,
            status=ConnectionStatus.CONNECTED if valid else ConnectionStatus.ERROR,
            message=msg,
        )

    def _apply_auth(
        self,
        headers: dict[str, str],
        query_params: dict[str, Any],
        meta: dict[str, Any],
    ) -> None:
        """Injects authentication headers or parameters into the request."""
        auth_type = str(meta.get("auth_type") or "none").strip().lower()

        token = str(meta.get("token") or meta.get("bearer_token") or meta.get("api_key") or "").strip()

        if auth_type == "bearer" and token:
            headers["Authorization"] = f"Bearer {token}"

        elif auth_type == "api_key" and token:
            header_name = str(meta.get("header_name") or "X-API-Key").strip()
            in_query = bool(meta.get("api_key_in_query", False))
            if in_query:
                param_name = str(meta.get("query_param_name") or "api_key").strip()
                query_params[param_name] = token
            else:
                headers[header_name] = token

        elif auth_type == "basic":
            user = str(meta.get("username") or "").strip()
            password = str(meta.get("password") or "").strip()
            if user and password:
                cred_str = f"{user}:{password}".encode("utf-8")
                b64 = base64.b64encode(cred_str).decode("ascii")
                headers["Authorization"] = f"Basic {b64}"

    def request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: Any = None,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """
        Executes a validated, safe HTTP request.
        """
        clean_method = method.upper().strip()
        if clean_method not in self.SUPPORTED_METHODS:
            raise ConnectorError(f"Unsupported HTTP method: '{method}'", provider=self.provider)

        # Base URL resolution
        base_url = str(self._auth_metadata.get("base_url") or "").rstrip("/")
        full_url = url
        if not full_url.startswith("http://") and not full_url.startswith("https://"):
            if base_url:
                full_url = f"{base_url}/{url.lstrip('/')}"
            else:
                raise ConnectorError(f"Relative URL provided without base_url: '{url}'", provider=self.provider)

        parsed = urllib.parse.urlparse(full_url)
        if parsed.scheme not in ("http", "https"):
            raise ConnectorError(f"Invalid URL scheme '{parsed.scheme}'. Only http and https are allowed.", provider=self.provider)

        # Merge headers and query parameters
        req_headers = {"User-Agent": "Aether-HTTP-Connector/1.0"}
        if headers:
            req_headers.update(headers)

        q_params = dict(params or {})
        self._apply_auth(req_headers, q_params, self._auth_metadata)

        if q_params:
            delim = "&" if "?" in full_url else "?"
            full_url = f"{full_url}{delim}{urllib.parse.urlencode(q_params)}"

        req_body = None
        if json_data is not None:
            req_body = json.dumps(json_data).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        elif data is not None:
            if isinstance(data, (dict, list)):
                req_body = json.dumps(data).encode("utf-8")
                req_headers["Content-Type"] = "application/json"
            elif isinstance(data, str):
                req_body = data.encode("utf-8")
            elif isinstance(data, bytes):
                req_body = data

        req = urllib.request.Request(full_url, data=req_body, headers=req_headers, method=clean_method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.status
                resp_bytes = response.read()
                resp_headers = dict(response.headers)

                parsed_data: Any = None
                raw_text = ""
                if resp_bytes:
                    raw_text = resp_bytes.decode("utf-8", errors="replace")
                    try:
                        parsed_data = json.loads(raw_text)
                    except Exception:
                        parsed_data = raw_text

                return {
                    "status_code": status_code,
                    "url": full_url,
                    "headers": resp_headers,
                    "data": parsed_data,
                    "text": raw_text,
                }
        except urllib.error.HTTPError as exc:
            err_body = ""
            err_data: Any = None
            try:
                raw_err = exc.read().decode("utf-8", errors="replace")
                err_body = raw_err
                err_data = json.loads(raw_err)
            except Exception:
                pass

            if exc.code in (401, 403):
                raise ConnectorAuthError(
                    f"HTTP request to '{parsed.netloc}' failed with {exc.code} Unauthorized: {err_body[:200]}",
                    provider=self.provider,
                ) from None
            raise ConnectorError(
                f"HTTP request to '{parsed.netloc}' failed with status {exc.code}: {err_body[:200]}",
                provider=self.provider,
                details={"status_code": exc.code, "error": err_data or err_body},
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectorError(f"HTTP network error connecting to '{parsed.netloc}': {exc}", provider=self.provider) from None

    def execute(self, operation: str, params: dict[str, Any]) -> ConnectorResult:
        clean_op = operation.lower().strip()
        method = "GET"
        if clean_op.startswith("http."):
            sub = clean_op.split(".", 1)[1].upper()
            if sub in self.SUPPORTED_METHODS:
                method = sub
        elif clean_op in [m.lower() for m in self.SUPPORTED_METHODS]:
            method = clean_op.upper()

        if "method" in params:
            method = str(params["method"]).upper().strip()

        url = str(params.get("url") or params.get("endpoint") or params.get("path") or "").strip()
        if not url:
            raise ConnectorError("URL parameter is required for HTTP operation.", provider=self.provider)

        resp = self.request(
            method=method,
            url=url,
            params=params.get("params") or params.get("query_params"),
            data=params.get("data"),
            json_data=params.get("json") or params.get("body") or params.get("json_data"),
            headers=params.get("headers"),
            timeout=float(params.get("timeout") or 15.0),
        )

        return ConnectorResult(
            success=True,
            operation=operation,
            provider=self.provider,
            data=resp,
        )
