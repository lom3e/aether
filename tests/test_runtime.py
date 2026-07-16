from aether.agents.agent import Agent
from aether.core.runtime import Runtime
from aether.providers.mock import MockProvider


def test_runtime_can_register_and_execute_agent():
    runtime = Runtime()
    agent = Agent(name="Assistant Agent", provider=MockProvider())

    runtime.register_agent(agent)

    result = runtime.execute("Assistant Agent", "Hello Aether")

    assert runtime.get_agent("Assistant Agent") is agent
    assert result == "Mock response: Hello Aether"
