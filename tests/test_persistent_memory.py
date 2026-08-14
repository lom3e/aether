"""Tests for PersistentConversationMemory."""
import pytest
from pathlib import Path
from typing import Generator
import sqlite3

from aether.core.execution import Message, ToolCall
from aether.memory.persistent_conversation import PersistentConversationMemory
from aether.team.team import Team
from aether.team.config import TeamConfig, AgentConfig
from aether.agents.identity import AgentStore

@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "conversations.db")

@pytest.fixture
def memory(db_path) -> Generator[PersistentConversationMemory, None, None]:
    mem = PersistentConversationMemory(db_path, agent_id="agent_123")
    yield mem
    # cleanup not strictly needed since it's a tmp_path

def test_save_and_retrieve_message(memory):
    msg = Message(role="user", content="Hello world")
    memory.add_message("session_1", msg)

    messages = memory.get_messages("session_1")
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].content == "Hello world"
    assert messages[0].tool_calls is None

def test_save_with_tool_calls(memory):
    tc = ToolCall(call_id="call_1", tool_name="search", arguments={"q": "test"})
    msg = Message(role="assistant", content="Searching...", tool_calls=[tc])

    memory.add_message("session_1", msg)

    messages = memory.get_messages("session_1")
    assert len(messages) == 1
    assert messages[0].role == "assistant"
    assert messages[0].content == "Searching..."
    assert messages[0].tool_calls is not None
    assert len(messages[0].tool_calls) == 1

    loaded_tc = messages[0].tool_calls[0]
    assert loaded_tc.call_id == "call_1"
    assert loaded_tc.tool_name == "search"
    assert loaded_tc.arguments == {"q": "test"}

def test_persistence_across_instances(db_path):
    mem1 = PersistentConversationMemory(db_path, agent_id="agent_123")
    mem1.add_message("session_1", Message(role="user", content="Test persist"))

    mem2 = PersistentConversationMemory(db_path, agent_id="agent_123")
    messages = mem2.get_messages("session_1")
    assert len(messages) == 1
    assert messages[0].content == "Test persist"

def test_isolation_between_agents(db_path):
    mem1 = PersistentConversationMemory(db_path, agent_id="agent_A")
    mem1.add_message("session_1", Message(role="user", content="For Agent A"))

    mem2 = PersistentConversationMemory(db_path, agent_id="agent_B")
    messages = mem2.get_messages("session_1")
    assert len(messages) == 0

def test_isolation_between_sessions(memory):
    memory.add_message("session_1", Message(role="user", content="Session 1"))
    memory.add_message("session_2", Message(role="user", content="Session 2"))

    assert len(memory.get_messages("session_1")) == 1
    assert memory.get_messages("session_1")[0].content == "Session 1"

    assert len(memory.get_messages("session_2")) == 1
    assert memory.get_messages("session_2")[0].content == "Session 2"

def test_chronological_order(memory):
    memory.add_message("session_1", Message(role="user", content="1"))
    memory.add_message("session_1", Message(role="assistant", content="2"))
    memory.add_message("session_1", Message(role="user", content="3"))

    msgs = memory.get_messages("session_1")
    assert [m.content for m in msgs] == ["1", "2", "3"]

def test_set_messages_overwrites(memory):
    memory.add_message("session_1", Message(role="user", content="old"))

    new_msgs = [
        Message(role="user", content="new_1"),
        Message(role="assistant", content="new_2")
    ]
    memory.set_messages("session_1", new_msgs)

    msgs = memory.get_messages("session_1")
    assert len(msgs) == 2
    assert [m.content for m in msgs] == ["new_1", "new_2"]

def test_clear_session(memory):
    memory.add_message("session_1", Message(role="user", content="1"))
    memory.clear("session_1")
    assert len(memory.get_messages("session_1")) == 0

def test_empty_database(memory):
    assert len(memory.get_messages("unknown_session")) == 0

def test_team_wires_persistent_memory(tmp_path):
    identity_db = tmp_path / "identities.db"
    conv_db = tmp_path / "conversations.db"

    agent_store = AgentStore(identity_db)
    config = TeamConfig(agents=[AgentConfig(name="persisted_agent")])

    # 1. Create Team and verify memory is wired
    team = Team(config, agent_store=agent_store, conversation_db_path=str(conv_db))
    agent = team.get_agent("persisted_agent")

    assert agent.memory_manager is not None
    assert isinstance(agent.memory_manager.conversation_memory, PersistentConversationMemory)
    assert agent.memory_manager.conversation_memory.db_path == str(conv_db)

    agent_id_1 = agent.id

    # 2. Add message directly to memory manager for test
    # Simulating what Agent.execute would do
    from aether.core.execution import AgentContext, Task
    ctx = AgentContext(agent_name="persisted_agent", task=Task(id="dummy", instruction=""), messages=[])
    ctx.messages.append(Message(role="user", content="I remember this"))
    agent.memory_manager.persist_context(ctx)

    # 3. Recreate Team with same DBs
    team2 = Team(config, agent_store=AgentStore(identity_db), conversation_db_path=str(conv_db))
    agent2 = team2.get_agent("persisted_agent")

    assert agent2.id == agent_id_1
    assert isinstance(agent2.memory_manager.conversation_memory, PersistentConversationMemory)

    # 4. Verify message exists
    history = agent2.memory_manager.conversation_memory.get_messages("dummy")
    assert len(history) == 1
    assert history[0].content == "I remember this"
