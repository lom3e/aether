"""
OpenAPI 3.x Tool Generator for Aether (Phase C & Sprint 1).
Parses local OpenAPI documents (JSON or YAML) and generates safe, discoverable Aether Tools
and ActionDefinitions registered in ToolRegistry and ActionRegistry.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any
import urllib.parse

import yaml

from aether.actions.models import (
    ActionDefinition,
    ActionPermissionLevel,
    ActionTier,
)
from aether.actions.registry import ActionRegistry
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
from aether.connections.http import HttpConnector
from aether.connections.models import ConnectionStatus
from aether.tools.base import Tool, ToolExecutionContext
from aether.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def sanitize_tool_name(name: str) -> str:
    """Sanitizes an operationId or path into a valid Python/JSON tool identifier."""
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_").lower()
    if not clean or clean[0].isdigit():
        clean = f"tool_{clean}"
    return clean


class OpenAPITool(Tool):
    """
    An Aether Tool generated dynamically from an OpenAPI 3.x operation specification.
    """

    def __init__(
        self,
        name: str,
        description: str,
        method: str,
        path: str,
        base_url: str = "",
        parameters: list[dict[str, Any]] | None = None,
        request_body_schema: dict[str, Any] | None = None,
        security_schemes: dict[str, Any] | None = None,
        auth_metadata: dict[str, Any] | None = None,
        http_connector: HttpConnector | None = None,
        permission_level: ActionPermissionLevel = ActionPermissionLevel.READ_ONLY,
        requires_confirmation: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.method = method.upper().strip()
        self.path = path
        self.base_url = base_url.rstrip("/")
        self.parameters = parameters or []
        self.request_body_schema = request_body_schema
        self.security_schemes = security_schemes or {}
        self.auth_metadata = auth_metadata or {}
        self.http_connector = http_connector or HttpConnector(auth_metadata=self.auth_metadata)
        self.permission_level = permission_level
        self.requires_confirmation = requires_confirmation

    def to_json_schema(self) -> dict[str, Any]:
        """
        Returns JSON Schema for the tool function arguments.
        """
        properties: dict[str, Any] = {}
        required: list[str] = []

        # Parameters (path, query, header)
        for param in self.parameters:
            p_name = param.get("name")
            if not p_name:
                continue
            p_schema = param.get("schema") or {"type": "string"}
            p_desc = param.get("description") or f"Parameter '{p_name}' ({param.get('in', 'query')})"
            properties[p_name] = {
                "type": p_schema.get("type", "string"),
                "description": p_desc,
            }
            if param.get("required"):
                required.append(p_name)

        # Request Body
        if self.request_body_schema:
            rb_props = self.request_body_schema.get("properties") or {}
            for prop_name, prop_spec in rb_props.items():
                properties[prop_name] = prop_spec
            for req in self.request_body_schema.get("required") or []:
                if req not in required:
                    required.append(req)

        schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }

    def execute(self, input_data: str | dict[str, Any], context: ToolExecutionContext | None = None) -> str:
        """
        Executes the OpenAPI operation via HttpConnector.
        """
        parsed_args: dict[str, Any] = {}
        if isinstance(input_data, dict):
            parsed_args = dict(input_data)
        elif isinstance(input_data, str) and input_data.strip():
            try:
                parsed_args = json.loads(input_data)
            except Exception:
                parsed_args = {"input": input_data}

        # Substitute path parameters
        resolved_path = self.path
        query_params: dict[str, Any] = {}
        header_params: dict[str, str] = {}
        body_data: dict[str, Any] = {}

        # Separate parameters by location
        param_locations = {p.get("name"): p.get("in", "query") for p in self.parameters if p.get("name")}

        for k, v in parsed_args.items():
            loc = param_locations.get(k)
            if loc == "path" or f"{{{k}}}" in resolved_path:
                resolved_path = resolved_path.replace(f"{{{k}}}", str(v))
            elif loc == "header":
                header_params[k] = str(v)
            elif loc == "query":
                query_params[k] = v
            else:
                # Body property or fallback
                body_data[k] = v

        full_url = resolved_path
        if self.base_url:
            full_url = f"{self.base_url}/{resolved_path.lstrip('/')}"

        # If there are leftovers and method supports body, send them in body
        json_payload = body_data if (body_data and self.method in ("POST", "PUT", "PATCH", "DELETE")) else None

        result = self.http_connector.request(
            method=self.method,
            url=full_url,
            params=query_params or None,
            json_data=json_payload,
            headers=header_params or None,
        )

        return json.dumps(result.get("data") if result.get("data") is not None else result)


class OpenAPIToolGenerator:
    """
    Parses OpenAPI 3.x documents and generates Aether Tool and Action definitions.
    """

    @staticmethod
    def load_spec(spec_or_path: str | Path | dict[str, Any]) -> dict[str, Any]:
        """Loads OpenAPI specification from file path, JSON/YAML string, or dict."""
        if isinstance(spec_or_path, dict):
            return spec_or_path

        p = Path(str(spec_or_path))
        if p.exists() and p.is_file():
            content = p.read_text(encoding="utf-8")
        else:
            content = str(spec_or_path)

        # Try parsing JSON first, then YAML
        try:
            return json.loads(content)
        except Exception:
            return yaml.safe_load(content)

    @classmethod
    def generate_tools(
        cls,
        spec_or_path: str | Path | dict[str, Any],
        base_url: str | None = None,
        auth_metadata: dict[str, Any] | None = None,
    ) -> list[OpenAPITool]:
        """Generates OpenAPITool instances from an OpenAPI 3.x specification."""
        spec = cls.load_spec(spec_or_path)
        if not isinstance(spec, dict):
            raise ValueError("Invalid OpenAPI specification format. Must be an object/dict.")

        # Determine default base URL from servers block
        resolved_base = base_url
        if not resolved_base:
            servers = spec.get("servers") or []
            if servers and isinstance(servers, list) and isinstance(servers[0], dict):
                resolved_base = servers[0].get("url", "")
        resolved_base = resolved_base or ""

        security_schemes = spec.get("components", {}).get("securitySchemes", {})
        paths = spec.get("paths", {})
        generated_tools: list[OpenAPITool] = []

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            path_params = path_item.get("parameters") or []

            for method in ("get", "post", "put", "patch", "delete", "head"):
                operation = path_item.get(method)
                if not isinstance(operation, dict):
                    continue

                op_id = operation.get("operationId")
                if not op_id:
                    clean_path = re.sub(r"[{}]", "", path).replace("/", "_").strip("_")
                    op_id = f"{method}_{clean_path}"

                tool_name = sanitize_tool_name(op_id)
                summary = operation.get("summary") or operation.get("description") or f"{method.upper()} {path}"
                desc = f"{summary} [OpenAPI: {method.upper()} {path}]"

                # Combine path-level and operation-level parameters
                all_params = list(path_params) + (operation.get("parameters") or [])

                # Extract request body schema (JSON)
                rb_schema = None
                req_body = operation.get("requestBody") or {}
                if isinstance(req_body, dict):
                    content = req_body.get("content") or {}
                    json_media = content.get("application/json") or content.get("*/*") or {}
                    rb_schema = json_media.get("schema")

                # Determine permission classification and safety
                is_read_only = method.lower() in ("get", "head")
                permission_level = (
                    ActionPermissionLevel.READ_ONLY
                    if is_read_only
                    else ActionPermissionLevel.EXTERNAL_MUTATION
                )
                requires_confirmation = not is_read_only

                tool = OpenAPITool(
                    name=tool_name,
                    description=desc,
                    method=method,
                    path=path,
                    base_url=resolved_base,
                    parameters=all_params,
                    request_body_schema=rb_schema,
                    security_schemes=security_schemes,
                    auth_metadata=auth_metadata,
                    permission_level=permission_level,
                    requires_confirmation=requires_confirmation,
                )
                generated_tools.append(tool)

        return generated_tools

    @classmethod
    def register_tools(
        cls,
        tool_registry: ToolRegistry,
        action_registry: ActionRegistry | None,
        spec_or_path: str | Path | dict[str, Any],
        base_url: str | None = None,
        auth_metadata: dict[str, Any] | None = None,
    ) -> list[OpenAPITool]:
        """
        Generates tools from OpenAPI spec and registers them into ToolRegistry and ActionRegistry.
        """
        tools = cls.generate_tools(spec_or_path, base_url=base_url, auth_metadata=auth_metadata)
        for t in tools:
            # Register in ToolRegistry
            if not tool_registry.has(t.name):
                tool_registry.register(t)

            # Register corresponding ActionDefinition in ActionRegistry
            if action_registry is not None:
                action_def = ActionDefinition(
                    id=f"openapi.{t.name}",
                    name=t.name.replace("_", " ").title(),
                    description=t.description,
                    tier=ActionTier.ANSWER if t.permission_level == ActionPermissionLevel.READ_ONLY else ActionTier.ACT,
                    permission_level=t.permission_level,
                    requires_confirmation=t.requires_confirmation,
                    provider="openapi",
                    input_schema=t.to_json_schema().get("function", {}).get("parameters", {}),
                )
                action_registry.register(action_def, handler=lambda inp, ws_id, target_tool=t: json.loads(target_tool.execute(inp)))

        return tools


class OpenAPIConnector(BaseConnector):
    """
    OpenAPI 3.x connector executing dynamically generated API operations.
    """

    def __init__(self, auth_metadata: dict[str, Any] | None = None) -> None:
        self._auth_metadata = dict(auth_metadata or {})
        self._tools: list[OpenAPITool] | None = None

    @property
    def provider(self) -> str:
        return "openapi"

    @property
    def capabilities(self) -> list[str]:
        return [
            "openapi.list_tools",
            "openapi.execute_tool",
            "openapi.inspect_spec",
        ]

    @property
    def credential_requirements(self) -> list[CredentialRequirement]:
        return [
            CredentialRequirement(
                key="spec_url",
                label="OpenAPI Spec URL",
                description="URL to the OpenAPI JSON or YAML specification.",
                required=False,
                secret=False,
            ),
            CredentialRequirement(
                key="spec_path",
                label="Local Spec Path",
                description="Local filesystem path to the OpenAPI specification file.",
                required=False,
                secret=False,
            ),
            CredentialRequirement(
                key="base_url",
                label="Base URL Override",
                description="Optional override for the API base server URL.",
                required=False,
                secret=False,
            ),
            CredentialRequirement(
                key="auth_type",
                label="Authentication Type",
                description="none, bearer, api_key, basic",
                required=False,
                secret=False,
                options=["none", "bearer", "api_key", "basic"],
                default="none",
            ),
            CredentialRequirement(
                key="token",
                label="API Token / Key",
                description="Bearer token or API key for authentication.",
                required=False,
                secret=True,
            ),
        ]

    def _resolve_spec(self, meta: dict[str, Any]) -> dict[str, Any] | None:
        spec_content = meta.get("spec_content")
        if spec_content:
            return OpenAPIToolGenerator.load_spec(spec_content)
        spec_path = meta.get("spec_path")
        if spec_path:
            return OpenAPIToolGenerator.load_spec(spec_path)
        spec_url = meta.get("spec_url")
        if spec_url:
            http = HttpConnector(auth_metadata=meta)
            res = http.request("GET", spec_url)
            content = res.get("data")
            if isinstance(content, dict):
                return content
            elif isinstance(content, str):
                return OpenAPIToolGenerator.load_spec(content)
        return None

    def verify(self, auth_metadata: dict[str, Any] | None = None, live_check: bool = False) -> tuple[bool, str]:
        meta = auth_metadata or self._auth_metadata
        spec_url = str(meta.get("spec_url") or "").strip()
        spec_path = str(meta.get("spec_path") or "").strip()
        spec_content = meta.get("spec_content")
        base_url = str(meta.get("base_url") or "").strip()

        if not spec_url and not spec_path and not spec_content and not base_url:
            return False, "OpenAPI Spec URL, local file path, or base URL is required."

        if spec_url:
            parsed = urllib.parse.urlparse(spec_url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return False, f"Invalid OpenAPI Spec URL: '{spec_url}'."

        if spec_path and not Path(spec_path).exists():
            return False, f"OpenAPI Spec file not found at path '{spec_path}'."

        if live_check or meta.get("live_check"):
            try:
                spec = self._resolve_spec(meta)
                if not spec and base_url:
                    http = HttpConnector(auth_metadata=meta)
                    return http.verify(live_check=True)
                if not spec:
                    return False, "Could not load or parse OpenAPI specification."
                tools = OpenAPIToolGenerator.generate_tools(
                    spec,
                    base_url=base_url or None,
                    auth_metadata=meta,
                )
                title = spec.get("info", {}).get("title", "API")
                version = spec.get("info", {}).get("version", "1.0")
                return True, f"OpenAPI specification '{title} v{version}' verified ({len(tools)} operations discovered)."
            except Exception as exc:
                return False, f"OpenAPI verification failed: {exc}"

        return True, "OpenAPI connector configuration format verified."

    def get_health(self) -> ConnectorHealth:
        valid, msg = self.verify(live_check=True)
        return ConnectorHealth(
            healthy=valid,
            status=ConnectionStatus.VERIFIED if valid else ConnectionStatus.VERIFICATION_FAILED,
            message=msg,
        )

    def get_tools(self) -> list[OpenAPITool]:
        if self._tools is None:
            spec = self._resolve_spec(self._auth_metadata)
            if not spec:
                raise ConnectorConfigurationError("No valid OpenAPI specification provided.", provider=self.provider)
            base_url = self._auth_metadata.get("base_url")
            self._tools = OpenAPIToolGenerator.generate_tools(
                spec,
                base_url=base_url,
                auth_metadata=self._auth_metadata,
            )
        return self._tools

    def execute(self, operation: str, params: dict[str, Any]) -> ConnectorResult:
        clean_op = operation.lower().strip()
        try:
            if clean_op in ("openapi.list_tools", "list_tools"):
                tools = self.get_tools()
                tool_list = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "method": t.method,
                        "path": t.path,
                        "requires_confirmation": t.requires_confirmation,
                    }
                    for t in tools
                ]
                return ConnectorResult(success=True, operation=operation, provider=self.provider, data={"tools": tool_list})

            elif clean_op in ("openapi.inspect_spec", "inspect_spec"):
                spec = self._resolve_spec(self._auth_metadata) or {}
                info = spec.get("info", {})
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data={
                        "title": info.get("title", "OpenAPI"),
                        "version": info.get("version", "unknown"),
                        "description": info.get("description", ""),
                        "endpoints_count": len(spec.get("paths", {})),
                    },
                )

            elif clean_op in ("openapi.execute_tool", "execute_tool"):
                tool_name = str(params.get("tool_name") or params.get("name") or "").strip()
                tools = self.get_tools()
                target_tool = next((t for t in tools if t.name == tool_name), None)
                if not target_tool:
                    raise ConnectorNotFoundError(f"OpenAPI tool '{tool_name}' not found.", provider=self.provider)
                input_data = params.get("parameters") or params.get("input_data") or params.get("input") or {}
                raw_out = target_tool.execute(input_data)
                try:
                    parsed_out = json.loads(raw_out)
                except Exception:
                    parsed_out = raw_out
                return ConnectorResult(success=True, operation=operation, provider=self.provider, data=parsed_out)

            else:
                target_name = clean_op.replace("openapi.", "")
                tools = self.get_tools()
                target_tool = next((t for t in tools if t.name == target_name or t.name == clean_op), None)
                if target_tool:
                    raw_out = target_tool.execute(params)
                    try:
                        parsed_out = json.loads(raw_out)
                    except Exception:
                        parsed_out = raw_out
                    return ConnectorResult(success=True, operation=operation, provider=self.provider, data=parsed_out)
                raise ConnectorError(f"Unsupported OpenAPI operation: '{operation}'", provider=self.provider)

        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError(f"OpenAPI operation '{operation}' failed: {exc}", provider=self.provider) from None

