"""
Tests for SkillLoader — directory loading, archive loading, dynamic import,
tool registration, path traversal protection, and permission gating.

All tests use tmp_path (no real filesystem state, no network).
"""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path
from textwrap import dedent

import pytest

from aether.errors import (
    InvalidSkillManifestError,
    InvalidSkillPackageError,
    SkillManifestNotFoundError,
    SkillPermissionDeniedError,
    SkillToolBindingError,
)
from aether.skills.loader import SkillLoader
from aether.skills.policy import SkillPermissionPolicy
from aether.tools.registry import ToolRegistry


# ── Fixtures & helpers ────────────────────────────────────────────────────────


MINIMAL_YAML = dedent("""\
    id: test-skill
    name: Test Skill
    version: 1.0.0
    description: A test skill.
    entrypoint:
      module: tools.mytool
      function: register
    permissions: []
    tools:
      - name: my_tool
        description: Does something.
""")

TOOL_CODE = dedent("""\
    from aether.tools.base import Tool, ToolExecutionContext

    class MyTool(Tool):
        name = "my_tool"
        description = "Does something."
        def execute(self, input_data, context=None):
            return f"result:{input_data}"

    def register(registry, context):
        registry.register(MyTool())
""")

MULTI_TOOL_CODE = dedent("""\
    from aether.tools.base import Tool, ToolExecutionContext

    class ToolA(Tool):
        name = "tool_a"
        description = "Tool A"
        def execute(self, input_data, context=None):
            return "a"

    class ToolB(Tool):
        name = "tool_b"
        description = "Tool B"
        def execute(self, input_data, context=None):
            return "b"

    def register(registry, context):
        registry.register(ToolA())
        registry.register(ToolB())
""")

PERMISSIONED_YAML = dedent("""\
    id: perm-skill
    name: Perm Skill
    version: 1.0.0
    description: Needs filesystem access.
    entrypoint:
      module: tools.mytool
      function: register
    permissions:
      - filesystem.read
    tools:
      - name: my_tool
        description: Reads files.
""")

# A tool whose mere import has a side effect we can detect.
SIDE_EFFECT_CODE = dedent("""\
    import builtins
    builtins._aether_test_imported = True

    from aether.tools.base import Tool

    class SideTool(Tool):
        name = "side_tool"
        description = "Has a side effect."
        def execute(self, input_data, context=None):
            return "side"

    def register(registry, context):
        registry.register(SideTool())
""")


def _make_skill_dir(base: Path, yaml: str = MINIMAL_YAML, tool_code: str = TOOL_CODE) -> Path:
    """Create a well-formed skill directory under *base*."""
    skill_dir = base / "skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "skill.yaml").write_text(yaml, encoding="utf-8")
    tools_dir = skill_dir / "tools"
    tools_dir.mkdir(exist_ok=True)
    (tools_dir / "__init__.py").write_text("", encoding="utf-8")
    (tools_dir / "mytool.py").write_text(tool_code, encoding="utf-8")
    return skill_dir


def _make_zip(base: Path, skill_dir: Path) -> Path:
    archive = base / "skill.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for f in skill_dir.rglob("*"):
            zf.write(f, f.relative_to(skill_dir))
    return archive


def _make_tar(base: Path, skill_dir: Path) -> Path:
    archive = base / "skill.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for f in skill_dir.rglob("*"):
            tf.add(f, arcname=str(f.relative_to(skill_dir)))
    return archive


def _make_aether_skill_zip(base: Path, skill_dir: Path) -> Path:
    archive = base / "skill.aether-skill"
    with zipfile.ZipFile(archive, "w") as zf:
        for f in skill_dir.rglob("*"):
            zf.write(f, f.relative_to(skill_dir))
    return archive


# ── Directory loading ─────────────────────────────────────────────────────────


def test_from_directory_loads_skill(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path)
    registry = ToolRegistry()
    loader = SkillLoader()

    loaded = loader.from_directory(skill_dir, registry)

    assert loaded.skill.name == "Test Skill"
    assert loaded.skill.version == "1.0.0"
    assert loaded.skill.skill_id == "test-skill@1.0.0"
    assert "my_tool" in loaded.registered_tools
    assert loaded.source_path.exists()


def test_from_directory_missing_manifest_raises(tmp_path: Path) -> None:
    skill_dir = tmp_path / "empty"
    skill_dir.mkdir()
    with pytest.raises(SkillManifestNotFoundError):
        SkillLoader().from_directory(skill_dir, ToolRegistry())


def test_from_directory_tool_callable(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path)
    registry = ToolRegistry()
    SkillLoader().from_directory(skill_dir, registry)

    result = registry.execute("my_tool", "hello")
    assert result == "result:hello"


def test_from_directory_registers_multiple_tools(tmp_path: Path) -> None:
    yaml = MINIMAL_YAML.replace("tools:\n  - name: my_tool\n    description: Does something.", 
                                 "tools:\n  - name: tool_a\n  - name: tool_b")
    skill_dir = _make_skill_dir(tmp_path, yaml=yaml, tool_code=MULTI_TOOL_CODE)
    registry = ToolRegistry()
    loaded = SkillLoader().from_directory(skill_dir, registry)

    assert "tool_a" in loaded.registered_tools
    assert "tool_b" in loaded.registered_tools
    assert registry.execute("tool_a", "") == "a"
    assert registry.execute("tool_b", "") == "b"


# ── Archive loading ───────────────────────────────────────────────────────────


def test_from_package_zip(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path / "src")
    archive = _make_zip(tmp_path, skill_dir)
    registry = ToolRegistry()

    loaded = SkillLoader().from_package(archive, registry)

    assert loaded.skill.name == "Test Skill"
    assert "my_tool" in loaded.registered_tools
    assert registry.execute("my_tool", "zip") == "result:zip"


