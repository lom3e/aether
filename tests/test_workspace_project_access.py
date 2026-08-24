"""
Tests for Phase 6: Workspace Project Access.

Validates:
1. Workspace without project root defaults to <workspace>/files/ (legacy compatibility).
2. Workspace with configured project root points sandbox to project root.
3. Persistence of project root in aether.yaml across Workspace reloads.
4. Filesystem tools operate correctly within the connected project root.
5. Directory traversal outside project root is strictly blocked.
6. Symlink escape outside project root is blocked.
7. Sensitive paths inside project root (.env, .git, .venv, etc.) are protected.
8. Filesystem events emit relative paths (no host absolute paths).
9. Disconnecting project reverts cleanly to <workspace>/files/.
10. Non-existent project directory is handled gracefully without crash.
11. REST API endpoints (GET /workspace/project, POST /workspace/project, DELETE /workspace/project).
12. Agent context instructions include workspace project guidance when filesystem tools are present.
"""
import os
import json
import tempfile
from pathlib import Path
import pytest
from starlette.requests import Request
from fastapi import HTTPException

from aether.workspace.workspace import Workspace
from aether.tools.filesystem import create_filesystem_tools
from aether.errors import (
    FilesystemToolError,
    SecurityBoundaryViolation,
    SensitivePathAccessDenied,
)
from aether.coordination.events import EventEmitter, AgentEvent, EventType
from aether.presets.applier import PresetApplier
from aether.server.app import app
from aether.server.routes import (
    get_workspace,
    get_workspace_project,
    connect_workspace_project,
    disconnect_workspace_project,
    ProjectConfigRequest,
)
from aether.agents.agent import Agent
from aether.core.execution import Task, ExecutionContext
from aether.providers.mock import MockProvider


@pytest.fixture
def clean_workspace(tmp_path):
    ws_dir = tmp_path / "test_ws"
    ws = Workspace.init(ws_dir, name="Test WS")
    PresetApplier().apply_preset("starter-workforce", ws)
    return ws


@pytest.fixture
def external_project(tmp_path):
    proj_dir = tmp_path / "my_external_project"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "src").mkdir()
    (proj_dir / "src" / "main.py").write_text("print('Hello from project')\n", encoding="utf-8")
    (proj_dir / "README.md").write_text("# My External Project\n", encoding="utf-8")
    return proj_dir


def test_workspace_without_project_root_legacy_behavior(clean_workspace):
    """Workspace without project root defaults to <workspace>/files/."""
    assert clean_workspace.project_path is None
    assert clean_workspace.project_info is None
    assert clean_workspace.sandbox.root == clean_workspace.files_dir
    assert clean_workspace.sandbox.root.exists()


def test_workspace_with_project_root_and_persistence(clean_workspace, external_project):
    """Connecting a project configures sandbox.root and persists to aether.yaml."""
    clean_workspace.set_project(external_project, project_type="local", name="My Project")

    assert clean_workspace.project_path == external_project.resolve()
    info = clean_workspace.project_info
    assert info is not None
    assert info["type"] == "local"
    assert info["name"] == "My Project"
    assert info["exists"] is True
    assert info["path"] == str(external_project.resolve())
    assert clean_workspace.sandbox.root == external_project.resolve()

    # Verify persistence by reloading a new Workspace instance from same dir
    reloaded_ws = Workspace(clean_workspace.root)
    assert reloaded_ws.project_path == external_project.resolve()
    assert reloaded_ws.sandbox.root == external_project.resolve()
    assert reloaded_ws.project_info["exists"] is True


def test_workspace_nonexistent_project_directory(clean_workspace, tmp_path):
    """A deleted/missing project directory does not crash and falls back gracefully."""
    missing_dir = tmp_path / "non_existent_folder_xyz"
    clean_workspace.set_project(missing_dir, project_type="local", name="Ghost Project")

    # project_path returns None because directory does not exist
    assert clean_workspace.project_path is None

    # project_info reports exists: False with descriptive error
    info = clean_workspace.project_info
    assert info is not None
    assert info["exists"] is False
    assert "error" in info

    # sandbox seamlessly falls back to <workspace>/files/
    assert clean_workspace.sandbox.root == clean_workspace.files_dir
    assert clean_workspace.sandbox.root.exists()


def test_workspace_disconnect_project(clean_workspace, external_project):
    """Disconnecting project root reverts cleanly to <workspace>/files/."""
    clean_workspace.set_project(external_project)
    assert clean_workspace.project_path == external_project.resolve()

    # Disconnect
    clean_workspace.set_project(None)
    assert clean_workspace.project_path is None
    assert clean_workspace.project_info is None
    assert clean_workspace.sandbox.root == clean_workspace.files_dir


def test_filesystem_tools_operate_on_project_root(clean_workspace, external_project):
    """Filesystem tools read, write, patch, delete files within connected project root."""
    clean_workspace.set_project(external_project)
    sandbox = clean_workspace.sandbox
    tools = {t.name: t for t in create_filesystem_tools(sandbox)}

    # 1. list_directory
    listing = tools["list_directory"].execute(json.dumps({"path": "."}))
    assert "src" in listing
    assert "README.md" in listing

    # 2. read_file
    read_content = tools["read_file"].execute(json.dumps({"path": "src/main.py"}))
    assert "print('Hello from project')" in read_content

    # 3. write_file
    write_res = tools["write_file"].execute(json.dumps({
        "path": "src/utils.py",
        "content": "def add(a, b): return a + b\n"
    }))
    assert "Successfully created file 'src/utils.py'" in write_res
    assert (external_project / "src" / "utils.py").exists()

    # 4. patch_file
    patch_res = tools["patch_file"].execute(json.dumps({
        "path": "src/utils.py",
        "search_content": "return a + b",
        "replace_content": "return a + b  # optimized"
    }))
    assert "Successfully patched" in patch_res
    assert "# optimized" in (external_project / "src" / "utils.py").read_text()

    # 5. delete_file (with confirmed=True)
    del_res = tools["delete_file"].execute(json.dumps({
        "path": "src/utils.py",
        "confirmed": True
    }))
    assert "Successfully deleted file 'src/utils.py'" in del_res
    assert not (external_project / "src" / "utils.py").exists()


