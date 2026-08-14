import pytest
from unittest.mock import MagicMock
from typing import Any
from aether.agents.agent import Agent
from aether.planning.types import Goal
from aether.core.execution import ExecutionStatus
from aether.core.interrupts import RequireInput
from aether.tools.base import Tool

class InterruptingTool(Tool):
    name = "interrupter"
    description = "Interrupts the execution"

    def execute(self, input_data: str, context: Any | None = None) -> str:
        raise RequireInput("Need secret code", key="code")

def test_agent_interrupt_and_resume():
    agent = Agent("test_agent")

    # Mock planning to use our tool
    # We'll use a mocked planner that produces a plan using the interrupter tool
    # and then finishes on the next step.
    agent.tools = ["interrupter"]
    agent.tool_registry.register(InterruptingTool())

    # Override achieve internally or use a mock provider that generates a plan with interrupter
    # Since we can't easily mock the provider without a complex setup, let's use the basic planner.

    # Mock the planner
    mock_planner = MagicMock()
    from aether.planning.types import CognitivePlan, Decision, DecisionAction

    # First plan: call interrupter
    plan1 = CognitivePlan(plan_id="p1", goal=Goal("test"), steps=["Call interrupter"])
    mock_planner.generate_plan.return_value = plan1

    def mock_evaluate(obs, goal, plan):
        if "Human Response: 42" in obs.result:
            return Decision(action=DecisionAction.FINISH, reasoning="Success")
        # If it wasn't the human response, it might be the step evaluation
        return Decision(action=DecisionAction.CONTINUE, reasoning="Continue")

    mock_planner.evaluate.side_effect = mock_evaluate
    agent.planner = mock_planner

    # We also need a compiler that compiles to the ToolUnit
    mock_compiler = MagicMock()
    from aether.engine.plan import ExecutionPlan
    from aether.engine.units import ToolUnit

    mock_compiler.compile.return_value = ExecutionPlan(
        units=[ToolUnit(tool_name="interrupter", input_data={})],
        metadata={}
    )
    agent.plan_compiler = mock_compiler

    # 1. Start execution
    goal = Goal("Interrupt me")
    result = agent.achieve(goal)

    assert result.success is False
    assert result.status == ExecutionStatus.INTERRUPTED
    assert result.interrupt is not None
    assert isinstance(result.interrupt, RequireInput)
    assert result.interrupt.key == "code"

    session_id = result.metadata["session_id"]

    # 2. Resume execution
    result2 = agent.resume(session_id, "42")

    assert result2.success is True
    assert result2.status == ExecutionStatus.COMPLETED
    assert result2.output == "Success"
