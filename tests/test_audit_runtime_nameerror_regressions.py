"""
Regressions for names that were used but never defined/imported.

These were invisible on Python 3.14 only for annotations, but three of them were real runtime faults:

* ``telegram_status_route`` referenced an undefined ``conn`` -> every call raised NameError (HTTP 500).
* ``PersonalAgentService._semantic_extract_coding_details`` used ``json`` without importing it; the broad
  ``except Exception`` hid the NameError, so the LLM extraction was silently always skipped.
* ``ContextResolver`` referenced an undefined ``p_str`` when a mentioned git branch exists in the active project.
"""
from __future__ import annotations

import asyncio
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

from aether.connections.models import ConnectionStatus
from aether.planning.contracts import IntentRequest
from aether.planning.resolver import ContextResolver
from aether.server.app import app
from aether.server.routes import telegram_status_route
from aether.workspace.workspace import Workspace


def _request() -> Request:
    return Request({"type": "http", "app": app, "headers": [], "path": "/", "method": "GET"})


def _with_workspace(ws):
    previous = getattr(app.state, "workspace", None)
    app.state.workspace = ws
    return previous


def test_telegram_status_without_connection_reports_disconnected():
    ws = MagicMock()
    ws.id = "ws-1"
    ws.canonical_id = lambda value=None: "ws-1"
    ws.connections.get_connection.return_value = None
    previous = _with_workspace(ws)
    try:
        result = asyncio.run(telegram_status_route(_request(), None))
    finally:
        app.state.workspace = previous
    assert result == {"configured": False, "status": "disconnected"}
    ws.connections.get_connection.assert_called_once_with("ws-1", "telegram")
    ws.connections.get_telegram_connector.assert_not_called()


def test_telegram_status_with_connection_verifies_for_real_connector():
    ws = MagicMock()
    ws.id = "ws-1"
    ws.canonical_id = lambda value=None: "ws-1"
    ws.connections.get_connection.return_value = SimpleNamespace(
        is_configured=True, status=ConnectionStatus.CONFIGURED
    )
    connector = MagicMock()
    connector.verify.return_value = (False, "bad token")
    connector._get_default_chat_id.return_value = "42"
    connector._get_allowed_chat_ids.return_value = ["42"]
    ws.connections.get_telegram_connector.return_value = connector
    previous = _with_workspace(ws)
    try:
        result = asyncio.run(telegram_status_route(_request(), None))
    finally:
        app.state.workspace = previous
    assert result["configured"] is True
    assert result["status"] == "verification_failed"
    assert result["connected"] is False
    assert result["message"] == "bad token"
    connector.verify.assert_called_once_with(live_check=True)


def test_semantic_extraction_parses_json_reply_instead_of_silently_skipping():
    from aether.personal.service import PersonalAgentService
    from aether.providers.types import ProviderResponse

    reply = (
        '```json\n{"target_project": null, "target_files": ["a.py"], '
        '"designated_provider": null, "summary": "fix a"}\n```'
    )
    provider = MagicMock()
    provider.generate.return_value = SimpleNamespace(content=reply)
    fake_self = SimpleNamespace(provider=provider)
    data = PersonalAgentService._semantic_extract_coding_details(fake_self, "fix a.py")
    assert data is not None, "valid JSON from the model must not be dropped"
    assert data["target_files"] == ["a.py"]
    assert ProviderResponse is not None  # import sanity: provider types stay importable


