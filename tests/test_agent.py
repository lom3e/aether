from aether.agents.agent import Agent
from aether.providers.mock import MockProvider


def test_agent_execution():
    provider = MockProvider()

    agent = Agent(
        name="Assistant Agent",
        role="general assistant",
        provider=provider
    )

    result = agent.execute("Hello Aether")

    assert result == "Mock response: Hello Aether"
