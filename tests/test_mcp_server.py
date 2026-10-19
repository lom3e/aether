"""
Comprehensive Acceptance and Integration Tests for Aether MCP Server (Macro 1).
Tests stdio JSON-RPC 2.0 protocol, tool execution, safety boundaries, workspace isolation,
and Antigravity configuration merging/revocation.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aether.mcp.config import (
    generate_antigravity_entry,
    merge_antigravity_config,
    revoke_antigravity_config,
)
from aether.mcp.server import AetherMCPServer
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    """Creates a temporary isolated Workspace fixture with valid directory structure."""
    ws_root = tmp_path / "test_workspace"
    ws_root.mkdir(parents=True, exist_ok=True)
    ws = Workspace(ws_root)
    ws.files_dir.mkdir(parents=True, exist_ok=True)
    (ws_root / "aether.yaml").write_text("workspace:\n  name: TestMCPWorkspace\n", encoding="utf-8")
    return ws


def test_mcp_server_initialization_and_capabilities(temp_workspace: Workspace):
    """Verifies that MCP server performs correct handshake and advertises capabilities."""
    server = AetherMCPServer(workspace=temp_workspace)
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    resp = server.handle_request(req)
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "aether-mcp"
    assert result["serverInfo"]["version"] == "1.8.0"


def test_mcp_server_notification_and_ping(temp_workspace: Workspace):
    """Verifies that notifications produce no response and ping responds with empty dict."""
    server = AetherMCPServer(workspace=temp_workspace)

    # Initialized notification must yield None
    notif_resp = server.handle_request({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    })
    assert notif_resp is None

    # Ping returns empty object
    ping_resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 42,
        "method": "ping",
        "params": {},
    })
    assert ping_resp == {"jsonrpc": "2.0", "id": 42, "result": {}}


def test_mcp_server_tools_list(temp_workspace: Workspace):
    """Verifies that tools/list exposes all 4 canonical read-only tools with valid schemas."""
    server = AetherMCPServer(workspace=temp_workspace)
    resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    })
    assert resp is not None
    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]

    expected_tools = [
        "aether_search_memory",
        "aether_get_project_context",
        "aether_list_tasks",
        "aether_list_calendar_events",
    ]
    for exp in expected_tools:
        assert exp in tool_names, f"Tool '{exp}' missing from tools/list"

    # Verify schema structure for each tool
    for t in tools:
        assert "description" in t and len(t["description"]) > 10
        assert "inputSchema" in t
        assert t["inputSchema"]["type"] == "object"
        assert "properties" in t["inputSchema"]


def test_mcp_server_search_memory_tool(temp_workspace: Workspace):
    """Verifies aether_search_memory returns structured results without exposing internal reasoning."""
    server = AetherMCPServer(workspace=temp_workspace)

    # 1. Missing query should return clean error indication
    res_missing = server.handle_request({
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {"name": "aether_search_memory", "arguments": {}},
    })
    assert res_missing is not None
    data_missing = json.loads(res_missing["result"]["content"][0]["text"])
    assert "error" in data_missing

    # 2. Valid query against workspace
    res_valid = server.handle_request({
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "aether_search_memory",
            "arguments": {"query": "architettura", "category": "decision", "limit": 5},
        },
    })
    assert res_valid is not None
    assert res_valid["result"]["isError"] is False
    content_text = res_valid["result"]["content"][0]["text"]
    data = json.loads(content_text)
    assert data["query"] == "architettura"
    assert data["category_filter"] == "decision"
    assert isinstance(data["memories"], list)
    assert "search_mode" in data


def test_mcp_server_get_project_context_tool(temp_workspace: Workspace):
    """Verifies aether_get_project_context returns project and file context truthfully."""
    # Create sample files in workspace files_dir
    sample_file = temp_workspace.files_dir / "notes.md"
    sample_file.write_text("# Project Notes\nSample content.\n", encoding="utf-8")

    server = AetherMCPServer(workspace=temp_workspace)
    resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {"name": "aether_get_project_context", "arguments": {}},
    })
    assert resp is not None
    assert resp["result"]["isError"] is False
    data = json.loads(resp["result"]["content"][0]["text"])

    assert data["workspace_id"] == temp_workspace.id
    assert "workspace_files" in data
    found_file = any(f["name"] == "notes.md" for f in data["workspace_files"])
    assert found_file is True
    assert "deliverables" in data
    assert "project_memories" in data


def test_mcp_server_list_tasks_tool(temp_workspace: Workspace):
    """Verifies aether_list_tasks returns personal tasks list with status filtering."""
    server = AetherMCPServer(workspace=temp_workspace)
    resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 13,
        "method": "tools/call",
        "params": {
            "name": "aether_list_tasks",
            "arguments": {"status": "pending", "limit": 10},
        },
    })
    assert resp is not None
    assert resp["result"]["isError"] is False
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["workspace_id"] == temp_workspace.id
    assert data["filter_status"] == "pending"
    assert isinstance(data["tasks"], list)


def test_mcp_server_calendar_events_tool_unconfigured(temp_workspace: Workspace):
    """Verifies calendar tool returns clear disconnected state when connection is not authorized."""
    server = AetherMCPServer(workspace=temp_workspace)
    resp = server.handle_request({
        "jsonrpc": "2.0",
        "id": 14,
        "method": "tools/call",
        "params": {
            "name": "aether_list_calendar_events",
            "arguments": {"limit": 5},
        },
    })
    assert resp is not None
    assert resp["result"]["isError"] is False
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["provider"] == "google_calendar"
    assert data["connected"] is False
    assert "message" in data


def test_mcp_server_unknown_tool_and_method(temp_workspace: Workspace):
    """Verifies proper JSON-RPC error codes for unknown tools (-32601) and unknown methods."""
    server = AetherMCPServer(workspace=temp_workspace)

    # 1. Unknown tool call
    call_err = server.handle_request({
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {"name": "non_existent_tool", "arguments": {}},
    })
    assert call_err is not None
    assert "error" in call_err
    assert call_err["error"]["code"] == -32601

    # 2. Unknown RPC method
    method_err = server.handle_request({
        "jsonrpc": "2.0",
        "id": 100,
        "method": "invalid/method",
        "params": {},
    })
    assert method_err is not None
    assert "error" in method_err
    assert method_err["error"]["code"] == -32601


def test_mcp_server_stdio_roundtrip(temp_workspace: Workspace):
    """Verifies that newline-delimited JSON-RPC messages are processed over stdio streams without corruption."""
    server = AetherMCPServer(workspace=temp_workspace)

    input_lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n",
    ]

    in_stream = io.StringIO("".join(input_lines))
    out_stream = io.StringIO()

    server.run_stdio(in_stream=in_stream, out_stream=out_stream)

    raw_output = out_stream.getvalue().strip().split("\n")
    assert len(raw_output) == 2  # Handshake response + tools/list response (notification yields no response)

    resp1 = json.loads(raw_output[0])
    assert resp1["id"] == 1
    assert resp1["result"]["serverInfo"]["name"] == "aether-mcp"

    resp2 = json.loads(raw_output[1])
    assert resp2["id"] == 2
    assert len(resp2["result"]["tools"]) == 4


def test_antigravity_config_safe_merge_and_revocation(tmp_path: Path):
    """Verifies non-destructive merge and revocation of Aether MCP config in Antigravity mcp_config.json."""
    config_file = tmp_path / "mcp_config.json"

    # Pre-populate with existing third-party servers
    initial_config = {
        "mcpServers": {
            "ollama": {
                "command": "python3",
                "args": ["/path/to/ollama_mcp.py"],
            },
            "vexp": {
                "command": "/path/to/vexp-core",
                "args": ["mcp"],
            },
        }
    }
    config_file.write_text(json.dumps(initial_config, indent=2), encoding="utf-8")

    # 1. Merge Aether configuration
    ok, msg = merge_antigravity_config(
        config_path=config_file,
        workspace_identifier="test-workspace-id",
        python_path="/custom/venv/bin/python",
    )
    assert ok is True
    assert "Successfully merged" in msg

    # Read back and verify all servers are preserved
    merged_data = json.loads(config_file.read_text(encoding="utf-8"))
    servers = merged_data["mcpServers"]
    assert "ollama" in servers, "Pre-existing 'ollama' server must be preserved"
    assert "vexp" in servers, "Pre-existing 'vexp' server must be preserved"
    assert "aether" in servers, "'aether' server must be added"

    aether_entry = servers["aether"]
    assert aether_entry["command"] == "/custom/venv/bin/python"
    assert aether_entry["args"] == ["-m", "aether.cli.main", "mcp", "--workspace", "test-workspace-id"]

    # 2. Revoke Aether configuration
    rev_ok, rev_msg = revoke_antigravity_config(config_path=config_file)
    assert rev_ok is True
    assert "Successfully revoked" in rev_msg

    # Read back and verify only 'aether' was removed
    after_revoke = json.loads(config_file.read_text(encoding="utf-8"))
    servers_after = after_revoke["mcpServers"]
    assert "aether" not in servers_after
    assert "ollama" in servers_after
    assert "vexp" in servers_after
