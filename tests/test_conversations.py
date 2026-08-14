"""
Unit tests for ConversationStore and multiple persistent conversations.
"""
import pytest
from pathlib import Path
from aether.conversations.store import ConversationStore

@pytest.fixture
def store(tmp_path):
    db_file = tmp_path / "conversations.db"
    return ConversationStore(db_file)

def test_create_and_list_conversations(store):
    c1 = store.create(title="Task One", team_name="starter-workforce")
    c2 = store.create(title="Task Two", team_name="research-workforce")

    convs = store.list()
    assert len(convs) == 2
    ids = [c["id"] for c in convs]
    assert c1["id"] in ids
    assert c2["id"] in ids

def test_add_messages_and_get_conversation(store):
    c = store.create(title="Acme Analysis")
    conv_id = c["id"]

    m1 = store.add_message(conv_id, role="user", content="Chi è il CEO?")
    assert m1["role"] == "user"

    m2 = store.add_message(conv_id, role="assistant", content="Il CEO è Elena Rostagno.", agent_name="manager")
    assert m2["agent_name"] == "manager"

    fetched = store.get(conv_id)
    assert fetched is not None
    assert fetched["title"] == "Acme Analysis"
    assert len(fetched["messages"]) == 2
    assert fetched["messages"][0]["content"] == "Chi è il CEO?"
    assert fetched["messages"][1]["content"] == "Il CEO è Elena Rostagno."

def test_update_and_search_conversations(store):
    c = store.create(title="Draft Report")
    conv_id = c["id"]

    store.add_message(conv_id, role="user", content="Scrivi una bozza.")
    store.update(conv_id, title="Final Strategic Report", status="completed")

    fetched = store.get(conv_id)
    assert fetched["title"] == "Final Strategic Report"
    assert fetched["status"] == "completed"

    # Search
    search_res = store.list(search="Strategic")
    assert len(search_res) == 1
    assert search_res[0]["id"] == conv_id

def test_delete_conversation(store):
    c = store.create(title="To Delete")
    conv_id = c["id"]
    store.add_message(conv_id, role="user", content="Hello")

    assert store.get(conv_id) is not None
    deleted = store.delete(conv_id)
    assert deleted is True
    assert store.get(conv_id) is None
    assert len(store.get_messages(conv_id)) == 0

def test_sqlite_persistence_across_instances(tmp_path):
    db_file = tmp_path / "conversations.db"
    store1 = ConversationStore(db_file)
    c = store1.create(title="Persistent Task")
    store1.add_message(c["id"], role="user", content="Persistent prompt")

    # Re-instantiate
    store2 = ConversationStore(db_file)
    convs = store2.list()
    assert len(convs) == 1
    assert convs[0]["title"] == "Persistent Task"

    msgs = store2.get_messages(c["id"])
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Persistent prompt"
