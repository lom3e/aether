"""
Watcher Engine for Aether Automations.
Provides real, non-simulated change detection across Filesystem, HTTP Endpoints, and GitHub Repositories.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
import urllib.request
import uuid

from aether.automation.models import AutomationDefinition, TriggerType

logger = logging.getLogger(__name__)


class BaseWatcher:
    """Base class for all automated change watchers."""

    def __init__(
        self,
        automation_id: str,
        watcher_type: str,
        check_interval_seconds: int = 30,
        watcher_id: str | None = None,
    ) -> None:
        self.id = watcher_id or f"watch_{uuid.uuid4().hex[:8]}"
        self.automation_id = automation_id
        self.watcher_type = watcher_type
        self.check_interval_seconds = max(1, check_interval_seconds)
        self.last_checked_at: datetime | None = None

    def is_due(self, now: datetime | None = None) -> bool:
        curr = now or datetime.now(timezone.utc)
        if self.last_checked_at is None:
            return True
        elapsed = (curr - self.last_checked_at).total_seconds()
        return elapsed >= self.check_interval_seconds

    async def check(self) -> tuple[bool, dict[str, Any]]:
        """
        Executes a check. Returns (has_changed, change_payload).
        """
        raise NotImplementedError


class FilesystemWatcher(BaseWatcher):
    """
    Watches a local directory for file creation or modification matching a glob pattern.
    """

    def __init__(
        self,
        automation_id: str,
        workspace_root: Path,
        watch_path: str | None = None,
        watch_pattern: str = "*.*",
        watch_events: list[str] | None = None,
        check_interval_seconds: int = 10,
        watcher_id: str | None = None,
    ) -> None:
        super().__init__(
            automation_id=automation_id,
            watcher_type="filesystem",
            check_interval_seconds=check_interval_seconds,
            watcher_id=watcher_id,
        )
        self.workspace_root = workspace_root
        self.watch_path = watch_path
        self.watch_pattern = watch_pattern or "*.*"
        self.watch_events = set(watch_events or ["created", "modified"])
        # Map path -> (mtime, size)
        self._file_snapshots: dict[str, tuple[float, int]] = {}
        self._initialized = False

    @property
    def target_dir(self) -> Path:
        if not self.watch_path:
            return self.workspace_root
        return (self.workspace_root / self.watch_path.lstrip("/")).resolve()

    def _scan_files(self) -> dict[str, tuple[float, int]]:
        files: dict[str, tuple[float, int]] = {}
        target = self.target_dir
        if not target.exists() or not target.is_dir():
            return files

        try:
            for p in target.rglob("*"):
                if p.is_file() and fnmatch.fnmatch(p.name, self.watch_pattern):
                    # Ignore common hidden directories
                    if any(part.startswith(".") and part not in [".", ".."] for part in p.parts):
                        continue
                    if "__pycache__" in p.parts or "node_modules" in p.parts:
                        continue
                    try:
                        stat = p.stat()
                        files[str(p.relative_to(self.workspace_root))] = (stat.st_mtime, stat.st_size)
                    except (OSError, ValueError):
                        pass
        except Exception as e:
            logger.warning("FilesystemWatcher scan error on %s: %s", target, e)
        return files

    async def check(self) -> tuple[bool, dict[str, Any]]:
        self.last_checked_at = datetime.now(timezone.utc)
        current_snapshots = await asyncio.to_thread(self._scan_files)

        if not self._initialized:
            # First run: establish baseline snapshot without firing
            self._file_snapshots = current_snapshots
            self._initialized = True
            return False, {}

        detected: list[dict[str, Any]] = []

        # Check newly created or modified files
        for rel_path, (mtime, size) in current_snapshots.items():
            if rel_path not in self._file_snapshots:
                if "created" in self.watch_events:
                    detected.append({"path": rel_path, "event": "created", "size": size})
            else:
                old_mtime, old_size = self._file_snapshots[rel_path]
                if (mtime > old_mtime or size != old_size) and "modified" in self.watch_events:
                    detected.append({"path": rel_path, "event": "modified", "size": size})

        self._file_snapshots = current_snapshots

        if detected:
            return True, {
                "detected_files": detected,
                "file_count": len(detected),
                "watcher_id": self.id,
            }
        return False, {}


class HttpPollingWatcher(BaseWatcher):
    """
    Periodically polls an external HTTP endpoint and detects changes via ETag,
    Last-Modified header, status code, or SHA-256 body hash.
    """

    def __init__(
        self,
        automation_id: str,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        expected_status: int = 200,
        check_interval_seconds: int = 30,
        watcher_id: str | None = None,
    ) -> None:
        super().__init__(
            automation_id=automation_id,
            watcher_type="http_poll",
            check_interval_seconds=check_interval_seconds,
            watcher_id=watcher_id,
        )
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.expected_status = expected_status
        self._last_etag: str | None = None
        self._last_modified_header: str | None = None
        self._last_content_hash: str | None = None
        self._last_status_code: int | None = None
        self._initialized = False

    def _fetch_sync(self) -> tuple[int, dict[str, str], str]:
        req = urllib.request.Request(self.url, headers=self.headers, method=self.method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                body = resp.read()
                content_hash = hashlib.sha256(body).hexdigest()
                return status, resp_headers, content_hash
        except urllib.error.HTTPError as he:
            body = he.read()
            content_hash = hashlib.sha256(body).hexdigest() if body else ""
            resp_headers = {k.lower(): v for k, v in he.headers.items()} if hasattr(he, "headers") else {}
            return he.code, resp_headers, content_hash
        except Exception as exc:
            logger.debug("HttpPollingWatcher request failed for %s: %s", self.url, exc)
            return 0, {}, ""

    async def check(self) -> tuple[bool, dict[str, Any]]:
        self.last_checked_at = datetime.now(timezone.utc)
        status, headers, content_hash = await asyncio.to_thread(self._fetch_sync)

        if status == 0:
            return False, {}

        etag = headers.get("etag")
        last_modified = headers.get("last-modified")

        if not self._initialized:
            self._last_etag = etag
            self._last_modified_header = last_modified
            self._last_content_hash = content_hash
            self._last_status_code = status
            self._initialized = True
            return False, {}

        has_changed = False
        change_reason = ""

        if status != self._last_status_code:
            has_changed = True
            change_reason = f"HTTP status changed from {self._last_status_code} to {status}"
        elif etag and self._last_etag and etag != self._last_etag:
            has_changed = True
            change_reason = f"ETag header updated to {etag}"
        elif last_modified and self._last_modified_header and last_modified != self._last_modified_header:
            has_changed = True
            change_reason = f"Last-Modified header updated to {last_modified}"
        elif content_hash and self._last_content_hash and content_hash != self._last_content_hash:
            has_changed = True
            change_reason = "Response content payload changed"

        self._last_etag = etag
        self._last_modified_header = last_modified
        self._last_content_hash = content_hash
        self._last_status_code = status

        if has_changed:
            return True, {
                "url": self.url,
                "status_code": status,
                "change_reason": change_reason,
                "etag": etag,
                "content_hash": content_hash,
                "watcher_id": self.id,
            }
        return False, {}


class GitHubRepoWatcher(BaseWatcher):
    """
    Polls a GitHub repository for new commits or releases.
    """

    def __init__(
        self,
        automation_id: str,
        owner: str,
        repo: str,
        token: str | None = None,
        watch_type: str = "commits",
        check_interval_seconds: int = 60,
        watcher_id: str | None = None,
    ) -> None:
        super().__init__(
            automation_id=automation_id,
            watcher_type="github_repo",
            check_interval_seconds=check_interval_seconds,
            watcher_id=watcher_id,
        )
        self.owner = owner
        self.repo = repo
        self.token = token
        self.watch_type = watch_type.lower()
        self._last_sha_or_tag: str | None = None
        self._initialized = False

    def _fetch_latest_commit_sync(self) -> dict[str, Any] | None:
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/commits?per_page=1"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Aether-Watcher/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list) and len(data) > 0:
                        commit_obj = data[0]
                        return {
                            "sha": commit_obj.get("sha"),
                            "message": commit_obj.get("commit", {}).get("message", "").splitlines()[0] if commit_obj.get("commit") else "",
                            "author": commit_obj.get("commit", {}).get("author", {}).get("name", "unknown"),
                            "date": commit_obj.get("commit", {}).get("author", {}).get("date"),
                        }
        except Exception as exc:
            logger.debug("GitHubRepoWatcher fetch error for %s/%s: %s", self.owner, self.repo, exc)
        return None

    async def check(self) -> tuple[bool, dict[str, Any]]:
        self.last_checked_at = datetime.now(timezone.utc)
        latest = await asyncio.to_thread(self._fetch_latest_commit_sync)

        if not latest or not latest.get("sha"):
            return False, {}

        current_sha = latest["sha"]
        if not self._initialized:
            self._last_sha_or_tag = current_sha
            self._initialized = True
            return False, {}

        if current_sha != self._last_sha_or_tag:
            self._last_sha_or_tag = current_sha
            return True, {
                "repository": f"{self.owner}/{self.repo}",
                "latest_commit": current_sha,
                "message": latest.get("message"),
                "author": latest.get("author"),
                "watcher_id": self.id,
            }
        return False, {}


class WatcherManager:
    """Manages the registry and periodic execution of active watchers."""

    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace
        self._watchers: dict[str, BaseWatcher] = {}

    def sync_automations(self, automations: list[AutomationDefinition]) -> None:
        """Synchronizes active watchers with the list of enabled automations."""
        active_ids = {a.id for a in automations if a.enabled}

        # Remove watchers for automations that are no longer enabled
        to_remove = [aid for aid in self._watchers if aid not in active_ids]
        for aid in to_remove:
            del self._watchers[aid]

        # Register or update watchers for enabled automations
        for auto in automations:
            if not auto.enabled:
                continue

            # 1. Standard FILE_WATCHER
            if auto.trigger.type == TriggerType.FILE_WATCHER:
                if auto.id not in self._watchers or self._watchers[auto.id].watcher_type != "filesystem":
                    self._watchers[auto.id] = FilesystemWatcher(
                        automation_id=auto.id,
                        workspace_root=self.workspace.root,
                        watch_path=auto.trigger.watch_path,
                        watch_pattern=auto.trigger.watch_pattern or "*.*",
                        watch_events=auto.trigger.watch_events,
                    )

            # 2. Metadata-specified watchers (HTTP Poll / GitHub Repo)
            elif auto.metadata and "watcher" in auto.metadata:
                w_meta = auto.metadata["watcher"]
                w_type = w_meta.get("type")
                if w_type == "http_poll":
                    if auto.id not in self._watchers or self._watchers[auto.id].watcher_type != "http_poll":
                        self._watchers[auto.id] = HttpPollingWatcher(
                            automation_id=auto.id,
                            url=w_meta.get("url", ""),
                            method=w_meta.get("method", "GET"),
                            headers=w_meta.get("headers"),
                            check_interval_seconds=int(w_meta.get("interval_seconds", 30)),
                        )
                elif w_type == "github_repo":
                    if auto.id not in self._watchers or self._watchers[auto.id].watcher_type != "github_repo":
                        self._watchers[auto.id] = GitHubRepoWatcher(
                            automation_id=auto.id,
                            owner=w_meta.get("owner", ""),
                            repo=w_meta.get("repo", ""),
                            token=w_meta.get("token"),
                            check_interval_seconds=int(w_meta.get("interval_seconds", 60)),
                        )

    async def check_all(self, automations_map: dict[str, AutomationDefinition]) -> list[tuple[AutomationDefinition, str, dict[str, Any]]]:
        """
        Evaluates all due watchers. Returns triggered (automation, trigger_type, payload) tuples.
        """
        triggered: list[tuple[AutomationDefinition, str, dict[str, Any]]] = []
        now = datetime.now(timezone.utc)

        for auto_id, watcher in list(self._watchers.items()):
            auto = automations_map.get(auto_id)
            if not auto or not auto.enabled:
                continue

            if watcher.is_due(now):
                try:
                    has_changed, payload = await watcher.check()
                    if has_changed:
                        triggered.append((auto, watcher.watcher_type, payload))
                except Exception as exc:
                    logger.error("Watcher error for automation %s: %s", auto_id, exc)

        return triggered
