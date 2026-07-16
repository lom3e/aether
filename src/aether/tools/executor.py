from __future__ import annotations

import time
from dataclasses import dataclass

from aether.engine.result import UnitExecutionResult, UnitExecutionStatus
from aether.tools.base import Tool, ToolExecutionContext


@dataclass(slots=True)
class ToolExecutor:
    """
    Tool-level execution foundation.
    
    The executor wraps the tool execution to provide a standardized Result contract,
    error handling, and execution timing.
    """
    
    def execute(
        self, 
        tool: Tool, 
        input_data: str, 
        context: ToolExecutionContext | None = None
    ) -> UnitExecutionResult:
        start_time = time.perf_counter()
        
        try:
            output = tool.execute(input_data, context)
            
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            
            return UnitExecutionResult(
                unit_id=tool.name,
                unit_name=tool.name,
                unit_type="tool",
                status=UnitExecutionStatus.SUCCESS,
                output=output,
                execution_time_ms=execution_time_ms,
                metadata={
                    "input_data": input_data,
                    "task_id": context.task_id if context else None,
                    "agent_name": context.agent_name if context else None,
                }
            )
        except Exception as exc:
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            return UnitExecutionResult(
                unit_id=tool.name,
                unit_name=tool.name,
                unit_type="tool",
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
