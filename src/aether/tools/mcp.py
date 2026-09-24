from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping
import urllib.error
import urllib.parse
import urllib.request

from aether.tools.base import Tool, ToolExecutionContext
from aether.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MCPToolDefinition:
    """Represents a tool definition advertised by an MCP server."""
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


class MCPClient:
    """
    Client for interacting with Model Context Protocol (MCP) servers
    via either standard stdio (subprocess) or HTTP JSON-RPC 2.0 transport.
    """

    def __init__(
        self,
        command: list[str] | str | None = None,
        endpoint_url: str | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        auth_token: str | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.command = command
        self.endpoint_url = endpoint_url
        self.cwd = cwd
        self.env = env or {}
        self.auth_token = auth_token
        self.headers = headers or {}
        self.timeout_seconds = timeout_seconds

        self._process: subprocess.Popen | None = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._connected = False
        self._server_info: dict[str, Any] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> dict[str, Any]:
        """
        Initializes connection with MCP server via initialize handshake and initialized notification.
        """
        if self._connected:
            return self._server_info

        if self.command:
            cmd = self.command if isinstance(self.command, list) else [self.command]
            proc_env = os.environ.copy()
            proc_env.update(self.env)
            if self.auth_token:
                proc_env["AETHER_AUTH_TOKEN"] = self.auth_token

            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.cwd,
                env=proc_env,
                bufsize=1,
            )

        # Handshake: initialize
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {},
            },
            "clientInfo": {
                "name": "aether-mcp-client",
                "version": "1.0.0",
            },
        }

        resp = self._send_request("initialize", init_params)
        self._server_info = resp.get("result", {})

        # Handshake: notification initialized
        self._send_notification("notifications/initialized", {})

        self._connected = True
        return self._server_info

    def list_tools(self) -> list[MCPToolDefinition]:
        """Queries the MCP server for available tools via tools/list."""
        if not self._connected:
            self.connect()

        resp = self._send_request("tools/list", {})
        result = resp.get("result", {})
        raw_tools = result.get("tools", [])

        tools: list[MCPToolDefinition] = []
        for t in raw_tools:
            if isinstance(t, dict):
                tools.append(
                    MCPToolDefinition(
                        name=t.get("name", "unnamed_tool"),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                    )
                )
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invokes a specific tool on the MCP server via tools/call."""
        if not self._connected:
            self.connect()

        params = {
            "name": name,
            "arguments": arguments,
        }
        resp = self._send_request("tools/call", params)
        if "error" in resp:
            err = resp["error"]
            err_msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(f"MCP tool error ({name}): {err_msg}")

        return resp.get("result", {})

    def close(self) -> None:
        """Closes the connection and terminates any running subprocess."""
        with self._lock:
            self._connected = False
            if self._process is not None:
                try:
                    if self._process.stdin:
                        self._process.stdin.close()
                    self._process.terminate()
                    self._process.wait(timeout=2.0)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                finally:
                    self._process = None

    def __enter__(self) -> MCPClient:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _next_request_id(self) -> int:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            return req_id

    def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        req_id = self._next_request_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        if self.endpoint_url:
            return self._send_http(payload)
        elif self._process:
            return self._send_stdio(payload, req_id)
        else:
            raise RuntimeError("MCPClient has neither endpoint_url nor active subprocess.")

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        if self.endpoint_url:
            try:
                self._send_http(payload)
            except Exception:
                pass
        elif self._process and self._process.stdin:
            try:
                line = json.dumps(payload) + "\n"
                self._process.stdin.write(line)
                self._process.stdin.flush()
            except Exception:
                pass

    def _send_http(self, payload: dict[str, Any]) -> dict[str, Any]:
        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Aether-MCPClient/1.0",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        headers.update(self.headers)

        req = urllib.request.Request(self.endpoint_url, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                resp_bytes = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                return json.loads(resp_bytes.decode(charset))
        except urllib.error.HTTPError as http_err:
            body = ""
            try:
                body = http_err.read().decode("utf-8")
            except Exception:
                pass
            raise RuntimeError(f"MCP HTTP error {http_err.code}: {body or http_err.reason}")
        except Exception as exc:
            raise RuntimeError(f"MCP HTTP connection failed: {exc}")

    def _send_stdio(self, payload: dict[str, Any], req_id: int) -> dict[str, Any]:
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("MCP subprocess stdio is not available.")

        line = json.dumps(payload) + "\n"
        self._process.stdin.write(line)
        self._process.stdin.flush()

        # Read line from stdout matching req_id
        while True:
            resp_line = self._process.stdout.readline()
            if not resp_line:
                stderr_text = ""
                if self._process.stderr:
                    stderr_text = self._process.stderr.read()
                raise RuntimeError(f"MCP subprocess terminated prematurely: {stderr_text.strip()}")

            resp_line = resp_line.strip()
            if not resp_line:
                continue

            try:
                data = json.loads(resp_line)
                # Ignore notifications received from server while awaiting response
                if "id" in data and data["id"] == req_id:
                    return data
            except Exception:
                continue


class MCPTool(Tool):
    """
    Adapter that exposes an MCP server tool as an Aether Tool.
    """

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any] | None,
        client: MCPClient,
    ) -> None:
        self.name = name
        self.description = description or f"Execute MCP tool '{name}'"
        self.input_schema = input_schema or {}
        self._client = client

    def to_json_schema(self) -> dict[str, Any]:
        """Provides the full schema advertised by the MCP server."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema or {
                    "type": "object",
                    "properties": {
                        "input_data": {
                            "type": "string",
                            "description": "Input for this tool.",
                        }
                    },
                },
            },
        }

    def execute(self, input_data: Any, context: ToolExecutionContext | None = None) -> str:
        """
        Executes the tool via the underlying MCP client.
        """
        arguments = self._resolve_arguments(input_data)
        try:
            result = self._client.call_tool(self.name, arguments)
            content = result.get("content", [])
            output_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        output_parts.append(item.get("text", ""))
                    elif item.get("type") == "image":
                        output_parts.append(f"[Image: {item.get('mimeType', 'unknown')}]")
                    elif item.get("type") == "resource":
                        output_parts.append(f"[Resource: {item.get('resource', {}).get('uri', '')}]")
                    else:
                        output_parts.append(json.dumps(item))
                elif isinstance(item, str):
                    output_parts.append(item)
                else:
                    output_parts.append(str(item))

            joined = "\n".join(output_parts).strip()
            if result.get("isError"):
                return f"[MCP TOOL ERROR] {joined or 'Tool failed without message'}"
            return joined or "[MCP TOOL COMPLETED (No text content)]"

        except Exception as exc:
            return f"[MCP TOOL ERROR] {exc}"

    def _resolve_arguments(self, input_data: Any) -> dict[str, Any]:
        if isinstance(input_data, dict):
            return input_data

        if isinstance(input_data, str):
            clean = input_data.strip()
            if clean.startswith("{") and clean.endswith("}"):
                try:
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass

            props = self.input_schema.get("properties", {})
            required = self.input_schema.get("required", [])

            # If there's an explicit required single property
            if len(required) == 1 and required[0] in props:
                return {required[0]: input_data}

            # If there is only 1 property in the schema, map to it
            if len(props) == 1:
                prop_name = next(iter(props.keys()))
                return {prop_name: input_data}

            # Check common property names
            for candidate in ("query", "prompt", "instruction", "input", "text", "city", "code", "command"):
                if candidate in props:
                    return {candidate: input_data}

            return {"input_data": input_data}

        return {"input_data": str(input_data)}


def create_mcp_tools(client: MCPClient) -> list[MCPTool]:
    """
    Connects to an MCP server, queries tools/list, and wraps each tool into an MCPTool.
    """
    definitions = client.list_tools()
    return [
        MCPTool(
            name=d.name,
            description=d.description,
            input_schema=d.input_schema,
            client=client,
        )
        for d in definitions
    ]


def register_mcp_server(
    registry: ToolRegistry,
    client: MCPClient | None = None,
    command: list[str] | str | None = None,
    endpoint_url: str | None = None,
    auth_token: str | None = None,
    headers: dict[str, str] | None = None,
) -> list[MCPTool]:
    """
    Convenience function to register all tools from an MCP server into an Aether ToolRegistry.
    """
    if client is None:
        client = MCPClient(
            command=command,
            endpoint_url=endpoint_url,
            auth_token=auth_token,
            headers=headers,
        )

    tools = create_mcp_tools(client)
    for tool in tools:
        if not registry.has(tool.name):
            registry.register(tool)
    return tools
