#!/usr/bin/env python3
"""
Build script for freezing the Aether Python Runtime into a standalone onedir sidecar.
Uses PyInstaller to bundle Python, FastAPI, Uvicorn, SQLite, and Aether components
into an isolated executable without external Python dependencies.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
ENTRYPOINT = SRC_DIR / "aether" / "entrypoint_standalone.py"
BUILD_DIR = REPO_ROOT / "build"
DIST_DIR = BUILD_DIR / "dist"
WORK_DIR = BUILD_DIR / "pyinstaller_temp"
OUTPUT_DIR = BUILD_DIR / "aether-runtime"

HIDDEN_IMPORTS = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespans",
    "uvicorn.lifespans.on",
    "uvicorn.lifespans.off",
    "fastapi",
    "starlette",
    "starlette.routing",
    "starlette.middleware",
    "starlette.middleware.cors",
    "starlette.staticfiles",
    "pydantic",
    "pydantic_core",
    "sqlite3",
    "yaml",
    "websockets",
    "multipart",
    "python_multipart",
    "aether",
    "aether.cli",
    "aether.cli.main",
    "aether.core",
    "aether.core.paths",
    "aether.core.sqlite",
    "aether.server",
    "aether.server.app",
    "aether.server.routes",
    "aether.server.sockets",
    "aether.workspace",
    "aether.workspace.workspace",
    "aether.workspace.registry",
    "aether.presets",
    "aether.presets.loader",
    "aether.presets.manifest",
    "aether.presets.applier",
    "aether.providers",
    "aether.providers.base",
    "aether.providers.ollama",
    "aether.providers.openai",
    "aether.providers.anthropic",
    "aether.providers.gemini",
    "aether.agents",
    "aether.team",
    "aether.knowledge",
    "aether.memory",
    "aether.skills",
]


def build_runtime() -> Path:
    print(f"==================================================")
    print(f"Building Aether Standalone Python Runtime (onedir)")
    print(f"Repository Root: {REPO_ROOT}")
    print(f"Entrypoint:      {ENTRYPOINT}")
    print(f"==================================================")

    # 1. Clean previous build artifacts
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR, ignore_errors=True)

    # 1b. Ensure UI dist is synchronized to server/static
    ui_dist_dir = REPO_ROOT / "ui" / "dist"
    server_static_dir = SRC_DIR / "aether" / "server" / "static"
    if ui_dist_dir.exists():
        print(f"Syncing UI bundle {ui_dist_dir} -> {server_static_dir}...")
        if server_static_dir.exists():
            shutil.rmtree(server_static_dir, ignore_errors=True)
        shutil.copytree(ui_dist_dir, server_static_dir, symlinks=True)

    # 2. Prepare PyInstaller command
    pyinstaller_bin = shutil.which("pyinstaller") or sys.executable
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--name",
        "aether-runtime",
        "--distpath",
        str(BUILD_DIR),
        "--workpath",
        str(WORK_DIR),
        "--specpath",
        str(BUILD_DIR),
        "--paths",
        str(SRC_DIR),
        "--noconfirm",
        "--clean",
    ]

    # Include builtin presets package data
    builtin_presets = SRC_DIR / "aether" / "presets" / "builtin"
    if builtin_presets.exists():
        cmd.extend(["--add-data", f"{builtin_presets}:aether/presets/builtin"])

    # Include UI dist if present
    ui_dist = REPO_ROOT / "ui" / "dist"
    if ui_dist.exists():
        cmd.extend(["--add-data", f"{ui_dist}:ui/dist"])

    # Add hidden imports
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])

    cmd.append(str(ENTRYPOINT))

    print(f"Running PyInstaller...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)

    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    if result.returncode != 0:
        print(f"ERROR: PyInstaller build failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    executable_path = OUTPUT_DIR / "aether-runtime"
    if not executable_path.exists():
        # On Windows or alternative layout
        executable_path_win = OUTPUT_DIR / "aether-runtime.exe"
        if executable_path_win.exists():
            executable_path = executable_path_win

    if not executable_path.exists():
        print(f"ERROR: Expected executable not found at {executable_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n==================================================")
    print(f"SUCCESS: Frozen runtime built successfully!")
    print(f"Executable: {executable_path}")
    print(f"Bundle dir: {OUTPUT_DIR}")
    print(f"==================================================\n")
    return executable_path


if __name__ == "__main__":
    build_runtime()
