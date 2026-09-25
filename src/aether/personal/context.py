"""
Desktop App Context, Deliverable Collector, and Universal Interaction Utilities for Aether Companion (Layer 19).
Probes native desktop context with zero simulation and organizes unified deliverables.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
import uuid

from aether.personal.models import (
    CompanionDeliverable,
    DesktopAppContext,
)

logger = logging.getLogger(__name__)


def capture_desktop_context(timeout_seconds: float = 1.5) -> DesktopAppContext:
    """
    Probes native OS frontmost application, window title, and clipboard text.
    Uses native platform inspection with zero simulation and non-blocking timeouts.
    """
    app_name = "Desktop"
    window_title = ""
    clipboard_text = ""
    screen_summary = ""

    os_platform = sys.platform

    if os_platform == "darwin":
        # 1. Inspect macOS clipboard via pbpaste
        try:
            p_clip = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            if p_clip.returncode == 0 and p_clip.stdout:
                clipboard_text = p_clip.stdout.strip()[:2000]
        except Exception:
            pass

        # 2. Inspect active application via osascript
        try:
            script_app = 'tell application "System Events" to get name of first application process whose frontmost is true'
            p_app = subprocess.run(
                ["osascript", "-e", script_app],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            if p_app.returncode == 0 and p_app.stdout.strip():
                app_name = p_app.stdout.strip()
        except Exception:
            pass

        # 3. Inspect active window title
        if app_name and app_name != "Desktop":
            try:
                script_win = f'tell application "System Events" to tell process "{app_name}" to get name of front window'
                p_win = subprocess.run(
                    ["osascript", "-e", script_win],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                if p_win.returncode == 0 and p_win.stdout.strip():
                    window_title = p_win.stdout.strip()
            except Exception:
                pass

    elif os_platform.startswith("linux"):
        # Inspect clipboard via xclip or wl-paste
        if shutil.which("wl-paste"):
            try:
                p_clip = subprocess.run(["wl-paste"], capture_output=True, text=True, timeout=timeout_seconds, check=False)
                if p_clip.returncode == 0:
                    clipboard_text = p_clip.stdout.strip()[:2000]
            except Exception:
                pass
        elif shutil.which("xclip"):
            try:
                p_clip = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=timeout_seconds, check=False)
                if p_clip.returncode == 0:
                    clipboard_text = p_clip.stdout.strip()[:2000]
            except Exception:
                pass

        # Inspect active window via xdotool
        if shutil.which("xdotool"):
            try:
                p_win = subprocess.run(["xdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True, timeout=timeout_seconds, check=False)
                if p_win.returncode == 0 and p_win.stdout.strip():
                    window_title = p_win.stdout.strip()
                    app_name = "X11 Application"
            except Exception:
                pass

    if app_name or window_title:
        screen_summary = f"Active: {app_name}" + (f" — '{window_title}'" if window_title else "")
        if clipboard_text:
            clip_preview = clipboard_text[:60].replace("\n", " ")
            screen_summary += f" | Clipboard: \"{clip_preview}...\""

    return DesktopAppContext(
        app_name=app_name,
        window_title=window_title,
        selected_text="",
        clipboard_text=clipboard_text,
        screen_summary=screen_summary,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def collect_workspace_deliverables(workspace: Any, limit: int = 25) -> list[CompanionDeliverable]:
    """
    Consolidates deliverables, outputs, and generated artifacts across Missions,
    Tasks, Automations, and Workspace folders into immediately accessible companion items.
    """
    deliverables: list[CompanionDeliverable] = []
    seen_paths: set[str] = set()

    # 1. Mission outputs
    if hasattr(workspace, "missions") and workspace.missions:
        try:
            missions = workspace.missions.list_missions(workspace_id=workspace.name)
            for m in missions:
                m_dict = m.to_dict() if hasattr(m, "to_dict") else vars(m)
                outputs = m_dict.get("outputs") or {}
                m_title = m_dict.get("title") or m_dict.get("goal") or "Mission"
                created_at = m_dict.get("created_at") or datetime.now(timezone.utc).isoformat()

                if isinstance(outputs, dict):
                    for k, v in outputs.items():
                        if isinstance(v, str) and (os.path.exists(v) or v.startswith("/") or v.startswith("./")):
                            p_str = str(Path(v).resolve()) if os.path.exists(v) else v
                            if p_str not in seen_paths:
                                seen_paths.add(p_str)
                                size = os.path.getsize(p_str) if os.path.exists(p_str) else 0
                                deliverables.append(
                                    CompanionDeliverable(
                                        id=f"deliv-m-{uuid.uuid4().hex[:6]}",
                                        title=f"{m_title}: {k}",
                                        source="mission",
                                        file_path=p_str,
                                        file_type=Path(p_str).suffix or "output",
                                        file_size_bytes=size,
                                        summary=f"Output generated from mission '{m_title}'",
                                        created_at=created_at,
                                    )
                                )
                elif isinstance(outputs, list):
                    for out in outputs:
                        if isinstance(out, str) and (os.path.exists(out) or out.startswith("/")):
                            if out not in seen_paths:
                                seen_paths.add(out)
                                size = os.path.getsize(out) if os.path.exists(out) else 0
                                deliverables.append(
                                    CompanionDeliverable(
                                        id=f"deliv-m-{uuid.uuid4().hex[:6]}",
                                        title=f"{m_title} Artifact",
                                        source="mission",
                                        file_path=out,
                                        file_type=Path(out).suffix or "file",
                                        file_size_bytes=size,
                                        summary=f"Deliverable from mission '{m_title}'",
                                        created_at=created_at,
                                    )
                                )
        except Exception as exc:
            logger.debug(f"Could not collect mission deliverables: {exc}")

    # 2. Background Tasks deliverable_path
    if hasattr(workspace, "personal_store") and workspace.personal_store:
        try:
            tasks = workspace.personal_store.list_tasks(workspace_id=workspace.name, limit=limit)
            for t in tasks:
                if t.deliverable_path and t.deliverable_path not in seen_paths:
                    seen_paths.add(t.deliverable_path)
                    p_obj = Path(t.deliverable_path)
                    size = p_obj.stat().st_size if p_obj.exists() else 0
                    deliverables.append(
                        CompanionDeliverable(
                            id=f"deliv-t-{t.id}",
                            title=t.title,
                            source="task",
                            file_path=t.deliverable_path,
                            file_type=p_obj.suffix or "document",
                            file_size_bytes=size,
                            summary=t.result_summary or f"Deliverable from task '{t.title}'",
                            created_at=t.updated_at or t.created_at,
                        )
                    )
        except Exception as exc:
            logger.debug(f"Could not collect task deliverables: {exc}")

    # 3. Workspace 'deliverables' or 'inbox' directory files
    for subdir_name in ("deliverables", "inbox", "documents"):
        target_dir = getattr(workspace, "root", Path(".")) / subdir_name
        if target_dir.exists() and target_dir.is_dir():
            try:
                for file_entry in sorted(target_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                    if file_entry.is_file() and not file_entry.name.startswith("."):
                        p_str = str(file_entry.resolve())
                        if p_str not in seen_paths:
                            seen_paths.add(p_str)
                            deliverables.append(
                                CompanionDeliverable(
                                    id=f"deliv-f-{file_entry.name[:10]}",
                                    title=file_entry.name,
                                    source=subdir_name,
                                    file_path=p_str,
                                    file_type=file_entry.suffix or "file",
                                    file_size_bytes=file_entry.stat().st_size,
                                    summary=f"Workspace {subdir_name} file: {file_entry.name}",
                                    created_at=datetime.fromtimestamp(file_entry.stat().st_mtime, tz=timezone.utc).isoformat(),
                                )
                            )
            except Exception:
                pass

    deliverables.sort(key=lambda d: d.created_at, reverse=True)
    return deliverables[:limit]


def handle_drag_and_drop_file(
    workspace: Any,
    filename: str,
    content: bytes,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Accepts a drag-and-drop file in the companion, stores it in the workspace inbox,
    and returns metadata ready for immediate conversation context and ingestion.
    """
    inbox_dir = getattr(workspace, "root", Path(".")) / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename).name
    target_file = inbox_dir / safe_name
    # Avoid collisions
    if target_file.exists():
        stem = Path(safe_name).stem
        ext = Path(safe_name).suffix
        target_file = inbox_dir / f"{stem}_{uuid.uuid4().hex[:4]}{ext}"

    with open(target_file, "wb") as f:
        f.write(content)

    file_size = len(content)
    file_type = target_file.suffix.lower()

    # Preview content if text / markdown / code
    text_preview = ""
    is_text = file_type in (".txt", ".md", ".json", ".yaml", ".yml", ".py", ".ts", ".tsx", ".js", ".html", ".css", ".csv")
    if is_text:
        try:
            text_preview = content.decode("utf-8", errors="replace")[:1500]
        except Exception:
            text_preview = ""

    # Log activity in workspace
    if hasattr(workspace, "activity") and workspace.activity:
        try:
            workspace.activity.log(
                workspace_id=workspace.name,
                title=f"File Ingested: {target_file.name}",
                description=f"Received via Companion drag & drop ({file_size} bytes)",
                category="companion",
                status="completed",
                metadata={"path": str(target_file), "size": file_size, "preview": text_preview[:200]},
            )
        except Exception:
            pass

    return {
        "status": "ingested",
        "file_name": target_file.name,
        "file_path": str(target_file),
        "file_size": file_size,
        "file_type": file_type,
        "text_preview": text_preview,
        "summary": f"Ingested {target_file.name} ({round(file_size / 1024, 1)} KB)",
    }
