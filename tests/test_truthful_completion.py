import pytest
from pathlib import Path
from aether.agents.agent import Agent
from aether.agents.lifecycle import AgentLifecycleState
from aether.core.execution import Task
from aether.providers.base import AIProvider
from aether.providers.types import Message, ProviderConfig, ProviderResponse
from aether.tools.filesystem import create_filesystem_tools
from aether.tools.registry import ToolRegistry
from aether.core.security import PathSandbox


class EmptyToolCallProvider(AIProvider):
    """Provider that falsely signals tool_calls finish_reason without tool_calls."""

    def __init__(self):
        super().__init__(ProviderConfig(model="mock-empty-tc"))

    @property
    def capabilities(self):
        from aether.providers.capabilities import ProviderCapabilities
        return ProviderCapabilities(tool_calling=True)

    def generate(self, messages, tools=None, output_schema=None):
        return ProviderResponse(
            content="",
            model="mock-empty-tc",
            finish_reason="tool_calls",
            message=Message(role="assistant", content="", tool_calls=[]),
        )


def test_missing_provider_fails_truthfully():
    agent = Agent(name="NoProviderAgent")
    task = Task(agent_name="NoProviderAgent", instruction="Write an article")

    result = agent.execute(task)

    assert result.success is False
    assert "No AI provider configured" in result.error
    assert agent.lifecycle.state == AgentLifecycleState.FAILED


def test_empty_tool_calls_with_finish_reason_fails_truthfully():
    agent = Agent(
        name="EmptyTCAgent",
        provider=EmptyToolCallProvider(),
    )
    task = Task(agent_name="EmptyTCAgent", instruction="Do something with tools")

    result = agent.execute(task)

    assert result.success is False
    assert "tool call" in result.error.lower()
    assert agent.lifecycle.state == AgentLifecycleState.FAILED


class WriteFileProvider(AIProvider):
    """Provider that calls write_file tool once, then completes."""

    def __init__(self):
        super().__init__(ProviderConfig(model="mock-writer"))
        self.turn = 0

    @property
    def capabilities(self):
        from aether.providers.capabilities import ProviderCapabilities
        return ProviderCapabilities(tool_calling=True)

    def generate(self, messages, tools=None, output_schema=None):
        from aether.core.execution import ToolCall
        self.turn += 1
        if self.turn == 1:
            return ProviderResponse(
                content="Writing file...",
                model="mock-writer",
                finish_reason="tool_calls",
                message=Message(
                    role="assistant",
                    content="Writing file...",
                    tool_calls=[
                        ToolCall(
                            call_id="call-w-1",
                            tool_name="write_file",
                            arguments={"path": "output.txt", "content": "Hello Aether Artifact"},
                        )
                    ],
                ),
            )
        else:
            return ProviderResponse(
                content="Done writing the file.",
                model="mock-writer",
                finish_reason="stop",
            )


def test_artifacts_tracking_in_execution_result(tmp_path):
    sandbox = PathSandbox(root=tmp_path)
    tools = create_filesystem_tools(sandbox)
    registry = ToolRegistry()
    for t in tools:
        registry.register(t)

    agent = Agent(
        name="ArtifactAgent",
        provider=WriteFileProvider(),
        tool_registry=registry,
    )
    task = Task(agent_name="ArtifactAgent", instruction="Create output.txt")

    result = agent.execute(task)

    assert result.success is True
    assert len(result.artifacts) == 1
    assert result.artifacts[0]["path"] == "output.txt"
    assert result.artifacts[0]["action"] == "created"
    assert (tmp_path / "output.txt").read_text(encoding="utf-8") == "Hello Aether Artifact"
