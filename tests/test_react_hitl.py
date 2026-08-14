import json

from aether.agents.agent import Agent
from aether.core.execution import ExecutionStatus, Task
from aether.core.interrupts import RequireApproval
from aether.providers.mock import MockProvider
from aether.tools.base import Tool


class DynamicApprovalTool(Tool):
    name = "approval_tool"
    description = "Requires approval before continuing."

    def execute(self, input_data: str, context=None) -> str:
        raise RequireApproval("Approve the protected action?")


def test_react_tool_interrupt_resumes_without_duplicate_tool_execution():
    provider = MockProvider(responses=[
        json.dumps({"name": "approval_tool", "arguments": {}}),
        "The protected action is complete.",
    ])
    agent = Agent("manager", provider=provider)
    agent.tool_registry.register(DynamicApprovalTool())
    agent.tools = ["approval_tool"]

    result = agent.execute(Task(instruction="perform protected action", agent_name="manager"))

    assert result.status == ExecutionStatus.INTERRUPTED
    assert isinstance(result.interrupt, RequireApproval)
    session_id = result.metadata["session_id"]

    resumed = agent.resume(session_id, "yes")

    assert resumed.success is True
    assert resumed.output == "The protected action is complete."
    assert provider._current_index == 2