def test_resolver_verifies_existing_branch_without_nameerror(tmp_path):
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    ws = Workspace.init(ws_dir, "test-ws")
    proj = tmp_path / "proj"
    proj.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    import os

    full_env = {**os.environ, **env}

    def git(*args):
        subprocess.run(["git", *args], cwd=proj, check=True, capture_output=True, env=full_env)

    git("init", "-q")
    (proj / "f.txt").write_text("x", encoding="utf-8")
    git("add", ".")
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "init")
    git("branch", "feature-x")
    ws.set_project(str(proj), name="proj")

    intent = IntentRequest(
        id="i-branch",
        workspace_id=ws.name,
        raw_input="Lavora sul branch feature-x del progetto proj",
        action_id="coding.delegate",
    )
    pack = ContextResolver(workspace=ws).resolve(intent)
    git_refs = [e for e in pack.evidence_references if e.source_type == "git"]
    assert git_refs, "an existing branch must yield a verified git evidence reference"
    assert git_refs[0].locator.endswith(":refs/heads/feature-x")
    assert str(proj) not in git_refs[0].locator, "locator must stay workspace-relative, never an absolute path"


def test_watcher_manager_registers_github_watcher_for_github_trigger():
    from aether.automation.models import AutomationDefinition, TriggerConfig, TriggerType
    from aether.automation.watchers import GitHubRepoWatcher, WatcherManager

    auto = AutomationDefinition(
        id="auto_gh",
        trigger=TriggerConfig(
            type=TriggerType.GITHUB_WATCHER,
            github_owner="lom3e",
            github_repo="aether",
            github_watch_type="commits",
        ),
    )
    manager = WatcherManager(workspace=MagicMock())
    manager.sync_automations([auto])  # used to raise NameError: name 'repo' is not defined
    watcher = manager._watchers["auto_gh"]
    assert isinstance(watcher, GitHubRepoWatcher)
    assert watcher.owner == "lom3e" and watcher.repo == "aether"


def test_tar_fallback_without_data_filter_rejects_symlink_members(tmp_path, monkeypatch):
    """
    On interpreters without ``tarfile`` extraction filters the loader used to extract after checking only member
    names, so a symlink member could redirect later writes outside the destination. Links must be refused.
    """
    import io
    import tarfile

    from aether.errors import InvalidSkillPackageError
    from aether.skills.loader import SkillLoader

    archive = tmp_path / "evil.tar.gz"
    outside = tmp_path / "outside"
    outside.mkdir()
    with tarfile.open(archive, "w:gz") as tf:
        link = tarfile.TarInfo("escape")
        link.type = tarfile.SYMTYPE
        link.linkname = str(outside)
        tf.addfile(link)
        payload = b"pwned"
        info = tarfile.TarInfo("escape/pwn.txt")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    real_extractall = tarfile.TarFile.extractall

    def legacy_extractall(self, path=".", members=None, *, numeric_owner=False, **kwargs):
        if "filter" in kwargs:
            raise TypeError("extractall() got an unexpected keyword argument 'filter'")
        return real_extractall(self, path, members, numeric_owner=numeric_owner)

    monkeypatch.setattr(tarfile.TarFile, "extractall", legacy_extractall)
    dest = tmp_path / "dest"
    dest.mkdir()
    loader = SkillLoader.__new__(SkillLoader)
    with pytest.raises(InvalidSkillPackageError, match="link or special file"):
        loader._extract_tar(archive, dest)
    assert not (outside / "pwn.txt").exists()


@pytest.mark.parametrize(
    "module,cls",
    [
        ("aether.policy.store", "PolicyStore"),
        ("aether.autonomy.store", "AutonomousGoalStore"),
        ("aether.benchmarking.store", "BenchmarkingStore"),
        ("aether.client.store", "ClientStore"),
        ("aether.content.store", "ContentStore"),
        ("aether.proactive.store", "ProactiveStore"),
    ],
)
def test_sqlite_stores_close_their_connection_after_each_use(tmp_path, module, cls):
    """
    ``with sqlite3.connect(...)`` only commits; it never closes. These stores kept a file handle open after every
    call, which on Windows makes the database file undeletable (WinError 32) until garbage collection.
    """
    import importlib
    import sqlite3

    store_cls = getattr(importlib.import_module(module), cls)
    store = store_cls(tmp_path / "x.db")
    with store._get_connection() as conn:
        conn.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
    (tmp_path / "x.db").unlink()  # must not raise PermissionError on Windows


