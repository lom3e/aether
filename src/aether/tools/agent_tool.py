from __future__ import annotations

from typing import Any
from uuid import uuid4

from aether.core.communication import DelegationContext, DelegationError
from aether.core.execution import Task
from aether.tools.base import Tool, ToolExecutionContext


class AgentTool(Tool):
    """
    Adapter that wraps an Agent as a Tool, enabling inter-agent delegation.

    Each invocation creates an isolated sub-task with its own task_id,
    AgentContext and conversation memory. The parent's context is never
    shared with the child agent.
    """

    def __init__(
        self,
        agent: Any,  # Avoid circular import; runtime type is Agent
        delegation_context: DelegationContext | None = None,
    ) -> None:
        self.name = agent.name
        self.description = (
            f"Delegate a task to the '{agent.name}' agent (role: {agent.role})."
        )
        self._agent = agent
        self._delegation_context = delegation_context

    def execute(self, input_data: str, context: ToolExecutionContext | None = None) -> str:
        """
        Create an isolated sub-task and execute it on the wrapped agent.
        """
        # Enforce delegation safety
        if self._delegation_context is not None:
            try:
                child_ctx = self._delegation_context.delegate(self._agent.name)
            except DelegationError as exc:
                return f"[DELEGATION ERROR] {exc}"
        else:
            child_ctx = DelegationContext(
                current_agent=self._agent.name,
                parent_agent=(context.agent_name if context else None),
                depth=1,
                chain=[context.agent_name, self._agent.name] if context and context.agent_name else [self._agent.name],
            )

        # Propagate delegation context to any AgentTool the child agent may have
        if self._agent.tool_registry:
            for tool in self._agent.tool_registry.list_tools():
                if isinstance(tool, AgentTool):
                    tool._delegation_context = child_ctx

        sub_task = Task(
            agent_name=self._agent.name,
            instruction=input_data,
            id=uuid4().hex,
            metadata={
                "parent_task_id": (context.task_id if context else None),
                "delegation_depth": child_ctx.depth,
                "delegation_chain": child_ctx.chain,
            },
        )

        result = self._agent.execute(sub_task)

        if result.success:
            return result.output or ""
        else:
            return f"[AGENT ERROR] {result.error or 'Unknown error'}"

    def to_json_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_data": {
                            "type": "string",
                            "description": f"The task instruction to delegate to the '{self._agent.name}' agent.",
                        }
                    },
                    "required": ["input_data"],
                },
            },
        }
