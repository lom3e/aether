"""
WorkspaceRegistry — Global registry and lifecycle manager for Aether Workspaces.
Allows discovering, creating, switching, renaming, and deleting workspaces.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aether.workspace.workspace import Workspace, WorkspaceError


_SLUG_PATTERN = re.compile(r"[^a-zA-Z0-9_\-]+")


def _get_registry_path() -> Path:
    base = Path.home() / ".aether"
    base.mkdir(parents=True, exist_ok=True)
    return base / "workspaces.json"


def _slugify(name: str) -> str:
    slug = _SLUG_PATTERN.sub("-", name.strip().lower()).strip("-")
    return slug or f"workspace-{uuid.uuid4().hex[:6]}"


_CRITICAL_PROTECTED_PATHS = {
    Path("/").resolve(),
    Path.home().resolve(),
    Path("/Users").resolve(),
    Path("/home").resolve(),
    Path("/tmp").resolve(),
    Path("/var").resolve(),
    Path("/etc").resolve(),
    Path("/usr").resolve(),
    Path("/System").resolve(),
    Path("/bin").resolve(),
    Path("/sbin").resolve(),
    Path("/Applications").resolve(),
    Path("/Library").resolve(),
    Path("/private").resolve(),
}


def _is_protected_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        if resolved in _CRITICAL_PROTECTED_PATHS:
            return True
        if len(resolved.parts) < 3:
            return True
        # Check if root is exactly equal to root partitions
        for prot in _CRITICAL_PROTECTED_PATHS:
            if resolved == prot:
                return True
        return False
    except Exception:
        return True


class WorkspaceRegistry:
    """
    Manages global workspace index and lifecycle operations.
    """

    @classmethod
    def load_registry(cls) -> dict[str, Any]:
        path = _get_registry_path()
        if not path.exists():
            return {"workspaces": []}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "workspaces" in data:
                    return data
        except Exception:
            pass
        return {"workspaces": []}

    @classmethod
    def save_registry(cls, data: dict[str, Any]) -> None:
        path = _get_registry_path()
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp.replace(path)
        except OSError:
            pass

    @classmethod
    def register(
        cls,
        root: str | Path,
        name: str | None = None,
        description: str = "",
        is_default: bool = False,
    ) -> dict[str, Any]:
        """Register or update an existing workspace path in global index."""
        root_path = Path(root).resolve()
        if _is_protected_path(root_path):
            raise WorkspaceError(f"Cannot register protected system directory: {root_path}")

        data = cls.load_registry()
        workspaces = data.get("workspaces", [])
        
        # Determine display name
        display_name = name
        if not display_name:
            if (root_path / "aether.yaml").exists():
                try:
                    import yaml
                    with open(root_path / "aether.yaml", "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f) or {}
                        display_name = cfg.get("workspace", {}).get("name")
                except Exception:
                    pass
            if not display_name:
                display_name = root_path.name

        now = datetime.now(timezone.utc).isoformat()
        ws_id = _slugify(display_name)

        found = False
        for entry in workspaces:
            if Path(entry.get("path", "")).resolve() == root_path:
                entry["name"] = display_name
                entry["last_active"] = now
                if description:
                    entry["description"] = description
                if is_default:
                    entry["is_default"] = True
                found = True
                break

        if not found:
            # Ensure unique id
            existing_ids = {w.get("id") for w in workspaces}
            base_id = ws_id
            counter = 1
            while ws_id in existing_ids:
                ws_id = f"{base_id}-{counter}"
                counter += 1

            workspaces.append({
                "id": ws_id,
                "name": display_name,
                "description": description,
                "path": str(root_path),
                "created_at": now,
                "last_active": now,
                "is_default": is_default,
            })

        if is_default:
            for w in workspaces:
                if Path(w.get("path", "")).resolve() != root_path:
                    w["is_default"] = False

        data["workspaces"] = workspaces
        cls.save_registry(data)
        return cls.get_workspace_entry(root_path) or {}

    @classmethod
    def list_workspaces(cls, active_root: str | Path | None = None) -> list[dict[str, Any]]:
        """List all valid workspaces, removing stale missing paths."""
        data = cls.load_registry()
        workspaces = data.get("workspaces", [])
        active_resolved = Path(active_root).resolve() if active_root else None

        valid_entries = []
        for w in workspaces:
            p = Path(w.get("path", ""))
            if p.exists() and (p / "aether.yaml").exists():
                entry = dict(w)
                entry["is_active"] = (active_resolved is not None and p.resolve() == active_resolved)
                
                # Fetch quick summary stats
                try:
                    ws = Workspace(p)
                    team_count = len(list(ws.teams_dir.glob("*.yaml")))
                    agents_count = 0
                    if (ws.teams_dir / "default.yaml").exists() or list(ws.teams_dir.glob("*.yaml")):
                        try:
                            team = ws.load_team()
                            agents_count = len(team.agents())
                        except Exception:
                            pass
                    entry["team_count"] = team_count
                    entry["agents_count"] = agents_count
                except Exception:
                    entry["team_count"] = 0
                    entry["agents_count"] = 0

                valid_entries.append(entry)

        # Also ensure active_root is registered if it is a valid workspace
        if active_resolved and active_resolved.exists() and (active_resolved / "aether.yaml").exists():
            if not any(Path(e["path"]).resolve() == active_resolved for e in valid_entries):
                new_entry = cls.register(active_resolved)
                new_entry["is_active"] = True
                valid_entries.append(new_entry)

        # Persist cleaned list if items were removed
        if len(valid_entries) != len(workspaces):
            data["workspaces"] = [{k: v for k, v in e.items() if k not in ("is_active", "team_count", "agents_count")} for e in valid_entries]
            cls.save_registry(data)

        # Sort: active first, then last_active desc
        valid_entries.sort(key=lambda x: (not x.get("is_active", False), x.get("last_active", "")), reverse=False)
        return valid_entries

    @classmethod
    def get_workspace_entry(cls, root_or_id: str | Path) -> dict[str, Any] | None:
        data = cls.load_registry()
        query = str(root_or_id)
        resolved_path = Path(query).resolve() if Path(query).exists() else None

        for w in data.get("workspaces", []):
            if w.get("id") == query:
                return w
            if resolved_path and Path(w.get("path", "")).resolve() == resolved_path:
                return w
        return None

    @classmethod
    def create_workspace(
        cls,
        name: str,
        description: str = "",
        preset_id: str = "starter-workforce",
        provider: str = "ollama",
        model: str = "qwen3.5:9b",
        api_key: str | None = None,
        target_dir: str | Path | None = None,
    ) -> Workspace:
        """Create and initialize a new isolated workspace with preset and DBs."""
        clean_name = name.strip()
        if not clean_name:
            raise WorkspaceError("Workspace name cannot be empty.")

        slug = _slugify(clean_name)
        if target_dir:
            ws_dir = Path(target_dir).resolve()
            if _is_protected_path(ws_dir):
                raise WorkspaceError(f"Cannot create workspace in protected system directory: {ws_dir}")
        else:
            base_dir = Path.home() / ".aether" / "workspaces"
            base_dir.mkdir(parents=True, exist_ok=True)
            ws_dir = base_dir / slug
            counter = 1
            while ws_dir.exists():
                ws_dir = base_dir / f"{slug}-{counter}"
                counter += 1

        ws_dir.mkdir(parents=True, exist_ok=True)
        ws = Workspace.init(ws_dir, clean_name)

        # Save API key if provided
        if api_key and provider:
            env_file = ws.root / ".env"
            key_map = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "gemini": "GEMINI_API_KEY",
            }
            if provider in key_map:
                env_file.write_text(f"{key_map[provider]}={api_key.strip()}\n", encoding="utf-8")

        # Apply preset
        if preset_id and preset_id != "empty":
            from aether.presets.applier import PresetApplier
            applier = PresetApplier()
            try:
                applier.apply_preset(
                    preset_id=preset_id,
                    workspace=ws,
                    provider=provider,
                    model=model,
                    seed_knowledge=True,
                    set_as_default=True,
                )
            except Exception:
                # Fallback to starter-workforce or default team
                pass
        else:
            # Create minimal empty default team
            default_team_path = ws.teams_dir / "default.yaml"
            default_yaml = f"""team:
  name: default
  provider: {provider}
  model: {model}