def test_security_traversal_blocked_in_project_root(clean_workspace, external_project, tmp_path):
    """Directory traversal out of project root is strictly blocked."""
    clean_workspace.set_project(external_project)
    sandbox = clean_workspace.sandbox
    tools = {t.name: t for t in create_filesystem_tools(sandbox)}

    with pytest.raises(SecurityBoundaryViolation):
        tools["read_file"].execute(json.dumps({"path": "../../some_secret.txt"}))


def test_security_symlink_escape_blocked_in_project_root(clean_workspace, external_project, tmp_path):
    """Symlink pointing outside project root is blocked."""
    outside_file = tmp_path / "outside_target.txt"
    outside_file.write_text("SECRET DATA OUTSIDE", encoding="utf-8")

    link_path = external_project / "symlink_escape.txt"
    try:
        os.symlink(outside_file, link_path)
    except OSError:
        pytest.skip("Symlinks not supported on this filesystem")

    clean_workspace.set_project(external_project)
    sandbox = clean_workspace.sandbox
    tools = {t.name: t for t in create_filesystem_tools(sandbox)}

    with pytest.raises(SecurityBoundaryViolation):
        tools["read_file"].execute(json.dumps({"path": "symlink_escape.txt"}))


def test_security_sensitive_paths_protected_in_project_root(clean_workspace, external_project):
    """Sensitive files (.env, .git, id_rsa) in project root are blocked."""
    (external_project / ".env").write_text("API_SECRET=12345", encoding="utf-8")
    clean_workspace.set_project(external_project)
    sandbox = clean_workspace.sandbox
    tools = {t.name: t for t in create_filesystem_tools(sandbox)}

    with pytest.raises(SensitivePathAccessDenied):
        tools["read_file"].execute(json.dumps({"path": ".env"}))


def test_filesystem_events_use_relative_paths(clean_workspace, external_project):
    """Filesystem tool events emit relative project paths without leaking host paths."""
    clean_workspace.set_project(external_project)
    sandbox = clean_workspace.sandbox
    emitter = EventEmitter()
    captured_events = []
    emitter.on(EventType.FILE_CREATED, lambda e: captured_events.append(e))

    tools = {t.name: t for t in create_filesystem_tools(sandbox, emitter=emitter)}
    tools["write_file"].execute(json.dumps({"path": "docs/guide.md", "content": "# Guide\n"}))

    file_events = [e for e in captured_events if e.event_type == EventType.FILE_CREATED]
    assert len(file_events) == 1
    event_path = file_events[0].metadata.get("path")
    assert event_path == "docs/guide.md"
    assert str(external_project) not in event_path


@pytest.mark.asyncio
async def test_rest_api_workspace_project_lifecycle(clean_workspace, external_project):
    """Test GET, POST, DELETE /workspace/project API endpoints."""
    app.state.workspace = clean_workspace
    app.state.team = clean_workspace.load_team()
    app.state.active_team_name = "starter-workforce"
    app.state.session_token = None

    req = Request({"type": "http", "app": app, "headers": [], "path": "/api/workspace/project", "method": "GET"})

    # 1. GET initial state (None)
    data = await get_workspace_project(req)
    assert data["project"] is None

    # 2. POST connect valid project
    post_req = Request({"type": "http", "app": app, "headers": [], "path": "/api/workspace/project", "method": "POST"})
    res = await connect_workspace_project(
        post_req,
        ProjectConfigRequest(path=str(external_project), project_type="local", name="API Project")
    )
    assert res["status"] == "ok"
    assert res["project"]["name"] == "API Project"
    assert res["project"]["exists"] is True

    # 3. GET workspace includes project info
    ws_info = await get_workspace(req)
    assert ws_info.project["name"] == "API Project"
    assert ws_info.project["exists"] is True

    # 4. POST non-existent directory returns 422
    with pytest.raises(HTTPException) as exc_info:
        await connect_workspace_project(
            post_req,
            ProjectConfigRequest(path="/non/existent/path/xyz_123")
        )
    assert exc_info.value.status_code == 422

    # 5. DELETE disconnects project
    del_res = await disconnect_workspace_project(req)
    assert del_res["status"] == "ok"
    assert del_res["project"] is None

    # Verify workspace sandbox reverted
    assert app.state.workspace.project_path is None


def test_agent_context_includes_project_guidance():
    """Agents equipped with filesystem tools receive workspace project guidance."""
    agent = Agent(
        name="coder",
        role="Software Engineer",
        provider=MockProvider(),
    )
    agent.tools = ["list_directory", "read_file", "write_file"]
    task = Task(id="t1", instruction="Write a new feature")
    ctx = ExecutionContext(task=task, agent_name=agent.name)
    messages = agent._build_messages(task, ctx, [])

    contents = [m.content for m in messages if m.role == "system"]
    assert any("workspace project environment is connected" in c for c in contents)
    assert any("relative paths" in c for c in contents)
