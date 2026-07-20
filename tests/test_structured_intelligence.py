import pytest

from aether.agents.agent import Agent
from aether.core.execution import ExecutionContext, Task
from aether.planning.compiler import BasicPlanCompiler
from aether.planning.planner import BasicPlanner
from aether.planning.types import CognitivePlan, Decision, DecisionAction, Goal, Observation
from aether.planning.validation import PlanValidator, ValidationResult
from aether.providers.base import AIProvider
from aether.providers.capabilities import ProviderCapabilities
from aether.providers.types import ProviderResponse, Message
from aether.providers.ollama import OllamaProvider


class MockStructuredProvider(AIProvider):
    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(structured_output=True)

    def generate(self, messages, tools=None, output_schema=None):
        content = "default content"
        if output_schema:
            content = f"schema: {output_schema}"
            
        return ProviderResponse(
            content=content,
            finish_reason="stop",
            model="mock",
        )


class MockPlanValidator(PlanValidator):
    def __init__(self, valid: bool = True):
        self.valid = valid

    def validate(self, plan: CognitivePlan) -> ValidationResult:
        if self.valid:
            return ValidationResult(is_valid=True)
        return ValidationResult(is_valid=False, errors=("Invalid plan",))


def test_provider_capabilities():
    caps = ProviderCapabilities(tools=True, structured_output=True)
    assert caps.tools is True
    assert caps.vision is False
    assert caps.structured_output is True
    assert caps.thinking is False


def test_ollama_capabilities():
    provider = OllamaProvider()
    caps = provider.capabilities
    assert caps.tools is True
    assert caps.structured_output is True
    assert caps.thinking is True


def test_validation_result():
    res_valid = ValidationResult(is_valid=True)
    assert res_valid.is_valid is True
    assert res_valid.errors == ()

    res_invalid = ValidationResult(is_valid=False, errors=("Error 1",))
    assert res_invalid.is_valid is False
    assert res_invalid.errors == ("Error 1",)


def test_planner_output_schema():
    provider = MockStructuredProvider()
    planner = BasicPlanner(provider=provider)
    goal = Goal(description="Test structured output")
    context = ExecutionContext(task=Task(instruction="Test", agent_name="Agent", id="t-1"), agent_name="Agent")
    
    plan = planner.generate_plan(goal, context, output_schema="MockSchema")
    assert plan.steps[0] == "schema: MockSchema"


def test_agent_achieve_valid_plan():
    provider = MockStructuredProvider()
    planner = BasicPlanner(provider=provider)
    validator = MockPlanValidator(valid=True)
    agent = Agent(name="TestAgent", provider=provider, planner=planner, plan_validator=validator)
    goal = Goal(description="Valid test")
    
    result = agent.achieve(goal)
    assert result.success is True
    assert result.output == "The step completed successfully."


def test_agent_achieve_invalid_plan():
    provider = MockStructuredProvider()
    planner = BasicPlanner(provider=provider)
    
    # Make validator valid on the second try to break the loop
    class FlakyValidator(PlanValidator):
        def __init__(self):
            self.attempts = 0
            
        def validate(self, plan: CognitivePlan) -> ValidationResult:
            self.attempts += 1
            if self.attempts == 1:
                return ValidationResult(is_valid=False, errors=("First attempt fails",))
            return ValidationResult(is_valid=True)
            
    validator = FlakyValidator()
    agent = Agent(name="TestAgent", provider=provider, planner=planner, plan_validator=validator)
    goal = Goal(description="Invalid test")
    
    result = agent.achieve(goal)
    assert result.success is True
    assert validator.attempts == 2


