"""Tests for Antigravity coding agent lifecycle hardening.

Verifies:
- Baseline isolation: pre-existing PLANNER_RESPONSE does not satisfy a new turn.
- Transcript ERROR status properly transitions execution to FAILED.
- Remaining timeout budget is calculated coherently.
- Cancellation distinguishes local from remote cancellation.
- collect_results isolates mission-introduced files from pre-existing git modifications
  and includes newly created untracked files.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aether.coding.models import (
    CodingExecutionStatus,
    CodingTask,
    CodingTaskExecution,
)
from aether.coding.providers.antigravity import AntigravityCodingProvider


@pytest.fixture
def provider():
    return AntigravityCodingProvider()


def test_wait_for_completion_ignores_baseline_entries(provider, tmp_path):
    """Old PLANNER_RESPONSE before baseline_line_count must not complete the turn."""
    conv_id = "test-conv-123"
    log_dir = tmp_path / ".gemini" / "antigravity" / "brain" / conv_id / ".system_generated" / "logs"
    log_dir.mkdir(parents=True)
    transcript_file = log_dir / "transcript.jsonl"

    old_entry = {
        "step_index": 1,
        "type": "PLANNER_RESPONSE",
        "source": "MODEL",
        "status": "DONE",
        "content": "Old response from previous turn",
        "tool_calls": [],
    }
    transcript_file.write_text(json.dumps(old_entry) + "\n", encoding="utf-8")

    # Call with baseline_line_count=1 and a short timeout
    with patch("pathlib.Path.home", return_value=tmp_path):
        turn_done, content, status, is_waiting = provider._wait_for_conversation_completion(
            conv_id=conv_id,
            p_dir=tmp_path,
            timeout=0.1,
            poll_interval=0.05,
            baseline_line_count=1,
        )

    # Since no new entry was added beyond baseline_line_count=1, it should time out
    assert not turn_done
    assert status == "TIMEOUT"
    assert content == ""


def test_wait_for_completion_picks_up_new_entry(provider, tmp_path):
    """A new PLANNER_RESPONSE after baseline_line_count must complete the turn."""
    conv_id = "test-conv-456"
    log_dir = tmp_path / ".gemini" / "antigravity" / "brain" / conv_id / ".system_generated" / "logs"
    log_dir.mkdir(parents=True)
    transcript_file = log_dir / "transcript.jsonl"

    old_entry = {
        "step_index": 1,
        "type": "PLANNER_RESPONSE",
        "source": "MODEL",
        "status": "DONE",
        "content": "Old response",
        "tool_calls": [],
    }
    user_entry = {"step_index": 2, "type": "USER_INPUT", "source": "USER_EXPLICIT", "status": "DONE", "content": "next"}
    new_entry = {
        "step_index": 3,
        "type": "PLANNER_RESPONSE",
        "source": "MODEL",
        "status": "DONE",
        "content": "New response for second turn",
        "tool_calls": [],
    }
    transcript_file.write_text(
        json.dumps(old_entry) + "\n" + json.dumps(user_entry) + "\n" + json.dumps(new_entry) + "\n",
        encoding="utf-8",
    )

    with patch("pathlib.Path.home", return_value=tmp_path):
        turn_done, content, status, is_waiting = provider._wait_for_conversation_completion(
            conv_id=conv_id,
            p_dir=tmp_path,
            timeout=0.5,
            poll_interval=0.05,
            baseline_line_count=1,
        )

    assert turn_done
    assert status == "DONE"
    assert content == "New response for second turn"
    assert not is_waiting


def test_wait_for_completion_error_status_fails(provider, tmp_path):
    """A PLANNER_RESPONSE with status ERROR must return status ERROR and not succeed."""
    conv_id = "test-conv-err"
    log_dir = tmp_path / ".gemini" / "antigravity" / "brain" / conv_id / ".system_generated" / "logs"
    log_dir.mkdir(parents=True)
    transcript_file = log_dir / "transcript.jsonl"

    err_entry = {
        "step_index": 1,
        "type": "PLANNER_RESPONSE",
        "source": "MODEL",
        "status": "ERROR",
        "content": "Model failed to generate response due to internal exception",
        "tool_calls": [],
    }
    user_entry = {"step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT", "status": "DONE", "content": "go"}
    transcript_file.write_text(json.dumps(user_entry) + "\n" + json.dumps(err_entry) + "\n", encoding="utf-8")

    with patch("pathlib.Path.home", return_value=tmp_path):
        turn_done, content, status, is_waiting = provider._wait_for_conversation_completion(
            conv_id=conv_id,
            p_dir=tmp_path,
            timeout=0.5,
            poll_interval=0.05,
            baseline_line_count=0,
        )

    assert not turn_done
    assert status == "ERROR"
    assert "internal exception" in content


def test_start_task_handles_error_status(provider, tmp_path):
    """When _wait_for_conversation_completion returns ERROR, start_task must mark execution as FAILED."""
    task = CodingTask(
        id="task-err-1",
        instruction="Fix the bug",
        project_path=str(tmp_path),
        timeout_seconds=60,
    )

    with patch.object(provider, "is_available", return_value=(True, "Ready")), \
         patch.object(provider, "resolve_binary", return_value="/bin/agentapi"), \
         patch("subprocess.run") as mock_run, \
         patch.object(
             provider,
             "_wait_for_conversation_completion",
             return_value=(False, "Fatal execution error", "ERROR", False),
         ):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({"response": {"conversationId": "conv-err-999"}})
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        execution = provider.start_task(task)

    assert execution.status == CodingExecutionStatus.FAILED
    assert "Fatal execution error" in execution.error
    assert execution.result is not None
    assert execution.result.status == CodingExecutionStatus.FAILED


def test_cancel_task_distinguishes_local_and_remote(provider):
    """cancel_task must set local_cancelled=True and accurately report remote_status."""
    task = CodingTask(id="task-c1", instruction="Do work", project_path="/tmp")
    execution = CodingTaskExecution(
        id="exec-c1",
        task=task,
        provider_id=provider.id,
        status=CodingExecutionStatus.RUNNING,
    )
    provider._executions["exec-c1"] = execution

    # Case 1: No child process attached
    ok = provider.cancel_task("exec-c1")
    assert ok is True
    assert execution.status == CodingExecutionStatus.CANCELLED
    assert execution.metadata["local_cancelled"] is True
    assert execution.metadata["remote_cancelled"] is False
    assert execution.metadata["remote_status"] == "remote_cancel_unsupported"

    # Case 2: Process attached and terminable
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # Process is running
    execution2 = CodingTaskExecution(
        id="exec-c2",
        task=task,
        provider_id=provider.id,
        status=CodingExecutionStatus.RUNNING,
    )
    setattr(execution2, "_process", mock_proc)
    provider._executions["exec-c2"] = execution2

    ok2 = provider.cancel_task("exec-c2")
    assert ok2 is True
    mock_proc.terminate.assert_called_once()
    assert execution2.metadata["local_cancelled"] is True
    assert execution2.metadata["remote_cancelled"] is True
    assert execution2.metadata["remote_status"] == "process_terminated"


def test_collect_results_filters_preexisting_and_captures_untracked(provider, tmp_path):
    """Pre-existing modifications are excluded; files created or edited by the run are reported."""
    from aether.coding.evidence import take_snapshot

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "preexisting.py").write_text("dirty before the run\n", encoding="utf-8")
    (repo_dir / "edited.py").write_text("a = 1\n", encoding="utf-8")

    task = CodingTask(id="task-col", instruction="Create new_created.py", project_path=str(repo_dir))
    execution = CodingTaskExecution(
        id="exec-col", task=task, provider_id=provider.id, status=CodingExecutionStatus.COMPLETED,
    )
    provider._executions["exec-col"] = execution
    provider._baselines["exec-col"] = take_snapshot(repo_dir)

    # The run creates an untracked file and edits an existing one; preexisting.py is untouched.
    (repo_dir / "new_created.py").write_text("def new_func():\n    return 42\n", encoding="utf-8")
    (repo_dir / "edited.py").write_text("a = 2\n", encoding="utf-8")

    with patch("subprocess.run") as mock_run:
        result = provider.collect_results("exec-col")

    mock_run.assert_not_called()  # collecting results never executes anything
    assert "preexisting.py" not in result.modified_files
    assert result.modified_files == ["edited.py", "new_created.py"]
    assert "+++ b/new_created.py" in result.diff
    assert "+def new_func():" in result.diff
    assert "-a = 1" in result.diff and "+a = 2" in result.diff
    assert "dirty before the run" not in result.diff


def _write(tmp_path, conv_id, *entries):
    log_dir = tmp_path / ".gemini" / "antigravity" / "brain" / conv_id / ".system_generated" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "transcript.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


USER = {"type": "USER_INPUT", "source": "USER_EXPLICIT", "status": "DONE", "content": "go"}


def test_planner_response_without_turn_start_marker_is_not_accepted(provider, tmp_path):
    """A model answer that is not preceded by this turn's USER_INPUT cannot complete the wait."""
    _write(tmp_path, "c-nouser", {"type": "PLANNER_RESPONSE", "source": "MODEL", "status": "DONE", "content": "stale", "tool_calls": []})
    with patch("pathlib.Path.home", return_value=tmp_path):
        done, _, status, _ = provider._wait_for_conversation_completion("c-nouser", tmp_path, timeout=0.3, poll_interval=0.05)
    assert not done and status == "TIMEOUT"


def test_ask_question_entry_is_an_interaction_request(provider, tmp_path):
    _write(tmp_path, "c-ask", USER, {"type": "ASK_QUESTION", "source": "MODEL", "status": "DONE", "content": "Which db?"})
    with patch("pathlib.Path.home", return_value=tmp_path):
        done, content, status, waiting = provider._wait_for_conversation_completion("c-ask", tmp_path, timeout=1, poll_interval=0.05)
    assert waiting and status == "WAITING"


def test_trailing_error_message_ends_the_turn_as_error_after_settling(provider, tmp_path):
    provider.ERROR_SETTLE_SECONDS = 0.1
    _write(tmp_path, "c-err2", USER, {"type": "ERROR_MESSAGE", "source": "SYSTEM", "status": "DONE", "content": "quota exceeded"})
    with patch("pathlib.Path.home", return_value=tmp_path):
        done, content, status, waiting = provider._wait_for_conversation_completion("c-err2", tmp_path, timeout=2, poll_interval=0.05)
    assert not done and status == "ERROR" and "quota" in content
