"""
Project-tree evidence for external coding agent runs.

A TreeSnapshot records the content hash of every project file (and the text of
small files) *before* an agent run. Comparing it with the tree afterwards
isolates exactly what the run changed: pre-existing uncommitted modifications
are excluded, files the agent created (tracked or not) are included, and the
unified diff covers only the run's own changes.

Pure Python: no git and no subprocess. It never executes project code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import base64
import difflib
import hashlib
import json
import os
from pathlib import Path
import zlib

EXCLUDED_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", ".next", "dist", "build", ".idea",
})
MAX_FILES = 20000
MAX_HASH_BYTES = 5 * 1024 * 1024
MAX_TEXT_BYTES = 200 * 1024
MAX_TEXT_TOTAL_BYTES = 32 * 1024 * 1024
MAX_DIFF_CHARS = 200_000


@dataclass
class TreeSnapshot:
    root: str
    hashes: dict[str, str] = field(default_factory=dict)
    texts: dict[str, str] = field(default_factory=dict)
    truncated: bool = False


@dataclass
class TreeChanges:
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)
    diff: str = ""
    diff_truncated: bool = False
    scan_truncated: bool = False

    @property
    def changed_files(self) -> list[str]:
        return sorted(set(self.added) | set(self.modified) | set(self.deleted) | {new for _, new in self.renamed})


def _fingerprint(path: Path) -> tuple[str, str | None]:
    """Returns (fingerprint, text-or-None). Symlinks are fingerprinted by target, never followed."""
    if path.is_symlink():
        return "link:" + os.readlink(path), None
    st = path.stat()
    if st.st_size > MAX_HASH_BYTES:
        return f"big:{st.st_size}:{st.st_mtime_ns}", None
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    text = None
    if st.st_size <= MAX_TEXT_BYTES and b"\x00" not in data:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = None
    return digest, text


def take_snapshot(root: str | Path) -> TreeSnapshot:
    base = Path(root).resolve()
    snap = TreeSnapshot(root=str(base))
    text_budget = MAX_TEXT_TOTAL_BYTES
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            if len(snap.hashes) >= MAX_FILES:
                snap.truncated = True
                return snap
            full = Path(dirpath) / name
            rel = full.relative_to(base).as_posix()
            try:
                fp, text = _fingerprint(full)
            except OSError:
                continue
            snap.hashes[rel] = fp
            if text is not None and len(text) <= text_budget:
                snap.texts[rel] = text
                text_budget -= len(text)
    return snap


def compare(before: TreeSnapshot, after: TreeSnapshot) -> TreeChanges:
    changes = TreeChanges(scan_truncated=before.truncated or after.truncated)
    for rel, fp in after.hashes.items():
        if rel not in before.hashes:
            changes.added.append(rel)
        elif before.hashes[rel] != fp:
            changes.modified.append(rel)
    for rel in before.hashes:
        if rel not in after.hashes:
            changes.deleted.append(rel)
    # A deleted file whose exact content reappears under a new path is a rename, not delete + add.
    by_fp: dict[str, list[str]] = {}
    for rel in changes.added:
        fp = after.hashes[rel]
        if not fp.startswith(("big:", "link:")):
            by_fp.setdefault(fp, []).append(rel)
    for old in list(changes.deleted):
        fp = before.hashes[old]
        candidates = by_fp.get(fp)
        if candidates:
            new = candidates.pop(0)
            changes.renamed.append((old, new))
            changes.deleted.remove(old)
            changes.added.remove(new)
    changes.renamed.sort()
    changes.added.sort()
    changes.modified.sort()
    changes.deleted.sort()

    parts: list[str] = []
    total = 0
    for old_path, new_path in changes.renamed:
        chunk = f"rename from {old_path}\nrename to {new_path}\n"
        parts.append(chunk)
        total += len(chunk)
    for rel in sorted(set(changes.added) | set(changes.modified) | set(changes.deleted)):
        old = before.texts.get(rel)
        new = after.texts.get(rel)
        if rel in changes.added:
            old = ""
        if rel in changes.deleted:
            new = ""
        if old is None or new is None:
            chunk = f"Binary or oversized file changed: {rel}\n"
        else:
            chunk = "".join(difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile="/dev/null" if rel in changes.added else f"a/{rel}",
                tofile="/dev/null" if rel in changes.deleted else f"b/{rel}",
            ))
            if chunk and not chunk.endswith("\n"):
                chunk += "\n"
        if total + len(chunk) > MAX_DIFF_CHARS:
            changes.diff_truncated = True
            break
        parts.append(chunk)
        total += len(chunk)
    changes.diff = "".join(parts)
    return changes


def snapshot_to_blob(snap: TreeSnapshot) -> str:
    """Compact, JSON-safe serialisation so a run baseline survives a server restart."""
    raw = json.dumps({"root": snap.root, "hashes": snap.hashes, "texts": snap.texts, "truncated": snap.truncated})
    return base64.b64encode(zlib.compress(raw.encode("utf-8"), 6)).decode("ascii")


def snapshot_from_blob(blob: str) -> TreeSnapshot:
    data = json.loads(zlib.decompress(base64.b64decode(blob.encode("ascii"))).decode("utf-8"))
    return TreeSnapshot(
        root=data["root"], hashes=dict(data["hashes"]), texts=dict(data.get("texts") or {}),
        truncated=bool(data.get("truncated")),
    )