def test_get_mission_without_deliverable_rows_does_not_recurse(tmp_path):
    """
    get_mission() -> list_deliverables() -> _list_deliverables_legacy() -> get_mission() used to recurse until
    RecursionError (swallowed by ``except Exception``), opening one SQLite connection per level on every read.
    """
    import sqlite3

    from aether.missions.store import MissionStore

    store = MissionStore(tmp_path / "m.db")
    mission = store.create_mission(title="T", objective="O", milestones=[{"title": "M1", "order_idx": 0}])

    calls = {"get_mission": 0, "connect": 0}
    real_get = store.get_mission
    real_connect = sqlite3.connect

    def counting_get(*a, **k):
        calls["get_mission"] += 1
        return real_get(*a, **k)

    def counting_connect(*a, **k):
        calls["connect"] += 1
        return real_connect(*a, **k)

    store.get_mission = counting_get  # type: ignore[method-assign]
    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(sqlite3, "connect", counting_connect)
        loaded = store.get_mission(mission.id)

    assert loaded is not None and loaded.id == mission.id
    assert calls["get_mission"] == 1, "deliverable lookup must not re-enter get_mission"
    assert calls["connect"] < 10, f"expected a handful of connections, opened {calls['connect']}"
    assert store.list_deliverables(mission.id) == []


def test_legacy_metadata_deliverables_are_still_listed(tmp_path):
    from aether.missions.models import Deliverable
    from aether.missions.store import MissionStore

    store = MissionStore(tmp_path / "m.db")
    mission = store.create_mission(
        title="T",
        objective="O",
        metadata={"deliverables": [{"id": "d1", "name": "report.md", "path": "report.md", "type": "document"}]},
    )
    found = store.list_deliverables(mission.id)
    assert [d.name for d in found] == ["report.md"]
    assert isinstance(found[0], Deliverable)


def test_terminate_process_tree_stops_grandchildren_on_every_platform(tmp_path):
    """signal.SIGKILL/os.killpg do not exist on Windows: timeouts and cancellations used to crash or orphan the agent."""
    import subprocess
    import sys
    import time

    from aether.core.process_control import new_process_group_kwargs, terminate_process_tree

    pid_file = tmp_path / "grandchild.pid"
    code = (
        "import subprocess, sys, time\n"
        "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open(r'{pid_file}', 'w').write(str(g.pid))\n"
        "time.sleep(60)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, **new_process_group_kwargs()
    )
    deadline = time.time() + 15
    while not pid_file.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert pid_file.exists(), "the helper process never started its child"
    grandchild_pid = int(pid_file.read_text())

    started = time.time()
    terminate_process_tree(proc, force=True)
    proc.communicate(timeout=10)  # would block for 60s if the grandchild kept the pipes open
    assert time.time() - started < 10

    def alive(pid: int) -> bool:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True).stdout
            return str(pid).encode() in out  # raw bytes: the localized "no tasks" message is not valid UTF-8
        try:
            import os

            os.kill(pid, 0)
            return True
        except OSError:
            return False

    for _ in range(40):
        if not alive(grandchild_pid):
            break
        time.sleep(0.1)
    assert not alive(grandchild_pid), "grandchild survived the tree termination"


def test_static_manifest_ignores_os_metadata_and_uses_portable_keys(tmp_path):
    """A .DS_Store in the dist folder used to be listed in the manifest (unverifiable on any clean checkout), and
    Windows wrote 'assets\app.js' keys that a POSIX verifier cannot resolve."""
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from scripts.sync_static import sync_static_assets, verify_static_manifest

    src, tgt = tmp_path / "dist", tmp_path / "static"
    (src / "assets").mkdir(parents=True)
    (src / "index.html").write_text("<html>x</html>", encoding="utf-8")
    (src / "assets" / "app.js").write_text("1", encoding="utf-8")
    (src / ".DS_Store").write_bytes(b"\x00\x01")
    manifest = sync_static_assets(source_dir=src, target_dir=tgt)
    assert sorted(manifest["files"]) == ["assets/app.js", "index.html"]
    assert verify_static_manifest(target_dir=tgt) == (True, "Manifest verified successfully.")


