"""
Helper for tests that need a fake coding-agent executable.

The agent is a tiny POSIX ``sh`` script. POSIX can execute it directly through its shebang; Windows cannot, so there a
``.cmd`` wrapper runs the same script through Git's ``sh`` (skipping the test if no ``sh`` is available).
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

import pytest


def _find_sh() -> str | None:
    found = shutil.which("sh")
    if found:
        return found
    for candidate in (r"C:\Program Files\Git\usr\bin\sh.exe", r"C:\Program Files (x86)\Git\usr\bin\sh.exe"):
        if os.path.exists(candidate):
            return candidate
    return None


def write_agent_script(directory: Path, name: str, body: str) -> str:
    """Writes ``body`` as an executable agent and returns the path to run (the .sh on POSIX, a .cmd on Windows)."""
    script = Path(directory) / f"{name}.sh"
    script.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8", newline="\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    if sys.platform != "win32":
        return str(script)
    sh = _find_sh()
    if sh is None:
        pytest.skip("a POSIX sh is required to run the fake agent script on Windows")
    wrapper = Path(directory) / f"{name}.cmd"
    wrapper.write_text(f'@echo off\r\n"{sh}" "%~dp0{script.name}" %*\r\n', encoding="ascii")
    return str(wrapper)
