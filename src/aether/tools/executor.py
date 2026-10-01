from __future__ import annotations

import time
from dataclasses import dataclass

from aether.engine.result import UnitExecutionResult, UnitExecutionStatus
from aether.engine.units import UnitType
from aether.tools.base import Tool, ToolExecutionContext
from aether.core.interrupts import AgentInterrupt


@dataclass(slots=True)
class ToolExecutor:
    """
    Tool-level execution foundation.

    The executor wraps the tool execution to provide a standardized Result contract,
    error handling, execution timing, and authorization boundary enforcement.
    """
    store: Any = None

    def execute(
        self,
        tool: Tool,
        input_data: str,
        context: ToolExecutionContext | None = None
    ) -> UnitExecutionResult:
        start_time = time.perf_counter()

        try:
            from aether.tools.base import ToolClassification
            from aether.core.execution import ExecutionBoundary, ExecutionAuthority, UnauthorizedExecutionError

            classification = getattr(tool, "classification", ToolClassification.UNKNOWN)
            if classification != ToolClassification.READ_ONLY:
                if not context or not context.authority:
                    raise UnauthorizedExecutionError(
                        f"Tool '{tool.name}' (classification={getattr(classification, 'value', str(classification))}) requires valid execution authority."
                    )
                if not isinstance(context.authority, ExecutionAuthority):
                    raise UnauthorizedExecutionError(
                        f"Invalid authority type for tool '{tool.name}': expected ExecutionAuthority, got {type(context.authority).__name__}."
                    )
                target_store = getattr(context, "store", None) or self.store
                if target_store and context.workspace_id:
                    ExecutionBoundary.validate_authority(
                        authority=context.authority,
                        workspace_id=context.workspace_id,
                        store=target_store,
                        action_or_boundary=f"tool:{tool.name}",
                    )

            output = tool.execute(input_data, context)

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            return UnitExecutionResult(
                unit_id=tool.name,
                unit_name=tool.name,
                unit_type=UnitType.TOOL,
                status=UnitExecutionStatus.SUCCESS,
                output=output,
                execution_time_ms=execution_time_ms,
                metadata={
                    "input_data": input_data,
                    "task_id": context.task_id if context else None,
                    "agent_name": context.agent_name if context else None,
                }
            )
        except (AgentInterrupt, UnauthorizedExecutionError):
            raise
        except Exception as exc:
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            return UnitExecutionResult(
                unit_id=tool.name,
                unit_name=tool.name,
                unit_type=UnitType.TOOL,
                status=UnitExecutionStatus.FAILED,
                error=str(exc),
                error_type=exc.__class__.__name__,
                execution_time_ms=execution_time_ms,
                metadata={
                    "input_data": input_data,
                    "task_id": context.task_id if context else None,
                    "agent_name": context.agent_name if context else None,
                }
            )
