"""Tests for team relationships and delegation wiring."""
import pytest

from aether.team.config import AgentConfig, Relationship, TeamConfig
from aether.team.team import Team


def test_delegates_to_wiring():
    config = TeamConfig(
        agents=[
            AgentConfig(name="manager", relationships=[Relationship("delegates_to", "worker")]),
            AgentConfig(name="worker"),
        ]
    )
    team = Team(config)
    manager = team.get_agent("manager")

    assert "worker" in manager.tools
    assert manager.tool_registry.get("worker") is not None


def test_invalid_relationship_target_raises_error():
    config = TeamConfig(
        agents=[
            AgentConfig(name="manager", relationships=[Relationship("delegates_to", "ghost")]),
        ]
    )
    with pytest.raises(ValueError, match="not found in team"):
        Team(config)


def test_collaborates_with_is_validated_but_not_wired_as_tool():
    config = TeamConfig(
        agents=[
            AgentConfig(name="manager", relationships=[Relationship("collaborates_with", "peer")]),
            AgentConfig(name="peer"),
        ]
    )
    team = Team(config)
    manager = team.get_agent("manager")

    assert "peer" not in manager.tools


def test_reports_to_is_validated_but_not_wired_as_tool():
    config = TeamConfig(
        agents=[
            AgentConfig(name="worker", relationships=[Relationship("reports_to", "boss")]),
            AgentConfig(name="boss"),
        ]
    )
    team = Team(config)
    worker = team.get_agent("worker")

    assert "boss" not in worker.tools


def test_agent_tool_emits_delegation_events():
    config = TeamConfig(
        agents=[
            AgentConfig(name="manager", relationships=[Relationship("delegates_to", "worker")]),
            AgentConfig(name="worker"),
        ]
    )
    # We must mock the provider to force the manager to call the worker tool
    from aether.providers.mock import MockProvider

    class DelegatingProvider(MockProvider):
        def generate(self, messages, tools=None, output_schema=None):
            from aether.core.execution import Message, ToolCall
            has_tool_result = any(m.role == "tool" for m in messages)
            print(f"Messages: {[m.content for m in messages]}")
            is_manager = any(m.content and "start" in m.content for m in messages)

            if is_manager and not has_tool_result:
                from aether.providers.types import ProviderResponse
                return ProviderResponse(
                    content="",
                    model="mock",
                    finish_reason="tool_calls",
                    message=Message(
                        role="assistant",
                        content="",
                        tool_calls=[ToolCall("call_123", "worker", {"input_data": "do this"})]
                    )
                )

            from aether.providers.types import ProviderResponse
            return ProviderResponse(
                content="done",
                model="mock",
                finish_reason="stop",
                message=Message(role="assistant", content="done")
            )

    team = Team(config, provider=DelegatingProvider())

    events_recorded = []
    def record_event(evt):
        events_recorded.append((evt.event_type.value, getattr(evt, 'agent_name', None), evt.metadata.get("tool_name"), evt.metadata.get("target_agent")))

    team.emitter.on(getattr(__import__('aether.coordination.events', fromlist=['EventType']), 'EventType').TASK_DELEGATED, record_event)
    team.emitter.on(getattr(__import__('aether.coordination.events', fromlist=['EventType']), 'EventType').TOOL_CALLED, record_event)
    team.emitter.on(getattr(__import__('aether.coordination.events', fromlist=['EventType']), 'EventType').TOOL_COMPLETED, record_event)

    team.run("start")

    assert ("task_delegated", "manager", None, "worker") in events_recorded
    assert ("tool_called", "manager", "worker", None) in events_recorded
    assert ("tool_completed", "manager", "worker", None) in events_recorded
