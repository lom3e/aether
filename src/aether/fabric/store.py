"""
SQLite persistence for Aether Local Execution Fabric & Hardware Mesh (Layer 17).
Provides thread-safe WAL storage for mesh nodes, hardware specs, and workload assignments.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any, Generator
import uuid

from aether.fabric.models import (
    HardwareCapabilities,
    MeshNode,
    NodeRole,
    NodeStatus,
    WorkloadAssignment,
    WorkloadTier,
)

logger = logging.getLogger(__name__)


class FabricStore:
    """SQLite-backed storage for compute nodes and mesh assignments."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._conns_lock = threading.Lock()
        self._all_conns: set[sqlite3.Connection] = set()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=False,
                isolation_level=None,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA foreign_keys = ON;")
            with self._conns_lock:
                self._all_conns.add(conn)
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        conn = self._get_connection()
        conn.execute("BEGIN IMMEDIATE;")
        cursor = conn.cursor()
        try:
            yield cursor
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

    def _init_db(self) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS mesh_nodes (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    is_local INTEGER NOT NULL DEFAULT 1,
                    capabilities TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    ping_ms REAL NOT NULL DEFAULT 0.0,
                    active_workloads INTEGER NOT NULL DEFAULT 0,
                    last_heartbeat TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_mesh_ws_status ON mesh_nodes(workspace_id, status);"
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_mesh_ws_name ON mesh_nodes(workspace_id, name);"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS workload_assignments (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    workload_name TEXT NOT NULL,
                    workload_tier TEXT NOT NULL,
                    assigned_node_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    allocated_cores INTEGER NOT NULL DEFAULT 1,
                    allocated_vram_gb REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_workload_ws_time ON workload_assignments(workspace_id, created_at DESC);"
            )

    def save_node(self, node: MeshNode) -> MeshNode:
        """Inserts or updates a mesh node."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO mesh_nodes (
                    id, workspace_id, name, role, status, endpoint,
                    is_local, capabilities, tags, ping_ms, active_workloads,
                    last_heartbeat, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.id,
                    node.workspace_id,
                    node.name,
                    node.role.value if isinstance(node.role, NodeRole) else str(node.role),
                    node.status.value if isinstance(node.status, NodeStatus) else str(node.status),
                    node.endpoint,
                    1 if node.is_local else 0,
                    json.dumps(node.capabilities.to_dict()),
                    json.dumps(node.tags),
                    node.ping_ms,
                    node.active_workloads,
                    node.last_heartbeat,
                    node.created_at,
                ),
            )
        return node

    def get_node(self, workspace_id: str, node_id: str) -> MeshNode | None:
        """Retrieves a single node by ID and workspace."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM mesh_nodes WHERE workspace_id = ? AND id = ?",
            (workspace_id, node_id),
        ).fetchone()
        return self._row_to_node(row) if row else None

    def get_local_node(self, workspace_id: str) -> MeshNode | None:
        """Retrieves the local controller node for a workspace."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM mesh_nodes WHERE workspace_id = ? AND is_local = 1",
            (workspace_id,),
        ).fetchone()
        return self._row_to_node(row) if row else None

    def list_nodes(self, workspace_id: str) -> list[MeshNode]:
        """Lists all nodes in the mesh."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM mesh_nodes WHERE workspace_id = ? ORDER BY is_local DESC, name ASC",
            (workspace_id,),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def delete_node(self, workspace_id: str, node_id: str) -> bool:
        """Removes a remote node from the mesh (local node cannot be deleted)."""
        with self._transaction() as cursor:
            cursor.execute(
                "DELETE FROM mesh_nodes WHERE workspace_id = ? AND id = ? AND is_local = 0",
                (workspace_id, node_id),
            )
            return cursor.rowcount > 0

    def record_heartbeat(self, node_id: str, ping_ms: float = 0.0, status: NodeStatus | None = None) -> bool:
        """Records a heartbeat for a node, updating ping latency and timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        with self._transaction() as cursor:
            if status is not None:
                cursor.execute(
                    """
                    UPDATE mesh_nodes
                    SET last_heartbeat = ?, ping_ms = ?, status = ?
                    WHERE id = ?
                    """,
                    (now, ping_ms, status.value, node_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE mesh_nodes
                    SET last_heartbeat = ?, ping_ms = ?
                    WHERE id = ?
                    """,
                    (now, ping_ms, node_id),
                )
            return cursor.rowcount > 0

    def save_workload_assignment(self, assignment: WorkloadAssignment) -> WorkloadAssignment:
        """Saves a workload assignment and increments node active_workloads count."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO workload_assignments (
                    id, workspace_id, workload_name, workload_tier, assigned_node_id,
                    status, allocated_cores, allocated_vram_gb, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment.id,
                    assignment.workspace_id,
                    assignment.workload_name,
                    assignment.workload_tier.value if isinstance(assignment.workload_tier, WorkloadTier) else str(assignment.workload_tier),
                    assignment.assigned_node_id,
                    assignment.status,
                    assignment.allocated_cores,
                    assignment.allocated_vram_gb,
                    assignment.created_at,
                ),
            )
            # Increment active workloads on target node
            cursor.execute(
                "UPDATE mesh_nodes SET active_workloads = active_workloads + 1 WHERE id = ?",
                (assignment.assigned_node_id,),
            )
        return assignment

    def list_workload_assignments(self, workspace_id: str, limit: int = 50) -> list[WorkloadAssignment]:
        """Lists recent workload assignments."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM workload_assignments WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
            (workspace_id, max(1, limit)),
        ).fetchall()
        return [self._row_to_workload(r) for r in rows]

    def _row_to_node(self, row: sqlite3.Row) -> MeshNode:
        caps_dict = json.loads(row["capabilities"]) if row["capabilities"] else {}
        caps = HardwareCapabilities.from_dict(caps_dict)
        return MeshNode(
            id=row["id"],
            workspace_id=row["workspace_id"],
            name=row["name"],
            role=NodeRole.from_str(row["role"]),
            status=NodeStatus.from_str(row["status"]),
            endpoint=row["endpoint"],
            is_local=bool(row["is_local"]),
            capabilities=caps,
            tags=json.loads(row["tags"]) if row["tags"] else [],
            ping_ms=float(row["ping_ms"]),
            active_workloads=int(row["active_workloads"]),
            last_heartbeat=row["last_heartbeat"],
            created_at=row["created_at"],
        )

    def _row_to_workload(self, row: sqlite3.Row) -> WorkloadAssignment:
        return WorkloadAssignment(
            id=row["id"],
            workspace_id=row["workspace_id"],
            workload_name=row["workload_name"],
            workload_tier=WorkloadTier.from_str(row["workload_tier"]),
            assigned_node_id=row["assigned_node_id"],
            status=row["status"],
            allocated_cores=int(row["allocated_cores"]),
            allocated_vram_gb=float(row["allocated_vram_gb"]),
            created_at=row["created_at"],
        )

    def close(self) -> None:
        with self._conns_lock:
            for conn in list(self._all_conns):
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_conns.clear()
        if hasattr(self._local, "conn"):
            self._local.conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
