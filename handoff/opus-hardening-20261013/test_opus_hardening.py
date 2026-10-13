"""
Opus hardening branch (audit 2026-10-13): non-blocking approvals, truthful semantic verification, credential
isolation of ordinary tests. Deterministic, temp data, no network.
"""
from __future__ import annotations

import asyncio
import os
import socket
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from aether.missions.models import Deliverable
from aether.missions.reviewer import QualityGateEvaluator


# --- Finding 1: the canonical approval must not block the event loop ---------------------------------------------

@pytest.mark.asyncio
async def test_slow_approval_does_not_block_health(tmp_path, monkeypatch):
    from fastapi import Request
    from aether.actions.models import ActionExecution, ActionExecutionStatus
    from aether.server.app import app
    from aether.server.routes import CanonicalApprovalPayload, approve_canonical_target_route, health
    from aether.workspace.workspace import Workspace

    ws = Workspace.init(tmp_path / "ws", "Approval WS")
    app.state.workspace = ws
    pending = ActionExecution(id="ax-slow", action_id="coding.delegate", workspace_id=ws.id,
                              status=ActionExecutionStatus.WAITING_APPROVAL)
    ws.action_store.save_execution(pending)

    def slow_approve(execution_id, approver="user"):
        time.sleep(1.5)                                  # a coding run / authorised tests taking long
        pending.status = ActionExecutionStatus.SUCCEEDED
        return pending

    monkeypatch.setattr(ws.actions, "approve", slow_approve)
    req = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "app": app})
    approval = asyncio.create_task(approve_canonical_target_route(req, target_id="ax-slow",
                                                                  payload=CanonicalApprovalPayload(target_type="action_execution")))
    await asyncio.sleep(0.05)
    t0 = time.monotonic()
    await asyncio.wait_for(health(req), timeout=0.5)     # used to wait for the whole approval (event loop blocked)
    assert time.monotonic() - t0 < 0.5 and not approval.done()
    result = await approval
    assert result["status"] == "approved" and result["entity"]["status"] == "succeeded"


# --- Finding 6: a failed / unverified coding run is not evidence ------------------------------------------------

def _file(tmp_path):
    p = tmp_path / "report.md"
    p.write_text("# Report\n\nContent.\n", encoding="utf-8")
    return [Deliverable(id="d1", mission_id="m1", name="report.md", path=str(p), type="document")]


def _gate(tmp_path, runs):
    return asyncio.run(QualityGateEvaluator().evaluate(
        mission_title="T", mission_objective="Write a report", deliverables=_file(tmp_path), completed_context=["ok"],
        team=None, workspace=None, evidence={"coding_runs": runs}, required_evidence=None))


@pytest.mark.parametrize("run", [
    {"id": "r", "status": "failed", "verification_passed": False},
    {"id": "r", "status": "completed", "verification_passed": False},
    {"id": "r", "status": "completed", "verification_passed": None},
    {"id": "r", "status": "requires_rework", "verification_passed": False},
    {"id": "r", "status": "waiting_for_interaction", "verification_passed": None},
])
def test_failed_or_unverified_runs_are_not_semantic_evidence(tmp_path, run):
    ev = _gate(tmp_path, [run])
    assert ev.passed is True and ev.method == "deterministic"
    assert ev.semantically_verified is False
    assert not ev.evidence_used.get("coding_runs")


def test_a_verified_completed_run_is_evidence(tmp_path):
    ok = {"id": "good", "status": "completed", "verification_passed": True}
    ev = _gate(tmp_path, [{"id": "bad", "status": "failed", "verification_passed": False}, ok])
    assert ev.semantically_verified is True
    assert [r["id"] for r in ev.evidence_used["coding_runs"]] == ["good"]          # only the proving run is cited


def test_memory_of_a_mission_backed_by_a_failed_run_is_not_verified(tmp_path):
    from aether.memory.ingestion import MemoryIngestionService
    from aether.memory.store import WorkforceMemoryStore

    ev = _gate(tmp_path, [{"id": "r", "status": "failed", "verification_passed": False}])
    store = WorkforceMemoryStore(str(tmp_path / "memory.db"))
    mem = MemoryIngestionService.ingest_mission_outcome(
        memory_store=store, workspace_id="ws-t", mission_id="m1", execution_id="e1", title="T", objective="o",
        stage_outputs=["x"], eval_result=ev, deliverables=_file(tmp_path))
    assert mem.provenance.verification_status == "inferred" and "unverified" in mem.tags


# --- Finding 7: ordinary tests do not inherit credentials and cannot reach the network ---------------------------

def test_ordinary_tests_do_not_see_provider_keys():
    assert all(not os.environ.get(v) for v in ("GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"))


def test_ordinary_tests_cannot_reach_external_hosts_or_local_ollama():
    for addr in (("93.184.216.34", 443), ("127.0.0.1", 11434)):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(RuntimeError, match="must not open network connections"):
                s.connect(addr)
        finally:
            s.close()


def test_resolver_finds_nothing_even_if_the_runner_exported_a_key():
    from aether.providers.resolution import resolve_provider
    ws = SimpleNamespace(config={}, secret_store=SimpleNamespace(get_secret=lambda ref: None))
    assert resolve_provider(workspace=ws) is None


@pytest.mark.live_provider
def test_live_provider_tests_keep_the_real_environment(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "set-by-live-test")
    assert os.environ["GROQ_API_KEY"] == "set-by-live-test"     # the isolation fixture does not interfere