def test_from_package_targz(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path / "src")
    archive = _make_tar(tmp_path, skill_dir)
    registry = ToolRegistry()

    loaded = SkillLoader().from_package(archive, registry)

    assert "my_tool" in loaded.registered_tools


def test_from_package_aether_skill_extension(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path / "src")
    archive = _make_aether_skill_zip(tmp_path, skill_dir)
    registry = ToolRegistry()

    loaded = SkillLoader().from_package(archive, registry)

    assert "my_tool" in loaded.registered_tools


def test_from_package_nonexistent_archive_raises(tmp_path: Path) -> None:
    with pytest.raises(InvalidSkillPackageError, match="not found"):
        SkillLoader().from_package(tmp_path / "nonexistent.zip", ToolRegistry())


def test_from_package_corrupt_zip_raises(tmp_path: Path) -> None:
    bad_zip = tmp_path / "corrupt.zip"
    bad_zip.write_bytes(b"this is not a zip file")
    with pytest.raises(InvalidSkillPackageError):
        SkillLoader().from_package(bad_zip, ToolRegistry())


def test_from_package_unsupported_extension_raises(tmp_path: Path) -> None:
    bad_file = tmp_path / "skill.rar"
    bad_file.write_bytes(b"Rar!")  # not zip/tar
    with pytest.raises(InvalidSkillPackageError, match="Unsupported"):
        SkillLoader().from_package(bad_file, ToolRegistry())


# ── Path traversal protection ─────────────────────────────────────────────────


def test_zip_path_traversal_rejected(tmp_path: Path) -> None:
    """Verify that a ZIP with a ../ entry is rejected before extraction."""
    evil_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil_zip, "w") as zf:
        zf.writestr("../evil_file.txt", "pwned")
    with pytest.raises(InvalidSkillPackageError, match="traversal"):
        SkillLoader().from_package(evil_zip, ToolRegistry())


def test_tar_path_traversal_rejected(tmp_path: Path) -> None:
    """Verify that a tar with a ../ entry is rejected before extraction."""
    evil_tar = tmp_path / "evil.tar.gz"
    content = b"pwned"
    info = tarfile.TarInfo(name="../evil_file.txt")
    info.size = len(content)
    with tarfile.open(evil_tar, "w:gz") as tf:
        tf.addfile(info, io.BytesIO(content))
    with pytest.raises(InvalidSkillPackageError, match="traversal"):
        SkillLoader().from_package(evil_tar, ToolRegistry())


# ── Permission gating ─────────────────────────────────────────────────────────


def test_permission_denied_blocks_skill_load(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path, yaml=PERMISSIONED_YAML)
    policy = SkillPermissionPolicy(denied={"filesystem.read"})
    with pytest.raises(SkillPermissionDeniedError, match="filesystem.read"):
        SkillLoader(permission_policy=policy).from_directory(skill_dir, ToolRegistry())


def test_permission_denied_before_code_import(tmp_path: Path) -> None:
    """
    Critical: verify that skill code is NOT imported when a permission is denied.

    The SIDE_EFFECT_CODE sets builtins._aether_test_imported = True on import.
    If the import runs, the sentinel will be set. If the permission check blocks
    loading first, the sentinel stays unset.
    """
    import builtins

    # Clean up any pre-existing sentinel.
    if hasattr(builtins, "_aether_test_imported"):
        del builtins._aether_test_imported

    yaml = PERMISSIONED_YAML.replace("tools:\n  - name: my_tool\n    description: Reads files.",
                                      "tools:\n  - name: side_tool\n    description: Has side effect.")
    yaml = yaml.replace("module: tools.mytool", "module: tools.sidetool")
    skill_dir = tmp_path / "side_skill"
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text(yaml, encoding="utf-8")
    tools_dir = skill_dir / "tools"
    tools_dir.mkdir()
    (tools_dir / "__init__.py").write_text("", encoding="utf-8")
    (tools_dir / "sidetool.py").write_text(SIDE_EFFECT_CODE, encoding="utf-8")

    policy = SkillPermissionPolicy(denied={"filesystem.read"})

    with pytest.raises(SkillPermissionDeniedError):
        SkillLoader(permission_policy=policy).from_directory(skill_dir, ToolRegistry())

    # The sentinel must NOT have been set — code was not imported.
    assert not hasattr(builtins, "_aether_test_imported"), (
        "Skill code was imported BEFORE permission check — this is a bug!"
    )


def test_permission_allowed_loads_skill(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path, yaml=PERMISSIONED_YAML)
    policy = SkillPermissionPolicy(allowed={"filesystem.read"})
    registry = ToolRegistry()
    loaded = SkillLoader(permission_policy=policy).from_directory(skill_dir, registry)
    assert loaded.skill.name == "Perm Skill"


# ── Tool binding errors ───────────────────────────────────────────────────────


def test_missing_register_function_raises(tmp_path: Path) -> None:
    no_register = "# no register function here\n"
    skill_dir = _make_skill_dir(tmp_path, tool_code=no_register)
    with pytest.raises(SkillToolBindingError, match="register"):
        SkillLoader().from_directory(skill_dir, ToolRegistry())


def test_register_raises_wraps_as_binding_error(tmp_path: Path) -> None:
    bad_register = dedent("""\
        def register(registry, context):
            raise RuntimeError("deliberate failure")
    """)
    skill_dir = _make_skill_dir(tmp_path, tool_code=bad_register)
    with pytest.raises(SkillToolBindingError, match="deliberate failure"):
        SkillLoader().from_directory(skill_dir, ToolRegistry())
