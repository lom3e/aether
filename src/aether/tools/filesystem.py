"""
Filesystem Tools for Aether Workspace Sandbox.

Provides safe, sandboxed file operations for agents:
- list_directory: inspect workspace files and subdirectories
- read_file: read text files within the sandbox
- write_file: create or overwrite files in the sandbox
- patch_file: modify existing files deterministically
- delete_file: delete files protected by HITL RequireApproval
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aether.core.interrupts import RequireApproval
from aether.core.security import OperationType, PathSandbox
from aether.errors import FilesystemToolError
from aether.tools.base import Tool
from aether.tools.decorator import tool

if TYPE_CHECKING:
    from aether.coordination.events import EventEmitter


def create_filesystem_tools(
    sandbox: PathSandbox,
    emitter: EventEmitter | None = None,
) -> list[Tool]:
    """
    Factory creating the standard suite of 5 sandboxed filesystem tools.
    """

    @tool(
        name="list_directory",
        description="List files and subdirectories within a directory in the workspace sandbox.",
    )
    def list_directory(path: str = ".") -> str:
        target = sandbox.validate_path(path, operation=OperationType.LIST, must_exist=True)
        rel_path = sandbox.get_relative_path(target)
        if not target.is_dir():
            raise FilesystemToolError(f"'{rel_path}' is a file, not a directory.")

        entries: list[str] = []
        try:
            for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                item_rel = sandbox.get_relative_path(item)
                if sandbox.is_sensitive(item_rel):
                    continue
                if item.is_dir():
                    entries.append(f"- {item.name}/ (directory)")
                else:
                    size = item.stat().st_size
                    entries.append(f"- {item.name} (file, {size} bytes)")
        except OSError as exc:
            raise FilesystemToolError(f"Failed to list directory '{rel_path}': {exc}") from exc

        header = f"Directory: '{rel_path}' ({len(entries)} items)"
        if not entries:
            return f"{header}\n(empty directory)"
        return f"{header}\n" + "\n".join(entries)

    @tool(
        name="read_file",
        description="Read the text content of a file in the workspace sandbox.",
    )
    def read_file(path: str) -> str:
        target = sandbox.validate_path(path, operation=OperationType.READ, must_exist=True)
        rel_path = sandbox.get_relative_path(target)
        if target.is_dir():
            raise FilesystemToolError(f"'{rel_path}' is a directory, not a file.")
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise FilesystemToolError(f"Failed to read file '{rel_path}': {exc}") from exc

    @tool(
        name="write_file",
        description="Create or overwrite a file in the workspace sandbox with the specified content.",
    )
    def write_file(path: str, content: str, context: Any | None = None) -> str:
        target = sandbox.validate_path(path, operation=OperationType.WRITE)
        rel_path = sandbox.get_relative_path(target)
        if target.exists() and target.is_dir():
            raise FilesystemToolError(f"'{rel_path}' is an existing directory.")

        is_new = not target.exists()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise FilesystemToolError(f"Failed to write file '{rel_path}': {exc}") from exc

        size_bytes = len(content.encode("utf-8"))
        action = "created" if is_new else "updated"

        if emitter is not None:
            from aether.coordination.events import AgentEvent, EventType
            evt_type = EventType.FILE_CREATED if is_new else EventType.FILE_MODIFIED
            agent_name = getattr(context, "agent_name", "agent") or "agent"
            task_id = getattr(context, "task_id", "") or ""
            emitter.emit(
                AgentEvent(
                    event_type=evt_type,
                    agent_name=agent_name,
                    task_id=task_id,
                    metadata={"path": rel_path, "size_bytes": size_bytes, "action": action},
                )
            )

        return f"Successfully {action} file '{rel_path}' ({size_bytes} bytes)."

    @tool(
        name="patch_file",
        description="Replace specific text content in an existing file in the workspace sandbox.",
    )
    def patch_file(path: str, search_content: str, replace_content: str, context: Any | None = None) -> str:
        target = sandbox.validate_path(path, operation=OperationType.PATCH, must_exist=True)
        rel_path = sandbox.get_relative_path(target)
        if target.is_dir():
            raise FilesystemToolError(f"'{rel_path}' is a directory, not a file.")

        try:
            existing_content = target.read_text(encoding="utf-8")
        except OSError as exc:
            raise FilesystemToolError(f"Failed to read file for patching '{rel_path}': {exc}") from exc

        if search_content not in existing_content:
            raise FilesystemToolError(f"Search content not found in '{rel_path}'.")

        occurrence_count = existing_content.count(search_content)
        new_content = existing_content.replace(search_content, replace_content, 1)

        try:
            target.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            raise FilesystemToolError(f"Failed to save patched file '{rel_path}': {exc}") from exc

        if emitter is not None:
            from aether.coordination.events import AgentEvent, EventType
            agent_name = getattr(context, "agent_name", "agent") or "agent"
            task_id = getattr(context, "task_id", "") or ""
            emitter.emit(
                AgentEvent(
                    event_type=EventType.FILE_MODIFIED,
                    agent_name=agent_name,
                    task_id=task_id,
                    metadata={"path": rel_path, "action": "patched"},
                )
            )

        return f"Successfully patched '{rel_path}' (replaced 1 of {occurrence_count} occurrences)."

    @tool(
        name="delete_file",
        description="Delete a file from the workspace sandbox. Requires human confirmation before deletion.",
    )
    def delete_file(path: str, confirmed: bool = False, context: Any | None = None) -> str:
        target = sandbox.validate_path(path, operation=OperationType.DELETE, must_exist=True)
        rel_path = sandbox.get_relative_path(target)
        if target.is_dir():
            raise FilesystemToolError(f"'{rel_path}' is a directory. delete_file only removes files.")

        if not confirmed:
            raise RequireApproval(
                f"Sei sicuro di voler eliminare definitivamente il file '{rel_path}'?",
                context={"action": "delete_file", "path": rel_path},
            )

        try:
            target.unlink()
        except OSError as exc:
            raise FilesystemToolError(f"Failed to delete file '{rel_path}': {exc}") from exc

        if emitter is not None:
            from aether.coordination.events import AgentEvent, EventType
            agent_name = getattr(context, "agent_name", "agent") or "agent"
            task_id = getattr(context, "task_id", "") or ""
            emitter.emit(
                AgentEvent(
                    event_type=EventType.FILE_DELETED,
                    agent_name=agent_name,
                    task_id=task_id,
                    metadata={"path": rel_path},
                )
            )

        return f"Successfully deleted file '{rel_path}'."

    return [list_directory, read_file, write_file, patch_file, delete_file]
