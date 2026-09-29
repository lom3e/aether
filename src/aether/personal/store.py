"""
Persistent SQLite Storage for Personal Agent Conversations (Phase C).
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

from aether.personal.models import (
    IntentTier,
    PersonalMessage,
    PersonalSession,
    PersonalStep,
    PersonalTask,
    PersonalTaskStatus,
)
from aether.planning.contracts import (
    ContextPack,
    IntentRequest,
    MissionProposal,
)

logger = logging.getLogger(__name__)


class PersonalStore:
    """SQLite-backed store for Personal Agent conversations and history."""

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
                CREATE TABLE IF NOT EXISTS personal_sessions (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ps_ws ON personal_sessions(workspace_id);")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS personal_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    steps TEXT,
                    action_execution_id TEXT,
                    mission_id TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES personal_sessions(id) ON DELETE CASCADE
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pm_session ON personal_messages(session_id, created_at ASC);")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS personal_tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    current_step TEXT,
                    result_summary TEXT,
                    mission_id TEXT,
                    action_execution_id TEXT,
                    error TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pt_ws_status ON personal_tasks(workspace_id, status, updated_at DESC);")

            # Phase A Macro-pass 1: Additive Intent & Proposal Foundation Tables
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS intent_requests (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    session_id TEXT,
                    raw_input TEXT NOT NULL,
                    source_surface TEXT NOT NULL,
                    status TEXT NOT NULL,
                    inferred_goal TEXT,
                    urgency TEXT NOT NULL DEFAULT 'normal',
                    constraints TEXT DEFAULT '[]',
                    requested_deliverables TEXT DEFAULT '[]',
                    relevant_entities TEXT DEFAULT '[]',
                    ambiguity TEXT DEFAULT '[]',
                    provenance TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ir_ws ON intent_requests(workspace_id, created_at DESC);")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS proposal_context (
                    id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    workspace_scope TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    resolved_entities TEXT DEFAULT '[]',
                    evidence_references TEXT DEFAULT '[]',
                    unresolved_references TEXT DEFAULT '[]',
                    ambiguity TEXT DEFAULT '[]',
                    assumptions TEXT DEFAULT '[]',
                    retrieval_failures TEXT DEFAULT '[]',
                    provenance TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (intent_id) REFERENCES intent_requests(id) ON DELETE CASCADE
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pc_intent ON proposal_context(intent_id);")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS mission_proposals (
                    id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    title TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    why TEXT NOT NULL,
                    context_summary TEXT NOT NULL,
                    proposed_steps TEXT DEFAULT '[]',
                    constraints TEXT DEFAULT '[]',
                    outcome_constraints TEXT DEFAULT '[]',
                    expected_deliverables TEXT DEFAULT '[]',
                    checkpoints TEXT DEFAULT '[]',
                    risks TEXT DEFAULT '[]',
                    assumptions TEXT DEFAULT '[]',
                    confidence REAL NOT NULL,
                    required_approvals TEXT DEFAULT '[]',
                    clarification_ids TEXT DEFAULT '[]',
                    clarification_requirements TEXT DEFAULT '[]',
                    provenance TEXT DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (intent_id) REFERENCES intent_requests(id) ON DELETE CASCADE
                );
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mp_ws ON mission_proposals(workspace_id, status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mp_intent ON mission_proposals(intent_id);")

    def save_session(self, session: PersonalSession) -> PersonalSession:
        """Saves or updates session metadata."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO personal_sessions (
                    id, workspace_id, title, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.workspace_id,
                    session.title,
                    session.created_at,
                    session.updated_at,
                ),
            )
        return session

    def get_session(self, session_id: str) -> PersonalSession | None:
        """Retrieves a session and all its messages."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM personal_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None

        msg_rows = conn.execute(
            "SELECT * FROM personal_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()

        messages = [self._row_to_message(r) for r in msg_rows]

        return PersonalSession(
            id=row["id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            messages=messages,
        )

    def list_sessions(self, workspace_id: str, limit: int = 20) -> list[PersonalSession]:
        """Lists recent sessions."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM personal_sessions WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT ?",
            (workspace_id, max(1, limit)),
        ).fetchall()

        return [
            PersonalSession(
                id=r["id"],
                workspace_id=r["workspace_id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                messages=[],
            )
            for r in rows
        ]

    def add_message(self, message: PersonalMessage) -> PersonalMessage:
        """Adds a message to a session."""
        if not self.get_session(message.session_id):
            self.save_session(
                PersonalSession(
                    id=message.session_id,
                    workspace_id=message.workspace_id,
                    title=f"Session {message.session_id[:8]}",
                )
            )
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO personal_messages (
                    id, session_id, workspace_id, role, content, tier,
                    steps, action_execution_id, mission_id, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.session_id,
                    message.workspace_id,
                    message.role,
                    message.content,
                    message.tier.value if isinstance(message.tier, IntentTier) else str(message.tier),
                    json.dumps([s.to_dict() for s in message.steps]),
                    message.action_execution_id,
                    message.mission_id,
                    json.dumps(message.metadata),
                    message.created_at,
                ),
            )
            cursor.execute(
                "UPDATE personal_sessions SET updated_at = ? WHERE id = ?",
                (message.created_at, message.session_id),
            )
        return message

    def _row_to_message(self, row: sqlite3.Row) -> PersonalMessage:
        raw_steps = json.loads(row["steps"]) if row["steps"] else []
        steps = [PersonalStep.from_dict(s) for s in raw_steps]

        return PersonalMessage(
            id=row["id"],
            session_id=row["session_id"],
            workspace_id=row["workspace_id"],
            role=row["role"],
            content=row["content"],
            tier=IntentTier.from_str(row["tier"]),
            steps=steps,
            action_execution_id=row["action_execution_id"],
            mission_id=row["mission_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
        )

    def get_messages(self, session_id: str) -> list[PersonalMessage]:
        """Retrieves all messages for a session ordered by creation time."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM personal_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_recent_messages(self, session_id: str, limit: int = 6) -> list[PersonalMessage]:
        """Retrieves the most recent messages for conversational context."""
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT * FROM personal_messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?
            ) ORDER BY created_at ASC
            """,
            (session_id, max(1, limit)),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def save_task(self, task: PersonalTask) -> PersonalTask:
        """Inserts or updates a persistent personal task."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO personal_tasks (
                    id, session_id, workspace_id, title, status, tier,
                    progress_percent, current_step, result_summary, mission_id,
                    action_execution_id, error, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.session_id,
                    task.workspace_id,
                    task.title,
                    task.status.value if isinstance(task.status, PersonalTaskStatus) else str(task.status),
                    task.tier.value if isinstance(task.tier, IntentTier) else str(task.tier),
                    task.progress_percent,
                    task.current_step,
                    task.result_summary,
                    task.mission_id,
                    task.action_execution_id,
                    task.error,
                    json.dumps(task.metadata),
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def get_task(self, task_id: str) -> PersonalTask | None:
        """Retrieves a personal task by ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM personal_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return self._row_to_task(row)

    def list_tasks(
        self,
        workspace_id: str,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[PersonalTask]:
        """Lists personal tasks for a workspace, optionally filtered by session or status."""
        conn = self._get_connection()
        conditions = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = " AND ".join(conditions)
        sql = f"SELECT * FROM personal_tasks WHERE {where_clause} ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, limit))

        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_task_progress(
        self,
        task_id: str,
        progress_percent: int,
        current_step: str,
        status: PersonalTaskStatus | str | None = None,
        result_summary: str | None = None,
        error: str | None = None,
    ) -> PersonalTask | None:
        """Updates progress, step, status, and outcome of a personal task."""
        task = self.get_task(task_id)
        if not task:
            return None

        task.progress_percent = progress_percent
        task.current_step = current_step
        if status:
            task.status = status if isinstance(status, PersonalTaskStatus) else PersonalTaskStatus.from_str(str(status))
        if result_summary is not None:
            task.result_summary = result_summary
        if error is not None:
            task.error = error
        task.updated_at = task.updated_at = str(task.created_at)  # refreshed below
        from datetime import datetime, timezone
        task.updated_at = datetime.now(timezone.utc).isoformat()

        return self.save_task(task)

    def _row_to_task(self, row: sqlite3.Row) -> PersonalTask:
        return PersonalTask(
            id=row["id"],
            session_id=row["session_id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            status=PersonalTaskStatus.from_str(row["status"]),
            tier=IntentTier.from_str(row["tier"]),
            progress_percent=int(row["progress_percent"]),
            current_step=row["current_step"] or "",
            result_summary=row["result_summary"],
            mission_id=row["mission_id"],
            action_execution_id=row["action_execution_id"],
            error=row["error"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # -----------------------------------------------------------------------
    # Phase A Macro-pass 1: Intent & Proposal Foundation Persistence
    # -----------------------------------------------------------------------

    def save_intent_and_proposal(
        self,
        intent: IntentRequest,
        context_pack: ContextPack,
        proposal: MissionProposal,
    ) -> tuple[IntentRequest, ContextPack, MissionProposal]:
        """
        Atomically persists an IntentRequest, ContextPack, and MissionProposal within a single SQLite transaction.
        If any write fails, the entire transaction rolls back and an exception is raised.
        """
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO intent_requests (
                    id, workspace_id, session_id, raw_input, source_surface,
                    status, inferred_goal, urgency, constraints, requested_deliverables,
                    relevant_entities, ambiguity, provenance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.id,
                    intent.workspace_id,
                    intent.session_id,
                    intent.raw_input,
                    intent.source_surface,
                    intent.status,
                    intent.inferred_goal,
                    intent.urgency,
                    json.dumps(intent.constraints),
                    json.dumps(intent.requested_deliverables),
                    json.dumps(intent.relevant_entities),
                    json.dumps(intent.ambiguity),
                    json.dumps(intent.provenance.to_dict() if intent.provenance else {}),
                    intent.created_at,
                ),
            )

            ctx_id = f"ctx-{intent.id}"
            cursor.execute(
                """
                INSERT OR REPLACE INTO proposal_context (
                    id, intent_id, workspace_scope, confidence, resolved_entities,
                    evidence_references, unresolved_references, ambiguity, assumptions,
                    retrieval_failures, provenance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx_id,
                    intent.id,
                    context_pack.workspace_scope,
                    context_pack.confidence,
                    json.dumps([e.to_dict() for e in context_pack.resolved_entities]),
                    json.dumps([ev.to_dict() for ev in context_pack.evidence_references]),
                    json.dumps(context_pack.unresolved_references),
                    json.dumps(context_pack.ambiguity),
                    json.dumps(context_pack.assumptions),
                    json.dumps(context_pack.retrieval_failures),
                    json.dumps(context_pack.provenance.to_dict() if context_pack.provenance else {}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO mission_proposals (
                    id, intent_id, workspace_id, version, title, objective, why,
                    context_summary, proposed_steps, constraints, outcome_constraints,
                    expected_deliverables, checkpoints, risks, assumptions, confidence,
                    required_approvals, clarification_ids, clarification_requirements,
                    provenance, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.id,
                    proposal.intent_id,
                    proposal.workspace_id,
                    proposal.version,
                    proposal.title,
                    proposal.objective,
                    proposal.why,
                    proposal.context_summary,
                    json.dumps([s.to_dict() for s in proposal.proposed_steps]),
                    json.dumps(proposal.constraints),
                    json.dumps([o.to_dict() for o in proposal.outcome_constraints]),
                    json.dumps([d.to_dict() for d in proposal.expected_deliverables]),
                    json.dumps(proposal.checkpoints),
                    json.dumps([r.to_dict() for r in proposal.risks]),
                    json.dumps([a.to_dict() for a in proposal.assumptions]),
                    proposal.confidence,
                    json.dumps([a.to_dict() for a in proposal.required_approvals]),
                    json.dumps(proposal.clarification_ids),
                    json.dumps([c.to_dict() for c in proposal.clarification_requirements]),
                    json.dumps(proposal.provenance.to_dict() if proposal.provenance else {}),
                    proposal.status.value if hasattr(proposal.status, "value") else str(proposal.status),
                    proposal.created_at,
                    proposal.updated_at,
                ),
            )
        return intent, context_pack, proposal

    def save_intent_request(self, intent: IntentRequest) -> IntentRequest:
        """Persists an IntentRequest record."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO intent_requests (
                    id, workspace_id, session_id, raw_input, source_surface,
                    status, inferred_goal, urgency, constraints, requested_deliverables,
                    relevant_entities, ambiguity, provenance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.id,
                    intent.workspace_id,
                    intent.session_id,
                    intent.raw_input,
                    intent.source_surface,
                    intent.status,
                    intent.inferred_goal,
                    intent.urgency,
                    json.dumps(intent.constraints),
                    json.dumps(intent.requested_deliverables),
                    json.dumps(intent.relevant_entities),
                    json.dumps(intent.ambiguity),
                    json.dumps(intent.provenance.to_dict() if intent.provenance else {}),
                    intent.created_at,
                ),
            )
        return intent

    def get_intent_request(self, intent_id: str) -> IntentRequest | None:
        """Retrieves an IntentRequest by ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM intent_requests WHERE id = ?", (intent_id,)).fetchone()
        if not row:
            return None
        return IntentRequest.from_dict({
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "raw_input": row["raw_input"],
            "source_surface": row["source_surface"],
            "created_at": row["created_at"],
            "session_id": row["session_id"],
            "inferred_goal": row["inferred_goal"],
            "constraints": json.loads(row["constraints"]) if row["constraints"] else [],
            "urgency": row["urgency"],
            "requested_deliverables": json.loads(row["requested_deliverables"]) if row["requested_deliverables"] else [],
            "relevant_entities": json.loads(row["relevant_entities"]) if row["relevant_entities"] else [],
            "ambiguity": json.loads(row["ambiguity"]) if row["ambiguity"] else [],
            "provenance": json.loads(row["provenance"]) if row["provenance"] else None,
            "status": row["status"],
        })

    def save_context_pack(self, context_pack: ContextPack, intent_id: str) -> ContextPack:
        """Persists resolved context pack associated with an intent."""
        ctx_id = f"ctx-{intent_id}"
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO proposal_context (
                    id, intent_id, workspace_scope, confidence, resolved_entities,
                    evidence_references, unresolved_references, ambiguity, assumptions,
                    retrieval_failures, provenance, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx_id,
                    intent_id,
                    context_pack.workspace_scope,
                    context_pack.confidence,
                    json.dumps([e.to_dict() for e in context_pack.resolved_entities]),
                    json.dumps([ev.to_dict() for ev in context_pack.evidence_references]),
                    json.dumps(context_pack.unresolved_references),
                    json.dumps(context_pack.ambiguity),
                    json.dumps(context_pack.assumptions),
                    json.dumps(context_pack.retrieval_failures),
                    json.dumps(context_pack.provenance.to_dict() if context_pack.provenance else {}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return context_pack

    def get_context_pack(self, intent_id: str) -> ContextPack | None:
        """Retrieves resolved ContextPack by intent ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM proposal_context WHERE intent_id = ?", (intent_id,)).fetchone()
        if not row:
            return None
        return ContextPack.from_dict({
            "workspace_scope": row["workspace_scope"],
            "confidence": row["confidence"],
            "resolved_entities": json.loads(row["resolved_entities"]) if row["resolved_entities"] else [],
            "evidence_references": json.loads(row["evidence_references"]) if row["evidence_references"] else [],
            "unresolved_references": json.loads(row["unresolved_references"]) if row["unresolved_references"] else [],
            "ambiguity": json.loads(row["ambiguity"]) if row["ambiguity"] else [],
            "assumptions": json.loads(row["assumptions"]) if row["assumptions"] else [],
            "retrieval_failures": json.loads(row["retrieval_failures"]) if row["retrieval_failures"] else [],
            "provenance": json.loads(row["provenance"]) if row["provenance"] else None,
        })

    def save_proposal(self, proposal: MissionProposal) -> MissionProposal:
        """Persists a MissionProposal record."""
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO mission_proposals (
                    id, intent_id, workspace_id, version, title, objective, why,
                    context_summary, proposed_steps, constraints, outcome_constraints,
                    expected_deliverables, checkpoints, risks, assumptions, confidence,
                    required_approvals, clarification_ids, clarification_requirements,
                    provenance, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.id,
                    proposal.intent_id,
                    proposal.workspace_id,
                    proposal.version,
                    proposal.title,
                    proposal.objective,
                    proposal.why,
                    proposal.context_summary,
                    json.dumps([s.to_dict() for s in proposal.proposed_steps]),
                    json.dumps(proposal.constraints),
                    json.dumps([o.to_dict() for o in proposal.outcome_constraints]),
                    json.dumps([d.to_dict() for d in proposal.expected_deliverables]),
                    json.dumps(proposal.checkpoints),
                    json.dumps([r.to_dict() for r in proposal.risks]),
                    json.dumps([a.to_dict() for a in proposal.assumptions]),
                    proposal.confidence,
                    json.dumps([a.to_dict() for a in proposal.required_approvals]),
                    json.dumps(proposal.clarification_ids),
                    json.dumps([c.to_dict() for c in proposal.clarification_requirements]),
                    json.dumps(proposal.provenance.to_dict() if proposal.provenance else {}),
                    proposal.status.value if hasattr(proposal.status, "value") else str(proposal.status),
                    proposal.created_at,
                    proposal.updated_at,
                ),
            )
        return proposal

    def get_proposal(self, proposal_id: str) -> MissionProposal | None:
        """Retrieves a MissionProposal by ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM mission_proposals WHERE id = ?", (proposal_id,)).fetchone()
        if not row:
            return None
        return MissionProposal.from_dict({
            "id": row["id"],
            "intent_id": row["intent_id"],
            "workspace_id": row["workspace_id"],
            "version": row["version"],
            "title": row["title"],
            "objective": row["objective"],
            "why": row["why"],
            "context_summary": row["context_summary"],
            "proposed_steps": json.loads(row["proposed_steps"]) if row["proposed_steps"] else [],
            "constraints": json.loads(row["constraints"]) if row["constraints"] else [],
            "outcome_constraints": json.loads(row["outcome_constraints"]) if row["outcome_constraints"] else [],
            "expected_deliverables": json.loads(row["expected_deliverables"]) if row["expected_deliverables"] else [],
            "checkpoints": json.loads(row["checkpoints"]) if row["checkpoints"] else [],
            "risks": json.loads(row["risks"]) if row["risks"] else [],
            "assumptions": json.loads(row["assumptions"]) if row["assumptions"] else [],
            "confidence": row["confidence"],
            "required_approvals": json.loads(row["required_approvals"]) if row["required_approvals"] else [],
            "clarification_ids": json.loads(row["clarification_ids"]) if row["clarification_ids"] else [],
            "clarification_requirements": json.loads(row["clarification_requirements"]) if row["clarification_requirements"] else [],
            "provenance": json.loads(row["provenance"]) if row["provenance"] else None,
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })

    def list_proposals(self, workspace_id: str, limit: int = 20) -> list[MissionProposal]:
        """Lists latest MissionProposals for a workspace."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM mission_proposals WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
            (workspace_id, limit),
        ).fetchall()
        proposals = []
        for row in rows:
            p = MissionProposal.from_dict({
                "id": row["id"],
                "intent_id": row["intent_id"],
                "workspace_id": row["workspace_id"],
                "version": row["version"],
                "title": row["title"],
                "objective": row["objective"],
                "why": row["why"],
                "context_summary": row["context_summary"],
                "proposed_steps": json.loads(row["proposed_steps"]) if row["proposed_steps"] else [],
                "constraints": json.loads(row["constraints"]) if row["constraints"] else [],
                "outcome_constraints": json.loads(row["outcome_constraints"]) if row["outcome_constraints"] else [],
                "expected_deliverables": json.loads(row["expected_deliverables"]) if row["expected_deliverables"] else [],
                "checkpoints": json.loads(row["checkpoints"]) if row["checkpoints"] else [],
                "risks": json.loads(row["risks"]) if row["risks"] else [],
                "assumptions": json.loads(row["assumptions"]) if row["assumptions"] else [],
                "confidence": row["confidence"],
                "required_approvals": json.loads(row["required_approvals"]) if row["required_approvals"] else [],
                "clarification_ids": json.loads(row["clarification_ids"]) if row["clarification_ids"] else [],
                "clarification_requirements": json.loads(row["clarification_requirements"]) if row["clarification_requirements"] else [],
                "provenance": json.loads(row["provenance"]) if row["provenance"] else None,
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
            proposals.append(p)
        return proposals

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
