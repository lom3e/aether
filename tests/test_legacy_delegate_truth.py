"""
Legacy delegate path (no MissionRuntime) + A4 behaviour. The REAL PersonalAgentService, Workspace, stores and task
manager; only the workforce execution itself (Runtime.execute) is simulated. No network, no model, no external agent.
"""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from aether.core.execution import ExecutionResult, ExecutionStatus
from aether.personal.service import MissionCreationError
from aether.workspace.workspace import Workspace
from conftest import make_test_accepted_authority

PROMPT = "Chiedi alla persona più adatta del team di preparare una sintesi per il cliente Rossi"


@pytest.fixture
def stack(tmp_path, monkeypatch):
    monkeypatch.setattr("aether.core.runtime.Runtime.resolve_provider", lambda self: None)   # no implicit model, ever
    ws = Workspace.init(tmp_path / "ws", "Legacy Truth WS")
    svc = ws.personal
    monkeypatch.setattr(svc, "_can_use_mission_runtime", lambda: False)                       # force the legacy branch
    yield ws, svc
    try:
        svc.shutdown()
    except Exception:
        pass
    ws.close()


def fake_execute(monkeypatch, svc, *, success=True, deliverables=None):
    calls = []

    def execute(request, progress_callback=None):
        calls.append(request)
        return ExecutionResult(success=success, status=ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED,
                               output="done" if success else None, error=None if success else "workforce failed",
                               execution_id="exec-fake", deliverables=deliverables or [], metadata={})

    monkeypatch.setattr(svc.runtime, "execute", execute)
    return calls


def delegate(ws, svc):
    _, authority = make_test_accepted_authority(ws, constraints=[f"allow:workforce.delegate,workforce.delegate:{ws.id}"], title="Rossi")
    msg = svc.process_prompt(prompt=PROMPT, workspace_id=ws.id, session_id="s-1", authority=authority)
    mission_id = msg.mission_id or msg.metadata.get("mission_id") or next(
        (st.details.get("mission_id") for st in msg.steps if st.details and st.details.get("mission_id")), None)
    assert mission_id, msg.to_dict()
    t0 = time.time()
    while time.time() - t0 < 30:
        m = ws.missions.get_mission(mission_id)
        if m.status.value in ("completed", "failed", "blocked", "cancelled"):
            time.sleep(0.3)
            return ws.missions.get_mission(mission_id), msg
        time.sleep(0.2)
    raise AssertionError("legacy mission never reached a terminal state")


def write(ws, name, text):
    p = Path(ws.root) / "files"
    p.mkdir(parents=True, exist_ok=True)
    (p / name).write_text(text, encoding="utf-8")
    return str(p / name)


def test_valid_output_is_verified_only_through_the_gate_and_says_how(stack, monkeypatch):
    ws, svc = stack
    path = write(ws, "sintesi.md", "# Sintesi Rossi\n\nIl cliente vuole il report ogni lunedì.\n")
    fake_execute(monkeypatch, svc, deliverables=[{"name": "sintesi.md", "path": path, "type": "document"}])
    mission, _ = delegate(ws, svc)
    assert mission.status.value == "completed"
    d = ws.missions.list_deliverables(mission.id)
    assert len(d) == 1 and d[0].status == "verified"
    assert d[0].metadata["verification_method"] == "deterministic"
    assert d[0].metadata["semantically_verified"] is False          # no model judged the content: said explicitly


def test_empty_file_is_not_verified_and_the_mission_is_not_completed(stack, monkeypatch):
    ws, svc = stack
    path = write(ws, "vuoto.md", "")
    fake_execute(monkeypatch, svc, deliverables=[{"name": "vuoto.md", "path": path, "type": "document"}])
    mission, _ = delegate(ws, svc)
    assert mission.status.value == "blocked"                         # waiting for review, not failed, not completed
    assert "quality gate failed" in mission.metadata["verification_note"].lower()
    assert [d.status for d in ws.missions.list_deliverables(mission.id)] == ["needs_revision"]


