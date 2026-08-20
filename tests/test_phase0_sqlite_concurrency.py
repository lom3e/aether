"""
Tests for PRE-05: SQLite Concurrency Hardening (WAL Mode, Busy Timeout, Stress Testing).
"""
import concurrent.futures
import sqlite3
import pytest
from aether.conversations.store import ConversationStore
from aether.knowledge.store import KnowledgeStore
from aether.knowledge.chunk import KnowledgeChunk
from aether.core.sqlite import get_sqlite_connection


def test_sqlite_pragmas_configured_on_connection(tmp_path):
    """Connections created via get_sqlite_connection have WAL, busy_timeout, and foreign_keys set."""
    db_file = tmp_path / "pragmas_test.db"
    conn = get_sqlite_connection(db_file)

    # 1. Foreign keys
    fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert fk == 1

    # 2. Journal mode (WAL)
    jm = conn.execute("PRAGMA journal_mode;").fetchone()[0].lower()
    assert jm == "wal"

    # 3. Busy timeout
    bt = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    assert bt >= 5000

    conn.close()


def test_conversations_store_high_concurrency_stress(tmp_path):
    """Stress test: 20 concurrent worker threads executing concurrent writes, reads, and updates."""
    db_file = tmp_path / "concurrent_convs.db"
    store = ConversationStore(db_file)

    # Create initial conversations
    for i in range(5):
        store.create(title=f"Initial Conversation {i}", conv_id=f"conv_{i}")

    errors = []

    def worker_action(worker_id: int):
        try:
            worker_store = ConversationStore(db_file)
            for step in range(15):
                conv_id = f"conv_{step % 5}"
                # 1. Add user message
                msg_id = worker_store.add_message(
                    conv_id=conv_id,
                    role="user",
                    content=f"Message from worker {worker_id} step {step}",
                )
                # 2. Add activity log
                worker_store.add_activity(
                    conv_id=conv_id,
                    agent=f"Agent_{worker_id % 3}",
                    activity_type="tool_execution",
                    message=f"Running tool step {step}",
                )
                # 3. Update status & unread
                worker_store.update(conv_id, status="active", unread=True)
                # 4. Read conversation
                conv = worker_store.get(conv_id)
                assert conv is not None
                # 5. Add assistant response
                worker_store.add_message(
                    conv_id=conv_id,
                    role="assistant",
                    content=f"Response from assistant for worker {worker_id}",
                )
                # 6. Mark read
                worker_store.mark_read(conv_id)
        except Exception as exc:
            errors.append((worker_id, exc))

    # Run 20 threads simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(worker_action, w_id) for w_id in range(20)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"

    # Verify final integrity
    convs = store.list()
    assert len(convs) == 5
    for c in convs:
        full_conv = store.get(c["id"])
        assert len(full_conv["messages"]) > 0
        assert len(full_conv["activities"]) > 0


def test_knowledge_store_concurrent_writes_and_reads(tmp_path):
    """Knowledge store handles concurrent chunk additions and searches without locking errors."""
    db_file = tmp_path / "concurrent_knowledge.db"
    store = KnowledgeStore(str(db_file))

    errors = []

    def writer_worker(w_id: int):
        try:
            local_store = KnowledgeStore(str(db_file))
            for i in range(10):
                chunk = KnowledgeChunk(
                    content=f"Knowledge content from worker {w_id} entry {i}",
                    source=f"doc_{w_id}.txt",
                    chunk_index=i,
                )
                local_store.add(chunk)
                # Search immediately
                res = local_store.search(f"worker {w_id}")
                assert len(res) >= 1
        except Exception as exc:
            errors.append((w_id, exc))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(writer_worker, w_id) for w_id in range(10)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Knowledge store concurrency errors: {errors}"
    assert store.count() == 100
