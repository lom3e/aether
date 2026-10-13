"""
Single definition of the directories that Aether must never treat as a project/workspace (delegating coding to them,
connecting them as a project, deleting them as a workspace, ...).

The previous checks were hand-written POSIX strings ("/System", "/etc", ...) repeated in several places, so on Windows
the Windows and Program Files directories and the drive root were not protected at all.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_POSIX_ROOTS = (
    "/", "/System", "/usr", "/bin", "/sbin", "/etc", "/var", "/Library", "/private", "/private/var", "/tmp",
    "/private/tmp", "/Users", "/home", "/Applications", "/Volumes", "/dev", "/opt", "/lib", "/boot", "/root",
)
_WINDOWS_ENV_ROOTS = ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData")


def _safe_resolve(raw: str | os.PathLike[str]) -> Path | None:
    try:
        return Path(raw).resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def protected_system_roots() -> set[Path]:
    """Directories that are protected themselves (their children are not, except where noted by the caller)."""
    roots: set[Path] = set()
    if sys.platform == "win32":
        for var in _WINDOWS_ENV_ROOTS:
            value = os.environ.get(var)
            if value and (p := _safe_resolve(value)) is not None:
                roots.add(p)
        drive = os.environ.get("SystemDrive", "C:")
        sep = os.sep
        for name in ("", "Windows", "Program Files", "Program Files (x86)", "ProgramData", "Users"):
            if (p := _safe_resolve(drive + sep + name)) is not None:
                roots.add(p)
    else:
        for raw in _POSIX_ROOTS:
            if (p := _safe_resolve(raw)) is not None:
                roots.add(p)
    if (tmp := _safe_resolve(tempfile.gettempdir())) is not None:
        roots.add(tmp)
    return roots


def is_protected_system_path(path: str | os.PathLike[str]) -> bool:
    """True for a filesystem root of any drive/mount, or one of the protected system directories above."""
    resolved = _safe_resolve(path)
    if resolved is None:
        return True  # cannot be resolved safely -> refuse
    if resolved.parent == resolved:  # "/" or "C:\" or "\server\share\"
        return True
    return resolved in protected_system_roots()