def test_static_manifest_verification_reports_missing_before_checksum_mismatch(tmp_path):
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from scripts.sync_static import sync_static_assets, verify_static_manifest

    src, tgt = tmp_path / "dist", tmp_path / "static"
    (src / "assets").mkdir(parents=True)
    (src / "index.html").write_text("<html>x</html>", encoding="utf-8")
    (src / "assets" / "a.js").write_text("1", encoding="utf-8")
    (src / "assets" / "z.css").write_text("2", encoding="utf-8")
    sync_static_assets(source_dir=src, target_dir=tgt)
    (tgt / "assets" / "a.js").write_text("tampered", encoding="utf-8")  # sorts before the deleted file
    (tgt / "assets" / "z.css").unlink()
    ok, msg = verify_static_manifest(target_dir=tgt)
    assert not ok and msg.startswith("Missing file")


def test_system_directories_are_protected_on_this_platform(tmp_path):
    import os
    import sys
    from pathlib import Path

    from aether.core.system_paths import is_protected_system_path

    assert is_protected_system_path(Path(tmp_path.anchor))  # a drive/filesystem root
    assert is_protected_system_path(tmp_path.anchor)
    assert not is_protected_system_path(tmp_path)  # a normal project directory is fine
    if sys.platform == "win32":
        assert is_protected_system_path(os.environ.get("SystemRoot", r"C:\Windows"))
        assert is_protected_system_path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        assert not is_protected_system_path(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "SomeApp" / "x")
    else:
        assert is_protected_system_path("/etc") and is_protected_system_path("/usr")


def test_orchestrator_refuses_filesystem_root_on_every_platform(tmp_path):
    from pathlib import Path

    from aether.coding.models import CodingTask
    from aether.coding.orchestrator import CodingAgentOrchestrator

    with pytest.raises(ValueError, match="protected system directory"):
        CodingAgentOrchestrator().delegate_task(CodingTask(instruction="x", project_path=Path(tmp_path.anchor).as_posix()))


def test_legacy_workspace_database_location_does_not_flip_while_loading(tmp_path):
    """
    A legacy workspace (no aether.yaml) keeps its databases in .aether/. Creating data/ (the encrypted vault does it on
    Windows) used to flip identity.db & co. to data/ in the middle of the same run, splitting the data in two places.
    """
    from aether.workspace.workspace import Workspace

    ws = Workspace(tmp_path)
    ws.legacy_team_yaml.write_text(
        "team:\n  name: legacy-team\n  provider: mock\n  model: mock-model\nagents:\n  - name: a\n    role: r\n",
        encoding="utf-8",
    )
    before = ws.identity_db_path
    ws.load_team("default")
    (tmp_path / "data" / "vault").mkdir(parents=True, exist_ok=True)  # what the secrets vault does
    assert ws.identity_db_path == before
    assert ".aether" in ws.identity_db_path and ws.conversations_db_path.startswith(str(tmp_path / ".aether"))
    ws.close()


def test_delete_workspace_releases_open_database_handles_and_never_lies(tmp_path):
    from aether.core.paths import set_aether_data_dir
    from aether.workspace.registry import WorkspaceRegistry

    set_aether_data_dir(tmp_path / "home")
    try:
        ws = WorkspaceRegistry.create_workspace(name="To Delete", preset_id="empty", target_dir=tmp_path / "ws-del")
        ws.load_team()  # opens identity/knowledge/conversation databases
        entry = WorkspaceRegistry.get_workspace_entry(ws.root)
        assert WorkspaceRegistry.delete_workspace(entry["id"]) is True
        assert not (tmp_path / "ws-del").exists(), "reported as deleted while the data was still on disk"
    finally:
        set_aether_data_dir(None)


