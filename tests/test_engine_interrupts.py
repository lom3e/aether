from aether.core.execution import ExecutionContext, Task, ToolCall
from aether.core.interrupts import RequireApproval
from aether.engine.core import ExecutionEngine
from aether.tools.base import Tool
from aether.tools.registry import ToolRegistry


class ApprovalTool(Tool):
    name = "approval_tool"
    description = "Requires a human approval before continuing."

    def execute(self, input_data: str, context=None) -> str:
        raise RequireApproval("Approve this action?")


def test_dynamic_tool_interrupt_is_not_converted_to_tool_error():
    registry = ToolRegistry()
    registry.register(ApprovalTool())
    context = ExecutionContext(
        task=Task(instruction="approve", agent_name="manager"),
        agent_name="manager",
        tool_registry=registry,
    )

    try:
        ExecutionEngine(tool_registry=registry).execute_tool_calls(
            [ToolCall(call_id="call-1", tool_name="approval_tool", arguments={})],
            context,
        )
    except RequireApproval as interrupt:
        assert interrupt.message == "Approve this action?"
    else:  # pragma: no cover - assertion documents the required control flow
        raise AssertionError("HITL interrupt was swallowed as a tool failure")
