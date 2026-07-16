from aether.agents.agent import Agent
from aether.core.execution import Task
from aether.providers.mock import MockProvider


def test_agent_execution():
    provider = MockProvider()

    agent = Agent(
        name="Assistant Agent",
        role="general assistant",
        provider=provider
    )

    task = Task(agent_name="Assistant Agent", instruction="Hello Aether")
    result = agent.execute(task)

    assert result.success is True
    assert result.output == "Mock response: Hello Aether"


def test_agent_execution_without_provider_preserves_fallback():
    agent = Agent(name="Assistant Agent")
    task = Task(agent_name="Assistant Agent", instruction="Hello Aether")

    result = agent.execute(task)

    assert result.success is True
    assert result.output == "Assistant Agent received: Hello Aether"