def test_delete_workspace_raises_instead_of_reporting_success_when_files_remain(tmp_path, monkeypatch):
    import shutil

    from aether.core.paths import set_aether_data_dir
    from aether.workspace import registry as registry_module
    from aether.workspace.registry import WorkspaceRegistry
    from aether.workspace.workspace import WorkspaceError

    set_aether_data_dir(tmp_path / "home")
    try:
        ws = WorkspaceRegistry.create_workspace(name="Stuck", preset_id="empty", target_dir=tmp_path / "ws-stuck")
        entry = WorkspaceRegistry.get_workspace_entry(ws.root)
        monkeypatch.setattr(shutil, "rmtree", lambda *a, **k: None)  # nothing can be removed
        monkeypatch.setattr("time.sleep", lambda s: None)
        with pytest.raises(WorkspaceError):
            WorkspaceRegistry.delete_workspace(entry["id"])
        assert WorkspaceRegistry.get_workspace_entry(ws.root) is not None, "the registry entry must be kept"
        assert registry_module is not None
    finally:
        set_aether_data_dir(None)


@pytest.mark.parametrize("quoted", [False, True])
def test_resolver_understands_windows_absolute_project_paths(tmp_path, quoted):
    """Only POSIX paths starting with a slash were recognised: a Windows drive path was not understood."""
    import sys

    if sys.platform != "win32":
        pytest.skip("Windows drive paths are only meaningful on Windows")
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    ws = Workspace.init(ws_dir, "win-paths")
    project = tmp_path / "my project" if quoted else tmp_path / "myproject"
    project.mkdir()
    shown = str(project)
    mention = f'"{shown}"' if quoted else shown
    intent = IntentRequest(
        id="i-win", workspace_id=ws.name, raw_input=f"Analizza il codice in {mention} e riassumilo", action_id="coding.delegate"
    )
    pack = ContextResolver(workspace=ws).resolve(intent)
    repos = [e for e in pack.resolved_entities if e.entity_type == "repository"]
    assert repos and __import__('pathlib').Path(repos[0].canonical_id) == __import__('pathlib').Path(shown)


@pytest.mark.parametrize(
    "prompt",
    ["Implement parser in C:/Users/x/proj", r"implementa il parser in C:\Users\x\proj", "Refactor files in /Library"],
)
def test_coding_intent_recognises_posix_and_windows_paths(prompt):
    from aether.personal.intent_rules import assess_coding_prompt

    assert assess_coding_prompt(prompt).operational is True


def test_coding_intent_ignores_a_bare_drive_letter_in_prose():
    from aether.personal.intent_rules import assess_coding_prompt

    assert assess_coding_prompt("what time is it in C").operational is False


@pytest.mark.parametrize(
    "prompt",
    ["implementa il middleware di autenticazione JWT", "crea un parser per i file di log", "write a plugin for the exporter"],
)
def test_common_code_nouns_make_an_implementation_request_operational(prompt):
    from aether.personal.intent_rules import assess_coding_prompt

    assert assess_coding_prompt(prompt).operational is True


@pytest.mark.parametrize("prompt", ["spiegami cos'è un middleware", "implementa la strategia di marketing"])
def test_explanations_and_non_code_requests_stay_non_operational(prompt):
    from aether.personal.intent_rules import assess_coding_prompt

    assert assess_coding_prompt(prompt).operational is False


def _desktop_dispatcher(tmp_path):
    from aether.notifications.dispatcher import NotificationDispatcher
    from aether.notifications.store import NotificationStore

    store = NotificationStore(tmp_path / "n.db")
    return NotificationDispatcher(store=store), store


def _deliver_desktop(dispatcher, title, message):
    from aether.notifications.models import ChannelType, Notification, NotificationChannel, NotificationType

    channel = NotificationChannel(id="ch", workspace_id="ws", channel_type=ChannelType.DESKTOP, name="Desktop", config={"sound_enabled": False})
    notification = Notification(id="n1", workspace_id="ws", type=NotificationType.INSIGHT, title=title, message=message)
    return dispatcher._deliver_desktop(channel, notification)


