"""
Skill manifest — parsing and validation of skill.yaml.

This module owns:
  - SkillManifest: the parsed, validated view of a skill.yaml file.
  - SkillManifestEntrypoint: describes the Python module/function to call.
  - SkillManifestTool: describes a tool declared in the manifest.

YAML parsing requires PyYAML. If it is not installed, an ImportError with
a clear installation message is raised at load time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aether.errors import InvalidSkillManifestError, SkillManifestNotFoundError
from aether.skills.skill import Skill, SkillPermission

# ── Optional YAML dependency ─────────────────────────────────────────────────

try:
    import yaml as _yaml  # PyYAML

    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False

_MANIFEST_FILENAME = "skill.yaml"

# Regex for valid skill IDs: lowercase letters, digits, hyphens; must start with a letter.
_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# Strict semver: MAJOR.MINOR.PATCH (integers only, no pre-release/build metadata).
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Valid Python dotted identifier (e.g. "tools.example" or "my_module.sub")
_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class SkillManifestEntrypoint:
    """Describes the Python module and callable that registers skill tools."""

    module: str
    function: str = "register"

    def __post_init__(self) -> None:
        self.module = self.module.strip()
        self.function = self.function.strip() or "register"

    def validate(self) -> None:
        if not self.module:
            raise InvalidSkillManifestError(
                "entrypoint.module must be a non-empty dotted Python module path."
            )
        if not _MODULE_RE.match(self.module):
            raise InvalidSkillManifestError(
                f"entrypoint.module {self.module!r} is not a valid Python module path "
                "(use dotted identifiers, e.g. 'tools.example')."
            )
        if not self.function:
            raise InvalidSkillManifestError(
                "entrypoint.function must be a non-empty identifier."
            )


@dataclass
class SkillManifestTool:
    """A tool declared in the skill manifest."""

    name: str
    description: str = ""

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.description = self.description.strip()

    def validate(self) -> None:
        if not self.name:
            raise InvalidSkillManifestError("Each tool declaration must have a non-empty 'name'.")


@dataclass
class SkillManifest:
    """
    The parsed and validated representation of a skill.yaml file.

    Use :meth:`from_path` or :meth:`from_dict` to construct instances.
    Call :meth:`validate` to enforce all invariants.
    """

    id: str
    name: str
    version: str
    description: str
    entrypoint: SkillManifestEntrypoint
    permissions: list[str] = field(default_factory=list)
    tools: list[SkillManifestTool] = field(default_factory=list)

    # ── Constructors ─────────────────────────────────────────────────────────

    @classmethod
    def from_path(cls, directory: Path) -> "SkillManifest":
        """
        Load and parse the skill.yaml from *directory*.

        Raises:
            SkillManifestNotFoundError: if skill.yaml is not found.
            InvalidSkillManifestError: if the YAML is malformed or fields invalid.
        """
        if not _HAS_YAML:
            raise ImportError(
                "PyYAML is required to load skill manifests. "
                "Install it with: pip install pyyaml"
            )

        manifest_path = directory / _MANIFEST_FILENAME
        if not manifest_path.exists():
            raise SkillManifestNotFoundError(
                f"skill.yaml not found in {directory}. "
                "Every skill directory must contain a skill.yaml manifest."
            )

        try:
            raw = manifest_path.read_text(encoding="utf-8")
            data = _yaml.safe_load(raw)
        except Exception as exc:
            raise InvalidSkillManifestError(
                f"Failed to parse skill.yaml in {directory}: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise InvalidSkillManifestError(
                f"skill.yaml in {directory} must be a YAML mapping, got {type(data).__name__}."
            )

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillManifest":
        """
        Build a SkillManifest from a raw dict (already parsed from YAML).

        Raises:
            InvalidSkillManifestError: on missing or invalid fields.
        """
        _require(data, "id")
        _require(data, "name")
        _require(data, "version")
        _require(data, "description")
        _require(data, "entrypoint")

        ep_raw = data["entrypoint"]
        if not isinstance(ep_raw, dict):
            raise InvalidSkillManifestError(
                "'entrypoint' must be a mapping with at least a 'module' key."
            )
        if "module" not in ep_raw:
            raise InvalidSkillManifestError("entrypoint.module is required.")

        entrypoint = SkillManifestEntrypoint(
            module=str(ep_raw.get("module", "")),
            function=str(ep_raw.get("function", "register")),
        )

        raw_permissions = data.get("permissions")
        if raw_permissions is None:
            raise InvalidSkillManifestError(
                "'permissions' key is required (use an empty list [] if the skill needs no permissions)."
            )
        if not isinstance(raw_permissions, list):
            raise InvalidSkillManifestError("'permissions' must be a list.")
        permissions = [str(p) for p in raw_permissions]

        raw_tools = data.get("tools")
        if raw_tools is None:
            raise InvalidSkillManifestError(
                "'tools' key is required (use an empty list [] if the skill provides no tools)."
            )
        if not isinstance(raw_tools, list):
            raise InvalidSkillManifestError("'tools' must be a list.")

        tools = []
        for item in raw_tools:
            if not isinstance(item, dict) or "name" not in item:
                raise InvalidSkillManifestError(
                    "Each entry in 'tools' must be a mapping with at least a 'name' key."
                )
            tools.append(SkillManifestTool(
                name=str(item["name"]),
                description=str(item.get("description", "")),
            ))

        manifest = cls(
            id=str(data["id"]).strip(),
            name=str(data["name"]).strip(),
            version=str(data["version"]).strip(),
            description=str(data["description"]).strip(),
            entrypoint=entrypoint,
            permissions=permissions,
            tools=tools,
        )
        manifest.validate()
        return manifest

    # ── Validation ───────────────────────────────────────────────────────────

    def validate(self) -> None:
        """
        Validate all manifest fields.

        Raises:
            InvalidSkillManifestError: on any validation failure.
        """
        if not self.id:
            raise InvalidSkillManifestError("'id' must not be empty.")
        if not _ID_RE.match(self.id):
            raise InvalidSkillManifestError(
                f"'id' {self.id!r} is invalid. Must match ^[a-z][a-z0-9-]*$ "
                "(lowercase letters, digits, hyphens; start with a letter)."
            )
        if not self.name:
            raise InvalidSkillManifestError("'name' must not be empty.")
        if not self.version:
            raise InvalidSkillManifestError("'version' must not be empty.")
        if not _VERSION_RE.match(self.version):
            raise InvalidSkillManifestError(
                f"'version' {self.version!r} must be MAJOR.MINOR.PATCH with integer parts (e.g. 1.0.0)."
            )
        if not self.description:
            raise InvalidSkillManifestError("'description' must not be empty.")

        self.entrypoint.validate()
        for tool in self.tools:
            tool.validate()

    # ── Conversion ───────────────────────────────────────────────────────────

    def to_skill(self) -> Skill:
        """Convert this manifest into a :class:`~aether.skills.skill.Skill` instance."""
        permissions = tuple(
            SkillPermission.from_value(p) for p in self.permissions
        )
        return Skill(
            name=self.name,
            description=self.description,
            version=self.version,
            skill_id=f"{self.id}@{self.version}",
            permissions=permissions,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _require(data: dict[str, Any], key: str) -> None:
    """Raise InvalidSkillManifestError if *key* is absent from *data*."""
    if key not in data:
        raise InvalidSkillManifestError(
            f"Required field '{key}' is missing from skill.yaml."
        )
