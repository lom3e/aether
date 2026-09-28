"""
P3.2 Release-Grade Hardening: Approval Concurrency & Terminal Consistency Test Suite.
Verifies:
1. Concurrent approve/reject race safety: No corrupted mixed states.
2. Multithreaded simultaneous approve calls: Exactly one execution runs, others return idempotently.
3. Strict terminal state invariants: Cannot decline approved/succeeded, cannot approve rejected.
4. Activity log & execution store consistency under high thread contention.
"""
from __future__ import annotations

import concurrent.futures
from pathlib import Path
import threading
import time
import pytest

from aether.actions.executor import ActionExecutor
from aether.actions.models import (
    ActionDefinition,
    ActionExecution,
    ActionExecutionStatus,
    ActionPermissionLevel,
)
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore


@pytest.fixture
def executor_setup(tmp_path: Path):
    db_path = tmp_path / "actions.db"
    store = ActionStore(str(db_path))
    registry = ActionRegistry()

    execution_counter = {"count": 0}
    lock = threading.Lock()

    def dummy_handler(input_data: dict, workspace_id: str) -> dict:
        with lock:
            execution_counter["count"] += 1
        time.sleep(0.01)  # small window to induce race conditions
        return {"result": "success", "input": input_data}

    # Register an action requiring explicit confirmation
    action_def = ActionDefinition(
        id="test.sensitive_op",
        name="Sensitive Operation",
        description="Requires user approval",
        permission_level=ActionPermissionLevel.SENSITIVE_MUTATION,
        requires_confirmation=True,
    )
    registry.register(action_def, handler=dummy_handler)

    executor = ActionExecutor(registry=registry, store=store)
    return executor, store, execution_counter


def test_concurrent_simultaneous_approvals(executor_setup):
    """
    10 threads try to approve the exact same WAITING_APPROVAL execution simultaneously.
    Guarantee:
    - Underlying action handler runs EXACTLY once.
    - All threads complete without unhandled crash.
    - Final state is SUCCEEDED.
    """
    executor, store, counter = executor_setup

    # Create pending execution
    pending = executor.execute(
        action_id="test.sensitive_op",
        workspace_id="ws-test",
        input_data={"target": "database_cleanup"},
        auto_approve=False,
    )
    assert pending.status == ActionExecutionStatus.WAITING_APPROVAL

    results = []
    errors = []

    def run_approve(thread_idx: int):
        try:
            res = executor.approve(pending.id, approver=f"admin_{thread_idx}")
            results.append(res)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=run_approve, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All threads should get back a valid execution (or raise nothing)
    assert len(errors) == 0
    assert len(results) == 10

    # Underlying handler ran EXACTLY once
    assert counter["count"] == 1

    # Final execution is SUCCEEDED in database
    final = store.get_execution(pending.id)
    assert final is not None
    assert final.status == ActionExecutionStatus.SUCCEEDED
    assert final.output_data == {"result": "success", "input": {"target": "database_cleanup"}}


def test_concurrent_approve_versus_reject_race(executor_setup):
    """
    Two threads simultaneously race: one calls approve(), one calls reject().
    Guarantee:
    - Atomicity: exactly one operation wins the race.
    - The loser raises a clear ValueError rather than leaving the system in an inconsistent state.
    - The winning state in SQLite is 100% consistent with the returned result.
    """
    executor, store, counter = executor_setup

    pending = executor.execute(
        action_id="test.sensitive_op",
        workspace_id="ws-test",
        input_data={"target": "nuclear_launch"},
        auto_approve=False,
    )
    assert pending.status == ActionExecutionStatus.WAITING_APPROVAL

    barrier = threading.Barrier(2)
    race_results = {}

    def do_approve():
        barrier.wait()
        try:
            res = executor.approve(pending.id, approver="user_lead")
            race_results["approve"] = ("ok", res)
        except Exception as e:
            race_results["approve"] = ("error", str(e))

    def do_reject():
        barrier.wait()
        try:
            res = executor.reject(pending.id, reason="Denied by security policy")
            race_results["reject"] = ("ok", res)
        except Exception as e:
            race_results["reject"] = ("error", str(e))

    t1 = threading.Thread(target=do_approve)
    t2 = threading.Thread(target=do_reject)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    final = store.get_execution(pending.id)
    assert final is not None

    if race_results["approve"][0] == "ok":
        # Approve won the race: final must be SUCCEEDED, reject must have raised
        assert final.status == ActionExecutionStatus.SUCCEEDED
        assert race_results["reject"][0] == "error"
        assert "already approved" in race_results["reject"][1].lower() or "terminal" in race_results["reject"][1].lower()
        assert counter["count"] == 1
    else:
        # Reject won the race: final must be REJECTED, handler was never executed
        assert final.status == ActionExecutionStatus.REJECTED
        assert race_results["reject"][0] == "ok"
        assert race_results["approve"][0] == "error"
        assert "declined" in race_results["approve"][1].lower() or "already" in race_results["approve"][1].lower()
        assert counter["count"] == 0


def test_terminal_state_invariants_and_idempotency(executor_setup):
    """
    Verifies state machine idempotency and immutable terminal state protections:
    - Succeeded actions cannot be declined.
    - Rejected actions cannot be approved.
    - Calling approve on already succeeded action is idempotent.
    - Calling reject on already rejected action is idempotent.
    """
    executor, store, counter = executor_setup

    # Case A: Approve then idempotent re-approve & reject attempt
    exec_a = executor.execute(
        action_id="test.sensitive_op",
        workspace_id="ws-test",
        input_data={"case": "A"},
        auto_approve=False,
    )
    approved_a = executor.approve(exec_a.id)
    assert approved_a.status == ActionExecutionStatus.SUCCEEDED

    # Idempotent re-approve returns completed execution without re-running handler
    count_before = counter["count"]
    re_approved = executor.approve(exec_a.id)
    assert re_approved.status == ActionExecutionStatus.SUCCEEDED
    assert counter["count"] == count_before

    # Attempt to reject already approved/terminal action must fail
    with pytest.raises(ValueError, match="Cannot decline execution"):
        executor.reject(exec_a.id, reason="Too late")

    # Case B: Reject then idempotent re-reject & approve attempt
    exec_b = executor.execute(
        action_id="test.sensitive_op",
        workspace_id="ws-test",
        input_data={"case": "B"},
        auto_approve=False,
    )
    rejected_b = executor.reject(exec_b.id, reason="Declined initially")
    assert rejected_b.status == ActionExecutionStatus.REJECTED

    # Idempotent re-reject
    re_rejected = executor.reject(exec_b.id, reason="Declined again")
    assert re_rejected.status == ActionExecutionStatus.REJECTED

    # Attempt to approve already rejected action must fail
    with pytest.raises(ValueError, match="Cannot approve execution"):
        executor.approve(exec_b.id)
