from __future__ import annotations

from dataclasses import dataclass, field

from aether.core.execution import ExecutionContext
from aether.engine.result import UnitExecutionResult
from aether.skills.executor import SkillExecutor
from aether.skills.skill import Skill
from aether.tools.base import ToolExecutionContext
from aether.tools.executor import ToolExecutor
from aether.tools.registry import ToolRegistry


@dataclass(slots=True)
class ExecutionEngine:
    """
    Unified engine for executing tasks, skills and tools.
    """
    
    skill_executor: SkillExecutor = field(default_factory=SkillExecutor)
    tool_executor: ToolExecutor = field(default_factory=ToolExecutor)
    tool_registry: ToolRegistry | None = None
    
    def execute_skill(self, skill: Skill, context: ExecutionContext) -> UnitExecutionResult:
        """
        Executes a skill via the dedicated SkillExecutor.
        """
        return self.skill_executor.execute(skill, context)
        
    def execute_tool(
        self, 
        tool_name: str, 
        input_data: str, 
        context: ToolExecutionContext | None = None,
        override_registry: ToolRegistry | None = None,
    ) -> UnitExecutionResult:
        """
        Executes a tool via the dedicated ToolExecutor, resolving it from the registry.
        """
        registry = override_registry or self.tool_registry
        if not registry:
            raise ValueError("ToolRegistry is not configured.")
            
        tool = registry.get(tool_name)
        return self.tool_executor.execute(tool, input_data, context)
