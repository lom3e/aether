"""
Tests for Stop Cancellation, In-Flight Message Persistence, and Restart Recovery.

Verifies:
- Test A: Stop cancellation cleanly interrupts active agent/team execution, breaks provider streaming, and records status 'interrupted'.
- Test B: User messages are immediately persisted to SQLite and never lost; stale active conversations on restart recover truthfully with an interruption notice.
- Test C: Subsequent conversation turns continue normally after interruption.
- Test D: Dual-channel stop endpoint signals cancellation token, updates status to interrupted, appends truthful message.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Iterator
from unittest.mock import MagicMock

import pytest

from aether.agents.agent import Agent
from aether.agents.lifecycle import AgentLifecycleState
from aether.conversations.store import ConversationStore
from aether.core.execution import ExecutionResult, ExecutionStatus, Task
from aether.providers.mock import MockProvider
from aether.providers.types import Message, ProviderStreamChunk
from aether.team.config import AgentConfig, TeamConfig
from aether.team.team import Team


class SlowStreamingProvider(MockProvider):
    """A mock provider that streams slowly and detects when the consumer stops consuming."""

    def __init__(self) -> None:
        super().__init__()
        self.stream_closed = False
        self.chunks_yielded = 0

    def generate_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> Iterator[ProviderStreamChunk]:
        try:
            for i in range(100):
                self.chunks_yielded += 1
                yield ProviderStreamChunk(text=f"chunk_{i} ")
                time.sleep(0.01)
        finally:
            self.stream_closed = True


def test_test_a_stop_cancellation_terminates_agent_stream():
    """Verify that setting cancellation_token immediately breaks streaming and returns INTERRUPTED."""
    provider = SlowStreamingProvider()
    agent = Agent(name="Worker", role="assistant", provider=provider)

    cancel_token = threading.Event()

    def cancel_after():
        time.sleep(0.03)
        cancel_token.set()

    t = threading.Thread(target=cancel_after)
    t.start()

    task = Task(
        agent_name="Worker",
        instruction="Generate lots of text",
        metadata={"cancellation_token": cancel_token},
    )

    result = agent.execute(task)
    t.join()

    assert result.status == ExecutionStatus.INTERRUPTED
    assert result.success is False
    assert "Execution cancelled by user" in (result.error or "")
    assert provider.stream_closed is True
    assert agent.lifecycle.state == AgentLifecycleState.FAILED


def test_test_a_stop_cancellation_in_team_run():
    """Verify that Team.run respects the cancellation_token and returns ExecutionStatus.INTERRUPTED."""
    provider = SlowStreamingProvider()
    cfg = TeamConfig(
        name="TestTeam",
        agents=[AgentConfig(name="Intelligence Lead", role="Lead", model="mock")],
    )
    team = Team(config=cfg)
    team._agents["Intelligence Lead"] = Agent(
        name="Intelligence Lead",
        role="Lead",
        provider=provider,
    )

    cancel_token = threading.Event()

    def cancel_after():
        time.sleep(0.03)
        cancel_token.set()

    t = threading.Thread(target=cancel_after)
    t.start()

    result = team.run(
        "Create a file named carshine-test.md",
        cancellation_token=cancel_token,
    )
    t.join()

    assert result.status == ExecutionStatus.INTERRUPTED
    assert result.success is False
    assert provider.stream_closed is True


def test_test_b_message_persistence_and_restart_recovery(tmp_path):
    """
    Verify that user prompt is persisted in SQLite, and if the app crashes/restarts while active,
    reset_stale_active_conversations preserves the prompt and adds a truthful restart message.
    """
    db_path = tmp_path / "conversations.db"
    store = ConversationStore(db_path)

    # 1. Create a conversation and add user prompt
    conv = store.create(title="CarShine Detailing")
    conv_id = conv["id"]

    user_prompt = (
        "Create a file named carshine-test.md containing exactly these three bullet points:\n"
        "* Exterior detailing\n"
        "* Interior deep cleaning\n"
        "* Ceramic coating\n"
        "Save the file in the workspace."
    )
    user_msg = store.add_message(conv_id=conv_id, role="user", content=user_prompt)
    assert user_msg["content"] == user_prompt

    # 2. Simulate task starting and conversation set to 'active'
    store.update(conv_id, status="active")
    active_conv = store.get(conv_id)
    assert active_conv["status"] == "active"

    # 3. Simulate application restart (e.g. after force quit)
    recovered_count = store.reset_stale_active_conversations()
    assert recovered_count == 1

    # 4. Verify conversation status and messages
    recovered_conv = store.get(conv_id)
    assert recovered_conv["status"] == "interrupted"

    messages = store.get_messages(conv_id)
    assert len(messages) == 2

    # Verify user message was preserved untouched
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == user_prompt

    # Verify assistant restart message was appended truthfully
    assert messages[1]["role"] == "assistant"
    assert "Execution interrupted by application restart." in messages[1]["content"]
    assert messages[1]["metadata"].get("interrupted") is True
    assert messages[1]["metadata"].get("interrupted_by") == "restart"

    # Verify activity was recorded
    activities = recovered_conv.get("activities", [])
    assert any(a.get("type") == "task_interrupted" for a in activities)


def test_test_c_clean_recovery_subsequent_turns(tmp_path):
    """
    Verify that after an interrupted task and restart recovery,
    subsequent user prompts can be sent and executed cleanly without corruption.
    """
    db_path = tmp_path / "conversations.db"
    store = ConversationStore(db_path)

    conv = store.create(title="CarShine Detailing")
    conv_id = conv["id"]

    # Turn 1: Interrupted
    store.add_message(conv_id, "user", "Create carshine-test.md")
    store.update(conv_id, status="active")
    store.reset_stale_active_conversations()

    conv_state = store.get(conv_id)
    assert conv_state["status"] == "interrupted"

    # Turn 2: Subsequent message after restart
    turn2_prompt = "Let's retry: please create carshine-test.md now."
    store.add_message(conv_id, "user", turn2_prompt)
    store.update(conv_id, status="active")

    # Team runs and finishes turn 2
    provider = MockProvider()
    cfg = TeamConfig(
        name="Team",
        agents=[AgentConfig(name="Lead", role="Lead", model="mock")],
    )
    team = Team(config=cfg)
    team._agents["Lead"] = Agent(name="Lead", role="Lead", provider=provider)

    result = team.run(turn2_prompt, session_id=conv_id)
    assert result.success is True
    assert result.status == ExecutionStatus.COMPLETED

    store.add_message(conv_id, "assistant", result.output, agent_name="Lead")
    store.update(conv_id, status="completed")

    final_conv = store.get(conv_id)
    assert final_conv["status"] == "completed"

    messages = store.get_messages(conv_id)
    assert len(messages) == 4
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["metadata"].get("interrupted") is True
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == turn2_prompt
    assert messages[3]["role"] == "assistant"
    assert messages[3]["content"] == result.output


@pytest.mark.asyncio
async def test_dual_channel_stop_endpoint(tmp_path):
    """Verify that stop_conversation_task endpoint signals cancellation and updates conversation state."""
    from aether.server.routes import stop_conversation_task
    from aether.workspace.workspace import Workspace

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    ws = Workspace(ws_dir)
    ws.data_dir.mkdir(parents=True, exist_ok=True)

    conv = ws.conversations.create(title="Stop Test")
    conv_id = conv["id"]
    ws.conversations.add_message(conv_id, "user", "Do something long")
    ws.conversations.update(conv_id, status="active")

    cancel_token = threading.Event()
    mock_request = MagicMock()
    mock_request.app.state.workspace = ws
    mock_request.app.state.cancellation_tokens = {conv_id: cancel_token}
    mock_request.app.state.active_tasks = {}
    mock_request.app.state.chat_sockets = set()

    resp = await stop_conversation_task(mock_request, conv_id)
    assert resp["status"] == "ok"
    assert resp["conv_id"] == conv_id

    assert cancel_token.is_set() is True

    conv_data = ws.conversations.get(conv_id)
    assert conv_data["status"] == "interrupted"
    messages = ws.conversations.get_messages(conv_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Execution stopped by user."
    assert messages[1]["metadata"].get("interrupted") is True
    assert messages[1]["metadata"].get("interrupted_by") == "user"
