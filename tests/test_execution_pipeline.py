from aether.agents.agent import Agent
from aether.core.execution import ExecutionResult, Task
from aether.core.runtime import Runtime
from aether.providers.base import AIProvider
from aether.providers.mock import MockProvider


class FailingProvider(AIProvider):
    def generate(self, messages, tools=None):
        raise RuntimeError("provider failed")



def test_task_and_result_models_can_be_created():
    task = Task(agent_name="Assistant Agent", instruction="Hello Aether")
    result = ExecutionResult(success=True, output="ok", metadata={"source": "test"})

    assert task.agent_name == "Assistant Agent"
    assert task.instruction == "Hello Aether"
    assert task.id
    assert result.success is True
    assert result.output == "ok"
    assert result.error is None
    assert result.metadata == {"source": "test"}


def test_runtime_executes_task_through_agent_and_provider():
    runtime = Runtime()
    agent = Agent(name="Assistant Agent", provider=MockProvider())
    runtime.register_agent(agent)

    result = runtime.execute(Task(agent_name="Assistant Agent", instruction="Hello Aether"))

    assert result.success is True
    assert result.output == "Mock response: Hello Aether"
    assert result.metadata["agent_name"] == "Assistant Agent"
    assert result.metadata["task_id"]


def test_runtime_returns_failure_for_missing_agent():
    runtime = Runtime()

    result = runtime.execute(Task(agent_name="Unknown Agent", instruction="Hello Aether"))

    assert result.success is False
    assert "not registered" in result.error
    assert result.metadata["agent_name"] == "Unknown Agent"


def test_runtime_returns_failure_when_provider_raises():
    runtime = Runtime()
    agent = Agent(name="Assistant Agent", provider=FailingProvider())
    runtime.register_agent(agent)

    result = runtime.execute(Task(agent_name="Assistant Agent", instruction="Hello Aether"))

    assert result.success is False
    assert result.error == "provider failed"
    assert result.metadata["agent_name"] == "Assistant Agent"
