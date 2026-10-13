"""
Canonical workspace identity.

The immutable ``workspace.id`` (``ws-…``) is the only key under which a workspace's data is stored. The display
name and the folder name are NOT identities: they may be renamed, collide between workspaces, and used to be
mixed with the id across stores (memory under the name, MCP under the id, authority checks comparing four
spellings). This module:

* freezes an identity into ``aether.yaml`` for workspaces that never had one (idempotent, with a backup), and
* migrates rows still keyed by a legacy alias (name / folder name) to the canonical id, per database, with a
  backup of every database it touches, a journal, a dry-run mode and a rollback.

Nothing here deletes data. Rows that cannot be moved (because the canonical row already exists) are reported,
never overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any

import yaml

logger = logging.getLogger(__name__)

MIGRATION_DIR = ".aether_migrations/identity_v1"
SKIP_DB_NAMES = {"secrets.vault"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TableReport:
    db: str
    table: str
    legacy_rows: int
    moved: int = 0
    conflicts: int = 0


@dataclass
class IdentityMigrationReport:
    workspace_id: str
    legacy_keys: list[str]
    dry_run: bool
    status: str = "noop"
    tables: list[TableReport] = field(default_factory=list)
    backups: list[str] = field(default_factory=list)
    backup_targets: dict[str, str] = field(default_factory=dict)
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None

    @property
    def total_legacy_rows(self) -> int:
        return sum(t.legacy_rows for t in self.tables)

    @property
    def total_moved(self) -> int:
        return sum(t.moved for t in self.tables)

    @property
    def total_conflicts(self) -> int:
        return sum(t.conflicts for t in self.tables)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id, "legacy_keys": self.legacy_keys, "dry_run": self.dry_run,
            "status": self.status, "started_at": self.started_at, "finished_at": self.finished_at,
            "backups": self.backups, "backup_targets": self.backup_targets,
            "tables": [t.__dict__ for t in self.tables],
            "total_legacy_rows": self.total_legacy_rows, "total_moved": self.total_moved,
            "total_conflicts": self.total_conflicts,
        }


def ensure_identity(ws: Any) -> str:
    """
    Writes an explicit, immutable ``workspace.id`` when the manifest has none. The id chosen is exactly what
    ``Workspace.id`` already resolved to (the name), so every existing key keeps working and a later rename of
    the display name can no longer change the identity. Idempotent; the manifest is backed up once.
    """
    cfg = dict(ws.config)
    section = dict(cfg.get("workspace") or {})
    if section.get("id"):
        return str(section["id"])
    if not ws.config_path.exists():
        return ws.id
    legacy_id = ws.id
    backup = ws.config_path.with_name(ws.config_path.name + ".pre_identity.bak")
    if not backup.exists():
        shutil.copy2(ws.config_path, backup)
    section["id"] = legacy_id
    cfg["workspace"] = section
    tmp = ws.config_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False)
    tmp.replace(ws.config_path)
    ws._config_cache = cfg
    logger.info("Froze workspace identity '%s' into %s", legacy_id, ws.config_path)
    return legacy_id


def _legacy_keys(ws: Any) -> list[str]:
    keys = []
    for k in (getattr(ws, "name", None), getattr(ws.root, "name", None)):
        if k and k != ws.id and k not in keys:
            keys.append(str(k))
    return keys


def _db_files(ws: Any) -> list[Path]:
    found: list[Path] = []
    for folder in (ws.data_dir, ws.legacy_aether_dir):
        if folder.is_dir():
            for p in sorted(folder.glob("*.db")):
                if p.name not in SKIP_DB_NAMES and p not in found:
                    found.append(p)
    return found


def _tables_with_workspace_id(conn: sqlite3.Connection) -> list[str]:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    out = []
    for t in tables:
        if t.endswith("_fts") or "_fts_" in t:
            continue
        try:
            cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{t}")')]
        except sqlite3.DatabaseError:
            continue
        if "workspace_id" in cols:
            out.append(t)
    return out


def migrate_workspace_identity(ws: Any, dry_run: bool = False) -> IdentityMigrationReport:
    """Moves rows keyed by a legacy alias to the canonical id. Safe to run repeatedly."""
    canonical = ws.id
    legacy = _legacy_keys(ws)
    report = IdentityMigrationReport(workspace_id=canonical, legacy_keys=legacy, dry_run=dry_run)
    if not legacy:
        report.status = "noop"
        report.finished_at = _now()
        return report

    mig_dir = ws.root / MIGRATION_DIR
    plan: list[tuple[Path, str, str, int]] = []
    for db in _db_files(ws):
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        except sqlite3.DatabaseError:
            continue
        try:
            for table in _tables_with_workspace_id(conn):
                for key in legacy:
                    n = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE workspace_id = ?', (key,)).fetchone()[0]
                    if n:
                        plan.append((db, table, key, n))
        except sqlite3.DatabaseError as exc:
            logger.warning("Identity scan skipped %s: %s", db, exc)
        finally:
            conn.close()

    for db, table, key, n in plan:
        report.tables.append(TableReport(db=db.name, table=table, legacy_rows=n))
    if not plan:
        report.status = "noop"
        report.finished_at = _now()
        return report
    if dry_run:
        report.status = "dry_run"
        report.finished_at = _now()
        return report

    mig_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backed_up: dict[Path, Path] = {}
    for db in sorted({p[0] for p in plan}):
        dest = mig_dir / f"{stamp}__{db.name}.bak"
        src = sqlite3.connect(str(db))
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)   # consistent copy even with WAL
        finally:
            dst.close()
            src.close()
        backed_up[db] = dest
        report.backups.append(str(dest))
        report.backup_targets[str(dest)] = str(db)
    (mig_dir / "journal.json").write_text(json.dumps({"status": "in_progress", **report.to_dict()}, indent=2), encoding="utf-8")

    for entry, (db, table, key, n) in zip(report.tables, plan):
        conn = sqlite3.connect(str(db), timeout=15)
        try:
            with conn:
                conn.execute(f'UPDATE OR IGNORE "{table}" SET workspace_id = ? WHERE workspace_id = ?', (canonical, key))
            left = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE workspace_id = ?', (key,)).fetchone()[0]
            entry.conflicts = left
            entry.moved = n - left
        finally:
            conn.close()

    report.status = "completed_with_conflicts" if report.total_conflicts else "completed"
    report.finished_at = _now()
    (mig_dir / "journal.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report


def rollback_identity_migration(ws: Any) -> list[str]:
    """Restores every database from the backups taken by the latest migration run."""
    mig_dir = ws.root / MIGRATION_DIR
    journal = mig_dir / "journal.json"
    if not journal.exists():
        raise FileNotFoundError("No identity migration journal found; nothing to roll back.")
    info = json.loads(journal.read_text(encoding="utf-8"))
    restored: list[str] = []
    for backup, target in (info.get("backup_targets") or {}).items():
        bpath, tpath = Path(backup), Path(target)
        if not bpath.exists():
            raise FileNotFoundError(f"Backup missing, rollback aborted: {bpath}")
        src = sqlite3.connect(str(bpath))
        dst = sqlite3.connect(str(tpath))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        restored.append(str(tpath))
    info["status"] = "rolled_back"
    info["rolled_back_at"] = _now()
    journal.write_text(json.dumps(info, indent=2), encoding="utf-8")
    return restored
