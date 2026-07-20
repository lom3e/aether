import pytest
from dataclasses import FrozenInstanceError

from aether.core.execution import ExecutionContext, Task
from aether.planning.types import Goal, CognitivePlan, Observation, Decision, DecisionAction
from aether.planning.planner import BasicPlanner
from aether.planning.compiler import BasicPlanCompiler
from aether.agents.agent import Agent
from aether.providers.base import AIProvider
from aether.providers.types import ProviderResponse, Message


class MockProvider(AIProvider):
    def generate(self, messages, tools=None, response_format=None):
        return ProviderResponse(
            content="Use the mock tool to proceed.",
            finish_reason="stop",
            model="mock",
        )


def test_goal_immutability():
    goal = Goal(description="Test goal")
    
    assert goal.description == "Test goal"
    
    with pytest.raises(FrozenInstanceError):
        goal.description = "New description"


def test_cognitive_plan_creation():
    goal = Goal(description="Test goal")
    plan = CognitivePlan(plan_id="p-123", goal=goal, steps=("step 1", "step 2"))
    
    assert plan.plan_id == "p-123"
    assert plan.goal == goal
    assert len(plan.steps) == 2
    
    with pytest.raises(FrozenInstanceError):
        plan.plan_id = "p-456"

def test_basic_plan_compiler():
    compiler = BasicPlanCompiler()
    goal = Goal(description="Test")
    cognitive_plan = CognitivePlan(plan_id="p-1", goal=goal, steps=("step",))
    context = ExecutionContext(task=Task(instruction="Test", agent_name="Agent", id="t-1"), agent_name="Agent")
    
    engine_plan = compiler.compile(cognitive_plan, context)
    
    assert engine_plan.metadata["cognitive_plan_id"] == "p-1"
    assert len(engine_plan.units) == 0

def test_basic_planner_no_provider():
    planner = BasicPlanner(provider=None)
    goal = Goal(description="Simple test")
    context = ExecutionContext(task=Task(instruction="Simple test", agent_name="Agent", id="t-1"), agent_name="Agent")
    
    plan = planner.generate_plan(goal, context)
    assert plan.goal == goal
    assert len(plan.steps) == 1
    assert plan.steps[0] == "Simple test"
    
    # Evaluate success
    obs_success = Observation(
        plan_id=plan.plan_id,
        step_id="step-0",
        action_taken="Simple test",
        result="Success",
        is_error=False
    )
    decision = planner.evaluate(obs_success, goal, plan)
    assert decision.action == DecisionAction.FINISH
    
    # Evaluate error
    obs_err = Observation(
        plan_id=plan.plan_id,
        step_id="step-0",
        action_taken="Simple test",
        result="Failure",
        is_error=True
    )
    decision_err = planner.evaluate(obs_err, goal, plan)
    assert decision_err.action == DecisionAction.REPLAN


def test_basic_planner_with_provider():
    planner = BasicPlanner(provider=MockProvider())
    goal = Goal(description="Complex test")
    context = ExecutionContext(task=Task(instruction="Complex test", agent_name="Agent", id="t-1"), agent_name="Agent")
    
    plan = planner.generate_plan(goal, context)
    assert plan.goal == goal
    assert len(plan.steps) == 1
    assert plan.steps[0] == "Use the mock tool to proceed."


def test_agent_achieve_lifecycle():
    agent = Agent(name="TestAgent", provider=MockProvider())
    goal = Goal(description="Lifecycle test")
    
    result = agent.achieve(goal)
    
    assert result.success is True
    assert result.output == "The step completed successfully."
    assert result.metadata["goal_description"] == "Lifecycle test"
