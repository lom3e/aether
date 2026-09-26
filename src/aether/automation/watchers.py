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
        self.last_changed_at: datetime | None = None
        self.last_error: str | None = None
        self.consecutive_failures: int = 0
        self.status: str = "healthy"  # healthy, degraded, failed, rate_limited, paused

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "automation_id": self.automation_id,
            "watcher_type": self.watcher_type,
            "status": self.status,
            "check_interval_seconds": self.check_interval_seconds,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "last_changed_at": self.last_changed_at.isoformat() if self.last_changed_at else None,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
        }


class FilesystemWatcher(BaseWatcher):
    """
    Watches a local directory for file creation or modification matching a glob pattern.
    Provides debouncing and permission-safe directory scans.
    """

    def __init__(
        self,
        automation_id: str,
        workspace_root: Path,
        watch_path: str | None = None,
        watch_pattern: str = "*.*",
        watch_events: list[str] | None = None,
        check_interval_seconds: int = 10,
        debounce_seconds: float = 0.5,
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
        self.debounce_seconds = debounce_seconds
        # Map path -> (mtime, size)
        self._file_snapshots: dict[str, tuple[float, int]] = {}
        self._last_event_timestamps: dict[str, float] = {}
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
            self.consecutive_failures += 1
            self.status = "degraded"
            self.last_error = f"Watch path does not exist or is not a directory: {target}"
            return files

        try:
            for p in target.rglob("*"):
                if p.is_file() and fnmatch.fnmatch(p.name, self.watch_pattern):
                    # Ignore common hidden or noisy directories
                    if any(part.startswith(".") and part not in [".", ".."] for part in p.parts):
                        continue
                    if any(ignored in p.parts for ignored in ["__pycache__", "node_modules", ".venv", ".git"]):
                        continue
                    try:
                        stat = p.stat()
                        rel_path = str(p.relative_to(self.workspace_root)) if self.workspace_root in p.parents else p.name
                        files[rel_path] = (stat.st_mtime, stat.st_size)
                    except (OSError, ValueError, PermissionError) as pe:
                        logger.debug("FilesystemWatcher stat error on %s: %s", p, pe)
            self.status = "healthy"
            self.last_error = None
            self.consecutive_failures = 0
        except PermissionError as pe:
            self.consecutive_failures += 1
            self.status = "degraded"
            self.last_error = f"Permission denied scanning {target}: {pe}"
            logger.warning("FilesystemWatcher permission error on %s: %s", target, pe)
        except Exception as e:
            self.consecutive_failures += 1
            self.status = "degraded"
            self.last_error = f"Scan error on {target}: {e}"
            logger.warning("FilesystemWatcher scan error on %s: %s", target, e)
        return files

    async def check(self) -> tuple[bool, dict[str, Any]]:
        now = datetime.now(timezone.utc)
        self.last_checked_at = now
        current_snapshots = await asyncio.to_thread(self._scan_files)

        if not self._initialized:
            # Baseline snapshot: establish current state without firing false alarms
            self._file_snapshots = current_snapshots
            self._initialized = True
            return False, {}

        detected: list[dict[str, Any]] = []
        now_ts = now.timestamp()

        # Check newly created or modified files
        for rel_path, (mtime, size) in current_snapshots.items():
            last_event_ts = self._last_event_timestamps.get(rel_path, 0.0)
            if now_ts - last_event_ts < self.debounce_seconds:
                # Debounced: skip duplicate event within debounce window
                continue

            if rel_path not in self._file_snapshots:
                if "created" in self.watch_events:
                    detected.append({"path": rel_path, "event": "created", "size": size, "mtime": mtime})
                    self._last_event_timestamps[rel_path] = now_ts
            else:
                old_mtime, old_size = self._file_snapshots[rel_path]
                if (mtime > old_mtime or size != old_size) and "modified" in self.watch_events:
                    detected.append({"path": rel_path, "event": "modified", "size": size, "mtime": mtime})
                    self._last_event_timestamps[rel_path] = now_ts

        self._file_snapshots = current_snapshots

        if detected:
            self.last_changed_at = now
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
    Truthfully distinguishes healthy+unchanged, healthy+changed, and failed.
    """

    def __init__(
        self,
        automation_id: str,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        expected_status: int = 200,
        check_interval_seconds: int = 30,
        initial_hash: str | None = None,
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
        self._last_content_hash: str | None = initial_hash
        self._last_status_code: int | None = None
        self._initialized = initial_hash is not None

    def _fetch_sync(self) -> tuple[int, dict[str, str], str, str | None, bool]:
        """
        Returns (status_code, resp_headers, content_hash, error_msg, is_retryable).
        """
        req = urllib.request.Request(self.url, headers=self.headers, method=self.method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                body = resp.read()
                content_hash = hashlib.sha256(body).hexdigest()
                return status, resp_headers, content_hash, None, False
        except urllib.error.HTTPError as he:
            body = he.read()
            content_hash = hashlib.sha256(body).hexdigest() if body else ""
            resp_headers = {k.lower(): v for k, v in he.headers.items()} if hasattr(he, "headers") else {}
            # 5xx errors are retryable; 4xx are client errors
            is_retryable = he.code >= 500 or he.code == 429
            return he.code, resp_headers, content_hash, f"HTTP Error {he.code}: {he.reason}", is_retryable
        except urllib.error.URLError as ue:
            return 0, {}, "", f"Network/URL Error: {ue.reason}", True
        except TimeoutError:
            return 0, {}, "", "Request timed out", True
        except Exception as exc:
            return 0, {}, "", f"Unexpected error: {exc}", True

    async def check(self) -> tuple[bool, dict[str, Any]]:
        now = datetime.now(timezone.utc)
        self.last_checked_at = now
        fetch_res = await asyncio.to_thread(self._fetch_sync)
        if len(fetch_res) >= 5:
            status, headers, content_hash, error_msg, is_retryable = fetch_res[:5]
        elif len(fetch_res) == 3:
            status, headers, content_hash = fetch_res
            error_msg, is_retryable = None, False
        else:
            status, headers, content_hash, error_msg, is_retryable = 0, {}, "", "Invalid fetch result", False

        if error_msg or (status == 0):
            self.consecutive_failures += 1
            self.status = "failed"
            self.last_error = error_msg or "Failed to connect"
            return False, {
                "error": self.last_error,
                "is_retryable": is_retryable,
                "status_code": status,
            }

        # Healthy connection
        self.status = "healthy"
        self.last_error = None
        self.consecutive_failures = 0

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

        if self._last_status_code is not None and status != self._last_status_code:
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
            self.last_changed_at = now
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
    Supports persistent checkpointing across server restarts and handles rate limits.
    """

    def __init__(
        self,
        automation_id: str,
        owner: str,
        repo: str,
        token: str | None = None,
        watch_type: str = "commits",
        check_interval_seconds: int = 60,
        checkpoint_sha: str | None = None,
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
        self._last_sha_or_tag: str | None = checkpoint_sha
        self._initialized = checkpoint_sha is not None

    @property
    def checkpoint_sha(self) -> str | None:
        return self._last_sha_or_tag

    def _fetch_latest_commit_sync(self) -> tuple[dict[str, Any] | None, str | None, bool]:
        """
        Returns (commit_obj, error_msg, is_rate_limited).
        """
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
                        }, None, False
            return None, "Empty commit list returned", False
        except urllib.error.HTTPError as he:
            is_rl = he.code == 403 or he.code == 429
            return None, f"GitHub HTTP {he.code}: {he.reason}", is_rl
        except Exception as exc:
            return None, f"GitHub connection error: {exc}", False

    async def check(self) -> tuple[bool, dict[str, Any]]:
        now = datetime.now(timezone.utc)
        self.last_checked_at = now
        raw_res = await asyncio.to_thread(self._fetch_latest_commit_sync)
        if isinstance(raw_res, tuple):
            latest, error_msg, is_rate_limited = raw_res
        else:
            latest, error_msg, is_rate_limited = raw_res, None, False

        if is_rate_limited:
            self.status = "rate_limited"
            self.last_error = error_msg or "GitHub API rate limit reached"
            return False, {}

        if error_msg:
            self.consecutive_failures += 1
            self.status = "failed"
            self.last_error = error_msg
            return False, {}

        if not latest or not latest.get("sha"):
            return False, {}

        self.status = "healthy"
        self.last_error = None
        self.consecutive_failures = 0

        current_sha = latest["sha"]
        if not self._initialized:
            self._last_sha_or_tag = current_sha
            self._initialized = True
            return False, {}

        if current_sha != self._last_sha_or_tag:
            previous_sha = self._last_sha_or_tag
            self._last_sha_or_tag = current_sha
            self.last_changed_at = now
            return True, {
                "repository": f"{self.owner}/{self.repo}",
                "latest_commit": current_sha,
                "previous_commit": previous_sha,
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

    def get_watchers_status(self) -> list[dict[str, Any]]:
        """Returns diagnostic status of all active watchers."""
        return [w.to_dict() for w in self._watchers.values()]

    def sync_automations(self, automations: list[AutomationDefinition]) -> None:
        """Synchronizes active watchers with the list of enabled automations."""
        active_ids = {a.id for a in automations if a.enabled and not a.is_draft}

        # Remove watchers for automations that are no longer enabled
        to_remove = [aid for aid in self._watchers if aid not in active_ids]
        for aid in to_remove:
            del self._watchers[aid]

        # Register or update watchers for enabled automations
        for auto in automations:
            if not auto.enabled or auto.is_draft:
                continue

            # 1. FILE_WATCHER
            if auto.trigger.type == TriggerType.FILE_WATCHER:
                if auto.id not in self._watchers or self._watchers[auto.id].watcher_type != "filesystem":
                    self._watchers[auto.id] = FilesystemWatcher(
                        automation_id=auto.id,
                        workspace_root=self.workspace.root,
                        watch_path=auto.trigger.watch_path,
                        watch_pattern=auto.trigger.watch_pattern or "*.*",
                        watch_events=auto.trigger.watch_events,
                        check_interval_seconds=auto.trigger.check_interval_seconds or 10,
                    )

            # 2. HTTP_WATCHER
            elif auto.trigger.type == TriggerType.HTTP_WATCHER or (auto.metadata and auto.metadata.get("watcher", {}).get("type") == "http_poll"):
                w_meta = auto.metadata.get("watcher", {}) if auto.metadata else {}
                url = auto.trigger.http_url or w_meta.get("url", "")
                method = auto.trigger.http_method or w_meta.get("method", "GET")
                headers = auto.trigger.http_headers or w_meta.get("headers", {})
                interval = auto.trigger.check_interval_seconds or int(w_meta.get("interval_seconds", 30))
                expected = auto.trigger.http_expected_status or int(w_meta.get("expected_status", 200))
                initial_hash = auto.metadata.get("watcher_checkpoint") if auto.metadata else None

                if url and (auto.id not in self._watchers or self._watchers[auto.id].watcher_type != "http_poll"):
                    self._watchers[auto.id] = HttpPollingWatcher(
                        automation_id=auto.id,
                        url=url,
                        method=method,
                        headers=headers,
                        expected_status=expected,
                        check_interval_seconds=interval,
                        initial_hash=initial_hash,
                    )

            # 3. GITHUB_WATCHER
            elif auto.trigger.type == TriggerType.GITHUB_WATCHER or (auto.metadata and auto.metadata.get("watcher", {}).get("type") == "github_repo"):
                w_meta = auto.metadata.get("watcher", {}) if auto.metadata else {}
                owner = auto.trigger.github_owner or w_meta.get("owner", "")
                repo = auto.trigger.github_repo or w_meta.get("repo", "")
                token = auto.trigger.github_token or w_meta.get("token")
                interval = auto.trigger.check_interval_seconds or int(w_meta.get("interval_seconds", 60))
                checkpoint = auto.metadata.get("watcher_checkpoint") if auto.metadata else None

                if owner and repo and (auto.id not in self._watchers or self._watchers[auto.id].watcher_type != "github_repo"):
                    self._watchers[auto.id] = GitHubRepoWatcher(
                        automation_id=auto.id,
                        owner=owner,
                        repo=repo,
                        token=token,
                        watch_type=auto.trigger.github_watch_type or w_meta.get("watch_type", "commits"),
                        check_interval_seconds=interval,
                        checkpoint_sha=checkpoint,
                    )

    async def check_all(self, automations_map: dict[str, AutomationDefinition]) -> list[tuple[AutomationDefinition, str, dict[str, Any]]]:
        """
        Evaluates all due watchers. Returns triggered (automation, trigger_type, payload) tuples.
        Also persists checkpoints if changes are detected.
        """
        triggered: list[tuple[AutomationDefinition, str, dict[str, Any]]] = []
        now = datetime.now(timezone.utc)

        for auto_id, watcher in list(self._watchers.items()):
            auto = automations_map.get(auto_id)
            if not auto or not auto.enabled or auto.is_draft:
                continue

            if watcher.is_due(now):
                try:
                    has_changed, payload = await watcher.check()
                    if has_changed:
                        # Update checkpoint in metadata
                        if isinstance(watcher, GitHubRepoWatcher) and payload.get("latest_commit"):
                            auto.metadata["watcher_checkpoint"] = payload["latest_commit"]
                            if hasattr(self.workspace, "automations"):
                                try:
                                    self.workspace.automations.save_automation(auto)
                                except Exception:
                                    pass
                        elif isinstance(watcher, HttpPollingWatcher) and payload.get("content_hash"):
                            auto.metadata["watcher_checkpoint"] = payload["content_hash"]
                            if hasattr(self.workspace, "automations"):
                                try:
                                    self.workspace.automations.save_automation(auto)
                                except Exception:
                                    pass

                        triggered.append((auto, watcher.watcher_type, payload))
                except Exception as exc:
                    logger.error("Watcher error for automation %s: %s", auto_id, exc)

        return triggered
