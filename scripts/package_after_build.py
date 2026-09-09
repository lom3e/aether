#!/usr/bin/env python3
"""
Post-Build Packaging Coordinator for Aether Desktop (DSK-04A / Automatic DMG Pipeline).
Invoked automatically following frontend compilation (`npm run build`).

Sequential Pipeline:
1. Verify `ui/dist` presence and integrity.
2. Synchronize frontend static assets: `ui/dist` -> `src/aether/server/static`.
3. Clear stale `build/Aether.dmg` to guarantee atomic success/failure semantics.
4. Execute `scripts/build_distribution.py --skip-ui` (compiles Aether.app, packages UDZO DMG, mounts & validates).
5. Verify that `build/Aether.dmg` is freshly generated and conforms to size/integrity thresholds.
6. Print distribution summary (DMG path and size).
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

# Re-execute with project virtual environment Python if available
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

PYTHON_BIN = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
UI_DIST_DIR = REPO_ROOT / "ui" / "dist"
SERVER_STATIC_DIR = REPO_ROOT / "src" / "aether" / "server" / "static"
BUILD_DIR = REPO_ROOT / "build"
APP_OUTPUT = BUILD_DIR / "Aether.app"
DMG_OUTPUT = BUILD_DIR / "Aether.dmg"
BUILD_DIST_SCRIPT = REPO_ROOT / "scripts" / "build_distribution.py"


def sync_frontend_static_assets() -> int:
    """Synchronizes ui/dist into src/aether/server/static."""
    print("\n--- [PIPELINE] 1. Synchronizing Frontend Static Assets ---")
    if not UI_DIST_DIR.exists() or not (UI_DIST_DIR / "index.html").exists():
        print(
            f"ERROR: UI distribution artifacts not found at {UI_DIST_DIR}. "
            f"Expected {UI_DIST_DIR / 'index.html'} to exist.",
            file=sys.stderr,
        )
        sys.exit(1)

    SERVER_STATIC_DIR.parent.mkdir(parents=True, exist_ok=True)
    if SERVER_STATIC_DIR.exists():
        shutil.rmtree(SERVER_STATIC_DIR, ignore_errors=True)

    shutil.copytree(UI_DIST_DIR, SERVER_STATIC_DIR, symlinks=True)

    static_index = SERVER_STATIC_DIR / "index.html"
    if not static_index.exists() or static_index.stat().st_size == 0:
        print(
            f"ERROR: Static asset synchronization failed: {static_index} missing or empty.",
            file=sys.stderr,
        )
        sys.exit(1)

    file_count = sum(len(files) for _, _, files in os.walk(SERVER_STATIC_DIR))
    print(f"✓ Synchronized {file_count} frontend files into {SERVER_STATIC_DIR}")
    return file_count


def run_packaging_pipeline():
    """Executes the desktop app build and DMG distribution pipeline."""
    print("\n--- [PIPELINE] 2. Packaging Desktop Application & macOS DMG ---")
    if not BUILD_DIST_SCRIPT.exists():
        print(f"ERROR: Build distribution script missing at {BUILD_DIST_SCRIPT}", file=sys.stderr)
        sys.exit(1)

    # Remove pre-existing DMG to ensure freshness and prevent reporting false success
    if DMG_OUTPUT.exists():
        print(f"Cleaning existing DMG at {DMG_OUTPUT} to ensure fresh build...")
        try:
            os.unlink(DMG_OUTPUT)
        except Exception as e:
            print(f"WARNING: Could not remove old DMG: {e}", file=sys.stderr)

    start_time = time.time()

    cmd = [PYTHON_BIN, str(BUILD_DIST_SCRIPT), "--skip-ui"]
    cmd_str = " ".join(cmd)
    print(f"Running: {cmd_str}")

    env = os.environ.copy()
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.exists():
        env["PATH"] = f"{cargo_bin}:{env.get('PATH', '')}"

    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    if result.returncode != 0:
        print(
            f"\nERROR: Packaging pipeline failed with exit code {result.returncode}",
            file=sys.stderr,
        )
        sys.exit(result.returncode)

    # Validation of generated artifacts
    if not APP_OUTPUT.exists():
        print(f"ERROR: Expected application bundle at {APP_OUTPUT} not found!", file=sys.stderr)
        sys.exit(1)

    if not DMG_OUTPUT.exists():
        print(f"ERROR: Expected DMG disk image at {DMG_OUTPUT} not found!", file=sys.stderr)
        sys.exit(1)

    dmg_stat = DMG_OUTPUT.stat()
    dmg_size_bytes = dmg_stat.st_size
    dmg_size_mb = dmg_size_bytes / (1024 * 1024)

    if dmg_size_mb < 10.0:
        print(
            f"ERROR: Generated DMG is unexpectedly small ({dmg_size_mb:.2f} MB < 10 MB)",
            file=sys.stderr,
        )
        sys.exit(1)

    if dmg_stat.st_mtime < start_time - 5.0:
        print(
            f"ERROR: DMG timestamp was not updated during this build cycle.",
            file=sys.stderr,
        )
        sys.exit(1)

    app_size_mb = sum(
        os.path.getsize(os.path.join(dirpath, f))
        for dirpath, _, filenames in os.walk(APP_OUTPUT)
        for f in filenames
        if not os.path.islink(os.path.join(dirpath, f))
    ) / (1024 * 1024)

    print("\n" + "=" * 74)
    print("  AETHER AUTOMATIC DMG BUILD PIPELINE: COMPLETED SUCCESSFULLY")
    print("=" * 74)
    print(f"  Frontend Static Assets: {SERVER_STATIC_DIR} (synchronized)")
    print(f"  Desktop App Bundle:     {APP_OUTPUT} ({app_size_mb:.2f} MB)")
    print(f"  DMG Disk Image:         {DMG_OUTPUT}")
    print(f"  DMG Disk Image Size:    {dmg_size_mb:.2f} MB ({dmg_size_bytes:,} bytes)")
    print("=" * 74 + "\n")


def main():
    sync_frontend_static_assets()
    run_packaging_pipeline()


if __name__ == "__main__":
    main()
