from aether.agents.agent import Agent
from aether.providers.base import AIProvider


class MockProvider(AIProvider):
    def generate(self, prompt: str) -> str:
        return f"Response to: {prompt}"


def test_agent_execution():
    provider = MockProvider()

    agent = Agent(
        name="Assistant Agent",
        role="general assistant",
        provider=provider
    )

    result = agent.run("Hello Aether")

    assert result == "Response to: Hello Aether"