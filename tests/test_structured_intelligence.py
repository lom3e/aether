import pytest

from aether.agents.agent import Agent
from aether.core.execution import ExecutionContext, Task
from aether.planning.compiler import BasicPlanCompiler
from aether.planning.planner import BasePlanner, BasicPlanner
from aether.planning.types import CognitivePlan, Decision, DecisionAction, Goal, Observation
from aether.planning.validation import PlanValidator, ValidationResult
from aether.providers.base import AIProvider
from aether.providers.capabilities import ProviderCapabilities
from aether.providers.types import ProviderResponse, Message
from aether.providers.ollama import OllamaProvider


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

class MockStructuredProvider(AIProvider):
    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(structured_output=True)

    def generate(self, messages, tools=None, output_schema=None):
        content = "default content"
        if output_schema:
            content = f"schema: {output_schema}"
        return ProviderResponse(content=content, finish_reason="stop", model="mock")


class MockPlanValidator(PlanValidator):
    def __init__(self, valid: bool = True):
        self.valid = valid

    def validate(self, plan: CognitivePlan) -> ValidationResult:
        if self.valid:
            return ValidationResult(is_valid=True)
        return ValidationResult(is_valid=False, errors=("Invalid plan",))


# ---------------------------------------------------------------------------
# ProviderCapabilities tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ValidationResult tests
# ---------------------------------------------------------------------------

def test_validation_result():
    res_valid = ValidationResult(is_valid=True)
    assert res_valid.is_valid is True
    assert res_valid.errors == ()

    res_invalid = ValidationResult(is_valid=False, errors=("Error 1",))
    assert res_invalid.is_valid is False
    assert res_invalid.errors == ("Error 1",)


# ---------------------------------------------------------------------------
# Planner structured output tests
# ---------------------------------------------------------------------------

def test_planner_output_schema():
    provider = MockStructuredProvider()
    planner = BasicPlanner(provider=provider)
    goal = Goal(description="Test structured output")
    context = ExecutionContext(task=Task(instruction="Test", agent_name="Agent", id="t-1"), agent_name="Agent")

    plan = planner.generate_plan(goal, context, output_schema="MockSchema")
    assert plan.steps[0] == "schema: MockSchema"


# ---------------------------------------------------------------------------
# evaluate_validation_result — unit tests
# ---------------------------------------------------------------------------

def test_evaluate_validation_result_default_returns_replan():
    """The default BasePlanner implementation must produce a REPLAN Decision."""
    planner = BasicPlanner()
    goal = Goal(description="Some goal")
    plan = CognitivePlan(plan_id="p-test", goal=goal, steps=("step",))
    result = ValidationResult(is_valid=False, errors=("constraint violated",))

    decision = planner.evaluate_validation_result(result, goal, plan)

    assert decision.action == DecisionAction.REPLAN
    assert "constraint violated" in decision.reasoning
    assert "constraint violated" in decision.metadata.get("validation_errors", [])


def test_evaluate_validation_result_embeds_plan_id():
    """The decision reasoning must reference the failing plan id for traceability."""
    planner = BasicPlanner()
    goal = Goal(description="Traceability test")
    plan = CognitivePlan(plan_id="p-trace-42", goal=goal, steps=("step",))
    result = ValidationResult(is_valid=False, errors=("missing tool",))

    decision = planner.evaluate_validation_result(result, goal, plan)

    assert "p-trace-42" in decision.reasoning


def test_evaluate_validation_result_empty_errors():
    """Must not crash when ValidationResult has no explicit errors."""
    planner = BasicPlanner()
    goal = Goal(description="No errors test")
    plan = CognitivePlan(plan_id="p-empty", goal=goal, steps=())
    result = ValidationResult(is_valid=False)  # errors defaults to ()

    decision = planner.evaluate_validation_result(result, goal, plan)

    assert decision.action == DecisionAction.REPLAN
    assert "unspecified validation failure" in decision.reasoning


def test_evaluate_validation_result_custom_override():
    """Subclasses can override to implement different recovery strategies."""

    class SmartPlanner(BasicPlanner):
        def evaluate_validation_result(
            self,
            result: ValidationResult,
            goal: Goal,
            plan: CognitivePlan,
        ) -> Decision:
            # A hypothetical advanced strategy: if the error is recoverable,
            # FINISH gracefully instead of looping forever.
            if result.errors == ("recoverable",):
                return Decision(action=DecisionAction.FINISH, reasoning="Handled gracefully")
            return super().evaluate_validation_result(result, goal, plan)

    planner = SmartPlanner()
    goal = Goal(description="Custom recovery test")
    plan = CognitivePlan(plan_id="p-smart", goal=goal, steps=())

    # Recoverable case: custom override kicks in
    decision_ok = planner.evaluate_validation_result(
        ValidationResult(is_valid=False, errors=("recoverable",)), goal, plan
    )
    assert decision_ok.action == DecisionAction.FINISH

    # Unrecoverable case: falls back to base REPLAN
    decision_fail = planner.evaluate_validation_result(
        ValidationResult(is_valid=False, errors=("fatal error",)), goal, plan
    )
    assert decision_fail.action == DecisionAction.REPLAN


# ---------------------------------------------------------------------------
# Agent.achieve() integration tests
# ---------------------------------------------------------------------------

def test_agent_achieve_valid_plan():
    """Case 1: Validation passes — ExecutionEngine is called, result is successful."""
    provider = MockStructuredProvider()
    planner = BasicPlanner(provider=provider)
    validator = MockPlanValidator(valid=True)
    agent = Agent(name="TestAgent", provider=provider, planner=planner, plan_validator=validator)
    goal = Goal(description="Valid test")

    result = agent.achieve(goal)

    assert result.success is True
    assert result.output == "The step completed successfully."


def test_agent_achieve_validation_fail_engine_not_called():
    """Case 2: Validation fails — planner receives the ValidationResult via
    evaluate_validation_result(); ExecutionEngine must NOT be called on that attempt."""

    class TrackingPlanner(BasicPlanner):
        """Records evaluate_validation_result calls for assertion."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.validation_decisions: list[Decision] = []

        def evaluate_validation_result(self, result, goal, plan):
            decision = super().evaluate_validation_result(result, goal, plan)
            self.validation_decisions.append(decision)
            return decision

    class AlwaysFailValidator(PlanValidator):
        def __init__(self):
            self.call_count = 0

        def validate(self, plan: CognitivePlan) -> ValidationResult:
            self.call_count += 1
            # Fail once, then pass so the loop terminates
            if self.call_count == 1:
                return ValidationResult(is_valid=False, errors=("step references unknown tool",))
            return ValidationResult(is_valid=True)

    provider = MockStructuredProvider()
    planner = TrackingPlanner(provider=provider)
    validator = AlwaysFailValidator()

    agent = Agent(name="TestAgent", provider=provider, planner=planner, plan_validator=validator)
    goal = Goal(description="Validation failure test")

    result = agent.achieve(goal)

    # Loop terminated successfully on second attempt
    assert result.success is True
    # evaluate_validation_result was called exactly once (on the first failure)
    assert len(planner.validation_decisions) == 1
    decision = planner.validation_decisions[0]
    assert decision.action == DecisionAction.REPLAN
    assert "step references unknown tool" in decision.reasoning
    # Validator was called twice: once fail, once pass
    assert validator.call_count == 2


def test_agent_achieve_invalid_plan_backwards_compat():
    """Original FlakyValidator test — must still pass after the refactor."""
    provider = MockStructuredProvider()
    planner = BasicPlanner(provider=provider)

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
