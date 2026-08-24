"""
Unit and Integration Tests for Phase 2: Filesystem Tool Suite.

Validates:
- list_directory: format, types, sizes, hidden sensitive files, errors
- read_file: content reading, non-existent files, directory target error
- write_file: creation, parent directory creation, overwrite, event emission
- patch_file: search & replace, search not found error, event emission
- delete_file: HITL RequireApproval interrupt, confirmation deletion, event emission
- Team & Agent integration: tool registration and preset configuration
"""
import json
import pytest
from pathlib import Path

from aether.coordination.events import EventEmitter, EventType, AgentEvent
from aether.core.interrupts import RequireApproval
from aether.core.security import PathSandbox
from aether.errors import (
    FilesystemToolError,
    FileNotFoundToolError,
    DirectoryNotFoundToolError,
    SecurityBoundaryViolation,
    SensitivePathAccessDenied,
)
from aether.tools.filesystem import create_filesystem_tools
from aether.workspace.workspace import Workspace
from aether.team.team import Team
from aether.team.config import TeamConfig, AgentConfig
from aether.providers.mock import MockProvider


@pytest.fixture
def fs_sandbox(tmp_path):
    """Set up a test sandbox with files and an event emitter."""
    root = tmp_path / "sandbox_files"
    root.mkdir(parents=True, exist_ok=True)
    emitter = EventEmitter()
    sandbox = PathSandbox(root)
    tools_list = create_filesystem_tools(sandbox, emitter=emitter)
    tools = {t.name: t for t in tools_list}
    return sandbox, root, emitter, tools


# ---------------------------------------------------------------------------
# 1. list_directory Tests
# ---------------------------------------------------------------------------

def test_list_directory_empty_and_populated(fs_sandbox):
    sandbox, root, _, tools = fs_sandbox
    list_dir = tools["list_directory"]

    # Empty directory
    res_empty = list_dir.execute(json.dumps({"path": "."}))
    assert "Directory: '.'" in res_empty
    assert "0 items" in res_empty or "(empty directory)" in res_empty

    # Create files and subdirectories
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("hello", encoding="utf-8")
    (root / "README.md").write_text("readme content", encoding="utf-8")
    # Create sensitive file that should be hidden from listing
    (root / ".env").write_text("SECRET=123", encoding="utf-8")

    res_populated = list_dir.execute(json.dumps({"path": "."}))
    assert "src/ (directory)" in res_populated
    assert "README.md (file, 14 bytes)" in res_populated
    assert ".env" not in res_populated  # Sensitive file filtered out

    # List subdirectory
    res_sub = list_dir.execute(json.dumps({"path": "src"}))
    assert "Directory: 'src'" in res_sub
    assert "main.py (file, 5 bytes)" in res_sub


def test_list_directory_errors(fs_sandbox):
    sandbox, root, _, tools = fs_sandbox
    list_dir = tools["list_directory"]

    # Non-existent directory
    with pytest.raises(DirectoryNotFoundToolError):
        list_dir.execute(json.dumps({"path": "does_not_exist"}))

    # Path is a file, not a directory
    (root / "file.txt").write_text("abc", encoding="utf-8")
    with pytest.raises(FilesystemToolError) as exc:
        list_dir.execute(json.dumps({"path": "file.txt"}))
    assert "is a file, not a directory" in str(exc.value)


# ---------------------------------------------------------------------------
# 2. read_file Tests
# ---------------------------------------------------------------------------

def test_read_file_success_and_errors(fs_sandbox):
    sandbox, root, _, tools = fs_sandbox
    read_file = tools["read_file"]

    (root / "hello.txt").write_text("Hello Aether Workforce!", encoding="utf-8")
    content = read_file.execute(json.dumps({"path": "hello.txt"}))
    assert content == "Hello Aether Workforce!"

    # Non-existent file
    with pytest.raises(FileNotFoundToolError):
        read_file.execute(json.dumps({"path": "missing.txt"}))

    # Target is a directory, not a file
    (root / "somedir").mkdir()
    with pytest.raises(FilesystemToolError) as exc:
        read_file.execute(json.dumps({"path": "somedir"}))
    assert "is a directory, not a file" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. write_file Tests
# ---------------------------------------------------------------------------

