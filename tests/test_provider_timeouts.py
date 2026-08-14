"""
Regression tests for provider timeout defaults, overrides, and isolation.
"""
import pytest
from aether.providers.types import ProviderConfig
from aether.providers.ollama import OllamaProvider
from aether.providers.mock import MockProvider
from aether.providers.base import AIProvider
from aether.team.config import TeamConfig, AgentConfig
from aether.team.team import Team

def test_ollama_default_timeout():
    provider = OllamaProvider()
    assert provider.config.timeout == 120.0

def test_mock_default_timeout():
    provider = MockProvider()
    assert provider.config.timeout == 30.0

def test_base_provider_default_timeout():
    class DummyProvider(AIProvider):
        @property
        def capabilities(self):
            from aether.providers.capabilities import ProviderCapabilities
            return ProviderCapabilities()
        def generate(self, messages, tools=None, output_schema=None):
            pass

    provider = DummyProvider()
    assert provider.config.timeout == 30.0

def test_explicit_timeout_override():
    ollama_custom = OllamaProvider(ProviderConfig(timeout=45.0))
    assert ollama_custom.config.timeout == 45.0

    mock_custom = MockProvider(ProviderConfig(timeout=10.0))
    assert mock_custom.config.timeout == 10.0

def test_provider_manager_isolation():
    from aether.providers.manager import ProviderManager
    manager = ProviderManager()

    ollama_p = manager.get("ollama")
    assert ollama_p.config.timeout == 120.0

    mock_p = manager.get("mock")
    assert mock_p.config.timeout == 30.0

    # Ensure Ollama default did NOT mutate Mock default
    mock_p2 = manager.get("mock")
    assert mock_p2.config.timeout == 30.0

def test_team_timeout_override_inheritance():
    team_config = TeamConfig(
        name="test-timeouts",
        default_provider="mock",
        default_model="mock-model",
        agents=[
            AgentConfig(name="agent1", role="worker"),
            AgentConfig(name="agent2", role="specialist", metadata={"timeout": 75.0}),
            AgentConfig(name="agent3", role="local", provider="ollama", model="qwen3.5:9b"),
        ],
        metadata={"timeout": 50.0}
    )

    team = Team(config=team_config)

    a1 = team.get_agent("agent1")
    assert a1.provider.config.timeout == 50.0  # Inherits team metadata timeout

    a2 = team.get_agent("agent2")
    assert a2.provider.config.timeout == 75.0  # Specific agent override

    a3 = team.get_agent("agent3")
    assert a3.provider.config.timeout == 50.0  # Team metadata overrides ollama default
