import pytest
from dataclasses import dataclass
from typing import Any

from aether.agents.agent import Agent
from aether.planning.planner import BasePlanner
from aether.planning.validation import PlanValidator, ValidationResult
from aether.planning.types import Goal, CognitivePlan, Decision, DecisionAction, Observation
from aether.providers.base import AIProvider
from aether.engine.core import ExecutionEngine
from aether.engine.plan import ExecutionPlan
from aether.engine.result import UnitExecutionResult, UnitExecutionStatus
from aether.engine.units import UnitType

class MockProvider(AIProvider):
    @property
    def capabilities(self):
        return None
    def generate(self, messages, tools=None, output_schema=None):
        return None

class MockPlanner(BasePlanner):
    def __init__(self):
        self.observations = []
        self.plan_calls = 0

    def generate_plan(self, goal: Goal, context: Any) -> CognitivePlan:
        self.plan_calls += 1
        return CognitivePlan(plan_id="p1", goal=goal, steps=["mock_step"])

    def evaluate(self, observation: Observation, goal: Goal, plan: CognitivePlan) -> Decision:
        self.observations.append(observation)
        return Decision(action=DecisionAction.FINISH, reasoning="done")

class MockValidator(PlanValidator):
    def validate(self, plan: CognitivePlan) -> ValidationResult:
        return ValidationResult(is_valid=True)

class MockExecutionEngine(ExecutionEngine):
    def __init__(self, mock_results):
        super().__init__()
        self.mock_results = mock_results

    def run(self, execution_plan: ExecutionPlan, context: Any) -> tuple[UnitExecutionResult, ...]:
        return self.mock_results

@dataclass
class DelegationResult:
    """Mock object to simulate a structured DelegationResult."""
    status: str
    data: dict

def create_mock_result(output) -> UnitExecutionResult:
    return UnitExecutionResult(
        unit_id="u1",
        unit_name="mock_tool",
        unit_type=UnitType.TOOL,
        status=UnitExecutionStatus.SUCCESS,
        output=output
    )

def test_agent_preserves_dict_payload():
    provider = MockProvider()
    planner = MockPlanner()
    validator = MockValidator()
    
    mock_dict = {"files_changed": ["a.py"], "tests_passed": True}
    engine = MockExecutionEngine(mock_results=(
        create_mock_result(mock_dict),
    ))
    
    agent = Agent(name="Test", provider=provider, planner=planner, plan_validator=validator)
    agent.execution_engine = engine  # override engine
    
    goal = Goal(description="test dict")
    agent.achieve(goal)
    
    assert len(planner.observations) == 1
    obs = planner.observations[0]
    assert obs.result == mock_dict
    assert isinstance(obs.result, dict)

def test_agent_preserves_delegation_result_payload():
    provider = MockProvider()
    planner = MockPlanner()
    validator = MockValidator()
    
    mock_obj = DelegationResult(status="success", data={"key": "value"})
    engine = MockExecutionEngine(mock_results=(
        create_mock_result(mock_obj),
    ))
    
    agent = Agent(name="Test", provider=provider, planner=planner, plan_validator=validator)
    agent.execution_engine = engine  # override engine
    
    goal = Goal(description="test obj")
    agent.achieve(goal)
    
    assert len(planner.observations) == 1
    obs = planner.observations[0]
    assert obs.result == mock_obj
    assert isinstance(obs.result, DelegationResult)

def test_agent_preserves_string_payload_legacy():
    provider = MockProvider()
    planner = MockPlanner()
    validator = MockValidator()
    
    engine = MockExecutionEngine(mock_results=(
        create_mock_result("task completato"),
    ))
    
    agent = Agent(name="Test", provider=provider, planner=planner, plan_validator=validator)
    agent.execution_engine = engine  # override engine
    
    goal = Goal(description="test string")
    agent.achieve(goal)
    
    assert len(planner.observations) == 1
    obs = planner.observations[0]
    assert obs.result == "task completato"
    assert isinstance(obs.result, str)

def test_agent_preserves_multiple_results_as_list():
    provider = MockProvider()
    planner = MockPlanner()
    validator = MockValidator()
    
    engine = MockExecutionEngine(mock_results=(
        create_mock_result("out1"),
        create_mock_result("out2"),
    ))
    
    agent = Agent(name="Test", provider=provider, planner=planner, plan_validator=validator)
    agent.execution_engine = engine  # override engine
    
    goal = Goal(description="test multiple")
    agent.achieve(goal)
    
    assert len(planner.observations) == 1
    obs = planner.observations[0]
    assert obs.result == ["out1", "out2"]
    assert isinstance(obs.result, list)
