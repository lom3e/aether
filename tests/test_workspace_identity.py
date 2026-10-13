"""
Canonical workspace identity: freezing an id, alias mapping, and the row migration
(idempotent, backed up, journaled, conflict-safe, reversible). Temp workspaces/databases only.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from aether.memory.models import MemoryProvenance, WorkforceMemory
from aether.workspace.identity import ensure_identity, migrate_workspace_identity, rollback_identity_migration
from aether.workspace.workspace import Workspace


@pytest.fixture
def ws(tmp_path):
    w = Workspace.init(tmp_path / "ws", "Acme Corp")
    yield w
    w.close()


def make_legacy_db(ws: Workspace, key: str):
    db = ws.data_dir / "legacy_things.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE things (id INTEGER PRIMARY KEY, workspace_id TEXT NOT NULL, label TEXT);"
        "CREATE TABLE singleton (workspace_id TEXT PRIMARY KEY, value TEXT);"
    )
    conn.executemany("INSERT INTO things (workspace_id, label) VALUES (?, ?)",
                     [(key, "a"), (key, "b"), ("someone-else", "c"), (ws.id, "d")])
    conn.execute("INSERT INTO singleton VALUES (?, 'legacy')", (key,))
    conn.commit()
    conn.close()
    return db


def rows(db, table="things"):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(f"SELECT workspace_id, label FROM {table} ORDER BY id" if table == "things" else f"SELECT * FROM {table}").fetchall()
    finally:
        conn.close()


def test_new_workspaces_get_an_immutable_id_distinct_from_the_name(ws):
    assert ws.id.startswith("ws-") and ws.name == "Acme Corp"
    assert ws.canonical_id("Acme Corp") == ws.id and ws.canonical_id("") == ws.id and ws.canonical_id("default") == ws.id
    assert ws.canonical_id("ws-other") == "ws-other"  # another workspace's key is never rewritten


def test_ensure_identity_freezes_the_legacy_effective_id_without_changing_it(tmp_path):
    root = tmp_path / "old_ws"
    root.mkdir()
    (root / "aether.yaml").write_text(yaml.safe_dump({"version": "1.0", "workspace": {"name": "Legacy Name"}}), encoding="utf-8")
    w = Workspace(root)
    before = w.id
    assert ensure_identity(w) == before == "Legacy Name"
    frozen = yaml.safe_load((root / "aether.yaml").read_text())
    assert frozen["workspace"]["id"] == "Legacy Name"
    assert (root / "aether.yaml.pre_identity.bak").exists()
    # renaming the display name afterwards can no longer change the identity
    frozen["workspace"]["name"] = "Renamed"
    (root / "aether.yaml").write_text(yaml.safe_dump(frozen), encoding="utf-8")
    assert Workspace(root).id == "Legacy Name"
    assert ensure_identity(Workspace(root)) == "Legacy Name"  # idempotent


def test_dry_run_reports_and_changes_nothing(ws):
    db = make_legacy_db(ws, ws.name)
    rep = migrate_workspace_identity(ws, dry_run=True)
    assert rep.status == "dry_run" and rep.total_legacy_rows == 3
    assert [r[0] for r in rows(db)].count(ws.name) == 2
    assert not (ws.root / ".aether_migrations").exists()


def test_migration_moves_only_legacy_rows_backs_up_and_is_idempotent(ws):
    db = make_legacy_db(ws, ws.name)
    rep = migrate_workspace_identity(ws)
    assert rep.status == "completed" and rep.total_moved == 3 and rep.total_conflicts == 0
    assert rows(db) == [(ws.id, "a"), (ws.id, "b"), ("someone-else", "c"), (ws.id, "d")]
    assert rep.backups and all(Path(b).exists() for b in rep.backups)
    journal = json.loads((ws.root / ".aether_migrations/identity_v1/journal.json").read_text())
    assert journal["total_moved"] == rep.total_moved
    again = migrate_workspace_identity(ws)
    assert again.status == "noop" and again.total_moved == 0


def test_conflicting_rows_are_reported_never_overwritten(ws):
    db = ws.data_dir / "conf.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE singleton (workspace_id TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO singleton VALUES (?, 'legacy')", (ws.name,))
    conn.execute("INSERT INTO singleton VALUES (?, 'canonical')", (ws.id,))
    conn.commit(); conn.close()
    rep = migrate_workspace_identity(ws)
    assert rep.total_conflicts == 1 and rep.status == "completed_with_conflicts"
    conn = sqlite3.connect(db)
    assert dict(conn.execute("SELECT workspace_id, value FROM singleton").fetchall()) == {ws.name: "legacy", ws.id: "canonical"}
    conn.close()


def test_rollback_restores_the_exact_previous_state(ws):
    db = make_legacy_db(ws, ws.name)
    before = rows(db)
    migrate_workspace_identity(ws)
    assert rows(db) != before
    restored = rollback_identity_migration(ws)
    assert str(db) in restored and rows(db) == before
    assert json.loads((ws.root / ".aether_migrations/identity_v1/journal.json").read_text())["status"] == "rolled_back"


def test_real_memory_store_is_readable_under_the_canonical_id_after_migration(ws):
    mem = WorkforceMemory.create(workspace_id=ws.name, category="fact", summary="Rossi vuole PDF",
                                 content="Il cliente Rossi vuole il report in PDF.",
                                 provenance=MemoryProvenance(source_entity="user_instruction", verification_status="user_stated"))
    ws.memory.create_memory(mem)
    assert ws.memory.list_memories(ws.id) == []          # not visible under the canonical key yet
    migrate_workspace_identity(ws)
    listed = ws.memory.list_memories(ws.id)
    assert [m.summary for m in listed] == ["Rossi vuole PDF"]
    assert ws.memory.list_memories(ws.name) == []         # and no longer under the alias: one logical partition


def test_ambiguous_names_never_resolve(tmp_path):
    a = Workspace.init(tmp_path / "a", "Twin")
    b = Workspace.init(tmp_path / "b", "Twin")
    try:
        assert Workspace.resolve_unique("Twin") is None
        assert Workspace.resolve_unique(a.id) is a and Workspace.resolve_unique(b.id) is b
    finally:
        a.close(); b.close()
