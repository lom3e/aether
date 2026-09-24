import http.server
import json
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any
import pytest

from aether.agents.agent import Agent
from aether.agents.external import ExternalAgentAdapter, ExternalAgentConfig
from aether.agents.lifecycle import AgentLifecycleState
from aether.core.execution import ExecutionContext, ExecutionResult, ExecutionStatus, Task
from aether.tools.mcp import MCPClient, MCPTool, create_mcp_tools, register_mcp_server
from aether.tools.registry import ToolRegistry
from aether.team.config import AgentConfig, Relationship, TeamConfig
from aether.team.team import Team
from aether.actions.registry import ActionRegistry
from aether.actions.executor import ActionExecutor
from aether.actions.store import ActionStore
from aether.personal.service import PersonalAgentService, IntentTier


class MockHttpWorkerHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        req_data = json.loads(body) if body else {}

        # Check auth if sent
        auth_header = self.headers.get("Authorization")

        if self.path == "/error":
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Worker internal failure"}).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        response = {
            "success": True,
            "status": "completed",
            "output": f"Processed instruction: {req_data.get('instruction')}",
            "artifacts": [{"name": "report.md", "content": "Analysis details"}],
            "metadata": {"echo_auth": auth_header},
        }
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format, *args):
        # Suppress logging during tests
        pass


@pytest.fixture
def http_worker_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), MockHttpWorkerHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def test_external_agent_http_protocol(http_worker_server):
    config = ExternalAgentConfig(
        name="cloud_analyst",
        role="deep_analyst",
        protocol="http",
        endpoint_url=f"{http_worker_server}/execute",
        auth_token="secret-worker-token-xyz",
        timeout_seconds=5.0,
    )
    adapter = ExternalAgentAdapter(config=config)

    task = Task(instruction="Analyze market volatility in Q3", id="task-ext-1")
    result = adapter.execute(task)

    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert "Processed instruction: Analyze market volatility in Q3" in (result.output or "")
    assert len(result.artifacts) == 1
    assert result.artifacts[0]["name"] == "report.md"
    assert result.metadata.get("is_external") is True
    assert result.metadata.get("protocol") == "http"
    assert adapter.lifecycle.state == AgentLifecycleState.COMPLETED


def test_external_agent_http_error(http_worker_server):
    config = ExternalAgentConfig(
        name="failing_worker",
        protocol="http",
        endpoint_url=f"{http_worker_server}/error",
        timeout_seconds=5.0,
    )
    adapter = ExternalAgentAdapter(config=config)

    task = Task(instruction="Will fail", id="task-ext-err")
    result = adapter.execute(task)

    assert result.success is False
    assert result.status == ExecutionStatus.FAILED
    assert "HTTP 500" in (result.error or "")
    assert adapter.lifecycle.state == AgentLifecycleState.FAILED


def test_external_agent_command_protocol():
    # Use python subprocess to simulate a CLI worker that reads JSON from stdin and prints JSON
    code = (
        "import sys, json; "
        "data = json.load(sys.stdin); "
        "print(json.dumps({'output': f'CLI execution: {data.get(\"instruction\")}', 'status': 'completed', 'artifacts': [{'type': 'log'}]}))"
    )
    cmd = [sys.executable, "-c", code]

    config = ExternalAgentConfig(
        name="cli_processor",
        role="batch_worker",
        protocol="command",
        command=cmd,
        timeout_seconds=10.0,
    )
    adapter = ExternalAgentAdapter(config=config)

    task = Task(instruction="Process batch 42", id="task-cli-1")
    result = adapter.execute(task)

    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED
    assert "CLI execution: Process batch 42" in (result.output or "")
    assert len(result.artifacts) == 1
    assert adapter.lifecycle.state == AgentLifecycleState.COMPLETED


def test_mcp_client_and_mcp_tool_stdio(tmp_path):
    # Create a tiny MCP server script in python
    server_script = tmp_path / "mcp_server.py"
    server_script.write_text(
        """
import sys, json

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "test-mcp", "version": "1.0"},
                    "capabilities": {"tools": {}}
                }
            }
            print(json.dumps(resp), flush=True)
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": "calc_tax",
                            "description": "Calculates tax on amount",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"amount": {"type": "number"}},
                                "required": ["amount"]
                            }
                        }
                    ]
                }
            }
            print(json.dumps(resp), flush=True)
        elif method == "tools/call":
            params = msg.get("params", {})
            args = params.get("arguments", {})
            amt = args.get("amount", 100)
            tax = amt * 0.22
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Tax: {tax}"}],
                    "isError": False
                }
            }
            print(json.dumps(resp), flush=True)
    except Exception as e:
        pass
"""
    )

    client = MCPClient(
        command=[sys.executable, str(server_script)],
        timeout_seconds=5.0,
    )
    with client:
        tools = create_mcp_tools(client)
        assert len(tools) == 1
        tool = tools[0]
        assert tool.name == "calc_tax"
        assert "Calculates tax" in tool.description

        schema = tool.to_json_schema()
        assert schema["function"]["name"] == "calc_tax"

        # Execute tool via Tool contract
        out = tool.execute(json.dumps({"amount": 200}))
        assert "Tax: 44.0" in out

        # Test registration in ToolRegistry
        registry = ToolRegistry()
        registry.register(tool)
        assert registry.has("calc_tax")
        reg_out = registry.execute("calc_tax", json.dumps({"amount": 50}))
        assert "Tax: 11.0" in reg_out


