"""
P3.2 Release-Grade Hardening: Automation Recovery & Change Detection Test Suite.
Verifies:
1. FilesystemWatcher resilience under rapid file bursts, debouncing, file renames, and deletions.
2. HttpPollingWatcher error categorization (retryable 5xx vs non-retryable 4xx), failure counter, and recovery.
3. GitHubRepoWatcher checkpoint persistence across restarts, change detection, and graceful rate-limit handling.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from unittest.mock import MagicMock, patch
import urllib.error
import pytest

from aether.automation.watchers import FilesystemWatcher, HttpPollingWatcher, GitHubRepoWatcher


# -----------------------------------------------------------------------------
# 1. FilesystemWatcher Burst, Rename, Delete & Debounce
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filesystem_watcher_burst_and_debouncing(tmp_path: Path):
    watch_dir = tmp_path / "incoming"
    watch_dir.mkdir()

    watcher = FilesystemWatcher(
        automation_id="auto-burst-test",
        workspace_root=tmp_path,
        watch_path="incoming",
        watch_pattern="*.txt",
        watch_events=["created", "modified"],
        debounce_seconds=0.2,
    )

    # 1. Baseline initialization
    has_changed, payload = await watcher.check()
    assert not has_changed
    assert watcher._initialized

    # 2. Burst creation: 10 files written simultaneously
    for i in range(10):
        (watch_dir / f"burst_{i}.txt").write_text(f"content {i}")

    has_changed, payload = await watcher.check()
    assert has_changed
    assert payload["file_count"] == 10
    detected_paths = {f["path"] for f in payload["detected_files"]}
    for i in range(10):
        assert f"incoming/burst_{i}.txt" in detected_paths

    # 3. Debouncing: Immediate re-check without waiting should debounce
    (watch_dir / "burst_0.txt").write_text("modified rapidly")
    has_changed_immediate, _ = await watcher.check()
    # burst_0.txt was modified within 0.2s of its creation, so debounce suppresses duplicate event
    assert not has_changed_immediate

    # Wait past debounce window and modify again
    await asyncio.sleep(0.25)
    (watch_dir / "burst_0.txt").write_text("modified after debounce")
    has_changed_after, payload_after = await watcher.check()
    assert has_changed_after
    assert payload_after["file_count"] == 1
    assert payload_after["detected_files"][0]["path"] == "incoming/burst_0.txt"
    assert payload_after["detected_files"][0]["event"] == "modified"


@pytest.mark.asyncio
async def test_filesystem_watcher_rename_and_deletion(tmp_path: Path):
    watch_dir = tmp_path / "docs"
    watch_dir.mkdir()
    f1 = watch_dir / "report.txt"
    f2 = watch_dir / "notes.txt"
    f1.write_text("Report content")
    f2.write_text("Notes content")

    watcher = FilesystemWatcher(
        automation_id="auto-rename-test",
        workspace_root=tmp_path,
        watch_path="docs",
        watch_events=["created", "modified", "deleted"],
        debounce_seconds=0.01,
    )

    # Baseline initialization
    await watcher.check()

    await asyncio.sleep(0.05)

    # 1. Rename report.txt -> report_final.txt
    f1_renamed = watch_dir / "report_final.txt"
    f1.rename(f1_renamed)

    has_changed, payload = await watcher.check()
    assert has_changed
    events = {f["event"]: f["path"] for f in payload["detected_files"]}
    assert events.get("deleted") == "docs/report.txt"
    assert events.get("created") == "docs/report_final.txt"

    await asyncio.sleep(0.05)

    # 2. Delete notes.txt
    f2.unlink()

    has_changed_del, payload_del = await watcher.check()
    assert has_changed_del
    assert len(payload_del["detected_files"]) == 1
    assert payload_del["detected_files"][0]["path"] == "docs/notes.txt"
    assert payload_del["detected_files"][0]["event"] == "deleted"


# -----------------------------------------------------------------------------
# 2. HttpPollingWatcher Error Categorization, Backoff & Recovery
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_polling_watcher_error_retryability_and_recovery():
    watcher = HttpPollingWatcher(
        automation_id="auto-http-test",
        url="https://api.example.com/status",
        check_interval_seconds=10,
    )

    # 1. Initial healthy check establishing baseline
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"etag": '"etag-v1"', "content-type": "application/json"}
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        has_changed, _ = await watcher.check()
        assert not has_changed
        assert watcher.status == "healthy"
        assert watcher._initialized
        assert watcher._last_etag == '"etag-v1"'

    # 2. Transient 503 Server Error (Retryable)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.example.com/status",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=None,
        )

        has_changed, payload = await watcher.check()
        assert not has_changed
        assert watcher.status == "failed"
        assert watcher.consecutive_failures == 1
        assert payload.get("is_retryable") is True
        assert "503" in watcher.last_error

    # 3. Client 404 Error (Non-Retryable)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.example.com/status",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )

        has_changed, payload = await watcher.check()
        assert not has_changed
        assert watcher.status == "failed"
        assert watcher.consecutive_failures == 2
        assert payload.get("is_retryable") is False

    # 4. Recovery: Endpoint recovers and returns updated content
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.headers = {"etag": '"etag-v2"', "content-type": "application/json"}
        mock_resp.read.return_value = b'{"status": "updated", "version": 2}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        has_changed, payload = await watcher.check()
        assert has_changed
        assert watcher.status == "healthy"
        assert watcher.consecutive_failures == 0
        assert watcher.last_error is None
        assert payload["etag"] == '"etag-v2"'
        assert "ETag header updated" in payload["change_reason"]


# -----------------------------------------------------------------------------
# 3. GitHubRepoWatcher Checkpoint Persistence & Rate Limiting
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_github_repo_watcher_checkpoint_and_ratelimit():
    # 1. Instantiate watcher with pre-existing checkpoint from previous session
    checkpoint_sha = "abc1234567890abcdef1234567890abcdef12345"
    watcher = GitHubRepoWatcher(
        automation_id="auto-gh-test",
        owner="aether-org",
        repo="aether-core",
        checkpoint_sha=checkpoint_sha,
    )
    assert watcher._initialized
    assert watcher.checkpoint_sha == checkpoint_sha

    # 2. Check returns the same commit -> has_changed is False
    with patch.object(watcher, "_fetch_latest_commit_sync") as mock_fetch:
        mock_fetch.return_value = (
            {
                "sha": checkpoint_sha,
                "message": "Previous commit",
                "author": "dev",
                "date": "2026-09-28T12:00:00Z",
            },
            None,
            False,
        )

        has_changed, _ = await watcher.check()
        assert not has_changed
        assert watcher.checkpoint_sha == checkpoint_sha

    # 3. New commit arrives -> has_changed is True, checkpoint advances
    new_sha = "def9876543210fedcba9876543210fedcba98765"
    with patch.object(watcher, "_fetch_latest_commit_sync") as mock_fetch:
        mock_fetch.return_value = (
            {
                "sha": new_sha,
                "message": "Feature: Release-grade hardening",
                "author": "engineer",
                "date": "2026-09-28T20:00:00Z",
            },
            None,
            False,
        )

        has_changed, payload = await watcher.check()
        assert has_changed
        assert payload["latest_commit"] == new_sha
        assert payload["previous_commit"] == checkpoint_sha
        assert watcher.checkpoint_sha == new_sha

    # 4. Rate limit response (403 / 429) -> status = 'rate_limited', checkpoint NOT lost!
    with patch.object(watcher, "_fetch_latest_commit_sync") as mock_fetch:
        mock_fetch.return_value = (
            None,
            "GitHub HTTP 429: Too Many Requests",
            True,
        )

        has_changed, _ = await watcher.check()
        assert not has_changed
        assert watcher.status == "rate_limited"
        # Crucial invariant: Checkpoint must be preserved through rate limits!
        assert watcher.checkpoint_sha == new_sha
