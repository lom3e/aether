"""
Unit tests for ConversationStore lifecycle operations: editing, truncating, deleting, archiving, duplicating, and searching.
"""
import pytest
from pathlib import Path
import tempfile

from aether.conversations.store import ConversationStore, generate_smart_title


def test_conversation_smart_title():
    assert generate_smart_title("Analizza i competitor del mercato italiano") == "Analizza i competitor del mercato italiano"
    assert generate_smart_title("# Titolo con markdown") == "Titolo con markdown"
    assert generate_smart_title("1. Primo punto della lista con una frase molto lunga che supera i caratteri massimi consentiti") != "New Task"


def test_conversation_edit_and_truncate(tmp_path):
    db_path = tmp_path / "convs.db"
    store = ConversationStore(db_path)

    conv = store.create(title="Test Task")
    cid = conv["id"]

    # Turn 1
    m1 = store.add_message(cid, "user", "Prompt 1")
    m2 = store.add_message(cid, "assistant", "Response 1")

    # Turn 2
    m3 = store.add_message(cid, "user", "Prompt 2")
    m4 = store.add_message(cid, "assistant", "Response 2")

    messages = store.get_messages(cid)
    assert len(messages) == 4

    # Edit Turn 1 (Prompt 1) with truncate_after=True
    updated = store.edit_message(cid, m1["id"], "Prompt 1 Modified", truncate_after=True)
    assert updated is not None
    
    remaining = store.get_messages(cid)
    assert len(remaining) == 1
    assert remaining[0]["id"] == m1["id"]
    assert remaining[0]["content"] == "Prompt 1 Modified"


def test_conversation_delete_and_truncate(tmp_path):
    db_path = tmp_path / "convs.db"
    store = ConversationStore(db_path)

    conv = store.create(title="Test Task")
    cid = conv["id"]

    m1 = store.add_message(cid, "user", "Turn 1")
    m2 = store.add_message(cid, "assistant", "Answer 1")
    m3 = store.add_message(cid, "user", "Turn 2")
    m4 = store.add_message(cid, "assistant", "Answer 2")

    # Delete from m3 forward
    store.delete_message(cid, m3["id"], truncate_after=True)
    remaining = store.get_messages(cid)
    assert len(remaining) == 2
    assert [m["content"] for m in remaining] == ["Turn 1", "Answer 1"]


def test_conversation_archive_and_duplicate(tmp_path):
    db_path = tmp_path / "convs.db"
    store = ConversationStore(db_path)

    conv = store.create(title="Original Task")
    cid = conv["id"]
    store.add_message(cid, "user", "Hello")
    store.add_message(cid, "assistant", "Hi there")

    # 1. Archive
    store.archive(cid, archived=True)
    active_list = store.list(include_archived=False)
    assert not any(c["id"] == cid for c in active_list)

    archived_list = store.list(status="archived", include_archived=True)
    assert any(c["id"] == cid for c in archived_list)

    # 2. Unarchive
    store.archive(cid, archived=False)
    active_list_2 = store.list(include_archived=False)
    assert any(c["id"] == cid for c in active_list_2)

    # 3. Duplicate
    dup = store.duplicate(cid)
    assert dup is not None
    assert dup["id"] != cid
    assert dup["title"] == "Original Task (Copy)"
    assert len(dup["messages"]) == 2


def test_conversation_search_across_messages(tmp_path):
    db_path = tmp_path / "convs.db"
    store = ConversationStore(db_path)

    c1 = store.create(title="Acme Strategy")
    store.add_message(c1["id"], "user", "Tell me about quantum computing")
    store.add_message(c1["id"], "assistant", "Quantum computers use qubits")

    c2 = store.create(title="Finance Report")
    store.add_message(c2["id"], "user", "Analyze balance sheet")
    store.add_message(c2["id"], "assistant", "Revenue increased by 15 percent")

    # Search for "qubits" (inside assistant message of c1)
    results = store.list(search="qubits")
    assert len(results) == 1
    assert results[0]["id"] == c1["id"]

    # Search for "balance" (inside user message of c2)
    results2 = store.list(search="balance")
    assert len(results2) == 1
    assert results2[0]["id"] == c2["id"]
