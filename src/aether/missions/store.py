"""
MissionStore — SQLite-backed persistence for Missions, Milestones, and Graph Generation.
Provides complete CRUD lifecycle for missions and milestones, with foreign-key integrity
and read-only DAG graph synthesis.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any, Generator
import uuid

from aether.core.sqlite import get_sqlite_connection, sqlite_connection
from aether.missions.models import (
    Deliverable,
    ExecutionMilestone,
    ExecutionStatus,
    GraphEdge,
    GraphNode,
    Milestone,
    MilestoneExecutionStatus,
    MilestoneStatus,
    Mission,
    MissionExecution,
    MissionGraph,
    MissionStatus,
)


class MissionStore:
    """
    Manages persistent Missions, Milestones, Executions, Deliverables, and Execution Graph models.
    Operates on the shared conversations database in the workspace data directory.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._is_memory = self.db_path == ":memory:" or "mode=memory" in self.db_path
        if self.db_path == ":memory:":
            self.db_path = f"file:memdb_missions_{uuid.uuid4().hex}?mode=memory&cache=shared"
        # For in-memory databases, retain a keepalive connection so the shared memory database is preserved
        self._keepalive_conn: sqlite3.Connection | None = (
            get_sqlite_connection(self.db_path) if self._is_memory else None
        )
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        with sqlite_connection(self.db_path) as conn:
            yield conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            # 0. Conversations table (for activity FK lineage)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    team_name TEXT DEFAULT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_message TEXT DEFAULT '',
                    agents TEXT DEFAULT '[]'
                )
                """
            )

            # 1. Missions table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    title TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    team_name TEXT DEFAULT NULL,
                    conversation_id TEXT DEFAULT NULL,
                    project_id TEXT DEFAULT NULL,
                    active_execution_id TEXT DEFAULT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            # 2. Mission Milestones table (Durable Stage Templates)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mission_milestones (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    order_idx INTEGER NOT NULL DEFAULT 0,
                    dependencies TEXT DEFAULT '[]',
                    completed_at TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE
                )
                """
            )

            # 3. Mission Executions table (Authoritative Execution Identity & Runs)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mission_executions (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    run_number INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    current_milestone_id TEXT DEFAULT NULL,
                    team_name TEXT DEFAULT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT DEFAULT NULL,
                    interrupted_at TEXT DEFAULT NULL,
                    duration_seconds REAL DEFAULT 0.0,
                    error_message TEXT DEFAULT NULL,
                    error_details TEXT DEFAULT NULL,
                    lease_owner TEXT DEFAULT NULL,
                    lease_expires_at TEXT DEFAULT NULL,
                    heartbeat_at TEXT DEFAULT NULL,
                    recovery_state TEXT DEFAULT 'none',
                    pending_approval TEXT DEFAULT NULL,
                    approval_history TEXT DEFAULT '[]',
                    milestone_states TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE,
                    FOREIGN KEY(current_milestone_id) REFERENCES mission_milestones(id) ON DELETE SET NULL
                )
                """
            )

            # 4. Mission Execution Milestones table (Per-Run Milestone States)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mission_execution_milestones (
                    id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL,
                    milestone_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    started_at TEXT DEFAULT NULL,
                    completed_at TEXT DEFAULT NULL,
                    duration_seconds REAL DEFAULT 0.0,
                    error TEXT DEFAULT NULL,
                    output TEXT DEFAULT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(execution_id) REFERENCES mission_executions(id) ON DELETE CASCADE,
                    FOREIGN KEY(milestone_id) REFERENCES mission_milestones(id) ON DELETE CASCADE
                )
                """
            )

            # 5. Mission Deliverables table (Authoritative Relational Lineage)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mission_deliverables (
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    execution_id TEXT DEFAULT NULL,
                    milestone_id TEXT DEFAULT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'document',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    sha256 TEXT DEFAULT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE,
                    FOREIGN KEY(execution_id) REFERENCES mission_executions(id) ON DELETE SET NULL,
                    FOREIGN KEY(milestone_id) REFERENCES mission_milestones(id) ON DELETE SET NULL
                )
                """
            )

            # 6. Ensure conversation_activities table exists for activity logging
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_activities (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    activity_type TEXT NOT NULL,
                    message TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Performance Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_missions_updated ON missions(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_missions_conv ON missions(conversation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_missions_project ON missions(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_milestones_mission ON mission_milestones(mission_id, order_idx ASC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_exec_lookup ON mission_executions(mission_id, run_number DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_exec_status ON mission_executions(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_exec_lease ON mission_executions(status, lease_expires_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_milestones_lookup ON mission_execution_milestones(execution_id, milestone_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_deliv_lookup ON mission_deliverables(mission_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_deliv_exec ON mission_deliverables(execution_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_deliv_path ON mission_deliverables(mission_id, path)")

            # Safe migrations for existing tables
            try:
                conn.execute("ALTER TABLE missions ADD COLUMN active_execution_id TEXT DEFAULT NULL")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE conversations ADD COLUMN mission_id TEXT DEFAULT NULL")
            except Exception:
                pass

            # Safe backfill of legacy deliverables from missions.metadata["deliverables"]
            try:
                rows = conn.execute("SELECT id, metadata, created_at FROM missions").fetchall()
                for r in rows:
                    mid = r["id"]
                    m_meta_raw = r["metadata"]
                    m_meta = json.loads(m_meta_raw) if m_meta_raw else {}
                    legacy_delivs = m_meta.get("deliverables")
                    if isinstance(legacy_delivs, list):
                        for ld in legacy_delivs:
                            if isinstance(ld, dict) and ld.get("id"):
                                conn.execute(
                                    """
                                    INSERT OR IGNORE INTO mission_deliverables
                                    (id, mission_id, execution_id, milestone_id, name, path, type, size_bytes, sha256, status, metadata, created_at, updated_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        ld["id"],
                                        mid,
                                        ld.get("execution_id"),
                                        ld.get("milestone_id"),
                                        ld.get("name", "Deliverable"),
                                        ld.get("path", ""),
                                        ld.get("type", "document"),
                                        int(ld.get("size_bytes", 0)),
                                        ld.get("sha256"),
                                        ld.get("status", "draft"),
                                        json.dumps(ld.get("metadata") or {}),
                                        ld.get("created_at") or r["created_at"],
                                        ld.get("updated_at") or r["created_at"],
                                    ),
                                )
            except Exception:
                pass

    # ---------------------------------------------------------------------------
    # Mission CRUD Operations
    # ---------------------------------------------------------------------------

    def create_mission(
        self,
        title: str,
        objective: str,
        workspace_id: str = "default",
        team_name: str | None = None,
        conversation_id: str | None = None,
        project_id: str | None = None,
        status: MissionStatus | str = MissionStatus.DRAFT,
        metadata: dict[str, Any] | None = None,
        milestones: list[dict[str, Any]] | None = None,
        mission_id: str | None = None,
    ) -> Mission:
        """Create a new mission with optional initial milestones."""
        clean_title = str(title).strip()
        clean_objective = str(objective).strip()
        if not clean_title:
            raise ValueError("Mission title cannot be empty.")
        if not clean_objective:
            raise ValueError("Mission objective cannot be empty.")

        mid = mission_id or uuid.uuid4().hex
        status_val = status.value if isinstance(status, MissionStatus) else str(status)
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})
        conv_id = conversation_id or f"conv_{mid}"

        created_milestones: list[Milestone] = []

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO conversations (
                    id, title, team_name, status, created_at, updated_at
                ) VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (conv_id, f"Mission: {clean_title}", team_name or "Workforce", now, now),
            )
            conn.execute(
                """
                INSERT INTO missions (
                    id, workspace_id, title, objective, status,
                    team_name, conversation_id, project_id, metadata,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    workspace_id,
                    clean_title,
                    clean_objective,
                    status_val,
                    team_name,
                    conv_id,
                    project_id,
                    meta_json,
                    now,
                    now,
                ),
            )

            # Insert initial milestones if provided
            if milestones:
                for idx, m_data in enumerate(milestones):
                    m_id = m_data.get("id") or uuid.uuid4().hex
                    m_title = str(m_data.get("title", f"Milestone {idx + 1}")).strip()
                    m_desc = str(m_data.get("description", "")).strip()
                    m_status_raw = m_data.get("status", "pending")
                    m_order = int(m_data.get("order_idx", idx))
                    m_deps = json.dumps(m_data.get("dependencies") or [])
                    m_completed_at = m_data.get("completed_at")

                    conn.execute(
                        """
                        INSERT INTO mission_milestones (
                            id, mission_id, title, description, status,
                            order_idx, dependencies, completed_at, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            m_id,
                            mid,
                            m_title,
                            m_desc,
                            m_status_raw,
                            m_order,
                            m_deps,
                            m_completed_at,
                            now,
                            now,
                        ),
                    )
                    created_milestones.append(
                        Milestone(
                            id=m_id,
                            mission_id=mid,
                            title=m_title,
                            description=m_desc,
                            status=MilestoneStatus(m_status_raw) if m_status_raw in MilestoneStatus._value2member_map_ else MilestoneStatus.PENDING,
                            order_idx=m_order,
                            dependencies=m_data.get("dependencies") or [],
                            completed_at=m_completed_at,
                            created_at=now,
                            updated_at=now,
                        )
                    )

            # If conversation_id is linked, update conversations table if possible
            if conversation_id:
                try:
                    conn.execute(
                        "UPDATE conversations SET mission_id = ? WHERE id = ?",
                        (mid, conversation_id),
                    )
                except Exception:
                    pass

        return Mission(
            id=mid,
            workspace_id=workspace_id,
            title=clean_title,
            objective=clean_objective,
            status=MissionStatus(status_val) if status_val in MissionStatus._value2member_map_ else MissionStatus.DRAFT,
            team_name=team_name,
            conversation_id=conversation_id,
            project_id=project_id,
            milestones=created_milestones,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

    def get_mission(self, mission_id: str, include_milestones: bool = True) -> Mission | None:
        """Retrieve a mission by ID with its milestones and active execution overlay."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, workspace_id, title, objective, status,
                       team_name, conversation_id, project_id, active_execution_id, metadata,
                       created_at, updated_at
                FROM missions
                WHERE id = ?
                """,
                (mission_id,),
            ).fetchone()

            if not row:
                return None

            active_exec_id = row["active_execution_id"] if "active_execution_id" in row.keys() else None
            exec_milestone_map: dict[str, tuple[str, str | None]] = {}
            if active_exec_id:
                try:
                    em_rows = conn.execute(
                        "SELECT milestone_id, status, completed_at FROM mission_execution_milestones WHERE execution_id = ?",
                        (active_exec_id,),
                    ).fetchall()
                    for em in em_rows:
                        exec_milestone_map[em["milestone_id"]] = (em["status"], em["completed_at"])
                except Exception:
                    pass

            milestones: list[Milestone] = []
            if include_milestones:
                m_rows = conn.execute(
                    """
                    SELECT id, mission_id, title, description, status,
                           order_idx, dependencies, completed_at, created_at, updated_at
                    FROM mission_milestones
                    WHERE mission_id = ?
                    ORDER BY order_idx ASC, created_at ASC
                    """,
                    (mission_id,),
                ).fetchall()

                for mr in m_rows:
                    deps = []
                    try:
                        deps = json.loads(mr["dependencies"] or "[]")
                    except Exception:
                        pass
                    st_val = mr["status"]
                    comp_at = mr["completed_at"]
                    if mr["id"] in exec_milestone_map:
                        st_val, comp_at = exec_milestone_map[mr["id"]]

                    milestones.append(
                        Milestone(
                            id=mr["id"],
                            mission_id=mr["mission_id"],
                            title=mr["title"],
                            description=mr["description"] or "",
                            status=MilestoneStatus(st_val) if st_val in MilestoneStatus._value2member_map_ else MilestoneStatus.PENDING,
                            order_idx=mr["order_idx"],
                            dependencies=deps,
                            completed_at=comp_at,
                            created_at=mr["created_at"],
                            updated_at=mr["updated_at"],
                        )
                    )

        meta = {}
        try:
            meta = json.loads(row["metadata"] or "{}")
        except Exception:
            pass

        st_val = row["status"]
        active_exec = self.get_execution(active_exec_id) if active_exec_id else None

        return Mission(
            id=row["id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            objective=row["objective"],
            status=MissionStatus(st_val) if st_val in MissionStatus._value2member_map_ else MissionStatus.DRAFT,
            team_name=row["team_name"],
            conversation_id=row["conversation_id"],
            project_id=row["project_id"],
            active_execution_id=active_exec_id,
            active_execution=active_exec,
            milestones=milestones,
            metadata=meta,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_missions(
        self,
        workspace_id: str | None = None,
        status: str | None = None,
        project_id: str | None = None,
        conversation_id: str | None = None,
        limit: int = 100,
    ) -> list[Mission]:
        """List missions with optional filtering, ordered by updated_at DESC."""
        query = """
            SELECT id, workspace_id, title, objective, status,
                   team_name, conversation_id, project_id, active_execution_id, metadata,
                   created_at, updated_at
            FROM missions
            WHERE 1=1
        """
        params: list[Any] = []

        if workspace_id:
            query += " AND workspace_id = ?"
            params.append(workspace_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if conversation_id:
            query += " AND conversation_id = ?"
            params.append(conversation_id)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            if not rows:
                return []

            mission_ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in mission_ids)
            m_rows = conn.execute(
                f"""
                SELECT id, mission_id, title, description, status,
                       order_idx, dependencies, completed_at, created_at, updated_at
                FROM mission_milestones
                WHERE mission_id IN ({placeholders})
                ORDER BY order_idx ASC, created_at ASC
                """,
                mission_ids,
            ).fetchall()

            active_exec_ids = [r["active_execution_id"] for r in rows if "active_execution_id" in r.keys() and r["active_execution_id"]]
            exec_milestone_map: dict[str, dict[str, tuple[str, str | None]]] = {}
            if active_exec_ids:
                try:
                    pl = ",".join("?" for _ in active_exec_ids)
                    em_rows = conn.execute(
                        f"SELECT execution_id, milestone_id, status, completed_at FROM mission_execution_milestones WHERE execution_id IN ({pl})",
                        active_exec_ids,
                    ).fetchall()
                    for em in em_rows:
                        exec_milestone_map.setdefault(em["execution_id"], {})[em["milestone_id"]] = (em["status"], em["completed_at"])
                except Exception:
                    pass

        milestones_by_mission: dict[str, list[Milestone]] = {mid: [] for mid in mission_ids}
        for mr in m_rows:
            deps = []
            try:
                deps = json.loads(mr["dependencies"] or "[]")
            except Exception:
                pass
            st_val = mr["status"]
            milestones_by_mission[mr["mission_id"]].append(
                Milestone(
                    id=mr["id"],
                    mission_id=mr["mission_id"],
                    title=mr["title"],
                    description=mr["description"] or "",
                    status=MilestoneStatus(st_val) if st_val in MilestoneStatus._value2member_map_ else MilestoneStatus.PENDING,
                    order_idx=mr["order_idx"],
                    dependencies=deps,
                    completed_at=mr["completed_at"],
                    created_at=mr["created_at"],
                    updated_at=mr["updated_at"],
                )
            )

        results: list[Mission] = []
        for r in rows:
            meta = {}
            try:
                meta = json.loads(r["metadata"] or "{}")
            except Exception:
                pass
            st_val = r["status"]
            active_eid = r["active_execution_id"] if "active_execution_id" in r.keys() else None
            m_milestones = milestones_by_mission.get(r["id"], [])

            if active_eid and active_eid in exec_milestone_map:
                e_map = exec_milestone_map[active_eid]
                updated_ms = []
                for m in m_milestones:
                    if m.id in e_map:
                        st, cat = e_map[m.id]
                        updated_ms.append(
                            Milestone(
                                id=m.id,
                                mission_id=m.mission_id,
                                title=m.title,
                                description=m.description,
                                status=MilestoneStatus(st) if st in MilestoneStatus._value2member_map_ else MilestoneStatus.PENDING,
                                order_idx=m.order_idx,
                                dependencies=m.dependencies,
                                completed_at=cat,
                                created_at=m.created_at,
                                updated_at=m.updated_at,
                            )
                        )
                    else:
                        updated_ms.append(m)
                m_milestones = updated_ms

            results.append(
                Mission(
                    id=r["id"],
                    workspace_id=r["workspace_id"],
                    title=r["title"],
                    objective=r["objective"],
                    status=MissionStatus(st_val) if st_val in MissionStatus._value2member_map_ else MissionStatus.DRAFT,
                    team_name=r["team_name"],
                    conversation_id=r["conversation_id"],
                    project_id=r["project_id"],
                    active_execution_id=active_eid,
                    milestones=m_milestones,
                    metadata=meta,
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
            )

        return results

    def update_mission(
        self,
        mission_id: str,
        title: str | None = None,
        objective: str | None = None,
        status: MissionStatus | str | None = None,
        team_name: str | None = None,
        conversation_id: str | None = None,
        project_id: str | None = None,
        active_execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Mission | None:
        """Update an existing mission's metadata, status, or active execution pointer."""
        updates: list[str] = []
        params: list[Any] = []

        if title is not None:
            clean_title = str(title).strip()
            if not clean_title:
                raise ValueError("Mission title cannot be empty.")
            updates.append("title = ?")
            params.append(clean_title)

        if objective is not None:
            clean_obj = str(objective).strip()
            if not clean_obj:
                raise ValueError("Mission objective cannot be empty.")
            updates.append("objective = ?")
            params.append(clean_obj)

        if status is not None:
            status_val = status.value if isinstance(status, MissionStatus) else str(status)
            updates.append("status = ?")
            params.append(status_val)

        if team_name is not None:
            updates.append("team_name = ?")
            params.append(team_name or None)

        if conversation_id is not None:
            updates.append("conversation_id = ?")
            params.append(conversation_id or None)

        if project_id is not None:
            updates.append("project_id = ?")
            params.append(project_id or None)

        if active_execution_id is not None:
            updates.append("active_execution_id = ?")
            params.append(active_execution_id or None)

        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if not updates:
            return self.get_mission(mission_id)

        now = datetime.now(timezone.utc).isoformat()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(mission_id)

        with self._get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE missions SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            if cursor.rowcount == 0:
                return None

            if conversation_id:
                try:
                    conn.execute(
                        "UPDATE conversations SET mission_id = ? WHERE id = ?",
                        (mission_id, conversation_id),
                    )
                except Exception:
                    pass

        return self.get_mission(mission_id)

    def delete_mission(self, mission_id: str) -> bool:
        """Delete a mission and its associated milestones."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM mission_milestones WHERE mission_id = ?", (mission_id,))
            cursor = conn.execute("DELETE FROM missions WHERE id = ?", (mission_id,))
            try:
                conn.execute("UPDATE conversations SET mission_id = NULL WHERE mission_id = ?", (mission_id,))
            except Exception:
                pass
            return cursor.rowcount > 0

    # ---------------------------------------------------------------------------
    # Milestone CRUD Operations
    # ---------------------------------------------------------------------------

    def create_milestone(
        self,
        mission_id: str,
        title: str,
        description: str = "",
        status: MilestoneStatus | str = MilestoneStatus.PENDING,
        order_idx: int | None = None,
        dependencies: list[str] | None = None,
        milestone_id: str | None = None,
    ) -> Milestone:
        """Add a new milestone to an existing mission."""
        clean_title = str(title).strip()
        if not clean_title:
            raise ValueError("Milestone title cannot be empty.")

        # Verify mission existence
        mission = self.get_mission(mission_id, include_milestones=False)
        if not mission:
            raise ValueError(f"Mission with id '{mission_id}' does not exist.")

        mid = milestone_id or uuid.uuid4().hex
        status_val = status.value if isinstance(status, MilestoneStatus) else str(status)
        now = datetime.now(timezone.utc).isoformat()
        deps_json = json.dumps(dependencies or [])

        with self._get_connection() as conn:
            if order_idx is None:
                max_order = conn.execute(
                    "SELECT COALESCE(MAX(order_idx), -1) FROM mission_milestones WHERE mission_id = ?",
                    (mission_id,),
                ).fetchone()[0]
                computed_order = max_order + 1
            else:
                computed_order = int(order_idx)

            conn.execute(
                """
                INSERT INTO mission_milestones (
                    id, mission_id, title, description, status,
                    order_idx, dependencies, completed_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    mission_id,
                    clean_title,
                    description.strip(),
                    status_val,
                    computed_order,
                    deps_json,
                    now if status_val == MilestoneStatus.COMPLETED.value else None,
                    now,
                    now,
                ),
            )

            conn.execute("UPDATE missions SET updated_at = ? WHERE id = ?", (now, mission_id))

        return Milestone(
            id=mid,
            mission_id=mission_id,
            title=clean_title,
            description=description.strip(),
            status=MilestoneStatus(status_val) if status_val in MilestoneStatus._value2member_map_ else MilestoneStatus.PENDING,
            order_idx=computed_order,
            dependencies=dependencies or [],
            completed_at=now if status_val == MilestoneStatus.COMPLETED.value else None,
            created_at=now,
            updated_at=now,
        )

    def get_milestone(self, milestone_id: str) -> Milestone | None:
        """Retrieve a milestone by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, mission_id, title, description, status,
                       order_idx, dependencies, completed_at, created_at, updated_at
                FROM mission_milestones
                WHERE id = ?
                """,
                (milestone_id,),
            ).fetchone()

            if not row:
                return None

            deps = []
            try:
                deps = json.loads(row["dependencies"] or "[]")
            except Exception:
                pass

            st_val = row["status"]
            return Milestone(
                id=row["id"],
                mission_id=row["mission_id"],
                title=row["title"],
                description=row["description"] or "",
                status=MilestoneStatus(st_val) if st_val in MilestoneStatus._value2member_map_ else MilestoneStatus.PENDING,
                order_idx=row["order_idx"],
                dependencies=deps,
                completed_at=row["completed_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_milestones(self, mission_id: str) -> list[Milestone]:
        """List all milestones for a mission ordered by index."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, mission_id, title, description, status,
                       order_idx, dependencies, completed_at, created_at, updated_at
                FROM mission_milestones
                WHERE mission_id = ?
                ORDER BY order_idx ASC, created_at ASC
                """,
                (mission_id,),
            ).fetchall()

        milestones: list[Milestone] = []
        for r in rows:
            deps = []
            try:
                deps = json.loads(r["dependencies"] or "[]")
            except Exception:
                pass
            st_val = r["status"]
            milestones.append(
                Milestone(
                    id=r["id"],
                    mission_id=r["mission_id"],
                    title=r["title"],
                    description=r["description"] or "",
                    status=MilestoneStatus(st_val) if st_val in MilestoneStatus._value2member_map_ else MilestoneStatus.PENDING,
                    order_idx=r["order_idx"],
                    dependencies=deps,
                    completed_at=r["completed_at"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
            )
        return milestones

    def update_milestone(
        self,
        milestone_id: str,
        title: str | None = None,
        description: str | None = None,
        status: MilestoneStatus | str | None = None,
        order_idx: int | None = None,
        dependencies: list[str] | None = None,
    ) -> Milestone | None:
        """Update milestone details, order, or status."""
        current = self.get_milestone(milestone_id)
        if not current:
            return None

        updates: list[str] = []
        params: list[Any] = []

        if title is not None:
            clean_title = str(title).strip()
            if not clean_title:
                raise ValueError("Milestone title cannot be empty.")
            updates.append("title = ?")
            params.append(clean_title)

        if description is not None:
            updates.append("description = ?")
            params.append(str(description).strip())

        now = datetime.now(timezone.utc).isoformat()
        if status is not None:
            status_val = status.value if isinstance(status, MilestoneStatus) else str(status)
            updates.append("status = ?")
            params.append(status_val)

            if status_val == MilestoneStatus.COMPLETED.value:
                updates.append("completed_at = ?")
                params.append(now)
            elif current.status == MilestoneStatus.COMPLETED:
                updates.append("completed_at = NULL")

        if order_idx is not None:
            updates.append("order_idx = ?")
            params.append(int(order_idx))

        if dependencies is not None:
            updates.append("dependencies = ?")
            params.append(json.dumps(dependencies))

        if not updates:
            return current

        updates.append("updated_at = ?")
        params.append(now)
        params.append(milestone_id)

        with self._get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE mission_milestones SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            if cursor.rowcount == 0:
                return None

            conn.execute(
                "UPDATE missions SET updated_at = ? WHERE id = ?",
                (now, current.mission_id),
            )

        return self.get_milestone(milestone_id)

    def delete_milestone(self, milestone_id: str) -> bool:
        """Delete a milestone and update mission updated_at."""
        milestone = self.get_milestone(milestone_id)
        if not milestone:
            return False

        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM mission_milestones WHERE id = ?", (milestone_id,))
            if cursor.rowcount > 0:
                conn.execute(
                    "UPDATE missions SET updated_at = ? WHERE id = ?",
                    (now, milestone.mission_id),
                )
                return True
        return False

    # ---------------------------------------------------------------------------
    # Read-Only Execution Graph Generation
    # ---------------------------------------------------------------------------

    def get_mission_graph(self, mission_id: str) -> MissionGraph | None:
        """
        Synthesizes a read-only DAG graph representing the mission, its milestones,
        and linked conversation activities / executions.
        """
        mission = self.get_mission(mission_id, include_milestones=True)
        if not mission:
            return None

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # 1. Root Mission Node
        root_node_id = f"mission_{mission.id}"
        nodes.append(
            GraphNode(
                id=root_node_id,
                type="mission",
                label=mission.title,
                status=mission.status.value if isinstance(mission.status, MissionStatus) else str(mission.status),
                metadata={
                    "objective": mission.objective,
                    "team_name": mission.team_name,
                    "created_at": mission.created_at,
                    "updated_at": mission.updated_at,
                },
            )
        )

        # 2. Milestone Nodes & Structural Edges
        for idx, m in enumerate(mission.milestones):
            m_node_id = f"milestone_{m.id}"
            m_status_val = m.status.value if isinstance(m.status, MilestoneStatus) else str(m.status)
            m_node = GraphNode(
                id=m_node_id,
                type="milestone",
                label=m.title,
                status=m_status_val,
                metadata={
                    "description": m.description,
                    "order_idx": m.order_idx,
                    "dependencies": m.dependencies,
                    "completed_at": m.completed_at,
                },
            )
            nodes.append(m_node)

            # Containment edge from Root Mission to Milestone
            edges.append(
                GraphEdge(
                    id=f"edge_contain_{mission.id}_{m.id}",
                    source=root_node_id,
                    target=m_node_id,
                    type="contains",
                    label="contains",
                )
            )

            # Dependencies / Sequential Edges
            if m.dependencies:
                for dep_id in m.dependencies:
                    edges.append(
                        GraphEdge(
                            id=f"edge_dep_{dep_id}_{m.id}",
                            source=f"milestone_{dep_id}",
                            target=m_node_id,
                            type="depends_on",
                            label="depends_on",
                        )
                    )
            elif idx > 0:
                prev_m = mission.milestones[idx - 1]
                edges.append(
                    GraphEdge(
                        id=f"edge_seq_{prev_m.id}_{m.id}",
                        source=f"milestone_{prev_m.id}",
                        target=m_node_id,
                        type="depends_on",
                        label="next",
                    )
                )

        # 3. If conversation_id is linked, fetch recent execution activities and map them
        if mission.conversation_id:
            try:
                with self._get_connection() as conn:
                    act_rows = conn.execute(
                        """
                        SELECT id, conversation_id, agent, activity_type, message, metadata, created_at
                        FROM conversation_activities
                        WHERE conversation_id = ?
                        ORDER BY created_at ASC
                        LIMIT 30
                        """,
                        (mission.conversation_id,),
                    ).fetchall()

                # Attach activities to the current running milestone or root
                active_target = None
                for m in mission.milestones:
                    if m.status in (MilestoneStatus.RUNNING, MilestoneStatus.PENDING):
                        active_target = f"milestone_{m.id}"
                        break
                if not active_target and mission.milestones:
                    active_target = f"milestone_{mission.milestones[-1].id}"
                if not active_target:
                    active_target = root_node_id

                for act in act_rows:
                    act_id = act["id"]
                    agent_name = act["agent"]
                    act_type = act["activity_type"]
                    msg = act["message"] or act_type
                    label = f"{agent_name}: {msg[:30]}..." if len(msg) > 30 else f"{agent_name}: {msg}"

                    act_node_id = f"activity_{act_id}"
                    nodes.append(
                        GraphNode(
                            id=act_node_id,
                            type="task" if "task" in act_type else "agent",
                            label=label,
                            status="completed" if "completed" in act_type else ("running" if "started" in act_type else "info"),
                            metadata={
                                "agent": agent_name,
                                "activity_type": act_type,
                                "created_at": act["created_at"],
                            },
                        )
                    )
                    edges.append(
                        GraphEdge(
                            id=f"edge_act_{act_id}",
                            source=active_target,
                            target=act_node_id,
                            type="delegated_to",
                            label=act_type,
                        )
                    )
            except Exception:
                pass

        # 4. Deliverable Nodes & Production Edges
        deliverables = self.list_deliverables(mission.id)
        for d in deliverables:
            d_node_id = f"deliverable_{d.id}"
            nodes.append(
                GraphNode(
                    id=d_node_id,
                    type="deliverable",
                    label=d.name,
                    status=d.status,
                    metadata=d.to_dict(),
                )
            )
            edges.append(
                GraphEdge(
                    id=f"edge_del_{d.id}",
                    source=root_node_id,
                    target=d_node_id,
                    type="produced",
                    label="produced",
                )
            )

        return MissionGraph(mission_id=mission.id, nodes=nodes, edges=edges)

    # ---------------------------------------------------------------------------
    # Deliverables Management & Lineage
    # ---------------------------------------------------------------------------

    def list_deliverables(self, mission_id: str, execution_id: str | None = None) -> list[Deliverable]:
        """
        Retrieves all real deliverables registered or produced for this mission,
        optionally filtered by execution_id.
        """
        with self._get_connection() as conn:
            query = """
                SELECT id, mission_id, execution_id, milestone_id, name, path,
                       type, size_bytes, sha256, status, metadata, created_at, updated_at
                FROM mission_deliverables
                WHERE mission_id = ?
            """
            params: list[Any] = [mission_id]
            if execution_id and isinstance(execution_id, str):
                query += " AND execution_id = ?"
                params.append(execution_id)
            query += " ORDER BY created_at ASC"

            rows = conn.execute(query, params).fetchall()
            if rows:
                deliverables: list[Deliverable] = []
                for r in rows:
                    meta = {}
                    if r["metadata"]:
                        try:
                            meta = json.loads(r["metadata"])
                        except Exception:
                            pass
                    sb = int(r["size_bytes"] or 0)
                    p_str = r["path"]
                    if sb <= 0 and p_str and not self._is_memory:
                        try:
                            fp = Path(p_str)
                            ws_root = Path(self.db_path).parent.parent
                            for candidate in [ws_root / "files" / fp, ws_root / fp, fp]:
                                if candidate.exists() and candidate.is_file():
                                    sb = candidate.stat().st_size
                                    break
                        except Exception:
                            pass

                    deliverables.append(
                        Deliverable(
                            id=r["id"],
                            mission_id=r["mission_id"],
                            execution_id=r["execution_id"],
                            milestone_id=r["milestone_id"],
                            name=r["name"],
                            path=r["path"],
                            type=r["type"],
                            size_bytes=sb,
                            sha256=r["sha256"],
                            status=r["status"],
                            metadata=meta,
                            created_at=r["created_at"],
                            updated_at=r["updated_at"],
                        )
                    )
                return deliverables

        return self._list_deliverables_legacy(mission_id)

    def _list_deliverables_legacy(self, mission_id: str) -> list[Deliverable]:
        """Fallback for un-migrated missions or dynamic activity inspection."""
        mission = self.get_mission(mission_id, include_milestones=False)
        if not mission:
            return []

        deliverables: list[Deliverable] = []
        seen_paths: set[str] = set()

        raw_delivs = mission.metadata.get("deliverables") if isinstance(mission.metadata, dict) else None
        if isinstance(raw_delivs, list):
            for item in raw_delivs:
                if isinstance(item, dict):
                    d = Deliverable.from_dict({**item, "mission_id": mission_id})
                    if d.size_bytes <= 0 and d.path and not self._is_memory:
                        try:
                            fp = Path(d.path)
                            ws_root = Path(self.db_path).parent.parent
                            for candidate in [ws_root / "files" / fp, ws_root / fp, fp]:
                                if candidate.exists() and candidate.is_file():
                                    d.size_bytes = candidate.stat().st_size
                                    break
                        except Exception:
                            pass
                    deliverables.append(d)
                    if d.path:
                        seen_paths.add(d.path)

        if mission.conversation_id:
            try:
                with self._get_connection() as conn:
                    rows = conn.execute(
                        """
                        SELECT id, metadata, created_at
                        FROM conversation_activities
                        WHERE conversation_id = ? AND (activity_type LIKE '%file%' OR metadata LIKE '%"path"%')
                        ORDER BY created_at ASC
                        """,
                        (mission.conversation_id,),
                    ).fetchall()

                for row in rows:
                    meta_raw = row["metadata"]
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) and meta_raw else {}
                    file_path = meta.get("path") or (meta.get("arguments") or {}).get("path")
                    if file_path and file_path not in seen_paths:
                        seen_paths.add(file_path)
                        filename = Path(file_path).name
                        ext = Path(file_path).suffix.lower()
                        ftype = "document" if ext in (".md", ".txt", ".pdf", ".docx") else ("data" if ext in (".json", ".csv", ".tsv", ".yaml", ".yml", ".parquet") else ("code" if ext in (".py", ".ts", ".tsx", ".js", ".sh", ".rs", ".go") else "archive"))
                        size_bytes = int(meta.get("size_bytes", 0))
                        if size_bytes <= 0 and file_path and not self._is_memory:
                            try:
                                fp = Path(file_path)
                                ws_root = Path(self.db_path).parent.parent
                                for candidate in [ws_root / "files" / fp, ws_root / fp, fp]:
                                    if candidate.exists() and candidate.is_file():
                                        size_bytes = candidate.stat().st_size
                                        break
                            except Exception:
                                pass
                        deliverables.append(
                            Deliverable(
                                id=f"del_{row['id']}",
                                mission_id=mission_id,
                                name=filename,
                                path=file_path,
                                type=ftype,
                                size_bytes=size_bytes,
                                status="verified" if "verified" in meta.get("action", "") else "draft",
                                metadata=meta,
                                created_at=row["created_at"],
                            )
                        )
            except Exception:
                pass

        return deliverables

    def add_deliverable(self, mission_id: str, deliverable: Deliverable) -> bool:
        """
        Registers or updates a deliverable in the mission_deliverables table
        and syncs legacy metadata for backward compatibility.
        """
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(deliverable.metadata or {})

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO mission_deliverables (
                    id, mission_id, execution_id, milestone_id, name, path,
                    type, size_bytes, sha256, status, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    execution_id = COALESCE(excluded.execution_id, mission_deliverables.execution_id),
                    milestone_id = COALESCE(excluded.milestone_id, mission_deliverables.milestone_id),
                    name = excluded.name,
                    path = excluded.path,
                    type = excluded.type,
                    size_bytes = excluded.size_bytes,
                    sha256 = COALESCE(excluded.sha256, mission_deliverables.sha256),
                    status = excluded.status,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (
                    deliverable.id,
                    mission_id,
                    deliverable.execution_id,
                    deliverable.milestone_id,
                    deliverable.name,
                    deliverable.path,
                    deliverable.type,
                    deliverable.size_bytes,
                    deliverable.sha256,
                    deliverable.status,
                    meta_json,
                    deliverable.created_at or now,
                    deliverable.updated_at or now,
                ),
            )

        # Sync to mission.metadata["deliverables"] for backward compatibility
        try:
            mission = self.get_mission(mission_id, include_milestones=False)
            if mission:
                meta = dict(mission.metadata) if isinstance(mission.metadata, dict) else {}
                delivs = list(meta.get("deliverables", []))
                delivs = [d for d in delivs if d.get("id") != deliverable.id]
                delivs.append(deliverable.to_dict())
                meta["deliverables"] = delivs
                with self._get_connection() as conn:
                    conn.execute(
                        "UPDATE missions SET metadata = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(meta), now, mission_id),
                    )
        except Exception:
            pass

        return True

    def get_deliverable(self, deliverable_id: str) -> Deliverable | None:
        """Fetch a single deliverable by ID."""
        with self._get_connection() as conn:
            r = conn.execute(
                """
                SELECT id, mission_id, execution_id, milestone_id, name, path,
                       type, size_bytes, sha256, status, metadata, created_at, updated_at
                FROM mission_deliverables
                WHERE id = ?
                """,
                (deliverable_id,),
            ).fetchone()
            if not r:
                return None
            meta = {}
            if r["metadata"]:
                try:
                    meta = json.loads(r["metadata"])
                except Exception:
                    pass
            return Deliverable(
                id=r["id"],
                mission_id=r["mission_id"],
                execution_id=r["execution_id"],
                milestone_id=r["milestone_id"],
                name=r["name"],
                path=r["path"],
                type=r["type"],
                size_bytes=int(r["size_bytes"] or 0),
                sha256=r["sha256"],
                status=r["status"],
                metadata=meta,
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )

    # ---------------------------------------------------------------------------
    # Execution Lifecycle & Lease Management
    # ---------------------------------------------------------------------------

    def create_execution(
        self,
        mission_id: str,
        team_name: str | None = None,
        run_number: int | None = None,
        status: ExecutionStatus = ExecutionStatus.PENDING,
        metadata: dict[str, Any] | None = None,
    ) -> MissionExecution:
        """
        Creates a new MissionExecution record and initializes its execution-scoped milestone states
        from the durable mission_milestones template.
        """
        now = datetime.now(timezone.utc).isoformat()
        status_val = status.value if isinstance(status, ExecutionStatus) else str(status)
        with self._get_connection() as conn:
            if run_number is None:
                row = conn.execute(
                    "SELECT COALESCE(MAX(run_number), 0) + 1 FROM mission_executions WHERE mission_id = ?",
                    (mission_id,),
                ).fetchone()
                run_num = row[0] if row else 1
            else:
                run_num = run_number

            exec_id = f"exec_{uuid.uuid4().hex[:12]}"
            meta_json = json.dumps(metadata or {})

            conn.execute(
                """
                INSERT INTO mission_executions (
                    id, mission_id, run_number, status, current_milestone_id,
                    team_name, started_at, duration_seconds, recovery_state,
                    pending_approval, approval_history, milestone_states, metadata,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exec_id,
                    mission_id,
                    run_num,
                    status_val,
                    None,
                    team_name,
                    now,
                    0.0,
                    "none",
                    None,
                    "[]",
                    "[]",
                    meta_json,
                    now,
                    now,
                ),
            )

            # Copy template milestones into execution-scoped milestone states
            tmpl_rows = conn.execute(
                """
                SELECT id, order_idx FROM mission_milestones
                WHERE mission_id = ?
                ORDER BY order_idx ASC, created_at ASC
                """,
                (mission_id,),
            ).fetchall()

            for mr in tmpl_rows:
                em_id = f"em_{exec_id}_{mr['id']}"
                conn.execute(
                    """
                    INSERT INTO mission_execution_milestones (
                        id, execution_id, milestone_id, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (em_id, exec_id, mr["id"], MilestoneExecutionStatus.PENDING.value, now, now),
                )

            # Update parent mission active_execution_id
            conn.execute(
                "UPDATE missions SET active_execution_id = ?, updated_at = ? WHERE id = ?",
                (exec_id, now, mission_id),
            )

        return MissionExecution(
            id=exec_id,
            mission_id=mission_id,
            run_number=run_num,
            status=ExecutionStatus.PENDING,
            current_milestone_id=None,
            team_name=team_name,
            started_at=now,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

    def get_execution(self, execution_id: str) -> MissionExecution | None:
        """Retrieve a specific execution run by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, mission_id, run_number, status, current_milestone_id,
                       team_name, started_at, completed_at, interrupted_at,
                       duration_seconds, error_message, error_details,
                       lease_owner, lease_expires_at, heartbeat_at, recovery_state,
                       pending_approval, approval_history, milestone_states, metadata,
                       created_at, updated_at
                FROM mission_executions
                WHERE id = ?
                """,
                (execution_id,),
            ).fetchone()

            if not row:
                return None

            return self._row_to_execution(row)

    def _row_to_execution(self, row: sqlite3.Row) -> MissionExecution:
        st_val = row["status"]
        status = ExecutionStatus(st_val) if st_val in ExecutionStatus._value2member_map_ else ExecutionStatus.PENDING

        pending_appr = None
        if row["pending_approval"]:
            try:
                pending_appr = json.loads(row["pending_approval"])
            except Exception:
                pass

        appr_hist = []
        if row["approval_history"]:
            try:
                appr_hist = json.loads(row["approval_history"])
            except Exception:
                pass

        ms_states = []
        if row["milestone_states"]:
            try:
                ms_states = json.loads(row["milestone_states"])
            except Exception:
                pass

        meta = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except Exception:
                pass

        return MissionExecution(
            id=row["id"],
            mission_id=row["mission_id"],
            run_number=row["run_number"],
            status=status,
            current_milestone_id=row["current_milestone_id"],
            team_name=row["team_name"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            interrupted_at=row["interrupted_at"],
            duration_seconds=float(row["duration_seconds"] or 0.0),
            error_message=row["error_message"],
            error_details=row["error_details"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            heartbeat_at=row["heartbeat_at"],
            recovery_state=row["recovery_state"] or "none",
            pending_approval=pending_appr,
            approval_history=appr_hist,
            milestone_states=ms_states,
            metadata=meta,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_active_execution(self, mission_id: str) -> MissionExecution | None:
        """Retrieves the active or most recent execution for a mission."""
        with self._get_connection() as conn:
            m_row = conn.execute(
                "SELECT active_execution_id FROM missions WHERE id = ?",
                (mission_id,),
            ).fetchone()
            if m_row and m_row["active_execution_id"]:
                return self.get_execution(m_row["active_execution_id"])

            row = conn.execute(
                """
                SELECT id, mission_id, run_number, status, current_milestone_id,
                       team_name, started_at, completed_at, interrupted_at,
                       duration_seconds, error_message, error_details,
                       lease_owner, lease_expires_at, heartbeat_at, recovery_state,
                       pending_approval, approval_history, milestone_states, metadata,
                       created_at, updated_at
                FROM mission_executions
                WHERE mission_id = ?
                ORDER BY run_number DESC LIMIT 1
                """,
                (mission_id,),
            ).fetchone()
            if row:
                return self._row_to_execution(row)
            return None

    def list_executions(self, mission_id: str) -> list[MissionExecution]:
        """List all execution runs for a mission, ordered by run_number DESC."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, mission_id, run_number, status, current_milestone_id,
                       team_name, started_at, completed_at, interrupted_at,
                       duration_seconds, error_message, error_details,
                       lease_owner, lease_expires_at, heartbeat_at, recovery_state,
                       pending_approval, approval_history, milestone_states, metadata,
                       created_at, updated_at
                FROM mission_executions
                WHERE mission_id = ?
                ORDER BY run_number DESC
                """,
                (mission_id,),
            ).fetchall()
            return [self._row_to_execution(r) for r in rows]

    def update_execution(
        self,
        execution_id: str,
        status: ExecutionStatus | str | None = None,
        current_milestone_id: str | None = None,
        team_name: str | None = None,
        completed_at: str | None = None,
        interrupted_at: str | None = None,
        duration_seconds: float | None = None,
        error_message: str | None = None,
        error_details: str | None = None,
        recovery_state: str | None = None,
        pending_approval: dict[str, Any] | None = None,
        approval_history: list[dict[str, Any]] | None = None,
        milestone_states: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MissionExecution | None:
        """Update fields on a mission execution."""
        updates: list[str] = []
        params: list[Any] = []

        if status is not None:
            st_val = status.value if isinstance(status, ExecutionStatus) else str(status)
            updates.append("status = ?")
            params.append(st_val)
        if current_milestone_id is not None:
            updates.append("current_milestone_id = ?")
            params.append(current_milestone_id or None)
        if team_name is not None:
            updates.append("team_name = ?")
            params.append(team_name or None)
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at or None)
        if interrupted_at is not None:
            updates.append("interrupted_at = ?")
            params.append(interrupted_at or None)
        if duration_seconds is not None:
            updates.append("duration_seconds = ?")
            params.append(float(duration_seconds))
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message or None)
        if error_details is not None:
            updates.append("error_details = ?")
            params.append(error_details or None)
        if recovery_state is not None:
            updates.append("recovery_state = ?")
            params.append(recovery_state)
        if pending_approval is not None:
            updates.append("pending_approval = ?")
            params.append(json.dumps(pending_approval) if pending_approval else None)
        if approval_history is not None:
            updates.append("approval_history = ?")
            params.append(json.dumps(approval_history))
        if milestone_states is not None:
            updates.append("milestone_states = ?")
            params.append(json.dumps(milestone_states))
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if not updates:
            return self.get_execution(execution_id)

        now = datetime.now(timezone.utc).isoformat()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(execution_id)

        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE mission_executions SET {', '.join(updates)} WHERE id = ?",
                params,
            )
        return self.get_execution(execution_id)

    def acquire_execution_lease(
        self,
        mission_id: str,
        execution_id: str,
        owner_token: str,
        ttl_seconds: int = 60,
    ) -> bool:
        """
        Atomically acquires a durable execution lease for an execution.
        Guarantees mutual exclusion: returns False if another execution for this mission
        holds a valid unexpired lease.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_iso = (now + timedelta(seconds=ttl_seconds)).isoformat()

        with self._get_connection() as conn:
            # Check for active lease held by any OTHER execution for this mission
            conflict = conn.execute(
                """
                SELECT id, lease_owner, lease_expires_at
                FROM mission_executions
                WHERE mission_id = ? AND status IN ('running', 'verifying')
                  AND id != ? AND lease_expires_at > ?
                """,
                (mission_id, execution_id, now_iso),
            ).fetchone()

            if conflict:
                return False

            # Grant lease to this execution
            res = conn.execute(
                """
                UPDATE mission_executions
                SET status = 'running',
                    lease_owner = ?,
                    lease_expires_at = ?,
                    heartbeat_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (owner_token, expires_iso, now_iso, now_iso, execution_id),
            )
            if res.rowcount == 0:
                return False

            # Keep parent mission status in sync
            conn.execute(
                "UPDATE missions SET status = 'running', active_execution_id = ?, updated_at = ? WHERE id = ?",
                (execution_id, now_iso, mission_id),
            )
            return True

    def renew_execution_lease(
        self,
        execution_id: str,
        owner_token: str,
        ttl_seconds: int = 60,
    ) -> bool:
        """Heartbeat renewal of an active execution lease."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_iso = (now + timedelta(seconds=ttl_seconds)).isoformat()

        with self._get_connection() as conn:
            res = conn.execute(
                """
                UPDATE mission_executions
                SET lease_expires_at = ?,
                    heartbeat_at = ?,
                    updated_at = ?
                WHERE id = ? AND lease_owner = ? AND status IN ('running', 'verifying')
                """,
                (expires_iso, now_iso, now_iso, execution_id, owner_token),
            )
            return res.rowcount > 0

    def release_execution_lease(
        self,
        execution_id: str,
        owner_token: str | None = None,
    ) -> bool:
        """Releases the execution lease when a run completes, pauses, or terminates."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            query = "UPDATE mission_executions SET lease_owner = NULL, lease_expires_at = NULL, updated_at = ? WHERE id = ?"
            params: list[Any] = [now_iso, execution_id]
            if owner_token:
                query += " AND lease_owner = ?"
                params.append(owner_token)
            res = conn.execute(query, params)
            return res.rowcount > 0

    def get_execution_milestones(self, execution_id: str) -> list[ExecutionMilestone]:
        """Returns execution-scoped milestone states for a given execution run."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, execution_id, milestone_id, status, started_at, completed_at,
                       duration_seconds, error, output, metadata, created_at, updated_at
                FROM mission_execution_milestones
                WHERE execution_id = ?
                ORDER BY created_at ASC
                """,
                (execution_id,),
            ).fetchall()

            res: list[ExecutionMilestone] = []
            for r in rows:
                st_val = r["status"]
                status = MilestoneExecutionStatus(st_val) if st_val in MilestoneExecutionStatus._value2member_map_ else MilestoneExecutionStatus.PENDING
                meta = {}
                if r["metadata"]:
                    try:
                        meta = json.loads(r["metadata"])
                    except Exception:
                        pass
                res.append(
                    ExecutionMilestone(
                        id=r["id"],
                        execution_id=r["execution_id"],
                        milestone_id=r["milestone_id"],
                        status=status,
                        started_at=r["started_at"],
                        completed_at=r["completed_at"],
                        duration_seconds=float(r["duration_seconds"] or 0.0),
                        error=r["error"],
                        output=r["output"],
                        metadata=meta,
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                    )
                )
            return res

    def update_execution_milestone(
        self,
        execution_id: str,
        milestone_id: str,
        status: MilestoneExecutionStatus | str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        duration_seconds: float | None = None,
        error: str | None = None,
        output: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionMilestone | None:
        """Updates the status and output of a specific milestone within an execution run."""
        updates: list[str] = []
        params: list[Any] = []

        if status is not None:
            st_val = status.value if isinstance(status, MilestoneExecutionStatus) else str(status)
            updates.append("status = ?")
            params.append(st_val)
        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at or None)
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at or None)
        if duration_seconds is not None:
            updates.append("duration_seconds = ?")
            params.append(float(duration_seconds))
        if error is not None:
            updates.append("error = ?")
            params.append(error or None)
        if output is not None:
            updates.append("output = ?")
            params.append(output or None)
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))

        if not updates:
            return None

        now = datetime.now(timezone.utc).isoformat()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(execution_id)
        params.append(milestone_id)

        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE mission_execution_milestones SET {', '.join(updates)} WHERE execution_id = ? AND milestone_id = ?",
                params,
            )

        milestones = self.get_execution_milestones(execution_id)
        for em in milestones:
            if em.milestone_id == milestone_id:
                return em
        return None

    def recover_stale_executions(self) -> list[str]:
        """
        Crash recovery: inspects mission_executions on startup.
        Any execution left in 'running' or 'verifying' is transitioned to 'interrupted',
        its running milestone reset to 'pending', and leases cleared.
        Executions in 'awaiting_approval' are preserved.
        """
        recovered_ids: list[str] = []
        now = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            stale_rows = conn.execute(
                """
                SELECT id, mission_id, run_number, current_milestone_id
                FROM mission_executions
                WHERE status IN ('running', 'verifying')
                """
            ).fetchall()

            for r in stale_rows:
                exec_id = r["id"]
                mid = r["mission_id"]
                curr_ms = r["current_milestone_id"]

                conn.execute(
                    """
                    UPDATE mission_executions
                    SET status = 'interrupted',
                        interrupted_at = ?,
                        recovery_state = 'recovered_from_crash',
                        error_message = 'Execution interrupted by application restart. Ready to resume.',
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, exec_id),
                )

                conn.execute(
                    """
                    UPDATE mission_execution_milestones
                    SET status = 'pending',
                        updated_at = ?
                    WHERE execution_id = ? AND status = 'running'
                    """,
                    (now, exec_id),
                )

                conn.execute(
                    """
                    UPDATE missions
                    SET status = 'interrupted',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, mid),
                )

                act_id = f"act_{uuid.uuid4().hex[:12]}"
                meta_act = json.dumps({
                    "execution_id": exec_id,
                    "milestone_id": curr_ms,
                    "reason": "crash_recovery",
                })
                conn.execute(
                    """
                    INSERT INTO conversation_activities (
                        id, conversation_id, agent, activity_type, message, metadata, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        act_id,
                        mid,
                        "System",
                        "execution_interrupted",
                        f"Execution Run #{r['run_number']} was interrupted by application restart. Ready to resume.",
                        meta_act,
                        now,
                    ),
                )
                recovered_ids.append(exec_id)

        return recovered_ids
