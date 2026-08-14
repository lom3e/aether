import os
import asyncio
from typing import Any
from aether.agents.agent import Agent
from aether.planning.types import Goal
from aether.tools.base import Tool
from aether.core.interrupts import RequireInput
from aether.core.execution import ExecutionStatus
from aether.providers.mock import MockProvider
from aether.providers.types import ProviderResponse, Message
from aether.providers.manager import ProviderManager

from aether.planning.planner import BasePlanner
from aether.planning.compiler import PlanCompiler
from aether.planning.types import CognitivePlan, Decision, DecisionAction
from aether.engine.plan import ExecutionPlan
from aether.engine.units import ToolUnit
import uuid

class AskUserTool(Tool):
    name = "ask_user"
    description = "Ask the user for input on a specific topic."

    def execute(self, input_data: str, context: Any | None = None) -> str:
        topic = input_data or "general input"
        # Instead of doing an input() block, which hangs the engine and uses deadline time,
        # we raise a RequireInput interrupt.
        raise RequireInput(
            message=f"The agent needs your input on: {topic}",
            key="user_input",
            context={"topic": topic}
        )



class HitlPlanner(BasePlanner):
    def generate_plan(self, goal: Goal, context: Any, output_schema: Any = None) -> CognitivePlan:
        return CognitivePlan(plan_id=f"plan-{uuid.uuid4().hex[:8]}", goal=goal, steps=["ask_user"])

    def evaluate(self, observation: Observation, goal: Goal, plan: CognitivePlan) -> Decision:
        if observation.result and "Human Response" in observation.result:
            return Decision(action=DecisionAction.FINISH, reasoning="User answered.")
        if observation.is_error:
            return Decision(action=DecisionAction.REPLAN, reasoning="Error")
        return Decision(action=DecisionAction.CONTINUE, reasoning="Continue")

class HitlCompiler(PlanCompiler):
    def compile(self, plan: CognitivePlan, context: Any) -> ExecutionPlan:
        units = []
        for step in plan.steps:
            if step == "ask_user":
                units.append(ToolUnit(tool_name="ask_user", input_data="favorite color"))
        return ExecutionPlan(units=units, metadata={"cognitive_plan_id": plan.plan_id})

async def main():
    # Setup Provider
    from aether.providers.types import ProviderConfig
    manager = ProviderManager()
    manager.register("mock", MockProvider)
    provider = manager.get("mock")

    # Initialize Agent
    agent = Agent(
        "hitl_agent",
        role="Assistant",
        provider=provider,
        planner=HitlPlanner(provider=provider),
        plan_compiler=HitlCompiler()
    )
    agent.tool_registry.register(AskUserTool())
    agent.tools = ["ask_user"]

    # We will use the execution loop
    goal = Goal("Ask the user for their favorite color, and then say 'I like [color] too!'")

    print("Starting agent...")
    result = agent.achieve(goal)

    if result.status == ExecutionStatus.INTERRUPTED:
        print("\n--- AGENT SUSPENDED ---")
        interrupt = result.interrupt
        print(f"Agent says: {interrupt.message}")

        # We can safely run input() here on the main thread, the agent is completely suspended!
        user_response = input("Your response: ")

        print("\n--- RESUMING AGENT ---")
        session_id = result.metadata["session_id"]
        result = agent.resume(session_id, user_response)

    print(f"\nFinal Result: {result.output}")
    print(f"Success: {result.success}")

if __name__ == "__main__":
    asyncio.run(main())
