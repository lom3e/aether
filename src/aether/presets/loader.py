"""
PresetLoader — discovers, parses, and loads available workforce presets and knowledge packs.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aether.presets.manifest import PresetManifest, PresetValidationError


class PresetLoader:
    """
    Discovers and parses preset packages from builtin and custom directories.
    """

    def __init__(self, search_paths: list[str | Path] | None = None) -> None:
        self.search_paths: list[Path] = []

        if search_paths:
            for p in search_paths:
                self.search_paths.append(Path(p).resolve())
        else:
            # 1. Built-in presets bundled with the python package
            builtin_dir = Path(__file__).parent / "builtin"
            if builtin_dir.exists():
                self.search_paths.append(builtin_dir)

            # 2. Local workspace/project presets folder if present
            cwd_presets = Path.cwd() / "presets"
            if cwd_presets.exists() and cwd_presets not in self.search_paths:
                self.search_paths.append(cwd_presets)

    def list_presets(self) -> list[PresetManifest]:
        """Discover and return all valid preset manifests in search paths."""
        presets: dict[str, PresetManifest] = {}

        for search_dir in self.search_paths:
            if not search_dir.exists():
                continue

            for entry in search_dir.iterdir():
                if entry.is_dir() and entry.name != "knowledge":
                    manifest_file = entry / "manifest.yaml"
                    if manifest_file.exists():
                        try:
                            manifest = PresetManifest.from_yaml(manifest_file)
                            if manifest.id not in presets:
                                presets[manifest.id] = manifest
                        except Exception:
                            # Skip invalid presets in discovery
                            continue

        return list(presets.values())

    def get_preset(self, preset_id: str) -> tuple[PresetManifest, Path]:
        """
        Locate a preset by ID and return its parsed manifest and root directory.
        """
        clean_id = preset_id.strip()

        for search_dir in self.search_paths:
            if not search_dir.exists():
                continue

            for entry in search_dir.iterdir():
                if entry.is_dir() and entry.name != "knowledge":
                    manifest_file = entry / "manifest.yaml"
                    if manifest_file.exists():
                        try:
                            manifest = PresetManifest.from_yaml(manifest_file)
                            if manifest.id == clean_id:
                                return manifest, entry
                        except Exception:
                            continue

        raise FileNotFoundError(f"Preset '{preset_id}' not found in search paths.")

    def get_knowledge_pack_path(self, pack_name: str) -> Path | None:
        """Find the directory containing a specific knowledge pack."""
        clean_pack = pack_name.strip()

        for search_dir in self.search_paths:
            # Look in builtin/knowledge/<pack_name> or presets/knowledge/<pack_name>
            candidates = [
                search_dir / "knowledge" / clean_pack,
                search_dir.parent / "builtin" / "knowledge" / clean_pack,
                Path(__file__).parent / "builtin" / "knowledge" / clean_pack,
            ]
            for cand in candidates:
                if cand.exists() and cand.is_dir():
                    return cand

        return None
