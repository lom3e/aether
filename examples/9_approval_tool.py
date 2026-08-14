import os
import asyncio
from typing import Any
from aether.agents.agent import Agent
from aether.planning.types import Goal
from aether.tools.base import Tool
from aether.core.interrupts import RequireApproval
from aether.core.execution import ExecutionStatus
from aether.providers.manager import ProviderManager

from aether.planning.planner import BasePlanner
from aether.planning.compiler import PlanCompiler
from aether.planning.types import CognitivePlan, Decision, DecisionAction
from aether.engine.plan import ExecutionPlan
from aether.engine.units import ToolUnit
import uuid

class DeleteFileTool(Tool):
    name = "delete_file"
    description = "Deletes a file from the disk. Dangerous!"

    def execute(self, input_data: str, context: Any | None = None) -> str:
        import json
        try:
            data = json.loads(input_data)
            filename = data.get("filename", "unknown")
            force = data.get("force", False)
        except:
            filename = input_data
            force = False
        if not force:
            # We raise RequireApproval so the agent suspends execution
            raise RequireApproval(
                message=f"Agent wants to delete file: {filename}. Do you approve?",
                context={"filename": filename}
            )

        # The user approved it, so we simulate the deletion
        return f"File '{filename}' deleted successfully."

class ApprovalPlanner(BasePlanner):
    def generate_plan(self, goal: Goal, context: Any, output_schema: Any = None) -> CognitivePlan:
        return CognitivePlan(plan_id=f"plan-{uuid.uuid4().hex[:8]}", goal=goal, steps=["delete_file"])

    def evaluate(self, observation: Observation, goal: Goal, plan: CognitivePlan) -> Decision:
        if observation.result and "Human Response" in observation.result:
            return Decision(action=DecisionAction.FINISH, reasoning="User answered.")
        if observation.is_error:
            return Decision(action=DecisionAction.REPLAN, reasoning="Error")
        return Decision(action=DecisionAction.CONTINUE, reasoning="Continue")

class ApprovalCompiler(PlanCompiler):
    def compile(self, plan: CognitivePlan, context: Any) -> ExecutionPlan:
        units = []
        for step in plan.steps:
            if step == "delete_file":
                units.append(ToolUnit(tool_name="delete_file", input_data="old_logs.txt"))
        return ExecutionPlan(units=units, metadata={"cognitive_plan_id": plan.plan_id})

async def main():
    # Setup Provider
    from aether.providers.types import ProviderConfig
    manager = ProviderManager()
    from aether.providers.mock import MockProvider
    manager.register("mock", MockProvider)
    provider = manager.get("mock")

    # Initialize Agent
    agent = Agent(
        "admin_agent",
        role="System Admin",
        provider=provider,
        planner=ApprovalPlanner(provider=provider),
        plan_compiler=ApprovalCompiler()
    )
    agent.tool_registry.register(DeleteFileTool())
    agent.tools = ["delete_file"]

    goal = Goal("Delete the file 'old_logs.txt'")

    print("Starting agent...")
    result = agent.achieve(goal)

    if result.status == ExecutionStatus.INTERRUPTED:
        print("\n--- AGENT SUSPENDED ---")
        interrupt = result.interrupt
        print(f"SECURITY ALERT: {interrupt.message}")

        user_response = input("Type 'yes' to approve, or anything else to reject: ")

        print("\n--- RESUMING AGENT ---")
        session_id = result.metadata["session_id"]

        # We tell the agent the user's decision
        if user_response.lower().strip() == 'yes':
            # The agent will re-evaluate the observation "Human Response: yes"
            # In a real scenario, the agent would then decide to call the tool again with force=True
            response = "Approved. Proceed with force=True."
        else:
            response = "Rejected. Do not delete the file."

        result = agent.resume(session_id, response)

    print(f"\nFinal Result: {result.output}")
    print(f"Success: {result.success}")

if __name__ == "__main__":
    asyncio.run(main())
