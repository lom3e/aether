"""Tests for AgentIdentity and AgentStore."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from aether.agents.identity import AgentIdentity, AgentStore


def test_agent_identity_create():
    identity = AgentIdentity.create(name="bob", role="worker")
    assert identity.name == "bob"
    assert identity.role == "worker"
    assert identity.id.startswith("agent_bob_")
    assert len(identity.id) > 10
    assert identity.created_at > 0
    assert identity.last_active == identity.created_at


def test_agent_store_create_load():
    store = AgentStore(":memory:")

    identity = AgentIdentity.create(name="alice", role="coordinator")
    store.save(identity)

    loaded_by_name = store.load_by_name("alice")
    assert loaded_by_name is not None
    assert loaded_by_name.id == identity.id
    assert loaded_by_name.name == "alice"
    assert loaded_by_name.role == "coordinator"
    assert loaded_by_name.created_at == identity.created_at

    loaded_by_id = store.load(identity.id)
    assert loaded_by_id is not None
    assert loaded_by_id.name == "alice"


def test_agent_store_persistence():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # First instance creates and saves
        store1 = AgentStore(db_path)
        identity1 = AgentIdentity.create(name="eve", role="spy")
        store1.save(identity1)

        # Second instance loads
        store2 = AgentStore(db_path)
        loaded = store2.load_by_name("eve")

        assert loaded is not None
        assert loaded.id == identity1.id
        assert loaded.created_at == identity1.created_at

    finally:
        Path(db_path).unlink(missing_ok=True)


def test_agent_store_update_preserves_created_at():
    store = AgentStore(":memory:")

    # Create initial
    identity = AgentIdentity.create(name="charlie", role="dev")
    original_id = identity.id
    original_created = identity.created_at
    store.save(identity)

    time.sleep(0.01)

    # Create a new identity object with the same name, pretending it's a new run
    new_identity = AgentIdentity.create(name="charlie", role="lead dev")
    assert new_identity.created_at > original_created
    assert new_identity.id != original_id

    # Saving it should UPDATE the existing one based on the unique name
    # Wait, the save() method does ON CONFLICT(name) DO UPDATE SET role=excluded.role...
    # It will use the OLD id and OLD created_at in the DB, but update role and last_active.
    # Let's save the new identity object:
    store.save(new_identity)

    # Reload from store
    loaded = store.load_by_name("charlie")
    assert loaded is not None
    assert loaded.id == original_id  # Should preserve original ID
    assert loaded.created_at == original_created  # Should preserve original created_at
    assert loaded.role == "lead dev"  # Should update role
    assert loaded.last_active == new_identity.last_active  # Should update last_active


def test_agent_store_nonexistent():
    store = AgentStore(":memory:")
    assert store.load_by_name("nobody") is None
    assert store.load("fake_id") is None


def test_agent_store_list_multiple():
    store = AgentStore(":memory:")

    store.save(AgentIdentity.create("zack", "worker"))
    store.save(AgentIdentity.create("alice", "lead"))
    store.save(AgentIdentity.create("bob", "dev"))

    identities = store.list()
    assert len(identities) == 3
    # Should be ordered by name
    assert identities[0].name == "alice"
    assert identities[1].name == "bob"
    assert identities[2].name == "zack"
