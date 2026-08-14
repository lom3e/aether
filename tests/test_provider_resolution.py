"""Tests for dynamic provider resolution across Team and Agents."""
import pytest
import yaml
from pathlib import Path

from aether.team.loader import TeamLoader
from aether.team.team import Team
from aether.team.config import TeamConfig, AgentConfig
from aether.providers.manager import ProviderManager
from aether.providers.mock import MockProvider
from aether.providers.base import AIProvider

class DummyOpenAI(MockProvider):
    pass

class DummyAnthropic(MockProvider):
    pass

class DummyOllama(MockProvider):
    pass


@pytest.fixture
def mock_manager(monkeypatch):
    """Inject a dummy ProviderManager that returns MockProviders."""
    manager = ProviderManager()
    manager.register("openai", DummyOpenAI)
    manager.register("anthropic", DummyAnthropic)
    manager.register("ollama", DummyOllama)

    # We monkeypatch the import inside _provider_for
    # But since it creates it dynamically, we can just patch ProviderManager class
    def mock_init(self):
        self._registry = manager._registry

    monkeypatch.setattr(ProviderManager, "__init__", mock_init)
    return manager


def test_provider_resolution_global_fallback(mock_manager):
    config = TeamConfig(
        default_provider="openai",
        default_model="gpt-4o",
        agents=[AgentConfig(name="manager")]
    )
    team = Team(config)
    agent = team.get_agent("manager")

    assert isinstance(agent.provider, DummyOpenAI)
    assert agent.provider.config.model == "gpt-4o"


def test_provider_resolution_agent_override(mock_manager):
    config = TeamConfig(
        default_provider="openai",
        agents=[
            AgentConfig(name="manager", provider="anthropic", model="claude-sonnet")
        ]
    )
    team = Team(config)
    agent = team.get_agent("manager")

    assert isinstance(agent.provider, DummyAnthropic)
    assert agent.provider.config.model == "claude-sonnet"


def test_provider_resolution_mixed_agents(mock_manager):
    config = TeamConfig(
        default_provider="openai",
        default_model="gpt-4o",
        agents=[
            AgentConfig(name="manager", provider="anthropic", model="claude-sonnet"),
            AgentConfig(name="researcher", provider="ollama", model="qwen3"),
            AgentConfig(name="writer") # falls back to team default
        ]
    )
    team = Team(config)

    manager = team.get_agent("manager")
    researcher = team.get_agent("researcher")
    writer = team.get_agent("writer")

    assert isinstance(manager.provider, DummyAnthropic)
    assert manager.provider.config.model == "claude-sonnet"

    assert isinstance(researcher.provider, DummyOllama)
    assert researcher.provider.config.model == "qwen3"

    assert isinstance(writer.provider, DummyOpenAI)
    assert writer.provider.config.model == "gpt-4o"


def test_yaml_loader_dict_formats(tmp_path):
    yaml_content = """
team:
  name: research-team
  provider:
    name: openai
    model: gpt-4o

agents:
  - name: manager
    role: coordinator
    provider:
      name: anthropic
      model: claude-sonnet

  - name: researcher
    role: researcher
    provider: ollama
    model: qwen3
"""
    file_path = tmp_path / "team.yaml"
    file_path.write_text(yaml_content)

    config = TeamLoader.from_yaml(file_path)

    assert config.default_provider == "openai"
    assert config.default_model == "gpt-4o"

    manager = config.get_agent("manager")
    assert manager.provider == "anthropic"
    assert manager.model == "claude-sonnet"

    researcher = config.get_agent("researcher")
    assert researcher.provider == "ollama"
    assert researcher.model == "qwen3"


def test_yaml_loader_backward_compatibility(tmp_path):
    yaml_content = """
team:
  name: old-team
  provider: ollama
  model: llama3

agents:
  - name: worker
"""
    file_path = tmp_path / "team.yaml"
    file_path.write_text(yaml_content)

    config = TeamLoader.from_yaml(file_path)

    assert config.default_provider == "ollama"
    assert config.default_model == "llama3"

    worker = config.get_agent("worker")
    assert worker.provider is None
    assert worker.model is None


def test_provider_resolution_invalid_provider_fallback(mock_manager):
    # If the provider is completely unknown, and we passed a provider instance to Team,
    # it should log a warning and fallback to the instance.
    config = TeamConfig(
        default_provider="openai",
        agents=[AgentConfig(name="manager", provider="unknown_provider")]
    )

    fallback_provider = DummyOllama()
    team = Team(config, provider=fallback_provider)

    agent = team.get_agent("manager")
    assert agent.provider is fallback_provider