def test_team_assembling_external_agent(http_worker_server):
    config = TeamConfig(
        name="hybrid_team",
        agents=[
            AgentConfig(
                name="coordinator",
                role="team_lead",
                relationships=[Relationship(type="delegates_to", target="cloud_worker")],
            ),
            AgentConfig(
                name="cloud_worker",
                role="data_cruncher",
                type="external",
                protocol="http",
                endpoint_url=f"{http_worker_server}/execute",
                capabilities=["big_data", "analytics"],
            ),
        ],
    )

    from aether.providers.mock import MockProvider
    team = Team(config, provider=MockProvider())

    # Verify agent was instantiated as ExternalAgentAdapter
    worker = team._agents.get("cloud_worker")
    assert worker is not None
    assert isinstance(worker, ExternalAgentAdapter)
    assert worker.protocol == "http"

    # Verify delegation was wired to coordinator via AgentTool
    coordinator = team._agents.get("coordinator")
    assert coordinator is not None
    assert coordinator.tool_registry.has("cloud_worker")

    # Delegate directly through AgentTool
    tool = coordinator.tool_registry.get("cloud_worker")
    res_str = tool.execute("Crunch numbers for Q4")
    assert "Processed instruction: Crunch numbers for Q4" in res_str


def test_action_executor_delegate_external(http_worker_server, tmp_path):
    registry = ActionRegistry()
    action_def = registry.get("agents.delegate_external")
    assert action_def is not None
    assert action_def.tier.value == "act"

    store = ActionStore(tmp_path / "actions.db")
    executor = ActionExecutor(registry=registry, store=store, project_path=tmp_path)

    exec_res = executor.execute(
        action_id="agents.delegate_external",
        workspace_id="test_ws",
        input_data={
            "agent_name": "remote_bot",
            "instruction": "Fetch remote logs",
            "protocol": "http",
            "endpoint_url": f"{http_worker_server}/execute",
        },
        auto_approve=True,
    )

    assert exec_res.status.value == "success"
    assert "Processed instruction: Fetch remote logs" in (exec_res.output_data or {}).get("output", "")


def test_personal_companion_external_agent_intent(http_worker_server, tmp_path):
    from aether.workspace.workspace import Workspace
    ws = Workspace.get_or_init(tmp_path, "Companion WS")
    service = ws.personal

    intent = service.classify_intent("delega all'agente esterno l'analisi dei contratti")
    assert intent.tier == IntentTier.ACT
    assert intent.action_id == "agents.delegate_external"

    # Execute prompt through companion
    msg = service.process_prompt(
        workspace_id=ws.name,
        prompt="delega all'agente esterno worker_contract l'analisi dei contratti",
    )

    # In ACT tier, requires confirmation unless approved, or pending approval is drafted
    assert msg.role == "assistant"
    assert len(msg.steps) >= 1


@pytest.mark.asyncio
async def test_server_external_agent_and_mcp_routes(http_worker_server, tmp_path):
    from starlette.requests import Request
    from aether.server.routes import (
        list_external_agents,
        invoke_external_agent,
        ExternalAgentInvokePayload,
        list_mcp_tools,
        call_mcp_tool,
        MCPCallPayload,
    )
    from aether.team.config import TeamConfig, AgentConfig
    from aether.team.team import Team
    from aether.providers.mock import MockProvider

    team_cfg = TeamConfig(
        name="test_team",
        agents=[
            AgentConfig(
                name="cloud_bot",
                role="remote_bot",
                type="external",
                protocol="http",
                endpoint_url=f"{http_worker_server}/execute",
            ),
            AgentConfig(name="local_lead", role="lead"),
        ],
    )
    team = Team(team_cfg, provider=MockProvider())

    class MockApp:
        def __init__(self, team):
            self.state = type("State", (), {"team": team, "workspace": None})()

    app = MockApp(team)

    # 1. Test GET /api/agents/external
    req = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/agents/external",
        "headers": [],
        "app": app,
    })
    agents = await list_external_agents(req)
    assert len(agents) == 1
    assert agents[0]["name"] == "cloud_bot"
    assert agents[0]["protocol"] == "http"

    # 2. Test POST /api/agents/external/invoke
    payload = ExternalAgentInvokePayload(
        agent_name="cloud_bot",
        instruction="Ping remote service",
        protocol="http",
        endpoint_url=f"{http_worker_server}/execute",
    )
    res = await invoke_external_agent(req, payload)
    assert res["success"] is True
    assert "Processed instruction: Ping remote service" in res["output"]
