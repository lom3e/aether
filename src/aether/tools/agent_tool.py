from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from aether.core.delegation import DelegationContext, DelegationError
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

    @property
    def function_name(self) -> str:
        """Provider-safe function identifier containing only letters, numbers, underscores, and dashes."""
        clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", self.name).strip("_")
        return clean or "delegate_agent"

    def execute(self, input_data: Any, context: ToolExecutionContext | None = None) -> str:
        """
        Create an isolated sub-task and execute it on the wrapped agent.
        """
        actual_instruction = self._extract_instruction(input_data)

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

        parent_task_id = context.task_id if context else None
        cancellation_token = (context.metadata or {}).get("cancellation_token") if context else None
        if cancellation_token and cancellation_token.is_set():
            return "[AGENT ERROR] Execution cancelled by user."

        sub_task = Task(
            agent_name=self._agent.name,
            instruction=actual_instruction,
            id=uuid4().hex,
            metadata={
                "parent_task_id": parent_task_id,
                "session_id": parent_task_id,
                "delegation_depth": child_ctx.depth,
                "delegation_chain": child_ctx.chain,
                "cancellation_token": cancellation_token,
            },
        )

        source_agent = context.agent_name if context else "unknown"
        if getattr(self._agent, "events", None):
            from aether.coordination.events import AgentEvent, EventType
            self._agent.events.emit(AgentEvent(
                event_type=EventType.TASK_DELEGATED,
                agent_name=source_agent,
                task_id=sub_task.id,
                metadata={
                    "target_agent": self._agent.name,
                    "instruction": actual_instruction,
                    "parent_task_id": parent_task_id,
                },
            ))

        result = self._agent.execute(sub_task)

        if getattr(self._agent, "events", None):
            from aether.coordination.events import AgentEvent, EventType
            self._agent.events.emit(AgentEvent(
                event_type=EventType.TASK_COMPLETED,
                agent_name=self._agent.name,
                task_id=sub_task.id,
                metadata={
                    "output": result.output,
                    "target_agent": source_agent,
                    "parent_task_id": parent_task_id,
                },
            ))

        if result.success:
            return result.output or ""
        else:
            return f"[AGENT ERROR] {result.error or 'Unknown error'}"

    def _extract_instruction(self, data: Any) -> str:
        """Extract clean instruction string from str, dict, or JSON-encoded payload."""
        if isinstance(data, dict):
            for k in ("instruction", "input_data", "task", "query", "prompt", "input"):
                val = data.get(k)
                if val is not None and str(val).strip():
                    return str(val).strip()
            return json.dumps(data)

        if isinstance(data, str):
            clean = data.strip()
            if clean.startswith("{") and clean.endswith("}"):
                try:
                    parsed = json.loads(clean)
                    if isinstance(parsed, dict):
                        for k in ("instruction", "input_data", "task", "query", "prompt", "input"):
                            val = parsed.get(k)
                            if val is not None and str(val).strip():
                                return str(val).strip()
                except Exception:
                    pass
            return clean

        return str(data) if data is not None else ""

    def to_json_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.function_name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instruction": {
                            "type": "string",
                            "description": f"The specific task instruction to delegate to the '{self._agent.name}' agent.",
                        },
                        "input_data": {
                            "type": "string",
                            "description": f"The task instruction to delegate to the '{self._agent.name}' agent.",
                        },
                    },
                    "required": ["input_data"],
                },
            },
        }