def test_windows_desktop_notification_is_really_submitted_not_just_reported_queued(tmp_path, monkeypatch):
    import subprocess
    import sys
    from types import SimpleNamespace

    from aether.notifications.models import ChannelType, DeliveryStatus

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("AETHER_DISABLE_DEV_WINDOWS_TOAST", raising=False)
    monkeypatch.delenv("AETHER_DESKTOP_RUNTIME", raising=False)
    monkeypatch.delenv("AETHER_APP_BUNDLE", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "powershell.exe")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["env"] = cmd, kwargs.get("env", {})
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    dispatcher, store = _desktop_dispatcher(tmp_path)
    try:
        status, detail = _deliver_desktop(dispatcher, "Evil'; calc; '", "msg $(whoami)")
    finally:
        store.close()
    assert status == DeliveryStatus.SENT, detail
    script = seen["cmd"][-1]
    assert "calc" not in script and "whoami" not in script, "user text must never be embedded in the script"
    assert seen["env"]["AETHER_TOAST_TITLE"] == "Evil'; calc; '" and seen["env"]["AETHER_TOAST_MESSAGE"] == "msg $(whoami)"
    assert ChannelType.DESKTOP is not None


def test_windows_desktop_notification_failure_is_reported_as_failed(tmp_path, monkeypatch):
    import subprocess
    import sys
    from types import SimpleNamespace

    from aether.notifications.models import DeliveryStatus

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("AETHER_DISABLE_DEV_WINDOWS_TOAST", raising=False)
    monkeypatch.delenv("AETHER_DESKTOP_RUNTIME", raising=False)
    monkeypatch.delenv("AETHER_APP_BUNDLE", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "powershell.exe")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stderr="boom", stdout=""))
    dispatcher, store = _desktop_dispatcher(tmp_path)
    try:
        status, detail = _deliver_desktop(dispatcher, "t", "m")
    finally:
        store.close()
    assert status == DeliveryStatus.FAILED and "boom" in detail


def test_mcp_client_survives_a_chatty_stderr_and_releases_its_pipes(tmp_path):
    """A server logging >64KB to stderr used to block forever on the full pipe; close() also leaked the pipe handles."""
    import sys
    import threading

    from aether.tools.mcp import MCPClient

    server = tmp_path / "chatty_server.py"
    server.write_text(
        "import sys, json\n"
        "sys.stderr.write('x' * 400000 + chr(10)); sys.stderr.flush()\n"
        "for line in sys.stdin:\n"
        "    msg = json.loads(line)\n"
        "    if msg.get('method') == 'initialize':\n"
        "        print(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'serverInfo': {'name': 'chatty'}}}), flush=True)\n"
        "    elif msg.get('method') == 'tools/list':\n"
        "        print(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'tools': []}}), flush=True)\n",
        encoding="utf-8",
    )
    client = MCPClient(command=[sys.executable, str(server)], timeout_seconds=20)
    outcome: dict = {}

    def run():
        try:
            outcome["info"] = client.connect()
            outcome["tools"] = client.list_tools()
        except Exception as exc:  # pragma: no cover - reported by the assertion below
            outcome["error"] = repr(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=20)
    proc = client._process
    try:
        assert not thread.is_alive(), "client hung on the server's stderr output"
        assert outcome.get("info", {}).get("serverInfo", {}).get("name") == "chatty", outcome
        assert outcome["tools"] == []
    finally:
        client.close()
    assert proc is not None and proc.stdout.closed and proc.stderr.closed and proc.poll() is not None


def test_cli_survives_printing_non_ascii_to_a_legacy_codepage_pipe():
    """The frozen Windows runtime crashed at startup printing the banner arrow to a cp1252 pipe."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"}
    out = subprocess.run(
        [sys.executable, "-c", "from aether.cli.main import _ensure_utf8_stdio as f; f(); print(chr(0x25BA), 'ready')"],
        capture_output=True,
        env=env,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
    assert out.stdout.startswith("\u25ba".encode("utf-8"))
