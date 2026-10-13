"""
Phase 1 lifecycle tests for the Antigravity provider.

Fully isolated: the agentapi subprocess is replaced by a fake, ``Path.home`` points at a temp dir,
and projects live in ``tmp_path``. Nothing here launches a real agent or runs project code.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from aether.coding.models import CodingExecutionStatus as S, CodingTask
from aether.coding.providers.antigravity import AntigravityCodingProvider

CONV = "conv-0001-aaaa"


class FakeAgentApi:
    """Stands in for ``subprocess.run`` of the agentapi CLI and records every command."""

    def __init__(self, home: Path, provider: AntigravityCodingProvider, project: Path | None = None):
        self.home = home
        self.provider = provider
        self.project = project
        self.calls: list[list[str]] = []
        self.registered_at_dispatch: bool | None = None
        self.on_new_conversation = None  # callable(project) simulating the agent's file edits
        self.new_conv_stdout = json.dumps({"response": {"newConversation": {"conversationId": CONV}}})
        self.new_conv_rc = 0

    def transcript(self, conv: str = CONV) -> Path:
        return self.home / ".gemini/antigravity/brain" / conv / ".system_generated/logs/transcript.jsonl"

    def write_entries(self, *entries: dict, conv: str = CONV, append: bool = False) -> None:
        tf = self.transcript(conv)
        tf.parent.mkdir(parents=True, exist_ok=True)
        with open(tf, "a" if append else "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def __call__(self, cmd, **kwargs):
        self.calls.append([str(c) for c in cmd])
        verb = next((c for c in cmd if c in ("new-conversation", "send-message")), None)
        if verb == "new-conversation":
            self.registered_at_dispatch = bool(self.provider._executions)
            if self.on_new_conversation and self.project:
                self.on_new_conversation(self.project)
            return subprocess.CompletedProcess(cmd, self.new_conv_rc, stdout=self.new_conv_stdout, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    def commands(self) -> list[str]:
        return [c[1] if len(c) > 1 else c[0] for c in self.calls]


def user_input(content="task"):
    return {"type": "USER_INPUT", "source": "USER_EXPLICIT", "status": "DONE", "content": content}


def planner(content="done", status="DONE", tool_calls=None):
    return {"type": "PLANNER_RESPONSE", "source": "MODEL", "status": status, "content": content, "tool_calls": tool_calls or []}


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    (other_cwd / "SENTINEL_NOT_THE_PROJECT.txt").write_text("x", encoding="utf-8")
    monkeypatch.chdir(other_cwd)
    provider = AntigravityCodingProvider()
    provider.POLL_INTERVAL = 0.02
    fake = FakeAgentApi(home, provider, project)
    with patch("pathlib.Path.home", return_value=home), \
         patch.object(provider, "is_available", return_value=(True, "ready")), \
         patch.object(provider, "resolve_binary", return_value="/fake/agentapi"), \
         patch("subprocess.run", side_effect=fake):
        yield provider, fake, project, other_cwd


def task_for(project: Path, instruction="Add a feature", timeout=5, **kw) -> CodingTask:
    return CodingTask(instruction=instruction, project_path=str(project), timeout_seconds=timeout, **kw)


# 1. Happy path ---------------------------------------------------------------

def test_happy_path_registers_runs_and_reports_project_evidence(env):
    provider, fake, project, other_cwd = env
    (project / "preexisting.py").write_text("dirty before\n", encoding="utf-8")
    (project / "tests").mkdir()
    (project / "tests" / "test_app.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")

    def agent_edits(p: Path):
        (p / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    fake.on_new_conversation = agent_edits
    fake.write_entries(user_input(), planner("Implemented add()."))
    task = task_for(project, "Aggiungi la funzione `add` in app.py")

    execution = provider.start_task(task)

    assert fake.registered_at_dispatch is True, "execution must be registered before dispatch/polling"
    assert provider._executions[execution.id] is execution
    assert execution.status == S.COMPLETED
    assert execution.external_task_id == CONV
    result = execution.result
    assert result.success is True and result.status == S.COMPLETED
    assert result.metadata["project_path"] == str(project.resolve())
    assert result.modified_files == ["app.py"]
    assert "+def add(a, b):" in result.diff
    assert "preexisting.py" not in result.modified_files
    assert "SENTINEL_NOT_THE_PROJECT.txt" not in result.modified_files + [result.diff]
    assert result.verification_passed is True
    # 8. no implicit execution of agent-produced code: only agentapi was ever invoked
    assert set(fake.commands()) <= {"new-conversation", "send-message"}
    assert not any("pytest" in " ".join(c) for c in fake.calls)
    assert result.test_passed is None and "not executed" in result.test_output


def test_collect_results_never_falls_back_to_process_cwd(env):
    provider, fake, project, other_cwd = env
    res = provider.collect_results("exec-unknown")
    assert res.success is False and res.status == S.FAILED
    assert str(other_cwd) not in json.dumps(res.to_dict())


# 2. Failure modes ------------------------------------------------------------

def test_missing_conversation_id_is_failed_not_completed(env):
    provider, fake, project, _ = env
    fake.new_conv_stdout = "started"
    ex = provider.start_task(task_for(project))
    assert ex.status == S.FAILED
    assert "conversation identifier" in ex.error
    assert ex.result.success is False
    assert ex.id in provider._executions


def test_nonzero_exit_is_failed(env):
    provider, fake, project, _ = env
    fake.new_conv_rc = 3
    assert provider.start_task(task_for(project)).status == S.FAILED


def test_transcript_error_status_is_failed(env):
    provider, fake, project, _ = env
    fake.write_entries(user_input(), planner("boom", status="ERROR"))
    ex = provider.start_task(task_for(project))
    assert ex.status == S.FAILED and "boom" in ex.error and ex.result.success is False


def test_running_status_is_never_reported_completed(env):
    provider, fake, project, _ = env
    fake.write_entries(user_input(), planner("Reading files...", status="RUNNING"))
    ex = provider.start_task(task_for(project, timeout=1))
    assert ex.status == S.TIMED_OUT
    assert ex.result.success is False


def test_stale_response_from_previous_turn_is_not_reused(env):
    provider, fake, project, _ = env
    fake.write_entries(user_input(), planner("first turn answer"))
    ex = provider.start_task(task_for(project, "Analizza il progetto", timeout=2))
    assert ex.status == S.COMPLETED
    ex.status = S.WAITING_FOR_INTERACTION  # agent paused; user now replies
    out = provider.send_message(ex.id, "continua")  # no new transcript entries are ever written
    assert out.status == S.TIMED_OUT, "the old PLANNER_RESPONSE must not satisfy the new turn"


# 3. Timeout and cancellation -------------------------------------------------

def test_timeout_reports_remote_session_not_stopped_and_keeps_partial_evidence(env):
    provider, fake, project, _ = env

    def agent_edits(p: Path):
        (p / "partial.py").write_text("x = 1\n", encoding="utf-8")

    fake.on_new_conversation = agent_edits
    fake.write_entries(user_input(), planner("working", status="IN_PROGRESS"))
    ex = provider.start_task(task_for(project, timeout=1))
    assert ex.status == S.TIMED_OUT
    assert ex.metadata["remote_cancelled"] is False
    assert ex.metadata["remote_status"] == "remote_session_not_stopped"
    assert ex.metadata["remote_session_may_continue"] is True
    assert ex.result.modified_files == ["partial.py"]
    assert ex.result.success is False and ex.result.status == S.TIMED_OUT


def test_cancel_during_wait_is_local_only_and_says_so(env):
    provider, fake, project, _ = env
    fake.write_entries(user_input(), planner("working", status="RUNNING"))
    holder = {}

    def run():
        holder["ex"] = provider.start_task(task_for(project, timeout=30))

    t = threading.Thread(target=run)
    t0 = time.time()
    t.start()
    deadline = time.time() + 5
    while not provider._executions and time.time() < deadline:
        time.sleep(0.01)
    exec_id = next(iter(provider._executions))
    time.sleep(0.2)
    assert provider.cancel_task(exec_id) is True
    t.join(timeout=5)
    assert not t.is_alive() and time.time() - t0 < 10, "cancel must stop the polling promptly"
    ex = holder["ex"]
    assert ex.status == S.CANCELLED
    assert ex.metadata["local_cancelled"] is True
    assert ex.metadata["remote_cancelled"] is False
    assert ex.metadata["remote_status"] == "remote_cancel_unsupported"
    assert ex.metadata["remote_session_may_continue"] is True
    assert provider.cancel_task(exec_id) is False  # already terminal


# 4. Pre-existing vs new files ------------------------------------------------

def test_preexisting_edits_untracked_and_deleted_files_are_attributed_correctly(env):
    provider, fake, project, _ = env
    (project / "dirty_before.py").write_text("v1\n", encoding="utf-8")
    (project / "touched.py").write_text("old\n", encoding="utf-8")
    (project / "gone.py").write_text("bye\n", encoding="utf-8")

    def agent_edits(p: Path):
        (p / "touched.py").write_text("new\n", encoding="utf-8")
        (p / "brand_new.py").write_text("n = 1\n", encoding="utf-8")
        (p / "gone.py").unlink()

    fake.on_new_conversation = agent_edits
    fake.write_entries(user_input(), planner("ok"))
    ex = provider.start_task(task_for(project, "Modifica touched.py"))
    r = ex.result
    assert r.modified_files == ["brand_new.py", "gone.py", "touched.py"]
    assert r.metadata["added_files"] == ["brand_new.py"]
    assert r.metadata["deleted_files"] == ["gone.py"]
    assert "dirty_before.py" not in r.modified_files


def test_code_change_task_without_changes_requires_verification_failure(env):
    provider, fake, project, _ = env
    fake.write_entries(user_input(), planner("I did it, trust me"))
    ex = provider.start_task(task_for(project, "Aggiungi una funzione somma a calc.py"))
    assert ex.result.success is False
    assert ex.status in (S.FAILED, S.REQUIRES_REWORK)


def test_analysis_task_wrapped_in_mandate_is_not_treated_as_code_change(env):
    provider, fake, project, _ = env
    fake.write_entries(user_input(), planner("Architettura riassunta."))
    from aether.personal.service import generate_executive_mandate
    ex = provider.start_task(task_for(project, generate_executive_mandate("Analizza il progetto e riassumi l'architettura")))
    assert ex.status == S.COMPLETED and ex.result.success is True


# 5. Follow-ups and permission waits ------------------------------------------

def test_permission_request_pauses_run_and_sends_no_followup(env):
    provider, fake, project, _ = env
    fake.write_entries(
        user_input(),
        {"type": "GENERIC", "source": "SYSTEM", "content": "", "tool_calls": []},
        {"type": "GENERIC", "source": "MODEL", "content": "needs access", "tool_calls": [{"name": "request_permission"}]},
    )
    ex = provider.start_task(task_for(project))
    assert ex.status == S.WAITING_FOR_INTERACTION
    assert ex.result.success is False
    assert fake.commands().count("send-message") == 0


def test_automatic_finalization_nudge_is_sent_at_most_once_and_never_while_waiting(env):
    provider, fake, project, _ = env
    entries = [{"type": "GENERIC", "content": "tool out", "tool_calls": []}] * 2
    provider._maybe_request_finalization(CONV, project, "exec-a", entries, entries[-1], idle_seconds=60, budget=10)
    provider._maybe_request_finalization(CONV, project, "exec-a", entries, entries[-1], idle_seconds=60, budget=10)
    assert fake.commands().count("send-message") == 1

    waiting = entries + [{"type": "GENERIC", "content": "", "tool_calls": [{"name": "ask_user"}]}]
    provider._maybe_request_finalization(CONV, project, "exec-b", waiting, waiting[-1], idle_seconds=60, budget=10)
    assert fake.commands().count("send-message") == 1


def test_finished_summary_mentioning_plan_is_not_a_pending_approval(env):
    provider, *_ = env
    text = "Lavoro concluso: ho applicato il piano di esecuzione e i test passano. Puoi procedere con la review."
    assert provider._check_if_waiting_for_interaction(text, {})[0] is False
    real = "Ecco il piano di esecuzione. In attesa della tua approvazione prima di modificare i file."
    assert provider._check_if_waiting_for_interaction(real, {})[0] is True


def test_send_message_state_guards(env):
    provider, fake, project, _ = env
    with pytest.raises(KeyError):
        provider.send_message("nope", "hi")
    fake.write_entries(user_input(), planner("ok"))
    ex = provider.start_task(task_for(project, "Analizza"))
    for bad in (S.RUNNING, S.CANCELLED, S.FAILED, S.TIMED_OUT):
        ex.status = bad
        with pytest.raises(ValueError):
            provider.send_message(ex.id, "x")
    assert "send-message" not in fake.commands()


def test_timeout_budget_is_cumulative_across_turns(env):
    provider, fake, project, _ = env
    fake.write_entries(user_input(), planner("ok"))
    ex = provider.start_task(task_for(project, "Analizza", timeout=3))
    ex.status = S.WAITING_FOR_INTERACTION
    ex.metadata["active_seconds"] = 3.0  # budget already consumed by earlier turns
    out = provider.send_message(ex.id, "go on")
    assert out.status == S.TIMED_OUT
    assert "send-message" not in fake.commands()
