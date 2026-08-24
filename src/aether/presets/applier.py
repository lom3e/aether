"""
PresetApplier — installs and activates workforce presets and knowledge packs in a workspace.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from aether.knowledge.ingestion import DocumentIngester
from aether.knowledge.store import KnowledgeStore
from aether.presets.loader import PresetLoader
from aether.presets.manifest import PresetManifest
from aether.team.config import TeamConfig
from aether.team.loader import TeamLoader


class PresetApplier:
    """
    Installs presets into a given workspace, writes team configurations,
    and seeds official system knowledge packs.
    """

    def __init__(self, loader: PresetLoader | None = None) -> None:
        self.loader = loader or PresetLoader()

    def apply_preset(
        self,
        preset_id: str,
        workspace,
        *,
        team_name: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        seed_knowledge: bool = True,
        set_as_default: bool = True,
    ) -> TeamConfig:
        """
        Apply a preset to the target workspace.

        Parameters
        ----------
        preset_id:
            The identifier of the preset (e.g. 'starter-workforce').
        workspace:
            The target Workspace instance.
        team_name:
            Target team file name. Defaults to preset_id.
        provider:
            Override default provider (e.g. 'ollama', 'openai').
        model:
            Override default model (e.g. 'qwen3.5:9b', 'gpt-4o').
        seed_knowledge:
            Whether to ingest associated system knowledge packs.
        set_as_default:
            Whether to set this team as the default in aether.yaml.
        """
        manifest, preset_dir = self.loader.get_preset(preset_id)
        effective_team_name = (team_name or manifest.id).strip()

        # 1. Load team.yaml template from preset
        team_template_path = preset_dir / "team.yaml"
        if not team_template_path.exists():
            raise FileNotFoundError(f"Missing team.yaml in preset '{preset_id}' at {preset_dir}")

        team_config = TeamLoader.from_yaml(team_template_path)
        team_config.name = effective_team_name
        if not team_config.icon and manifest.icon:
            team_config.icon = manifest.icon
        if not team_config.color and manifest.color:
            team_config.color = manifest.color

        # Apply provider/model overrides if supplied
        if provider:
            team_config.default_provider = provider
            for agent in team_config.agents:
                if not agent.provider:
                    agent.provider = provider

        if model:
            team_config.default_model = model
            for agent in team_config.agents:
                if not agent.model:
                    agent.model = model

        # 2. Write team.yaml into workspace teams directory
        workspace.teams_dir.mkdir(parents=True, exist_ok=True)
        dest_team_path = workspace.teams_dir / f"{effective_team_name}.yaml"
        TeamLoader.to_yaml(team_config, dest_team_path)

        # 3. Seed System Knowledge Packs
        if seed_knowledge and manifest.knowledge_packs:
            self.seed_knowledge_packs(manifest.knowledge_packs, workspace)

        # 4. Set as default team in workspace config if requested
        if set_as_default:
            workspace.set_default_team(effective_team_name)

        return team_config

    def seed_knowledge_packs(
        self,
        knowledge_packs: list[str],
        workspace,
    ) -> int:
        """
        Ingest the specified knowledge packs into the workspace's KnowledgeStore
        under scope='system'.
        """
        store = KnowledgeStore(workspace.knowledge_db_path)
        ingester = DocumentIngester(store)
        total_chunks = 0

        for pack_name in knowledge_packs:
            pack_dir = self.loader.get_knowledge_pack_path(pack_name)
            if not pack_dir or not pack_dir.exists():
                continue

            for doc_file in sorted(pack_dir.glob("*.md")):
                filename = doc_file.name
                content_bytes = doc_file.read_bytes()
                size_bytes = len(content_bytes)
                content_hash = hashlib.sha256(content_bytes).hexdigest()
                doc_id = f"sys_{pack_name}_{doc_file.stem}"

                # Register document in documents table with scope='system'
                store.register_document(
                    doc_id=doc_id,
                    filename=filename,
                    size_bytes=size_bytes,
                    content_hash=content_hash,
                    scope="system",
                )

                # Ingest document chunks under scope='system'
                chunks_added = ingester.ingest(
                    doc_file,
                    source_name=filename,
                    scope="system",
                )
                store.update_document(doc_id, "Ready", chunks_added)
                total_chunks += chunks_added

        store.close()
        return total_chunks
