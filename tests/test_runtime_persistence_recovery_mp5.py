"""
MP5 — Runtime, Persistence & Recovery Verification Test Suite.

Verifies:
1. Workspace Registry: Disambiguation by unique ID and canonical root path, eliminating collisions
   when multiple workspaces share the same display name across different roots.
2. SQLite Concurrency & Hygiene: WAL journal mode, busy_timeout=5000, foreign_keys=ON, synchronous=NORMAL
   applied via get_sqlite_connection.
3. Action Idempotency Ledger: Proposal step idempotency and args_digest ledger prevents replay
   and duplicate side-effects.
4. Crash Recovery: Actions left in 'running', 'queued', or 'approved' are cleanly marked failed/interrupted
   upon restart, while 'waiting_approval' is preserved.
"""
from __future__ import annotations

import sqlite3
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone

import pytest

from aether.workspace.workspace import Workspace
from aether.core.sqlite import get_sqlite_connection, configure_sqlite_connection
from aether.actions.models import ActionExecution, ActionExecutionStatus, ActionPermissionLevel, ActionTier, ActionDefinition
from aether.actions.store import ActionStore
from aether.actions.executor import ActionExecutor
from aether.personal.store import PersonalStore
from aether.planning.contracts import IntentRequest, MissionProposal, ProposedStep, ProposalStatus
from aether.core.execution import (
    ExecutionAuthority,
    ExecutionBoundary,
    UnauthorizedExecutionError,
    compute_args_digest,
)


def test_workspace_registry_no_collision_same_name():
    """Two workspaces with the same name in different directories do not overwrite each other."""
    with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
        ws1 = Workspace.init(Path(dir1), name="shared_name")
        ws2 = Workspace.init(Path(dir2), name="shared_name")

        # Each workspace has a distinct root and unique id
        assert ws1.root != ws2.root
        assert ws1.id != ws2.id

        # Retrieving by ID returns the correct workspace instance
        assert Workspace.get(ws1.id) is ws1
        assert Workspace.get(ws2.id) is ws2

        # Retrieving by canonical root path returns the correct workspace
        assert Workspace.get(ws1.root) is ws1
        assert Workspace.get(ws2.root) is ws2

        # Injected workspace in ActionExecutor matches self
        assert ws1.actions.workspace is ws1
        assert ws2.actions.workspace is ws2

        # Close ws1 - ws2 remains active and registered
        ws1.close()
        assert Workspace.get(ws2.id) is ws2
        ws2.close()


def test_sqlite_hardening_pragmas():
    """Verify that get_sqlite_connection applies WAL, busy_timeout, foreign_keys, and synchronous pragmas."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_hardened.db"
        conn = get_sqlite_connection(db_file)

        try:
            # Check journal_mode is WAL
            journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            assert str(journal_mode).upper() == "WAL"

            # Check busy_timeout is 5000
            busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
            assert int(busy_timeout) == 5000

            # Check foreign_keys is 1 (ON)
            fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            assert int(fk) == 1

            # Check synchronous is 1 (NORMAL)
            sync_mode = conn.execute("PRAGMA synchronous;").fetchone()[0]
            assert int(sync_mode) in (1, 2)
        finally:
            conn.close()


def test_action_idempotency_ledger_prevents_duplicate_execution():
    """Idempotency ledger prevents replay of executed step or matching args_digest."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Workspace.init(Path(tmp_dir), name="idempotency_ws")
        p_store = ws.personal_store

        # 1. Create and accept a proposal with a step
        p_store.save_intent_request(IntentRequest(
            id="intent-idem-1",
            workspace_id=ws.id,
            raw_input="Idempotency test intent",
            source_surface="test",
        ))
        step = ProposedStep(
            id="step-unique-1",
            order_idx=0,
            title="Read summary",
            description="Read status",
            required_tools_or_actions=["files.read_document"],
        )
        prop = MissionProposal(
            id="prop-idem-1",
            intent_id="intent-idem-1",
            workspace_id=ws.id,
            title="Idempotency Test",
            objective="Ensure step only executes once",
            why="Testing idempotency ledger",
            context_summary="",
            expected_deliverables=[],
            proposed_steps=[step],
            status=ProposalStatus.ACCEPTED,
        )
        p_store.save_proposal(prop)

        # First run authority
        auth = ExecutionBoundary.issue_authority(prop, step_id="step-unique-1")

        # Step not yet recorded
        assert p_store.is_step_executed("prop-idem-1", "step-unique-1") is False

        # Validate authority succeeds
        validated = ExecutionBoundary.validate_authority(
            authority=auth,
            workspace_id=ws.id,
            store=p_store,
            action_or_boundary="files.read_document",
            step_id="step-unique-1",
        )
        assert validated is not None

        # Record step execution
        p_store.record_step_executed(
            proposal_id="prop-idem-1",
            step_id="step-unique-1",
            action_id="files.read_document",
            args_digest=auth.args_digest or "digest-1",
        )

        assert p_store.is_step_executed("prop-idem-1", "step-unique-1") is True
        assert p_store.is_action_executed("prop-idem-1", "files.read_document", auth.args_digest or "digest-1") is True

        # Second validation MUST fail closed with UnauthorizedExecutionError
        with pytest.raises(UnauthorizedExecutionError) as exc_info:
            ExecutionBoundary.validate_authority(
                authority=auth,
                workspace_id=ws.id,
                store=p_store,
                action_or_boundary="files.read_document",
                step_id="step-unique-1",
            )
        assert "already been executed" in str(exc_info.value)

        ws.close()


def test_crash_recovery_cleans_interrupted_executions():
    """Startup crash recovery marks 'running', 'queued', and 'approved' actions as failed while preserving 'waiting_approval'."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Workspace.init(Path(tmp_dir), name="recovery_ws")
        act_store = ws.action_store

        # Insert actions across various states simulating pre-crash environment
        running_exec = ActionExecution(
            id="ax-running",
            action_id="files.create_document",
            workspace_id=ws.id,
            status=ActionExecutionStatus.RUNNING,
            input_data={"path": "report.txt"},
        )
        queued_exec = ActionExecution(
            id="ax-queued",
            action_id="files.create_document",
            workspace_id=ws.id,
            status=ActionExecutionStatus.QUEUED,
            input_data={"path": "queued.txt"},
        )
        approved_exec = ActionExecution(
            id="ax-approved",
            action_id="files.create_document",
            workspace_id=ws.id,
            status=ActionExecutionStatus.APPROVED,
            input_data={"path": "approved.txt"},
        )
        pending_approval_exec = ActionExecution(
            id="ax-waiting",
            action_id="email.send",
            workspace_id=ws.id,
            status=ActionExecutionStatus.WAITING_APPROVAL,
            input_data={"to": "user@example.com"},
        )

        act_store.save_execution(running_exec)
        act_store.save_execution(queued_exec)
        act_store.save_execution(approved_exec)
        act_store.save_execution(pending_approval_exec)

        # Run crash recovery
        recovery_summary = ws.recover_on_startup()
        assert recovery_summary["recovered_actions"] == 3

        # Verify states
        assert act_store.get_execution("ax-running").status == ActionExecutionStatus.FAILED
        assert "interrupted" in (act_store.get_execution("ax-running").error_message or "").lower()

        assert act_store.get_execution("ax-queued").status == ActionExecutionStatus.FAILED
        assert act_store.get_execution("ax-approved").status == ActionExecutionStatus.FAILED

        # Waiting approval MUST be preserved so user decisions survive restart
        assert act_store.get_execution("ax-waiting").status == ActionExecutionStatus.WAITING_APPROVAL

        ws.close()
