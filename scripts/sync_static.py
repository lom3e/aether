#!/usr/bin/env python3
"""
Single canonical utility to synchronize frontend UI distribution assets
from ui/dist to src/aether/server/static, creating a cryptographic build manifest
for verification and drift prevention.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UI_DIST = REPO_ROOT / "ui" / "dist"
DEFAULT_SERVER_STATIC = REPO_ROOT / "src" / "aether" / "server" / "static"
MANIFEST_FILENAME = ".build_manifest.json"


def compute_file_sha256(path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def sync_static_assets(
    source_dir: Path | None = None,
    target_dir: Path | None = None,
    clean_target: bool = True,
) -> dict[str, Any]:
    """
    Synchronizes static assets from source_dir (ui/dist) to target_dir (server/static).
    Generates and writes a .build_manifest.json in the target directory.
    Returns the manifest dictionary.
    """
    src = (source_dir or DEFAULT_UI_DIST).resolve()
    tgt = (target_dir or DEFAULT_SERVER_STATIC).resolve()

    if not src.exists():
        raise FileNotFoundError(f"Source UI distribution directory does not exist: {src}")

    src_index = src / "index.html"
    if not src_index.exists() or src_index.stat().st_size == 0:
        raise ValueError(f"Source directory missing or empty index.html: {src_index}")

    tgt.parent.mkdir(parents=True, exist_ok=True)
    if clean_target and tgt.exists():
        shutil.rmtree(tgt, ignore_errors=True)

    tgt.mkdir(parents=True, exist_ok=True)

    file_hashes: dict[str, str] = {}
    total_bytes = 0

    # Copy files and compute hashes
    for root, _, files in os.walk(src):
        for f in files:
            if f == MANIFEST_FILENAME:
                continue
            src_file = Path(root) / f
            rel_path = src_file.relative_to(src)
            tgt_file = tgt / rel_path

            tgt_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, tgt_file)

            file_hash = compute_file_sha256(tgt_file)
            file_hashes[str(rel_path)] = file_hash
            total_bytes += tgt_file.stat().st_size

    # Verify target index.html
    tgt_index = tgt / "index.html"
    if not tgt_index.exists() or tgt_index.stat().st_size == 0:
        raise RuntimeError(f"Target index.html failed verification: {tgt_index}")

    manifest: dict[str, Any] = {
        "manifest_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(src),
        "target": str(tgt),
        "file_count": len(file_hashes),
        "total_bytes": total_bytes,
        "files": file_hashes,
    }

    manifest_path = tgt / MANIFEST_FILENAME
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def verify_static_manifest(target_dir: Path | None = None) -> tuple[bool, str]:
    """
    Verifies that the target directory conforms to its .build_manifest.json.
    Returns (True, "OK") or (False, "Reason").
    """
    tgt = (target_dir or DEFAULT_SERVER_STATIC).resolve()
    manifest_path = tgt / MANIFEST_FILENAME

    if not manifest_path.exists():
        return False, f"Manifest file not found: {manifest_path}"

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        return False, f"Failed to parse manifest: {e}"

    expected_files = manifest.get("files", {})
    if not expected_files:
        return False, "Manifest contains no files list."

    for rel_path_str, expected_hash in expected_files.items():
        actual_file = tgt / rel_path_str
        if not actual_file.exists():
            return False, f"Missing file declared in manifest: {rel_path_str}"
        actual_hash = compute_file_sha256(actual_file)
        if actual_hash != expected_hash:
            return False, f"Checksum mismatch for {rel_path_str}: expected {expected_hash}, got {actual_hash}"

    return True, "Manifest verified successfully."


if __name__ == "__main__":
    try:
        manifest = sync_static_assets()
        print(
            f"✓ Successfully synchronized {manifest['file_count']} files "
            f"({manifest['total_bytes']} bytes) into {manifest['target']}"
        )
        ok, msg = verify_static_manifest()
        if not ok:
            print(f"✗ Manifest verification failed: {msg}", file=sys.stderr)
            sys.exit(1)
        print("✓ Build manifest verified.")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
