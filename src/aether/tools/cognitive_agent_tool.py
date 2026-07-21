from __future__ import annotations

from typing import Any
from uuid import uuid4

from aether.core.delegation import DelegationContext, DelegationError
from aether.planning.delegation import DelegationRequest, DelegationResult
from aether.planning.types import Goal
from aether.tools.base import Tool, ToolExecutionContext


class CognitiveAgentTool(Tool):
    """
    Adapter that wraps an Agent as a Cognitive Tool, enabling inter-agent delegation.
    This differs from the legacy AgentTool by utilizing the `DelegationRequest`
    and `Goal` cognitive workflow, instead of raw `Task` executions.
    """

    def __init__(
        self,
        agent: Any,  # Avoid circular import; runtime type is Agent
        delegation_context: DelegationContext | None = None,
    ) -> None:
        self.name = agent.name
        self.description = (
            f"Delegate a cognitive goal to the '{agent.name}' agent (role: {agent.role})."
        )
        self._agent = agent
        self._delegation_context = delegation_context

    def execute(
        self, input_data: dict[str, Any], context: ToolExecutionContext | None = None
    ) -> DelegationResult:
        """
        Creates a Goal from the DelegationRequest and invokes `achieve` on the child agent.
        """
        # 1. Parse and validate DelegationRequest
        try:
            req = DelegationRequest(**input_data)
        except TypeError as exc:
            return DelegationResult(
                success=False, output=None, metadata={"error": f"Invalid delegation request format: {exc}"}
            )

        # 2. Enforce delegation safety
        if self._delegation_context is not None:
            try:
                child_ctx = self._delegation_context.delegate(self._agent.name)
            except DelegationError as exc:
                return DelegationResult(
                    success=False, output=None, metadata={"error": f"Delegation error: {exc}"}
                )
        else:
            # If parent didn't provide a context, start a new delegation chain
            child_ctx = DelegationContext(
                current_agent=self._agent.name,
                parent_agent=(context.agent_name if context else None),
                depth=1,
                chain=[context.agent_name, self._agent.name]
                if context and context.agent_name
                else [self._agent.name],
            )

        # 3. Propagate delegation context to any CognitiveAgentTool the child agent may have
        if self._agent.tool_registry:
            for tool in self._agent.tool_registry.list_tools():
                if isinstance(tool, CognitiveAgentTool):
                    tool._delegation_context = child_ctx

        # 4. Create the Goal
        goal = Goal(
            description=req.goal_description,
            success_criteria=tuple(req.success_criteria) if req.success_criteria else (),
            constraints=tuple(req.constraints) if req.constraints else (),
        )

        # 5. Execute the Goal on the child agent (cognitive cycle)
        # Note: We do NOT pass execution context implicitly to avoid shared memory.
        # Isolation is strictly maintained.
        result = self._agent.achieve(goal)

        # 6. Return structured DelegationResult
        return DelegationResult(
            success=result.success,
            output=result.output,
            metadata={
                "parent_task_id": (context.task_id if context else None),
                "delegation_depth": child_ctx.depth,
                "delegation_chain": child_ctx.chain,
                "child_execution_metadata": result.metadata,
                "reasoning_transferred": req.reasoning,
                "context_transferred": req.context,
            },
        )

    def to_json_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "goal_description": {
                            "type": "string",
                            "description": "The specific sub-goal the child agent must achieve.",
                        },
                        "success_criteria": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Criteria to verify the goal has been achieved.",
                        },
                        "constraints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Rules or constraints the child agent must follow.",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Why this task is being delegated.",
                        },
                        "context": {
                            "type": "object",
                            "description": "Structured context, data, or variables transferred to the child.",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["goal_description"],
                },
            },
        }
