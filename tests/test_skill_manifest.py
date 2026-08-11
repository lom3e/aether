"""Tests for SkillManifest — parsing, validation, and conversion."""

from __future__ import annotations

import pytest

from aether.errors import InvalidSkillManifestError, SkillManifestNotFoundError
from aether.skills.manifest import (
    SkillManifest,
    SkillManifestEntrypoint,
    SkillManifestTool,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _valid_data() -> dict:
    return {
        "id": "hello-skill",
        "name": "Hello Skill",
        "version": "1.0.0",
        "description": "A test skill.",
        "entrypoint": {"module": "tools.hello", "function": "register"},
        "permissions": [],
        "tools": [{"name": "say_hello", "description": "Says hello."}],
    }


def _write_manifest(directory, content: str) -> None:
    (directory / "skill.yaml").write_text(content, encoding="utf-8")


# ── Valid manifest ────────────────────────────────────────────────────────────


def test_valid_manifest_from_dict() -> None:
    manifest = SkillManifest.from_dict(_valid_data())
    assert manifest.id == "hello-skill"
    assert manifest.name == "Hello Skill"
    assert manifest.version == "1.0.0"
    assert manifest.description == "A test skill."
    assert manifest.entrypoint.module == "tools.hello"
    assert manifest.entrypoint.function == "register"
    assert manifest.permissions == []
    assert len(manifest.tools) == 1
    assert manifest.tools[0].name == "say_hello"


def test_valid_manifest_default_entrypoint_function() -> None:
    data = _valid_data()
    del data["entrypoint"]["function"]
    manifest = SkillManifest.from_dict(data)
    assert manifest.entrypoint.function == "register"


def test_valid_manifest_with_permissions() -> None:
    data = _valid_data()
    data["permissions"] = ["filesystem.read", "network.connect"]
    manifest = SkillManifest.from_dict(data)
    assert len(manifest.permissions) == 2


def test_valid_manifest_empty_tools() -> None:
    data = _valid_data()
    data["tools"] = []
    manifest = SkillManifest.from_dict(data)
    assert manifest.tools == []


def test_valid_manifest_from_path(tmp_path) -> None:
    yaml_content = """\
id: test-skill
name: Test Skill
version: 2.1.3
description: Testing from path.
entrypoint:
  module: mymod
  function: setup
permissions: []
tools: []
"""
    _write_manifest(tmp_path, yaml_content)
    manifest = SkillManifest.from_path(tmp_path)
    assert manifest.id == "test-skill"
    assert manifest.version == "2.1.3"
    assert manifest.entrypoint.function == "setup"


# ── Missing required fields ───────────────────────────────────────────────────


@pytest.mark.parametrize("field", ["id", "name", "version", "description", "entrypoint"])
def test_missing_required_field_raises(field: str) -> None:
    data = _valid_data()
    del data[field]
    with pytest.raises(InvalidSkillManifestError, match=field):
        SkillManifest.from_dict(data)


def test_missing_permissions_field_raises() -> None:
    data = _valid_data()
    del data["permissions"]
    with pytest.raises(InvalidSkillManifestError, match="permissions"):
        SkillManifest.from_dict(data)


def test_missing_tools_field_raises() -> None:
    data = _valid_data()
    del data["tools"]
    with pytest.raises(InvalidSkillManifestError, match="tools"):
        SkillManifest.from_dict(data)


def test_missing_entrypoint_module_raises() -> None:
    data = _valid_data()
    del data["entrypoint"]["module"]
    with pytest.raises(InvalidSkillManifestError, match="module"):
        SkillManifest.from_dict(data)


# ── Invalid field values ──────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_id", [
    "Hello",          # uppercase
    "1bad",           # starts with digit
    "-bad",           # starts with hyphen
    "bad_skill",      # underscore not allowed
    "bad skill",      # space
    "",               # empty
])
def test_invalid_id_raises(bad_id: str) -> None:
    data = _valid_data()
    data["id"] = bad_id
    with pytest.raises(InvalidSkillManifestError, match="id"):
        SkillManifest.from_dict(data)


@pytest.mark.parametrize("bad_version", [
    "1.0",            # missing patch
    "1.0.0.0",        # extra segment
    "v1.0.0",         # v-prefix
    "1.0.0-alpha",    # pre-release tag
    "latest",         # not semver
    "",               # empty
])
def test_invalid_version_raises(bad_version: str) -> None:
    data = _valid_data()
    data["version"] = bad_version
    with pytest.raises(InvalidSkillManifestError, match="version"):
        SkillManifest.from_dict(data)


def test_invalid_entrypoint_module_raises() -> None:
    data = _valid_data()
    data["entrypoint"]["module"] = "1invalid"
    with pytest.raises(InvalidSkillManifestError):
        SkillManifest.from_dict(data)


def test_empty_name_raises() -> None:
    data = _valid_data()
    data["name"] = "  "
    with pytest.raises(InvalidSkillManifestError, match="name"):
        SkillManifest.from_dict(data)


def test_empty_description_raises() -> None:
    data = _valid_data()
    data["description"] = ""
    with pytest.raises(InvalidSkillManifestError, match="description"):
        SkillManifest.from_dict(data)


# ── Malformed YAML ────────────────────────────────────────────────────────────


def test_malformed_yaml_raises(tmp_path) -> None:
    _write_manifest(tmp_path, "id: [\nbad yaml {{{{")
    with pytest.raises(InvalidSkillManifestError):
        SkillManifest.from_path(tmp_path)


def test_yaml_not_a_mapping_raises(tmp_path) -> None:
    _write_manifest(tmp_path, "- item1\n- item2\n")
    with pytest.raises(InvalidSkillManifestError):
        SkillManifest.from_path(tmp_path)


# ── Missing manifest file ─────────────────────────────────────────────────────


def test_missing_manifest_raises(tmp_path) -> None:
    with pytest.raises(SkillManifestNotFoundError):
        SkillManifest.from_path(tmp_path)


# ── to_skill() ────────────────────────────────────────────────────────────────


def test_to_skill_builds_skill_object() -> None:
    data = _valid_data()
    data["permissions"] = ["filesystem.read"]
    manifest = SkillManifest.from_dict(data)
    skill = manifest.to_skill()
    assert skill.name == "Hello Skill"
    assert skill.version == "1.0.0"
    assert skill.skill_id == "hello-skill@1.0.0"
    assert len(skill.permissions) == 1
    assert skill.permissions[0].identifier == "filesystem.read"
