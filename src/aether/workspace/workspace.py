from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from aether.team.team import Team
from aether.team.loader import TeamLoader


import json

from aether.core.paths import get_global_config_path

class WorkspaceError(Exception):
    pass

def _get_global_config_path() -> Path:
    # The global file is only a convenience pointer, never workspace state.
    # Reading it must not create data directory as a side effect of starting the API.
    return get_global_config_path()

def _save_last_workspace(path: str | Path) -> None:
    try:
        config_path = _get_global_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                pass

        config["last_workspace"] = str(Path(path).resolve())
        tmp_path = config_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f)
        tmp_path.replace(config_path)
    except OSError:
        # Workspace initialization must work in locked-down environments.
        # The global pointer is an optional convenience, never a prerequisite.
        return

def get_last_workspace_path() -> Path | None:
    config_path = _get_global_config_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                last_ws = config.get("last_workspace")
                if last_ws and Path(last_ws).exists():
                    return Path(last_ws)
        except Exception:
            pass
    return None


class Workspace:
    """
    Central abstraction for an Aether Workspace installation.
    Manages filesystem boundaries, paths, and configuration.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

        # Core configuration
        self.config_path = self.root / "aether.yaml"
        self._config_cache: dict[str, Any] | None = None

        # Modern paths (Aether >= 1.4 Workspace)
        self.data_dir = self.root / "data"
        self.agents_dir = self.root / "agents"
        self.teams_dir = self.root / "teams"
        self.skills_dir = self.root / "skills"
        self.knowledge_dir = self.root / "knowledge"

        # Legacy paths (Aether <= 1.3)
        self.legacy_aether_dir = self.root / ".aether"
        self.legacy_team_yaml = self.root / "team.yaml"

    @property
    def config(self) -> dict[str, Any]:
        """Load and return the workspace configuration."""
        if self._config_cache is not None:
            return self._config_cache

        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
            except (OSError, yaml.YAMLError) as exc:
                raise WorkspaceError(
                    f"Invalid workspace configuration at {self.config_path}: {exc}"
                ) from exc
            if not isinstance(loaded, dict):
                raise WorkspaceError(
                    f"Workspace configuration must be a mapping: {self.config_path}"
                )
            self._config_cache = loaded
        else:
            self._config_cache = {}

        return self._config_cache

    @property
    def name(self) -> str:
        """Return the display name of the workspace."""
        return self.config.get("workspace", {}).get("name") or self.root.name

    @property
    def identity_db_path(self) -> str:
        """Path to the agent identity database."""
        if self.data_dir.exists() or self.config_path.exists():
            return str(self.data_dir / "identity.db")
        return str(self.legacy_aether_dir / "identity.db")

    @property
    def conversations_db_path(self) -> str:
        """Path to the persistent conversation database."""
        if self.data_dir.exists() or self.config_path.exists():
            return str(self.data_dir / "conversations.db")
        return str(self.legacy_aether_dir / "conversations.db")

    @property
    def knowledge_db_path(self) -> str:
        """Path to the local vector/document knowledge database."""
        if self.data_dir.exists() or self.config_path.exists():
            return str(self.data_dir / "knowledge.db")
        return str(self.legacy_aether_dir / "knowledge.db")

    @property
    def conversations(self):
        """Return the ConversationStore for this workspace."""
        from aether.conversations.store import ConversationStore
        Path(self.conversations_db_path).parent.mkdir(parents=True, exist_ok=True)
        return ConversationStore(self.conversations_db_path)

    @classmethod
    def init(cls, root: str | Path, name: str) -> "Workspace":
        """
        Scaffold a new Workspace structure.
        """
        ws = cls(root)

        if ws.config_path.exists():
            raise WorkspaceError(f"Workspace already initialized at {ws.root}")

        ws.data_dir.mkdir(parents=True, exist_ok=True)
        ws.agents_dir.mkdir(parents=True, exist_ok=True)
        ws.teams_dir.mkdir(parents=True, exist_ok=True)
        ws.skills_dir.mkdir(parents=True, exist_ok=True)
        ws.knowledge_dir.mkdir(parents=True, exist_ok=True)

        # Create aether.yaml manifest
        manifest = {
            "version": "1.0",
            "workspace": {
                "name": name,
                "default_team": "default"
            }
        }
        with open(ws.config_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest, f, sort_keys=False, default_flow_style=False)

        _save_last_workspace(ws.root)
        return ws

    @classmethod
    def get_or_init(cls, root: str | Path, name: str) -> "Workspace":
        """
        Get an existing Workspace at root, or init a new one if it doesn't exist.
        """
        try:
            ws = cls(root)
            if ws.config_path.exists():
                _save_last_workspace(ws.root)
                return ws
            return cls.init(root, name)
        except WorkspaceError:
            raise

    def _resolve_team_yaml(self, team_name: str) -> Path:
        """Find the yaml definition for a team, falling back to legacy paths."""
        if not team_name or team_name in {".", ".."} or Path(team_name).name != team_name:
            raise WorkspaceError(f"Invalid team selection: {team_name!r}")
        # 1. Try modern path
        modern_path = self.teams_dir / f"{team_name}.yaml"
        if modern_path.exists():
            return modern_path

        # 2. If looking for "default", try legacy team.yaml
        if team_name == "default" and self.legacy_team_yaml.exists():
            return self.legacy_team_yaml

        raise WorkspaceError(f"Team configuration '{team_name}' not found.")

    def load_team(self, team_name: str | None = None) -> Team:
        """
        Build a Team instance from the workspace, wiring all local persistence.
        """
        if not team_name:
            team_name = self.config.get("workspace", {}).get("default_team", "default")

        yaml_path = self._resolve_team_yaml(team_name)
        team_config = TeamLoader.from_yaml(yaml_path)

        # Wire identity
        from aether.agents.identity import AgentStore
        Path(self.identity_db_path).parent.mkdir(parents=True, exist_ok=True)
        agent_store = AgentStore(self.identity_db_path)

        # Wire knowledge eagerly so a newly created workspace has the full
        # local-first persistence layout even before the first upload.
        from aether.knowledge.store import KnowledgeStore
        Path(self.knowledge_db_path).parent.mkdir(parents=True, exist_ok=True)
        knowledge_store = KnowledgeStore(self.knowledge_db_path)

        # Instantiate Team (this will internally wire PersistentConversationMemory using conversation_db_path)
        return Team(
            config=team_config,
            knowledge_store=knowledge_store,
            agent_store=agent_store,
            conversation_db_path=self.conversations_db_path
        )

    def set_default_team(self, team_name: str) -> None:
        """Persist the active team in the workspace manifest."""
        clean_name = str(team_name).strip()
        if not clean_name:
            raise WorkspaceError("Team name cannot be empty.")
        config = dict(self.config)
        workspace_section = dict(config.get("workspace") or {})
        workspace_section["default_team"] = clean_name
        config["workspace"] = workspace_section
        tmp_path = self.config_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, sort_keys=False)
        tmp_path.replace(self.config_path)
        self._config_cache = config

    def apply_preset(
        self,
        preset_id: str,
        *,
        team_name: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        seed_knowledge: bool = True,
        set_as_default: bool = True,
    ) -> Team:
        """Install and activate a workforce preset in this workspace."""
        from aether.presets.applier import PresetApplier
        applier = PresetApplier()
        applier.apply_preset(
            preset_id=preset_id,
            workspace=self,
            team_name=team_name,
            provider=provider,
            model=model,
            seed_knowledge=seed_knowledge,
            set_as_default=set_as_default,
        )
        return self.load_team(team_name or preset_id)
