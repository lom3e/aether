"""
Comprehensive security tests for Phase 1: Filesystem Sandbox & Security Boundary.

Validates:
- Root directory anchoring
- Canonical path resolution via realpath
- Directory traversal attacks (../, nested ../, absolute paths)
- Symlink escapes
- Sensitive path blacklist (.env*, .git, credentials, keys, node_modules, .venv, etc.)
- Operation policies (destructive actions on root, must_exist validations)
- Exception hierarchy conformance
"""
import os
import pytest
from pathlib import Path

from aether.core.security import PathSandbox, OperationType
from aether.errors import (
    SecurityError,
    SecurityBoundaryViolation,
    SensitivePathAccessDenied,
    FilesystemToolError,
    FileNotFoundToolError,
    DirectoryNotFoundToolError,
)
from aether.workspace.workspace import Workspace


@pytest.fixture
def sandbox_env(tmp_path):
    """Create a temporary sandbox root with test files and directories."""
    sandbox_root = tmp_path / "workspace_files"
    sandbox_root.mkdir(parents=True, exist_ok=True)
    
    # Create valid files
    (sandbox_root / "src").mkdir()
    (sandbox_root / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (sandbox_root / "docs").mkdir()
    (sandbox_root / "docs" / "index.md").write_text("# Docs", encoding="utf-8")
    (sandbox_root / "README.md").write_text("# Readme", encoding="utf-8")

    # Create outside sensitive target for symlink testing
    outside_dir = tmp_path / "outside_system"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("system-secret-data", encoding="utf-8")

    sandbox = PathSandbox(sandbox_root)
    return sandbox, sandbox_root, outside_dir


def test_exception_hierarchy():
    """Verify security exceptions inherit from unified Aether error model."""
    assert issubclass(SecurityError, Exception)
    assert issubclass(SecurityBoundaryViolation, SecurityError)
    assert issubclass(SensitivePathAccessDenied, SecurityError)
    assert issubclass(FilesystemToolError, Exception)
    assert issubclass(FileNotFoundToolError, FilesystemToolError)
    assert issubclass(DirectoryNotFoundToolError, FilesystemToolError)


def test_valid_paths_resolve_correctly(sandbox_env):
    """Valid relative paths inside the sandbox resolve to canonical Paths."""
    sandbox, sandbox_root, _ = sandbox_env

    # Root
    assert sandbox.resolve("") == sandbox_root
    assert sandbox.resolve(".") == sandbox_root

    # Top-level file
    p1 = sandbox.resolve("README.md")
    assert p1 == sandbox_root / "README.md"
    assert p1.exists()

    # Nested file
    p2 = sandbox.resolve("src/main.py")
    assert p2 == sandbox_root / "src" / "main.py"
    assert p2.exists()

    # Deep nested path to be created
    p3 = sandbox.resolve("src/modules/submodule/app.py")
    assert p3 == sandbox_root / "src" / "modules" / "submodule" / "app.py"


def test_traversal_attacks_blocked(sandbox_env):
    """Attempting directory traversal using ../ must raise SecurityBoundaryViolation."""
    sandbox, sandbox_root, _ = sandbox_env

    attack_paths = [
        "../",
        "../../",
        "../../../etc/passwd",
        "src/../../outside.txt",
        "src/../..",
        "docs/../../..",
        "./../../",
        "src/./../../etc/hosts",
    ]

    for bad_path in attack_paths:
        with pytest.raises(SecurityBoundaryViolation) as exc_info:
            sandbox.resolve(bad_path)
        assert "violates sandbox boundary" in str(exc_info.value) or "outside sandbox root" in str(exc_info.value)


def test_absolute_paths_anchored_or_rejected(sandbox_env):
    """Absolute paths are safely anchored to sandbox root or rejected if escaping."""
    sandbox, sandbox_root, _ = sandbox_env

    # When stripped of leading slashes, '/etc/passwd' -> 'etc/passwd' under sandbox_root
    p = sandbox.resolve("/src/main.py")
    assert p == sandbox_root / "src" / "main.py"

    # Absolute traversal attempts
    with pytest.raises(SecurityBoundaryViolation):
        sandbox.resolve("/../../../etc/passwd")


def test_null_byte_injection_blocked(sandbox_env):
    """Paths containing null bytes must be immediately rejected."""
    sandbox, _, _ = sandbox_env

    with pytest.raises(SecurityBoundaryViolation) as exc:
        sandbox.resolve("src/main.py\0.jpg")
    assert "null byte" in str(exc.value)


def test_symlink_escape_blocked(sandbox_env):
    """Symlinks pointing outside sandbox root must raise SecurityBoundaryViolation."""
    sandbox, sandbox_root, outside_dir = sandbox_env

    # Create symlink pointing outside
    outside_file = outside_dir / "secret.txt"
    symlink_path = sandbox_root / "leak_link"
    
    try:
        symlink_path.symlink_to(outside_file)
    except OSError:
        pytest.skip("Symlinks not supported on this filesystem")

    with pytest.raises(SecurityBoundaryViolation) as exc_info:
        sandbox.resolve("leak_link")
    assert "resolves outside sandbox root" in str(exc_info.value) or "points outside sandbox boundary" in str(exc_info.value) or "violates sandbox boundary" in str(exc_info.value)


def test_internal_symlink_allowed(sandbox_env):
    """Symlinks pointing within the sandbox are valid and allowed."""
    sandbox, sandbox_root, _ = sandbox_env

    target_file = sandbox_root / "src" / "main.py"
    internal_link = sandbox_root / "main_link.py"

    try:
        internal_link.symlink_to(target_file)
    except OSError:
        pytest.skip("Symlinks not supported on this filesystem")

    resolved = sandbox.resolve("main_link.py")
    assert resolved == target_file.resolve()


def test_sensitive_files_blacklisted(sandbox_env):
    """Accessing blacklisted sensitive files must raise SensitivePathAccessDenied."""
    sandbox, sandbox_root, _ = sandbox_env

    sensitive_attempts = [
        ".env",
        ".env.local",
        ".env.production",
        ".envrc",
        ".git",
        ".git/config",
        ".git/HEAD",
        "sub/.git/config",
        ".svn/entries",
        ".hg/store",
        "node_modules/axios/index.js",
        ".venv/bin/python",
        "__pycache__/module.cpython-311.pyc",
        ".pytest_cache/v/cache/nodeids",
        ".tox/py39/bin/pytest",
        "aws_credentials.json",
        "credentials.txt",
        "id_rsa",
        "id_rsa.pub",
        "id_ed25519",
        "server.pem",
        "private.key",
        "cert.pfx",
        "cert.p12",
        ".DS_Store",
        "database.db",
        "app.db-wal",
    ]

    for sensitive_path in sensitive_attempts:
        with pytest.raises(SensitivePathAccessDenied) as exc_info:
            sandbox.validate_path(sensitive_path)
        assert "matches protected sensitive pattern" in str(exc_info.value)


def test_operation_policies(sandbox_env):
    """Verify operation policies (must_exist, delete root, list directory)."""
    sandbox, sandbox_root, _ = sandbox_env

    # 1. Existing file with must_exist=True
    valid_file = sandbox.validate_path("src/main.py", operation=OperationType.READ, must_exist=True)
    assert valid_file.exists()

    # 2. Non-existing file with must_exist=True -> FileNotFoundToolError
    with pytest.raises(FileNotFoundToolError) as exc:
        sandbox.validate_path("non_existing.txt", operation=OperationType.READ, must_exist=True)
    assert "File not found" in str(exc.value)

    # 3. Non-existing directory with must_exist=True on LIST -> DirectoryNotFoundToolError
    with pytest.raises(DirectoryNotFoundToolError) as exc:
        sandbox.validate_path("non_existing_dir", operation=OperationType.LIST, must_exist=True)
    assert "Directory not found" in str(exc.value)

    # 4. Destructive operation on sandbox root itself -> Blocked
    with pytest.raises(SecurityBoundaryViolation) as exc:
        sandbox.validate_path(".", operation=OperationType.DELETE)
    assert "Cannot perform destructive operation" in str(exc.value)

    with pytest.raises(SecurityBoundaryViolation):
        sandbox.validate_path(".", operation=OperationType.WRITE)

    with pytest.raises(SecurityBoundaryViolation):
        sandbox.validate_path(".", operation=OperationType.PATCH)


def test_relative_path_formatting(sandbox_env):
    """get_relative_path formats paths safely relative to sandbox root without leaking host paths."""
    sandbox, sandbox_root, _ = sandbox_env

    assert sandbox.get_relative_path(sandbox_root) == "."
    assert sandbox.get_relative_path(sandbox_root / "src" / "main.py") == "src/main.py"
    assert sandbox.get_relative_path("src/main.py") == "src/main.py"


def test_is_safe_helper(sandbox_env):
    """is_safe returns boolean without raising exceptions."""
    sandbox, _, _ = sandbox_env

    assert sandbox.is_safe("src/main.py") is True
    assert sandbox.is_safe("../etc/passwd") is False
    assert sandbox.is_safe(".env") is False
    assert sandbox.is_safe(".git/config") is False


def test_workspace_files_dir_and_sandbox_integration(tmp_path):
    """Workspace instance automatically scaffolds files_dir and exposes sandbox."""
    ws_dir = tmp_path / "my_project_ws"
    ws = Workspace.init(ws_dir, name="Test Filesystem Workspace")

    assert ws.files_dir.exists()
    assert ws.files_dir.name == "files"
    assert ws.sandbox is not None
    assert ws.sandbox.root == ws.files_dir.resolve()

    # Writing within workspace sandbox
    test_target = ws.sandbox.validate_path("hello.py", operation=OperationType.WRITE)
    test_target.write_text("print('aether')", encoding="utf-8")
    assert test_target.exists()
    assert (ws.files_dir / "hello.py").exists()

    # Traversal from workspace sandbox blocked
    with pytest.raises(SecurityBoundaryViolation):
        ws.sandbox.validate_path("../aether.yaml", operation=OperationType.READ)
