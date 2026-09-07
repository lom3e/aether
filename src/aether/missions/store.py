"""
MissionStore — SQLite-backed persistence for Missions, Milestones, and Graph Generation.
Provides complete CRUD lifecycle for missions and milestones, with foreign-key integrity
and read-only DAG graph synthesis.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from aether.core.sqlite import get_sqlite_connection
from aether.missions.models import (
    GraphEdge,
    GraphNode,
    Milestone,
    MilestoneStatus,
    Mission,
    MissionGraph,
    MissionStatus,
    Deliverable,
)


class MissionStore:
    """
    Manages persistent Missions, Milestones, and Read-Only Execution Graph models.
    Operates on the shared conversations database in the workspace data directory.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        if self.db_path == ":memory:":
            self.db_path = f"file:memdb_missions_{uuid.uuid4().hex}?mode=memory&cache=shared"
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return get_sqlite_connection(self.db_path)

    def _init_db(self) -> None:
        with self._get_connection() as conn:
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
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            # 2. Mission Milestones table
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

            # 3. Performance Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_missions_updated ON missions(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_missions_conv ON missions(conversation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_missions_project ON missions(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_milestones_mission ON mission_milestones(mission_id, order_idx ASC)")

            # 4. Safe migration for conversations table if present
            try:
                conn.execute("ALTER TABLE conversations ADD COLUMN mission_id TEXT DEFAULT NULL")
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

        created_milestones: list[Milestone] = []

        with self._get_connection() as conn:
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
                    conversation_id,
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
        """Retrieve a mission by ID with its milestones."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, workspace_id, title, objective, status,
                       team_name, conversation_id, project_id, metadata,
                       created_at, updated_at
                FROM missions
                WHERE id = ?
                """,
                (mission_id,),
            ).fetchone()

            if not row:
                return None

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
                    milestones.append(
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

        meta = {}
        try:
            meta = json.loads(row["metadata"] or "{}")
        except Exception:
            pass

        st_val = row["status"]
        return Mission(
            id=row["id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            objective=row["objective"],
            status=MissionStatus(st_val) if st_val in MissionStatus._value2member_map_ else MissionStatus.DRAFT,
            team_name=row["team_name"],
            conversation_id=row["conversation_id"],
            project_id=row["project_id"],
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
                   team_name, conversation_id, project_id, metadata,
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
                    milestones=milestones_by_mission.get(r["id"], []),
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
        metadata: dict[str, Any] | None = None,
    ) -> Mission | None:
        """Update an existing mission's metadata or status."""
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
    # Deliverables Management
    # ---------------------------------------------------------------------------

    def list_deliverables(self, mission_id: str) -> list[Deliverable]:
        """
        Retrieves all real deliverables registered or produced for this mission.
        Inspects mission metadata and linked conversation activities without fabricating fake items.
        """
        mission = self.get_mission(mission_id, include_milestones=False)
        if not mission:
            return []

        deliverables: list[Deliverable] = []
        seen_paths: set[str] = set()

        # 1. Inspect explicit registered deliverables in mission.metadata["deliverables"]
        raw_delivs = mission.metadata.get("deliverables") if isinstance(mission.metadata, dict) else None
        if isinstance(raw_delivs, list):
            for item in raw_delivs:
                if isinstance(item, dict):
                    d = Deliverable.from_dict({**item, "mission_id": mission_id})
                    deliverables.append(d)
                    if d.path:
                        seen_paths.add(d.path)

        # 2. If conversation_id is linked, inspect conversation activities for file modifications
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
                    file_path = meta.get("path")
                    if file_path and file_path not in seen_paths:
                        seen_paths.add(file_path)
                        filename = Path(file_path).name
                        ext = Path(file_path).suffix.lower()
                        ftype = "document" if ext in (".md", ".txt", ".pdf", ".docx") else ("data" if ext in (".json", ".csv", ".tsv", ".yaml", ".yml", ".parquet") else ("code" if ext in (".py", ".ts", ".tsx", ".js", ".sh", ".rs", ".go") else "archive"))
                        size_bytes = int(meta.get("size_bytes", 0))
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
        Registers a real deliverable into the mission's metadata.
        """
        mission = self.get_mission(mission_id, include_milestones=False)
        if not mission:
            return False

        meta = dict(mission.metadata) if isinstance(mission.metadata, dict) else {}
        delivs = list(meta.get("deliverables", []))
        # Avoid duplicate deliverable IDs
        delivs = [d for d in delivs if d.get("id") != deliverable.id]
        delivs.append(deliverable.to_dict())
        meta["deliverables"] = delivs

        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE missions SET metadata = ?, updated_at = ? WHERE id = ?",
                (json.dumps(meta), now, mission_id),
            )
            return True
