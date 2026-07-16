from aether.agents.agent import Agent
from aether.agents.lifecycle import AgentLifecycleState
from aether.core.execution import Task
from aether.core.runtime import Runtime
from aether.providers.mock import MockProvider


def test_agent_execution():
    provider = MockProvider()

    agent = Agent(
        name="Assistant Agent",
        role="general assistant",
        provider=provider
    )

    runtime = Runtime()
    runtime.register_agent(agent)

    task = Task(agent_name="Assistant Agent", instruction="Hello Aether")
    result = runtime.execute(task)

    assert result.success is True
    assert result.output == "Mock response: Hello Aether"
    assert agent.lifecycle.state == AgentLifecycleState.COMPLETED


def test_agent_execution_without_provider_preserves_fallback():
    agent = Agent(name="Assistant Agent")
    task = Task(agent_name="Assistant Agent", instruction="Hello Aether")

    result = agent.execute(task)

    assert result.success is True
    assert result.output == "Assistant Agent received: Hello Aether"
