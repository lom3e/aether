"""
Tests for MissionExecution, ExecutionMilestone, MissionDeliverables, Lease Management, and Crash Recovery.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from aether.missions.models import (
    Deliverable,
    ExecutionStatus,
    MilestoneExecutionStatus,
    MissionStatus,
)
from aether.missions.store import MissionStore


@pytest.fixture
def store(tmp_path: Path) -> MissionStore:
    db_file = tmp_path / "test_missions.db"
    return MissionStore(db_file)


def test_create_and_get_execution(store: MissionStore) -> None:
    # 1. Create a mission with 2 milestones
    mission = store.create_mission(
        title="Audit Security",
        objective="Analyze codebase security vulnerabilities",
        milestones=[
            {"title": "Scan Dependencies", "order_idx": 0},
            {"title": "Patch Vulnerabilities", "order_idx": 1},
        ],
    )

    # Verify template milestones exist in draft state
    assert len(mission.milestones) == 2
    ms1_id = mission.milestones[0].id
    ms2_id = mission.milestones[1].id

    # 2. Create first execution run
    exec1 = store.create_execution(mission.id, team_name="dev_team")
    assert exec1.id.startswith("exec_")
    assert exec1.mission_id == mission.id
    assert exec1.run_number == 1
    assert exec1.status == ExecutionStatus.PENDING

    # 3. Check execution-scoped milestones
    exec_milestones = store.get_execution_milestones(exec1.id)
    assert len(exec_milestones) == 2
    assert {em.milestone_id for em in exec_milestones} == {ms1_id, ms2_id}
    assert all(em.status == MilestoneExecutionStatus.PENDING for em in exec_milestones)

    # 4. Check active execution on mission
    updated_mission = store.get_mission(mission.id)
    assert updated_mission is not None
    assert updated_mission.active_execution_id == exec1.id
    assert updated_mission.active_execution is not None
    assert updated_mission.active_execution.id == exec1.id


def test_execution_milestone_updates_and_template_preservation(store: MissionStore) -> None:
    mission = store.create_mission(
        title="Deploy App",
        objective="Deploy application to staging",
        milestones=[
            {"title": "Build Container", "order_idx": 0},
            {"title": "Push Registry", "order_idx": 1},
        ],
    )
    ms1_id = mission.milestones[0].id
    ms2_id = mission.milestones[1].id

    # Run #1
    exec1 = store.create_execution(mission.id)
    store.update_execution_milestone(
        exec1.id,
        ms1_id,
        status=MilestoneExecutionStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc).isoformat(),
        output="Docker image built: sha256:abc1234",
    )
    store.update_execution_milestone(
        exec1.id,
        ms2_id,
        status=MilestoneExecutionStatus.FAILED,
        error="Connection timed out pushing to registry",
    )
    store.update_execution(exec1.id, status=ExecutionStatus.FAILED, error_message="Deployment failed at step 2")

    # Inspect Run #1 milestones
    em_list1 = store.get_execution_milestones(exec1.id)
    em_map1 = {em.milestone_id: em for em in em_list1}
    assert em_map1[ms1_id].status == MilestoneExecutionStatus.COMPLETED
    assert em_map1[ms2_id].status == MilestoneExecutionStatus.FAILED

    # Run #2 (Re-run)
    exec2 = store.create_execution(mission.id)
    assert exec2.run_number == 2
    assert exec2.id != exec1.id

    # Run #2 milestones must be fresh PENDING
    em_list2 = store.get_execution_milestones(exec2.id)
    em_map2 = {em.milestone_id: em for em in em_list2}
    assert em_map2[ms1_id].status == MilestoneExecutionStatus.PENDING
    assert em_map2[ms2_id].status == MilestoneExecutionStatus.PENDING

    # Run #1 milestones must still be preserved!
    em_list1_again = store.get_execution_milestones(exec1.id)
    em_map1_again = {em.milestone_id: em for em in em_list1_again}
    assert em_map1_again[ms1_id].status == MilestoneExecutionStatus.COMPLETED
    assert em_map1_again[ms2_id].status == MilestoneExecutionStatus.FAILED

    # Template rows in mission_milestones were not corrupted
    with store._get_connection() as conn:
        rows = conn.execute("SELECT status FROM mission_milestones WHERE mission_id = ?", (mission.id,)).fetchall()
        assert all(r["status"] == "pending" for r in rows)


def test_lease_acquisition_and_mutual_exclusion(store: MissionStore) -> None:
    mission = store.create_mission(title="Lease Mission", objective="Test locking")
    exec1 = store.create_execution(mission.id)
    exec2 = store.create_execution(mission.id)

    worker_a = "worker_node_1:pid_100:uuid_aaa"
    worker_b = "worker_node_2:pid_200:uuid_bbb"

    # Worker A acquires lease on exec1
    assert store.acquire_execution_lease(mission.id, exec1.id, worker_a, ttl_seconds=60) is True

    # Check status
    e1 = store.get_execution(exec1.id)
    assert e1 is not None
    assert e1.status == ExecutionStatus.RUNNING
    assert e1.lease_owner == worker_a
    assert e1.lease_expires_at is not None

    # Worker B tries to acquire lease on exec2 for the same mission while A is active -> MUST FAIL
    assert store.acquire_execution_lease(mission.id, exec2.id, worker_b, ttl_seconds=60) is False

    # Worker A renews lease
    assert store.renew_execution_lease(exec1.id, worker_a, ttl_seconds=120) is True

    # Worker A releases lease
    assert store.release_execution_lease(exec1.id, worker_a) is True

    # Now Worker B can acquire lease on exec2
    assert store.acquire_execution_lease(mission.id, exec2.id, worker_b, ttl_seconds=60) is True
    e2 = store.get_execution(exec2.id)
    assert e2 is not None
    assert e2.status == ExecutionStatus.RUNNING
    assert e2.lease_owner == worker_b


def test_deliverable_lineage_across_runs(store: MissionStore) -> None:
    mission = store.create_mission(
        title="Report Generator",
        objective="Create reports",
        milestones=[{"title": "Draft Document"}],
    )
    ms_id = mission.milestones[0].id

    exec1 = store.create_execution(mission.id)
    d1 = Deliverable(
        id="del_1",
        mission_id=mission.id,
        execution_id=exec1.id,
        milestone_id=ms_id,
        name="report_v1.pdf",
        path="/tmp/report_v1.pdf",
        size_bytes=1024,
        sha256="hash111",
        status="verified",
    )
    assert store.add_deliverable(mission.id, d1) is True

    exec2 = store.create_execution(mission.id)
    d2 = Deliverable(
        id="del_2",
        mission_id=mission.id,
        execution_id=exec2.id,
        milestone_id=ms_id,
        name="report_v2.pdf",
        path="/tmp/report_v2.pdf",
        size_bytes=2048,
        sha256="hash222",
        status="verified",
    )
    assert store.add_deliverable(mission.id, d2) is True

    # All deliverables for mission
    all_delivs = store.list_deliverables(mission.id)
    assert len(all_delivs) == 2
    assert {d.id for d in all_delivs} == {"del_1", "del_2"}

    # Scoped to Run #1
    run1_delivs = store.list_deliverables(mission.id, execution_id=exec1.id)
    assert len(run1_delivs) == 1
    assert run1_delivs[0].id == "del_1"
    assert run1_delivs[0].name == "report_v1.pdf"
    assert run1_delivs[0].execution_id == exec1.id

    # Scoped to Run #2
    run2_delivs = store.list_deliverables(mission.id, execution_id=exec2.id)
    assert len(run2_delivs) == 1
    assert run2_delivs[0].id == "del_2"
    assert run2_delivs[0].name == "report_v2.pdf"
    assert run2_delivs[0].execution_id == exec2.id


def test_crash_recovery(store: MissionStore) -> None:
    mission = store.create_mission(
        title="Crash Mission",
        objective="Test crash recovery",
        milestones=[{"title": "Step 1"}, {"title": "Step 2"}],
    )
    ms1_id = mission.milestones[0].id

    # Execution 1: Running when process crashes
    exec1 = store.create_execution(mission.id)
    store.acquire_execution_lease(mission.id, exec1.id, "worker_1", ttl_seconds=60)
    store.update_execution(exec1.id, current_milestone_id=ms1_id)
    store.update_execution_milestone(exec1.id, ms1_id, status=MilestoneExecutionStatus.RUNNING)

    # Execution 2 on another mission: Awaiting approval (should NOT be interrupted by crash recovery)
    mission2 = store.create_mission(title="Approval Mission", objective="Wait for user")
    exec2 = store.create_execution(mission2.id)
    store.update_execution(
        exec2.id,
        status=ExecutionStatus.AWAITING_APPROVAL,
        pending_approval={"prompt": "Please review plan"},
    )

    # Perform crash recovery
    recovered = store.recover_stale_executions()
    assert exec1.id in recovered
    assert exec2.id not in recovered

    # Verify exec1 state
    e1 = store.get_execution(exec1.id)
    assert e1 is not None
    assert e1.status == ExecutionStatus.INTERRUPTED
    assert e1.recovery_state == "recovered_from_crash"
    assert e1.lease_owner is None
    assert e1.lease_expires_at is None

    # Verify milestone state was reset to pending
    em1 = store.get_execution_milestones(exec1.id)
    assert em1[0].status == MilestoneExecutionStatus.PENDING

    # Verify mission 1 status
    m1 = store.get_mission(mission.id)
    assert m1 is not None
    assert m1.status == MissionStatus.INTERRUPTED

    # Verify exec2 (awaiting_approval) was preserved
    e2 = store.get_execution(exec2.id)
    assert e2 is not None
    assert e2.status == ExecutionStatus.AWAITING_APPROVAL
    assert e2.pending_approval == {"prompt": "Please review plan"}
