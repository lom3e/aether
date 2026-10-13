"""
Shared coding runtime (base provider): evidence, renames, one-shot CLI runner, events, restore.
The 'agent' is a tiny shell script written by the test into a temp dir: real child processes,
no real coding agent, no network.
"""
from __future__ import annotations

import json
import os
import stat
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fake_agent_script import write_agent_script

from aether.coding.evidence import compare, snapshot_from_blob, snapshot_to_blob, take_snapshot
from aether.coding.models import CodingExecutionStatus as S, CodingTask
from aether.coding.providers.claude_code import ClaudeCodeCodingProvider
from aether.coding.providers.codex import CodexCodingProvider


def make_agent(tmp_path: Path, body: str) -> str:
    return write_agent_script(tmp_path, "fake_agent", body)


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    (p / "dirty.py").write_text("dirty before\n", encoding="utf-8")
    (p / "old_name.py").write_text("print('x')\n", encoding="utf-8")
    return p


def provider_with(cls, binary):
    prov = cls()
    return prov, patch.object(prov, "is_available", return_value=(True, "ok")), patch.object(prov, "resolve_binary", return_value=binary)


def run(cls, binary, project, instruction="Aggiungi un file", timeout=10, **task_kw):
    prov, a, b = provider_with(cls, binary)
    events = []
    prov.add_run_listener(lambda ev, ex, data: events.append(ev))
    with a, b:
        ex = prov.start_task(CodingTask(instruction=instruction, project_path=str(project), timeout_seconds=timeout,
                                        workspace_id="ws-1", mission_id="m-1", proposal_id="p-1", **task_kw))
    return prov, ex, events


def test_snapshot_detects_modified_added_deleted_and_renamed(project):
    before = take_snapshot(project)
    (project / "old_name.py").rename(project / "new_name.py")
    (project / "created.py").write_text("n = 1\n", encoding="utf-8")
    (project / "dirty.py").write_text("dirty after\n", encoding="utf-8")
    ch = compare(before, take_snapshot(project))
    assert ch.renamed == [("old_name.py", "new_name.py")]
    assert ch.added == ["created.py"] and ch.modified == ["dirty.py"] and ch.deleted == []
    assert "rename from old_name.py" in ch.diff and "+n = 1" in ch.diff
    assert sorted(ch.changed_files) == ["created.py", "dirty.py", "new_name.py"]


def test_snapshot_blob_roundtrip_survives_a_restart(project):
    snap = take_snapshot(project)
    again = snapshot_from_blob(snapshot_to_blob(snap))
    assert again.hashes == snap.hashes and again.texts == snap.texts


@pytest.mark.parametrize("cls", [ClaudeCodeCodingProvider, CodexCodingProvider])
def test_cli_agent_success_shares_evidence_identity_and_events(tmp_path, project, cls):
    agent = make_agent(tmp_path, 'echo \'{"result": "I added feature.py"}\'\necho "x = 1" > feature.py')
    prov, ex, events = run(cls, agent, project)
    assert ex.status == S.COMPLETED and ex.id in prov._executions
    r = ex.result
    assert r.success and r.modified_files == ["feature.py"] and "dirty.py" not in r.modified_files
    assert r.metadata["workspace_id"] == "ws-1" and r.metadata["mission_id"] == "m-1"
    assert r.metadata["provider_id"] == prov.id
    assert events == ["run_started", "run_completed"]
    assert r.test_passed is None  # nothing was executed to verify anything


def test_cli_agent_failure_is_failed_with_stderr(tmp_path, project):
    agent = make_agent(tmp_path, 'echo "bad auth" >&2\nexit 3')
    _, ex, events = run(ClaudeCodeCodingProvider, agent, project)
    assert ex.status == S.FAILED and "bad auth" in ex.error and ex.result.success is False
    assert events[-1] == "run_failed"


def test_cli_agent_timeout_kills_the_process_and_says_so(tmp_path, project):
    agent = make_agent(tmp_path, "echo partial > partial.txt\nexec sleep 30")
    t0 = time.time()
    _, ex, _ = run(CodexCodingProvider, agent, project, timeout=1)
    assert time.time() - t0 < 10
    assert ex.status == S.TIMED_OUT
    assert ex.metadata["remote_cancelled"] is True and ex.metadata["remote_status"] == "process_killed_on_timeout"
    assert ex.result.modified_files == ["partial.txt"]


def test_cli_agent_cancel_terminates_the_real_process(tmp_path, project):
    agent = make_agent(tmp_path, "exec sleep 30")
    prov, a, b = provider_with(ClaudeCodeCodingProvider, agent)
    holder = {}

    def go():
        with a, b:
            holder["ex"] = prov.start_task(CodingTask(instruction="x", project_path=str(project), timeout_seconds=60))

    th = threading.Thread(target=go)
    th.start()
    deadline = time.time() + 5
    while not prov._executions and time.time() < deadline:
        time.sleep(0.02)
    time.sleep(0.3)
    eid = next(iter(prov._executions))
    assert prov.cancel_task(eid) is True
    th.join(timeout=10)
    assert not th.is_alive()
    ex = holder["ex"]
    assert ex.status == S.CANCELLED and ex.metadata["remote_cancelled"] is True
    assert ex.metadata["remote_status"] == "process_terminated"


def test_restore_execution_reattaches_state_and_baseline(tmp_path, project):
    agent = make_agent(tmp_path, "echo hi > created.py")
    prov, ex, _ = run(ClaudeCodeCodingProvider, agent, project)
    baseline_blob = snapshot_to_blob(prov.baseline_for(ex.id))

    fresh = ClaudeCodeCodingProvider()  # "server restart"
    from aether.coding.models import CodingTaskExecution
    restored = CodingTaskExecution.from_dict(ex.to_dict())
    fresh.restore_execution(restored, snapshot_from_blob(baseline_blob))
    res = fresh.collect_results(ex.id)
    assert res.modified_files == ["created.py"] and res.success is True
    assert fresh.get_status(ex.id).status == S.COMPLETED


def test_listener_errors_never_break_a_run(tmp_path, project):
    agent = make_agent(tmp_path, "true")
    prov, a, b = provider_with(CodexCodingProvider, agent)
    prov.add_run_listener(lambda *a, **k: 1 / 0)
    with a, b:
        ex = prov.start_task(CodingTask(instruction="Analizza", project_path=str(project), timeout_seconds=5))
    assert ex.status == S.COMPLETED