agents:
  - name: manager
    role: "AI Workforce Coordinator"
    instructions: "You coordinate tasks for the workspace."
"""
            default_team_path.write_text(default_yaml, encoding="utf-8")
            # Still seed official system knowledge
            from aether.presets.applier import PresetApplier
            try:
                PresetApplier().seed_knowledge_packs(["aether-core-knowledge"], ws)
            except Exception:
                pass

        # Register in global registry
        cls.register(ws.root, name=clean_name, description=description)
        return ws

    @classmethod
    def rename_workspace(cls, ws: Workspace, new_name: str) -> None:
        """Update workspace display name in aether.yaml and registry."""
        clean_name = new_name.strip()
        if not clean_name:
            raise WorkspaceError("New workspace name cannot be empty.")

        config = dict(ws.config)
        ws_sec = dict(config.get("workspace") or {})
        ws_sec["name"] = clean_name
        config["workspace"] = ws_sec

        import yaml
        tmp = ws.config_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, sort_keys=False)
        tmp.replace(ws.config_path)
        ws._config_cache = config

        cls.register(ws.root, name=clean_name)

    @classmethod
    def delete_workspace(cls, root_or_id: str | Path) -> bool:
        """Permanently delete a workspace folder and deregister it."""
        try:
            p = Path(root_or_id).resolve()
            if _is_protected_path(p):
                raise WorkspaceError(f"Cannot delete protected system directory: {p}")
        except Exception as e:
            if isinstance(e, WorkspaceError):
                raise

        entry = cls.get_workspace_entry(root_or_id)
        if not entry:
            return False

        ws_path = Path(entry["path"]).resolve()

        # Strict safety check: Never delete system root or home directory
        if _is_protected_path(ws_path):
            raise WorkspaceError(f"Cannot delete protected system directory: {ws_path}")

        # Delete workspace folder
        if ws_path.exists():
            shutil.rmtree(ws_path, ignore_errors=True)

        # Remove from registry
        data = cls.load_registry()
        data["workspaces"] = [w for w in data.get("workspaces", []) if Path(w.get("path", "")).resolve() != ws_path]
        cls.save_registry(data)

        # Clean global config if deleted workspace was active
        try:
            cfg_path = Path.home() / ".aether" / "config.json"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                if cfg_data.get("active_workspace") and Path(cfg_data["active_workspace"]).resolve() == ws_path:
                    cfg_data["active_workspace"] = None
                    tmp = cfg_path.with_suffix(".tmp")
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(cfg_data, f, indent=2)
                    tmp.replace(cfg_path)
        except Exception:
            pass

        return True

    @classmethod
    def get_storage_stats(cls, ws: Workspace) -> dict[str, Any]:
        """Compute metrics for storage and databases in a workspace."""
        def file_size(p: str | Path) -> int:
            path = Path(p)
            return path.stat().st_size if path.exists() else 0

        conv_size = file_size(ws.conversations_db_path)
        ident_size = file_size(ws.identity_db_path)
        know_size = file_size(ws.knowledge_db_path)
        
        # Count documents
        doc_count = 0
        chunk_count = 0
        if Path(ws.knowledge_db_path).exists():
            try:
                from aether.knowledge.store import KnowledgeStore
                ks = KnowledgeStore(ws.knowledge_db_path)
                docs = ks.list_documents()
                doc_count = len(docs)
                chunk_count = ks.count()
            except Exception:
                pass

        # Count conversations
        conv_count = 0
        if Path(ws.conversations_db_path).exists():
            try:
                convs = ws.conversations.list(include_archived=True, limit=10000)
                conv_count = len(convs)
            except Exception:
                pass

        # Count agents
        agent_count = 0
        try:
            team = ws.load_team()
            agent_count = len(team.agents())
        except Exception:
            pass

        return {
            "conversations_count": conv_count,
            "conversations_size_bytes": conv_size,
            "knowledge_documents_count": doc_count,
            "knowledge_chunks_count": chunk_count,
            "knowledge_size_bytes": know_size,
            "identity_size_bytes": ident_size,
            "agents_count": agent_count,
            "total_size_bytes": conv_size + ident_size + know_size,
        }
