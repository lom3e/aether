"""
PresetManifest — schema and validation for Aether workforce presets.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


class PresetValidationError(Exception):
    """Raised when a preset manifest or configuration is invalid."""
    pass


@dataclass
class PresetAgentInfo:
    name: str
    role: str
    description: str = ""
    skills: list[str] = field(default_factory=list)
    delegates_to: list[str] = field(default_factory=list)
    icon: str | None = None
    color: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PresetAgentInfo:
        return cls(
            name=str(data.get("name", "")).strip(),
            role=str(data.get("role", "")).strip(),
            description=str(data.get("description", "")).strip(),
            skills=list(data.get("skills", [])),
            delegates_to=list(data.get("delegates_to", [])),
            icon=str(data.get("icon", "")).strip() or None if data.get("icon") else None,
            color=str(data.get("color", "")).strip() or None if data.get("color") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "skills": self.skills,
            "delegates_to": self.delegates_to,
        }
        if self.icon:
            res["icon"] = self.icon
        if self.color:
            res["color"] = self.color
        return res


from aether.team.config import SUPPORTED_AGENT_COLORS, SUPPORTED_AGENT_ICONS


@dataclass
class PresetManifest:
    """
    Official metadata and specification for an Aether Workforce Preset.
    """
    id: str
    name: str
    version: str
    description: str
    type: str = "workforce_preset"
    author: str = "Aether Team"
    compatibility: dict[str, Any] = field(default_factory=lambda: {"min_aether_version": "1.0.0"})
    agents: list[PresetAgentInfo] = field(default_factory=list)
    relationships: list[dict[str, str]] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    knowledge_packs: list[str] = field(default_factory=list)
    icon: str | None = None
    color: str | None = None

    def validate(self) -> None:
        """Validate the manifest integrity."""
        if not self.id or not self.id.strip():
            raise PresetValidationError("Preset manifest requires a non-empty 'id'.")
        if not re.match(r"^[a-z0-9_-]+$", self.id):
            raise PresetValidationError(f"Invalid preset id '{self.id}'. Only lowercase alphanumeric, '-' and '_' allowed.")
        if not self.name or not self.name.strip():
            raise PresetValidationError("Preset manifest requires a non-empty 'name'.")
        if not self.version or not self.version.strip():
            raise PresetValidationError("Preset manifest requires a non-empty 'version'.")
        if not self.description or not self.description.strip():
            raise PresetValidationError("Preset manifest requires a non-empty 'description'.")
        if not self.agents:
            raise PresetValidationError("Preset must include at least one agent in 'agents'.")

        if self.icon and self.icon not in SUPPORTED_AGENT_ICONS:
            raise PresetValidationError(
                f"Unsupported preset icon '{self.icon}'. Supported: {', '.join(SUPPORTED_AGENT_ICONS)}"
            )
        if self.color and self.color not in SUPPORTED_AGENT_COLORS:
            raise PresetValidationError(
                f"Unsupported preset color '{self.color}'. Supported: {', '.join(SUPPORTED_AGENT_COLORS)}"
            )

        agent_names = set()
        for a in self.agents:
            if not a.name:
                raise PresetValidationError("Each agent in preset must have a non-empty name.")
            if not a.role:
                raise PresetValidationError(f"Agent '{a.name}' in preset must have a non-empty role.")
            if a.icon and a.icon not in SUPPORTED_AGENT_ICONS:
                raise PresetValidationError(
                    f"Agent '{a.name}' has unsupported icon '{a.icon}'."
                )
            if a.color and a.color not in SUPPORTED_AGENT_COLORS:
                raise PresetValidationError(
                    f"Agent '{a.name}' has unsupported color '{a.color}'."
                )
            if a.name.lower() in agent_names:
                raise PresetValidationError(f"Duplicate agent name '{a.name}' in preset manifest.")
            agent_names.add(a.name.lower())

        for rel in self.relationships:
            src = rel.get("source", "").lower()
            tgt = rel.get("target", "").lower()
            if src not in agent_names:
                raise PresetValidationError(f"Relationship source '{rel.get('source')}' not found in preset agents.")
            if tgt not in agent_names:
                raise PresetValidationError(f"Relationship target '{rel.get('target')}' not found in preset agents.")
            if src == tgt:
                raise PresetValidationError(f"Agent '{rel.get('source')}' cannot delegate to itself.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PresetManifest:
        agents_data = [
            PresetAgentInfo.from_dict(a) if isinstance(a, dict) else PresetAgentInfo(name=str(a), role="Agent")
            for a in data.get("agents", [])
        ]

        icon = str(data.get("icon", "")).strip() or None if data.get("icon") else None
        color = str(data.get("color", "")).strip() or None if data.get("color") else None

        manifest = cls(
            id=str(data.get("id", "")).strip(),
            name=str(data.get("name", "")).strip(),
            version=str(data.get("version", "1.0.0")).strip(),
            description=str(data.get("description", "")).strip(),
            type=str(data.get("type", "workforce_preset")).strip(),
            author=str(data.get("author", "Aether Team")).strip(),
            compatibility=data.get("compatibility") or {"min_aether_version": "1.0.0"},
            agents=agents_data,
            relationships=list(data.get("relationships", [])),
            skills=list(data.get("skills", [])),
            knowledge_packs=list(data.get("knowledge_packs", [])),
            icon=icon,
            color=color,
        )
        manifest.validate()
        return manifest

    @classmethod
    def from_yaml(cls, path: str | Path) -> PresetManifest:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Manifest file not found: {p}")
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            raise PresetValidationError(f"Failed to parse manifest YAML at {p}: {exc}") from exc

        if not isinstance(data, dict):
            raise PresetValidationError(f"Manifest at {p} must be a dictionary.")
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "type": self.type,
            "author": self.author,
            "compatibility": self.compatibility,
            "agent_count": len(self.agents),
            "agents": [a.to_dict() for a in self.agents],
            "relationships": self.relationships,
            "skills": self.skills,
            "knowledge_packs": self.knowledge_packs,
            "icon": self.icon or "Bot",
            "color": self.color or "violet",
        }
