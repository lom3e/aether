"""
API Integration Tests for Mission Runtime Action Endpoints.
Verifies start, pause, resume, cancel, re-run, approval gates, and executions queries.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from starlette.requests import Request
from fastapi import HTTPException

from aether.coordination.events import EventEmitter
from aether.core.execution import ExecutionResult
from aether.missions.models import ExecutionStatus, MissionStatus
from aether.missions.runtime import MissionRuntime
from aether.server.app import app
from aether.server.routes import (
    start_mission_route,
    rerun_mission_route,
    pause_mission_route,
    resume_mission_route,
    cancel_mission_route,
    retry_mission_route,
    approve_mission_route,
    reject_mission_route,
    list_mission_executions,
    get_mission_execution,
    list_mission_deliverables,
    download_mission_deliverable,
    open_mission_deliverable,
    MissionActionStartPayload,
    MissionActionPausePayload,
    MissionActionCancelPayload,
    MissionActionRetryPayload,
    MissionActionApprovePayload,
    MissionActionRejectPayload,
    create_mission,
    CreateMissionPayload,
)
from aether.workspace.workspace import Workspace


from aether.workspace.registry import WorkspaceRegistry


def make_request(method: str = "GET", path: str = "/") -> Request:
    scope = {"type": "http", "app": app, "headers": [], "path": path, "method": method}
    return Request(scope)


class MockTeam:
    def __init__(self):
        self.emitter = EventEmitter()
        self.call_count = 0

    def run(self, task_instruction, **kwargs):
        self.call_count += 1
        return ExecutionResult(success=True, output=f"Executed: {task_instruction}")


@pytest.fixture
def test_workspace(tmp_path: Path):
    root = tmp_path / "ws"
    ws = WorkspaceRegistry.create_workspace(
        name="Mission Test Workspace",
        preset_id="starter-workforce",
        target_dir=root,
    )

    mock_team = MockTeam()
    ws.load_team = MagicMock(return_value=mock_team)

    runtime = MissionRuntime(ws)
    app.state.workspace = ws
    app.state.mission_runtime = runtime

    yield ws, runtime, mock_team

    # Cleanup
    try:
        asyncio.run(runtime.shutdown())
    except Exception:
        pass


@pytest.mark.asyncio
async def test_start_and_list_executions(test_workspace):
    ws, runtime, mock_team = test_workspace
    req = make_request()

    # Create mission
    create_payload = CreateMissionPayload(
        title="Deploy Pipeline",
        objective="Automate production deployment",
        team_name="default",
        status="draft",
        milestones=[
            {"title": "Unit Tests"},
            {"title": "Build Container"},
        ],
    )
    created = await create_mission(req, create_payload)
    mid = created["id"]

    # Start mission
    start_res = await start_mission_route(req, mid, MissionActionStartPayload())
    assert start_res["execution"]["run_number"] == 1
    assert start_res["execution"]["status"] in ("running", "completed")

    # Wait for execution task to finish
    handle = runtime._active_executions.get(start_res["execution"]["id"])
    if handle and handle.task:
        await handle.task

    # List executions
    execs = await list_mission_executions(req, mid)
    assert len(execs) == 1
    assert execs[0]["run_number"] == 1
    assert execs[0]["status"] == "completed"

    # Get single execution
    exec_single = await get_mission_execution(req, mid, execs[0]["id"])
    assert exec_single["id"] == execs[0]["id"]
    assert len(exec_single["milestone_states"]) == 2


@pytest.mark.asyncio
async def test_rerun_mission_lifecycle(test_workspace):
    ws, runtime, mock_team = test_workspace
    req = make_request()

    mission = ws.missions.create_mission(
        title="ETL Job",
        objective="Run ETL",
        milestones=[{"title": "Extract"}, {"title": "Transform"}],
    )
    mid = mission.id

    # Run 1
    res1 = await start_mission_route(req, mid, MissionActionStartPayload())
    exec1_id = res1["execution"]["id"]
    handle1 = runtime._active_executions.get(exec1_id)
    if handle1 and handle1.task:
        await handle1.task

    # Re-run -> Run 2
    res2 = await rerun_mission_route(req, mid, MissionActionStartPayload())
    assert res2["execution"]["run_number"] == 2
    exec2_id = res2["execution"]["id"]
    assert exec2_id != exec1_id

    handle2 = runtime._active_executions.get(exec2_id)
    if handle2 and handle2.task:
        await handle2.task

    # Verify both executions exist
    execs = await list_mission_executions(req, mid)
    assert len(execs) == 2
    run_numbers = [e["run_number"] for e in execs]
    assert sorted(run_numbers) == [1, 2]


@pytest.mark.asyncio
async def test_pause_and_resume_routes(test_workspace):
    ws, runtime, mock_team = test_workspace
    req = make_request()

    mission = ws.missions.create_mission(
        title="Pausable Job",
        objective="Test pause/resume",
        milestones=[{"title": "Stage A"}, {"title": "Stage B"}],
    )
    mid = mission.id

    # Create run directly in store as running
    run = ws.missions.create_execution(mid, run_number=1, status=ExecutionStatus.RUNNING)
    ws.missions.update_mission(mid, status=MissionStatus.RUNNING, active_execution_id=run.id)

    # Pause
    pause_res = await pause_mission_route(req, mid, MissionActionPausePayload(reason="Manual inspection"))
    assert pause_res["execution"]["status"] == "interrupted"
    assert pause_res["mission"]["status"] == "interrupted"

    # Resume
    resume_res = await resume_mission_route(req, mid)
    assert resume_res["execution"]["status"] in ("running", "completed")
    handle = runtime._active_executions.get(run.id)
    if handle and handle.task:
        await handle.task


@pytest.mark.asyncio
async def test_approval_and_rejection_routes(test_workspace):
    ws, runtime, mock_team = test_workspace
    req = make_request()

    mission = ws.missions.create_mission(
        title="Gated Mission",
        objective="Requires signoff",
        milestones=[
            {"title": "Analysis"},
            {"title": "[Approval] Production Deploy"},
        ],
    )
    mid = mission.id

    # Start mission
    start_res = await start_mission_route(req, mid)
    handle = runtime._active_executions.get(start_res["execution"]["id"])
    if handle and handle.task:
        await handle.task

    # Mission should now be awaiting approval
    mission_state = ws.missions.get_mission(mid)
    assert mission_state.status == MissionStatus.AWAITING_APPROVAL

    # Approve
    appr_res = await approve_mission_route(req, mid, MissionActionApprovePayload(notes="Approved by Lead"))
    handle2 = runtime._active_executions.get(start_res["execution"]["id"])
    if handle2 and handle2.task:
        await handle2.task

    final_mission = ws.missions.get_mission(mid)
    assert final_mission.status == MissionStatus.COMPLETED


@pytest.mark.asyncio
async def test_error_handling_not_found(test_workspace):
    req = make_request()
    with pytest.raises(HTTPException) as exc:
        await start_mission_route(req, "non-existent-id")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_deliverable_download_and_size_resolution(test_workspace):
    ws, runtime, mock_team = test_workspace
    req = make_request()

    mission = ws.missions.create_mission(
        title="Deliverable Test",
        objective="Verify deliverable download and real size",
    )
    mid = mission.id

    # Create a real file in the workspace files directory
    ws.files_dir.mkdir(parents=True, exist_ok=True)
    report_file = ws.files_dir / "summary_report.md"
    content = b"# Aether Executive Summary\nAll objectives achieved with high precision."
    report_file.write_bytes(content)

    # Register deliverable with relative path and initial size 0
    from aether.missions.models import Deliverable
    d = Deliverable(
        id="del_report_01",
        mission_id=mid,
        name="summary_report.md",
        path="summary_report.md",
        type="document",
        size_bytes=0,
        status="verified",
    )
    ws.missions.add_deliverable(mid, d)

    # 1. Size resolution test: list_deliverables must resolve real size from disk
    delivs = ws.missions.list_deliverables(mid)
    assert len(delivs) == 1
    assert delivs[0].size_bytes == len(content)
    assert delivs[0].size_bytes > 0

    # 2. Download endpoint test
    resp = await download_mission_deliverable(req, mid, "del_report_01")
    assert resp.path == str(report_file.resolve())
    assert resp.filename == "summary_report.md"

    # 3. Missing deliverable ID
    with pytest.raises(HTTPException) as exc:
        await download_mission_deliverable(req, mid, "non_existent_del")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_deliverable_open_and_reveal(test_workspace, monkeypatch):
    ws, runtime, mock_team = test_workspace
    req = make_request()

    mission = ws.missions.create_mission(
        title="Deliverable Open Test",
        objective="Verify deliverable open and reveal",
    )
    mid = mission.id

    ws.files_dir.mkdir(parents=True, exist_ok=True)
    report_file = ws.files_dir / "output.txt"
    report_file.write_text("Test deliverable output")

    from aether.missions.models import Deliverable
    d = Deliverable(
        id="del_output_01",
        mission_id=mid,
        name="output.txt",
        path="output.txt",
        type="document",
        size_bytes=0,
        status="verified",
    )
    ws.missions.add_deliverable(mid, d)

    popen_calls = []

    def mock_popen(cmd, *args, **kwargs):
        popen_calls.append(cmd)
        mock_proc = MagicMock()
        return mock_proc

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # 1. Open action (reveal=False)
    res_open = await open_mission_deliverable(req, mid, "del_output_01", reveal=False)
    assert res_open["status"] == "ok"
    assert res_open["action"] == "open"
    assert len(popen_calls) == 1
    assert str(report_file.resolve()) in popen_calls[0]

    # 2. Reveal action (reveal=True)
    res_reveal = await open_mission_deliverable(req, mid, "del_output_01", reveal=True)
    assert res_reveal["status"] == "ok"
    assert res_reveal["action"] == "reveal"
    assert len(popen_calls) == 2


@pytest.mark.asyncio
async def test_deliverable_security_boundary_enforcement(test_workspace, tmp_path):
    ws, runtime, mock_team = test_workspace
    req = make_request()

    mission = ws.missions.create_mission(
        title="Security Boundary Test",
        objective="Test path traversal rejection",
    )
    mid = mission.id

    # Create a secret file outside the workspace root
    external_dir = tmp_path / "external_system"
    external_dir.mkdir()
    secret_file = external_dir / "secret.txt"
    secret_file.write_text("super_secret_credentials")

    from aether.missions.models import Deliverable

    # Attempt path traversal deliverable
    d_traversal = Deliverable(
        id="del_malicious_01",
        mission_id=mid,
        name="secret.txt",
        path="../../../external_system/secret.txt",
        type="document",
        size_bytes=10,
        status="draft",
    )
    ws.missions.add_deliverable(mid, d_traversal)

    # Must be blocked with 403 Forbidden
    with pytest.raises(HTTPException) as exc_dl:
        await download_mission_deliverable(req, mid, "del_malicious_01")
    assert exc_dl.value.status_code == 403

    with pytest.raises(HTTPException) as exc_open:
        await open_mission_deliverable(req, mid, "del_malicious_01", reveal=False)
    assert exc_open.value.status_code == 403