def test_write_file_creation_and_overwrite(fs_sandbox):
    sandbox, root, emitter, tools = fs_sandbox
    write_file = tools["write_file"]

    events = []
    emitter.on(EventType.FILE_CREATED, lambda e: events.append(e))
    emitter.on(EventType.FILE_MODIFIED, lambda e: events.append(e))

    # 1. Create new file with automatic parent directories
    res_create = write_file.execute(json.dumps({
        "path": "nested/sub/module.py",
        "content": "def run():\n    pass\n"
    }))
    assert "Successfully created file 'nested/sub/module.py'" in res_create
    assert (root / "nested" / "sub" / "module.py").exists()
    assert (root / "nested" / "sub" / "module.py").read_text() == "def run():\n    pass\n"
    assert len(events) == 1
    assert events[0].event_type == EventType.FILE_CREATED
    assert events[0].metadata["path"] == "nested/sub/module.py"

    # 2. Overwrite existing file
    res_update = write_file.execute(json.dumps({
        "path": "nested/sub/module.py",
        "content": "def run():\n    return 42\n"
    }))
    assert "Successfully updated file 'nested/sub/module.py'" in res_update
    assert (root / "nested" / "sub" / "module.py").read_text() == "def run():\n    return 42\n"
    assert len(events) == 2
    assert events[1].event_type == EventType.FILE_MODIFIED


# ---------------------------------------------------------------------------
# 4. patch_file Tests
# ---------------------------------------------------------------------------

def test_patch_file_success_and_errors(fs_sandbox):
    sandbox, root, emitter, tools = fs_sandbox
    patch_file = tools["patch_file"]

    events = []
    emitter.on(EventType.FILE_MODIFIED, lambda e: events.append(e))

    target = root / "script.py"
    target.write_text("name = 'old_name'\nvalue = 100\n", encoding="utf-8")

    # Success patch
    res = patch_file.execute(json.dumps({
        "path": "script.py",
        "search_content": "name = 'old_name'",
        "replace_content": "name = 'new_name'"
    }))
    assert "Successfully patched 'script.py'" in res
    assert target.read_text() == "name = 'new_name'\nvalue = 100\n"
    assert len(events) == 1
    assert events[0].event_type == EventType.FILE_MODIFIED

    # Search content not found
    with pytest.raises(FilesystemToolError) as exc:
        patch_file.execute(json.dumps({
            "path": "script.py",
            "search_content": "non_existent_code()",
            "replace_content": "foo()"
        }))
    assert "Search content not found" in str(exc.value)


# ---------------------------------------------------------------------------
# 5. delete_file & HITL RequireApproval Tests
# ---------------------------------------------------------------------------

def test_delete_file_hitl_approval_and_execution(fs_sandbox):
    sandbox, root, emitter, tools = fs_sandbox
    delete_file = tools["delete_file"]

    events = []
    emitter.on(EventType.FILE_DELETED, lambda e: events.append(e))

    target = root / "to_delete.txt"
    target.write_text("temporary data", encoding="utf-8")

    # 1. Calling without confirmed=True raises RequireApproval
    with pytest.raises(RequireApproval) as exc_info:
        delete_file.execute(json.dumps({"path": "to_delete.txt"}))
    
    interrupt = exc_info.value
    assert "Sei sicuro di voler eliminare" in interrupt.message
    assert interrupt.context.get("action") == "delete_file"
    assert interrupt.context.get("path") == "to_delete.txt"

    # File must NOT be deleted yet!
    assert target.exists()
    assert len(events) == 0

    # 2. Calling with confirmed=True executes deletion
    res_del = delete_file.execute(json.dumps({"path": "to_delete.txt", "confirmed": True}))
    assert "Successfully deleted file 'to_delete.txt'" in res_del
    assert not target.exists()
    assert len(events) == 1
    assert events[0].event_type == EventType.FILE_DELETED


# ---------------------------------------------------------------------------
# 6. Team & Preset Integration Tests
# ---------------------------------------------------------------------------

def test_team_registers_filesystem_tools(tmp_path):
    """Team with sandbox automatically provides filesystem tools to configured agents."""
    ws_files = tmp_path / "files"
    ws_files.mkdir()
    sandbox = PathSandbox(ws_files)

    config = TeamConfig(
        name="dev-team",
        agents=[
            AgentConfig(
                name="dev",
                role="Engineer",
                tools=["list_directory", "write_file", "read_file"]
            )
        ]
    )

    team = Team(config=config, sandbox=sandbox, provider=MockProvider())
    agent = team.get_agent("dev")
    assert agent is not None
    assert "list_directory" in agent.tools
    assert "write_file" in agent.tools
    assert "read_file" in agent.tools
    assert agent.tool_registry.get("write_file") is not None


def test_developer_workforce_preset_has_filesystem_tools(tmp_path):
    """Developer Workforce preset loads with filesystem tools configured."""
    ws_dir = tmp_path / "dev_preset_ws"
    ws = Workspace.init(ws_dir, name="Dev Preset Workspace")
    from aether.presets.applier import PresetApplier
    PresetApplier().apply_preset("developer-workforce", ws)

    team = ws.load_team()
    analyst = team.get_agent("code-analyst")
    writer = team.get_agent("documentation-writer")

    assert analyst is not None
    assert "write_file" in analyst.tools
    assert "read_file" in analyst.tools
    assert "patch_file" in analyst.tools

    assert writer is not None
    assert "delete_file" in writer.tools
    assert "write_file" in writer.tools