def test_file_that_does_not_exist_is_not_verified(stack, monkeypatch):
    ws, svc = stack
    fake_execute(monkeypatch, svc, deliverables=[{"name": "fantasma.md", "path": str(Path(ws.root) / "files" / "fantasma.md"), "type": "document"}])
    mission, _ = delegate(ws, svc)
    assert mission.status.value == "blocked"
    assert all(d.status != "verified" for d in ws.missions.list_deliverables(mission.id))


def test_broken_python_output_is_not_verified(stack, monkeypatch):
    ws, svc = stack
    path = write(ws, "tool.py", "def broken(:\n")
    fake_execute(monkeypatch, svc, deliverables=[{"name": "tool.py", "path": path, "type": "code"}])
    mission, _ = delegate(ws, svc)
    assert mission.status.value == "blocked"
    assert all(d.status == "needs_revision" for d in ws.missions.list_deliverables(mission.id))


def test_success_without_any_deliverable_is_not_completed(stack, monkeypatch):
    ws, svc = stack
    fake_execute(monkeypatch, svc, deliverables=[])
    mission, _ = delegate(ws, svc)
    assert mission.status.value == "blocked" and not ws.missions.list_deliverables(mission.id)


def test_failed_run_fails_the_mission_and_verifies_nothing(stack, monkeypatch):
    ws, svc = stack
    path = write(ws, "parziale.md", "# bozza\n")
    fake_execute(monkeypatch, svc, success=False, deliverables=[{"name": "parziale.md", "path": path, "type": "document"}])
    mission, _ = delegate(ws, svc)
    assert mission.status.value == "failed"
    assert [d.status for d in ws.missions.list_deliverables(mission.id)] == ["draft"]


# --- A4 behavioural: creation is attempted, fails explicitly, nothing else starts -----------------------------------

def _authority(ws):
    return make_test_accepted_authority(ws, constraints=[f"allow:workforce.delegate,workforce.delegate:{ws.id}"], title="Rossi")[1]


def test_mission_creation_failure_is_explicit_and_starts_nothing(stack, monkeypatch):
    ws, svc = stack
    runtime_calls = fake_execute(monkeypatch, svc, deliverables=[])
    created = []

    def failing_create(*a, **k):
        created.append(k.get("title"))
        raise RuntimeError("disk full")

    monkeypatch.setattr(svc.mission_store, "create_mission", failing_create)
    submitted = []
    monkeypatch.setattr(svc.task_manager, "submit_task", lambda **k: submitted.append(k))
    before = len(ws.missions.list_missions(workspace_id=ws.id))

    with pytest.raises(MissionCreationError, match="disk full"):
        svc.process_prompt(prompt=PROMPT, workspace_id=ws.id, session_id="s-1", authority=_authority(ws))

    assert len(created) == 1                                           # the creation really was attempted
    assert submitted == [] and runtime_calls == []                      # no task, no workforce run
    assert len(ws.missions.list_missions(workspace_id=ws.id)) == before  # no half-recorded mission


def test_missing_mission_store_is_explicit_and_starts_nothing(stack, monkeypatch):
    ws, svc = stack
    runtime_calls = fake_execute(monkeypatch, svc, deliverables=[])
    monkeypatch.setattr(svc, "mission_store", None)
    submitted = []
    monkeypatch.setattr(svc.task_manager, "submit_task", lambda **k: submitted.append(k))
    with pytest.raises(MissionCreationError, match="No mission store"):
        svc.process_prompt(prompt=PROMPT, workspace_id=ws.id, session_id="s-1", authority=_authority(ws))
    assert submitted == [] and runtime_calls == []


@pytest.mark.asyncio
async def test_http_boundary_returns_an_honest_error_not_a_generic_500(stack, monkeypatch):
    from fastapi import HTTPException, Request
    from aether.server.app import app
    from aether.server.routes import PersonalChatPayload, personal_chat_route

    ws, svc = stack
    monkeypatch.setattr(svc, "mission_store", None)
    app.state.workspace = ws
    req = Request({"type": "http", "method": "POST", "path": "/api/personal/chat", "headers": [], "app": app})
    with pytest.raises(HTTPException) as exc:
        await personal_chat_route(req, PersonalChatPayload(prompt=PROMPT, workspace_id=ws.id, authority=_authority(ws).to_dict()))
    assert exc.value.status_code == 500 and "Delegation not started" in exc.value.detail and "No mission store" in exc.value.detail
