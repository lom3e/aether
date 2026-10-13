"""
Persistent coding runs: durable state, events, baselines, project locks and authorised test runs.

Why this exists: the in-memory orchestrator used to be the only source of truth for a run. A restart
lost running and waiting sessions, nothing prevented a second task from writing to a project while a
remote agent might still be working on it, and nothing tied a result to a workspace/mission/provider.

* ``CodingRunStore``     SQLite store per workspace: runs, ordered events, pre-run baselines.
* ``CodingRunRegistry``  process-wide map workspace -> store, plus the recorder that provider listeners call.
* project lock           a project is busy while a run on it is active OR may still be active remotely.
* ``run_authorised_tests``  the ONLY place project code is executed, and only through an authorised action.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable

from aether.coding.evidence import TreeSnapshot, snapshot_from_blob, snapshot_to_blob
from aether.coding.models import CodingExecutionStatus, CodingTaskExecution
from aether.core.process_control import new_process_group_kwargs, terminate_process_tree
from aether.core.sqlite import get_sqlite_connection

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = {
    CodingExecutionStatus.RUNNING.value,
    CodingExecutionStatus.QUEUED.value,
    CodingExecutionStatus.WAITING_FOR_INTERACTION.value,
    CodingExecutionStatus.WAITING_FOR_APPROVAL.value,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectBusyError(RuntimeError):
    """Raised when a project may still be modified by a previous coding run."""

    def __init__(self, project_path: str, run_id: str, reason: str) -> None:
        super().__init__(
            f"Project '{project_path}' is busy: run '{run_id}' {reason}. "
            f"Wait for it to finish, or release it explicitly once the remote session is confirmed stopped."
        )
        self.project_path = project_path
        self.run_id = run_id


class CodingRunStore:
    """SQLite persistence for coding runs of ONE workspace."""

    def __init__(self, db_path: str | Path, workspace_id: str) -> None:
        self.db_path = str(db_path)
        self.workspace_id = workspace_id
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS coding_runs (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    mission_id TEXT,
                    proposal_id TEXT,
                    provider_id TEXT NOT NULL,
                    model TEXT,
                    project_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    external_task_id TEXT,
                    remote_session_may_continue INTEGER NOT NULL DEFAULT 0,
                    remote_released INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    execution_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_ws ON coding_runs(workspace_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_runs_project ON coding_runs(project_path, status);
                CREATE INDEX IF NOT EXISTS idx_runs_mission ON coding_runs(mission_id);
                CREATE TABLE IF NOT EXISTS coding_run_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    mission_id TEXT,
                    provider_id TEXT,
                    event TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_events_run ON coding_run_events(run_id, seq);
                CREATE TABLE IF NOT EXISTS coding_run_baselines (
                    run_id TEXT PRIMARY KEY,
                    blob TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _conn(self) -> sqlite3.Connection:
        return get_sqlite_connection(self.db_path, check_same_thread=False)

    # -- runs ---------------------------------------------------------------
    def save_run(self, execution: CodingTaskExecution) -> None:
        meta = execution.metadata or {}
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO coding_runs (id, workspace_id, mission_id, proposal_id, provider_id, model, project_path,
                    status, external_task_id, remote_session_may_continue, remote_released, created_at, updated_at,
                    completed_at, execution_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    mission_id=excluded.mission_id, proposal_id=excluded.proposal_id, model=excluded.model,
                    status=excluded.status, external_task_id=excluded.external_task_id,
                    remote_session_may_continue=excluded.remote_session_may_continue,
                    remote_released=excluded.remote_released, updated_at=excluded.updated_at,
                    completed_at=excluded.completed_at, execution_json=excluded.execution_json
                """,
                (
                    execution.id, self.workspace_id, execution.task.mission_id or meta.get("mission_id"),
                    execution.task.proposal_id or meta.get("proposal_id"), execution.provider_id,
                    meta.get("model") or execution.task.model, str(Path(execution.task.project_path).resolve()),
                    execution.status.value, execution.external_task_id,
                    int(bool(meta.get("remote_session_may_continue"))), int(bool(meta.get("remote_released"))),
                    execution.started_at or _now(), _now(), execution.completed_at,
                    json.dumps(execution.to_dict(), default=str),
                ),
            )

    def get_run(self, run_id: str) -> CodingTaskExecution | None:
        with self._conn() as conn:
            row = conn.execute("SELECT execution_json FROM coding_runs WHERE id=?", (run_id,)).fetchone()
        return CodingTaskExecution.from_dict(json.loads(row["execution_json"])) if row else None

    def list_runs(self, mission_id: str | None = None, status: str | None = None, limit: int = 50) -> list[CodingTaskExecution]:
        sql, params = "SELECT execution_json FROM coding_runs WHERE workspace_id=?", [self.workspace_id]
        if mission_id:
            sql += " AND mission_id=?"; params.append(mission_id)
        if status:
            sql += " AND status=?"; params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(max(1, limit))
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [CodingTaskExecution.from_dict(json.loads(r["execution_json"])) for r in rows]

    def blocking_runs_for_project(self, project_path: str) -> list[dict[str, Any]]:
        """Runs that make the project unsafe to touch: active ones, or ended ones whose remote session may live on."""
        path = str(Path(project_path).resolve())
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, status, provider_id, remote_session_may_continue, remote_released
                   FROM coding_runs WHERE project_path=?""", (path,),
            ).fetchall()
        out = []
        for r in rows:
            if r["status"] in ACTIVE_STATUSES:
                out.append({"id": r["id"], "reason": f"is {r['status']}", "provider_id": r["provider_id"], "active": True})
            elif r["remote_session_may_continue"] and not r["remote_released"]:
                out.append({"id": r["id"], "reason": f"ended as {r['status']} but its remote session may still be working",
                            "provider_id": r["provider_id"], "active": False})
        return out

    def mark_released(self, run_id: str, reason: str) -> bool:
        run = self.get_run(run_id)
        if run is None:
            return False
        run.metadata["remote_released"] = True
        run.metadata["release_reason"] = reason
        run.metadata["released_at"] = _now()
        self.save_run(run)
        self.add_event(run, "project_released", {"reason": reason})
        return True

    # -- events / baselines ---------------------------------------------------
    def add_event(self, execution: CodingTaskExecution, event: str, data: dict[str, Any] | None = None) -> int:
        meta = execution.metadata or {}
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO coding_run_events (run_id, workspace_id, mission_id, provider_id, event, ts, data_json) VALUES (?,?,?,?,?,?,?)",
                (execution.id, self.workspace_id, execution.task.mission_id or meta.get("mission_id"),
                 execution.provider_id, event, _now(), json.dumps(data or {}, default=str)),
            )
            return int(cur.lastrowid)

    def list_events(self, run_id: str | None = None, mission_id: str | None = None, after_seq: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM coding_run_events WHERE workspace_id=? AND seq>?", [self.workspace_id, after_seq]
        if run_id:
            sql += " AND run_id=?"; params.append(run_id)
        if mission_id:
            sql += " AND mission_id=?"; params.append(mission_id)
        sql += " ORDER BY seq LIMIT ?"; params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [{**dict(r), "data": json.loads(r["data_json"])} for r in rows]

    def save_baseline(self, run_id: str, snap: TreeSnapshot) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO coding_run_baselines (run_id, blob, created_at) VALUES (?,?,?)",
                (run_id, snapshot_to_blob(snap), _now()),
            )

    def load_baseline(self, run_id: str) -> TreeSnapshot | None:
        with self._conn() as conn:
            row = conn.execute("SELECT blob FROM coding_run_baselines WHERE run_id=?", (run_id,)).fetchone()
        return snapshot_from_blob(row["blob"]) if row else None


class CodingRunRegistry:
    """Process-wide map workspace -> store, plus the listener providers call on every lifecycle event."""

    def __init__(self) -> None:
        self._stores: dict[str, CodingRunStore] = {}
        self._lock = threading.RLock()
        self._subscribers: list[Callable[[str, CodingTaskExecution, dict[str, Any], int], None]] = []

    def bind(self, store: CodingRunStore) -> CodingRunStore:
        with self._lock:
            self._stores.setdefault(store.workspace_id, store)
            return self._stores[store.workspace_id]

    def store_for(self, workspace_id: str | None) -> CodingRunStore | None:
        with self._lock:
            return self._stores.get(workspace_id or "")

    def stores(self) -> list[CodingRunStore]:
        with self._lock:
            return list(self._stores.values())

    def subscribe(self, fn: Callable[[str, CodingTaskExecution, dict[str, Any], int], None]) -> None:
        """``fn(event, execution, data, seq)`` is called after the event is durably stored (UI/notifications hook)."""
        with self._lock:
            if fn not in self._subscribers:
                self._subscribers.append(fn)

    def _ensure_default_subscribers(self) -> None:
        """Every registry closes the loop on its own: run events update the linked mission (see missions.coding_outcomes)."""
        if getattr(self, "_defaults_attached", False):
            return
        self._defaults_attached = True
        try:
            from aether.missions.coding_outcomes import CodingMissionFinalizer
            self.subscribe(CodingMissionFinalizer())
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not attach the coding mission finalizer: %s", exc)

    def record(self, provider: Any, event: str, execution: CodingTaskExecution, data: dict[str, Any]) -> None:
        """The provider listener: persist run state + event (+ baseline at start), then notify subscribers."""
        ws = execution.task.workspace_id or (execution.metadata or {}).get("workspace_id")
        store = self.store_for(ws)
        if store is None:
            return
        if event == "run_started":
            snap = provider.baseline_for(execution.id) if hasattr(provider, "baseline_for") else None
            if snap is not None:
                store.save_baseline(execution.id, snap)
        store.save_run(execution)
        seq = store.add_event(execution, event, data)
        self._ensure_default_subscribers()
        for fn in list(self._subscribers):
            try:
                fn(event, execution, data, seq)
            except Exception as exc:
                logger.warning("Coding run subscriber failed on %s: %s", event, exc)

    # -- project lock -------------------------------------------------------
    def assert_project_free(self, project_path: str, providers: dict[str, Any]) -> None:
        """
        Refuses a new task when a previous run could still be writing to the same project (any workspace).
        An ended run whose remote session may continue is released automatically only if its provider can
        positively observe that the session went quiet; otherwise a human must release it.
        """
        for store in self.stores():
            for blocker in store.blocking_runs_for_project(project_path):
                if not blocker["active"]:
                    provider = providers.get(blocker["provider_id"])
                    run = store.get_run(blocker["id"])
                    state = "unknown"
                    if provider is not None and run is not None and hasattr(provider, "remote_activity_state"):
                        try:
                            state = provider.remote_activity_state(run)
                        except Exception:
                            state = "unknown"
                    if state == "idle":
                        store.mark_released(blocker["id"], "remote session observed idle")
                        continue
                raise ProjectBusyError(str(project_path), blocker["id"], blocker["reason"])


_registry = CodingRunRegistry()


def get_run_registry() -> CodingRunRegistry:
    return _registry


# --------------------------------------------------------------------------- authorised test execution

@dataclass(frozen=True)
class RunnerCommand:
    id: str
    argv: tuple[str, ...]


# Whitelisted runners only: a caller can pick one, never inject an arbitrary command line.
TEST_COMMANDS: dict[str, RunnerCommand] = {
    "pytest": RunnerCommand("pytest", (sys.executable, "-m", "pytest", "-q", "-x", "--no-header", "-p", "no:cacheprovider")),
    "unittest": RunnerCommand("unittest", (sys.executable, "-m", "unittest", "discover", "-v")),
}

_SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH", "COOKIE", "SESSION")


def _clean_env(project: Path, home: str) -> dict[str, str]:
    """Environment for running agent-written code: no inherited credentials, no bytecode/cache writes."""
    keep = {"PATH", "LANG", "LC_ALL", "TMPDIR", "TERM"}
    env = {k: v for k, v in os.environ.items() if k in keep and not any(h in k.upper() for h in _SECRET_HINTS)}
    env["HOME"] = home
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(project)
    return env


def detect_test_runner(project: Path) -> str:
    """pytest when the project clearly uses it and it is importable, otherwise the stdlib runner."""
    uses_pytest = any((project / n).exists() for n in ("pytest.ini", "conftest.py")) or any(
        "pytest" in (p.read_text(errors="ignore")) for p in project.glob("test*.py")
    ) or any(
        "pytest" in (p.read_text(errors="ignore")) for p in (project / "tests").glob("test*.py")
    )
    if uses_pytest:
        try:
            import importlib.util
            if importlib.util.find_spec("pytest") is not None:
                return "pytest"
        except Exception:
            pass
    return "unittest"


def run_authorised_tests(
    execution: CodingTaskExecution,
    runner: str = "auto",
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """
    Executes the project's tests for ``execution``. Callers MUST have passed the action layer
    (authority + policy + human approval) first. Runs in the run's own project directory, in its own process
    group, with a scrubbed environment and a hard timeout, and returns concrete evidence.
    """
    project = Path(execution.task.project_path).resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")
    chosen = detect_test_runner(project) if runner == "auto" else runner
    if chosen not in TEST_COMMANDS:
        raise ValueError(f"Unsupported test runner '{runner}'. Allowed: {sorted(TEST_COMMANDS)} or 'auto'.")
    cmd = TEST_COMMANDS[chosen]
    started = time.time()
    scratch_home = tempfile.mkdtemp(prefix="aether_testhome_")
    proc = subprocess.Popen(
        list(cmd.argv), cwd=str(project), env=_clean_env(project, scratch_home), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, **new_process_group_kwargs(),
    )
    timed_out = False
    try:
        out, _ = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_process_tree(proc, force=True)
        out, _ = proc.communicate()
    shutil.rmtree(scratch_home, ignore_errors=True)
    exit_code = proc.returncode
    passed = (exit_code == 0) and not timed_out
    output = (out or "")[-4000:]
    result = {
        "runner": chosen,
        "command": " ".join(cmd.argv[1:]),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "passed": passed,
        "duration_seconds": round(time.time() - started, 2),
        "output": output,
        "project_path": str(project),
        "ran_at": _now(),
    }
    execution.metadata["test_run"] = result
    return result
