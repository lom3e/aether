from __future__ import annotations

import os
from datetime import datetime
import pytest

from aether.core.execution import AgentContext, ExecutionContext, Message, Task
from aether.memory.base import MemoryDocument
from aether.memory.conversation import ConversationMemory, estimate_message_tokens
from aether.memory.semantic import SemanticMemory
from aether.memory.manager import MemoryManager
from aether.agents.agent import Agent
from aether.providers.base import AIProvider
from aether.providers.types import ProviderResponse


def test_memory_document_creation() -> None:
    doc = MemoryDocument(content="Test content", metadata={"source": "unit_test"})
    assert doc.content == "Test content"
    assert len(doc.id) > 0
    assert doc.metadata == {"source": "unit_test"}
    assert isinstance(doc.timestamp, datetime)


def test_estimate_message_tokens() -> None:
    msg = Message(role="user", content="Hello world")
    # Content length = 11. 11 // 4 = 2. Plus base fee 4 = 6.
    assert estimate_message_tokens(msg) == 6


def test_conversation_memory_operations() -> None:
    store = ConversationMemory()
    session_id = "session_1"
    msg1 = Message(role="user", content="Hello")
    msg2 = Message(role="assistant", content="Hi there")

    store.add_message(session_id, msg1)
    store.add_message(session_id, msg2)

    messages = store.get_messages(session_id)
    assert len(messages) == 2
    assert messages[0].content == "Hello"
    assert messages[1].content == "Hi there"

    # Overwrite messages
    store.set_messages(session_id, [msg2])
    assert len(store.get_messages(session_id)) == 1
    assert store.get_messages(session_id)[0].content == "Hi there"

    # Clear
    store.clear(session_id)
    assert len(store.get_messages(session_id)) == 0


def test_conversation_memory_truncation() -> None:
    store = ConversationMemory()
    messages = [
        Message(role="system", content="System Prompt"),  # 13 chars // 4 = 3 + 4 = 7 tokens
        Message(role="user", content="Middle Message 1"),  # 16 chars // 4 = 4 + 4 = 8 tokens
        Message(role="assistant", content="Middle Message 2"),  # 16 chars // 4 = 4 + 4 = 8 tokens
        Message(role="user", content="Last Prompt"),  # 11 chars // 4 = 2 + 4 = 6 tokens
    ]

    # Total tokens = 7 + 8 + 8 + 6 = 29 tokens
    # Truncate with max_tokens = 15.
    # System (7) + Last (6) = 13 tokens.
    # Middle Message 2 (8) cannot fit because 13 + 8 = 21 > 15.
    truncated = store.truncate_context(messages, 15)
    assert len(truncated) == 2
    assert truncated[0].content == "System Prompt"
    assert truncated[1].content == "Last Prompt"

    # Truncate with max_tokens = 22.
    # System (7) + Last (6) = 13.
    # Middle Message 2 (8) fits because 13 + 8 = 21 <= 22.
    # Middle Message 1 (8) does not fit because 21 + 8 = 29 > 22.
    truncated = store.truncate_context(messages, 22)
    assert len(truncated) == 3
    assert truncated[0].content == "System Prompt"
    assert truncated[1].content == "Middle Message 2"
    assert truncated[2].content == "Last Prompt"


def test_semantic_memory_sqlite(tmp_path) -> None:
    db_file = os.path.join(tmp_path, "test_memory.db")
    store = SemanticMemory(db_path=db_file)

    doc1 = MemoryDocument(content="Apple is a fruit.", metadata={"cat": "nature"})
    doc2 = MemoryDocument(content="Python is a programming language.", metadata={"cat": "tech"})
    doc3 = MemoryDocument(content="Bananas are sweet fruits.", metadata={"cat": "nature"})

    store.add(doc1)
    store.add(doc2)
    store.add(doc3)

    # Search fruit
    results = store.search("fruit")
    assert len(results) == 2
    # doc1 and doc3 match, sorted by keyword matching first
    contents = [d.content for d in results]
    assert "Apple is a fruit." in contents
    assert "Bananas are sweet fruits." in contents

    # Search language
    results = store.search("programming")
    assert len(results) == 1
    assert results[0].content == "Python is a programming language."

    # Clear
    store.clear()
    assert len(store.search("fruit")) == 0


def test_memory_manager_orchestration() -> None:
    conv_store = ConversationMemory()
    sem_store = SemanticMemory()
    manager = MemoryManager(conversation_memory=conv_store, semantic_memory=sem_store)

    # Add facts to semantic memory
    manager.add_fact("Aether is an agentic AI framework.", {"source": "docs"})
    manager.add_fact("The primary language of Aether is Python.")

    task = Task(id="task_123", instruction="Tell me about Aether framework")
    exec_context = ExecutionContext(task=task, agent_name="Assistant")
    agent_context = AgentContext.from_context(exec_context)
    agent_context.messages = [
        Message(role="system", content="Initial system prompt"),
        Message(role="user", content="Tell me about Aether framework"),
    ]

    manager.load_context(agent_context)

    # Context should contain injected facts
    assert len(agent_context.messages) == 3
    assert agent_context.messages[0].content == "Initial system prompt"
    assert "Aether is an agentic AI framework." in agent_context.messages[1].content
    assert agent_context.messages[2].content == "Tell me about Aether framework"

    # Persist context
    agent_context.messages.append(Message(role="assistant", content="Aether is written in Python."))
    manager.persist_context(agent_context)

    # Check conversation history has been saved
    saved_history = conv_store.get_messages("task_123")
    assert len(saved_history) == 4
    assert saved_history[-1].content == "Aether is written in Python."


class DummyProvider(AIProvider):
    def generate(self, messages: list, tools: list | None = None) -> ProviderResponse:
        return ProviderResponse(content="Dummy answer", model="dummy", finish_reason="stop")


def test_agent_integration() -> None:
    conv_store = ConversationMemory()
    sem_store = SemanticMemory()
    manager = MemoryManager(conversation_memory=conv_store, semantic_memory=sem_store)

    manager.add_fact("User's favourite color is blue.")

    provider = DummyProvider()
    agent = Agent(
        name="TestAgent",
        provider=provider,
        memory_manager=manager,
    )

    task = Task(id="session_xyz", instruction="What is my favourite color?")
    res = agent.execute(task)

    assert res.success is True
    # The conversation memory should be persisted now
    history = conv_store.get_messages("session_xyz")
    assert len(history) > 0
    # The facts system message should have been injected
    system_messages = [m.content for m in history if m.role == "system"]
    assert any("favourite color is blue" in sm for sm in system_messages)
