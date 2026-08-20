#!/usr/bin/env python3
"""
Production Distribution Script for Aether Desktop (DSK-04A).
Automates the full pipeline:
1. Builds React UI bundle
2. Freezes standalone Python sidecar (PyInstaller onedir)
3. Builds Tauri production Aether.app bundle
4. Generates compressed macOS disk image: build/Aether.dmg with Applications drag-and-drop link
5. Validates bundle & DMG integrity
"""
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"
SCRIPTS_DIR = REPO_ROOT / "scripts"
BUILD_DESKTOP_SCRIPT = SCRIPTS_DIR / "build_desktop_app.py"
APP_OUTPUT = BUILD_DIR / "Aether.app"
DMG_OUTPUT = BUILD_DIR / "Aether.dmg"
DMG_STAGING_DIR = BUILD_DIR / "dmg_staging"


def run_command(cmd, cwd=REPO_ROOT, env=None):
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    print(f"\n[DIST STEP] Running: {cmd_str}")
    current_env = os.environ.copy()
    if env:
        current_env.update(env)
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.exists():
        current_env["PATH"] = f"{cargo_bin}:{current_env.get('PATH', '')}"

    result = subprocess.run(cmd, cwd=str(cwd), env=current_env, shell=isinstance(cmd, str))
    if result.returncode != 0:
        print(f"ERROR: Step failed with return code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def create_dmg() -> Path:
    print("\n--- Generating Compressed macOS Disk Image (Aether.dmg) ---")
    if not APP_OUTPUT.exists():
        print(f"ERROR: Expected {APP_OUTPUT} before creating DMG.", file=sys.stderr)
        sys.exit(1)

    if DMG_STAGING_DIR.exists():
        shutil.rmtree(DMG_STAGING_DIR, ignore_errors=True)
    DMG_STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Copy Aether.app into staging
    staging_app = DMG_STAGING_DIR / "Aether.app"
    print(f"Staging Aether.app -> {staging_app}...")
    shutil.copytree(APP_OUTPUT, staging_app, symlinks=True)

    # 2. Create Applications symlink for drag-and-drop installer UX
    staging_apps_link = DMG_STAGING_DIR / "Applications"
    print(f"Creating Applications symlink -> {staging_apps_link}...")
    os.symlink("/Applications", staging_apps_link)

    # 3. Create DMG via hdiutil
    if DMG_OUTPUT.exists():
        os.unlink(DMG_OUTPUT)

    print(f"Creating UDZO compressed DMG at {DMG_OUTPUT}...")
    hdiutil_cmd = [
        "hdiutil", "create",
        "-volname", "Aether",
        "-srcfolder", str(DMG_STAGING_DIR),
        "-ov",
        "-format", "UDZO",
        str(DMG_OUTPUT)
    ]
    subprocess.run(hdiutil_cmd, check=True)

    # 4. Clean up staging
    shutil.rmtree(DMG_STAGING_DIR, ignore_errors=True)

    assert DMG_OUTPUT.exists(), f"Failed to generate {DMG_OUTPUT}"
    return DMG_OUTPUT


def validate_distribution():
    print("\n--- Validating Distribution Artifacts ---")
    assert APP_OUTPUT.exists(), "Aether.app missing"
    assert DMG_OUTPUT.exists(), "Aether.dmg missing"

    # Validate Info.plist
    info_plist = APP_OUTPUT / "Contents" / "Info.plist"
    with open(info_plist, "rb") as f:
        plist_data = plistlib.load(f)

    assert plist_data.get("CFBundleIdentifier") == "com.aether.desktop"
    assert plist_data.get("CFBundleDisplayName") == "Aether"
    assert plist_data.get("CFBundleShortVersionString") == "1.3.5"

    # Validate DMG by mounting temporarily
    print("Testing DMG mount integrity...")
    mount_out = subprocess.check_output(["hdiutil", "attach", str(DMG_OUTPUT), "-plist"]).decode()
    plist_mount = plistlib.loads(mount_out.encode("utf-8"))
    mount_point = None
    for entity in plist_mount.get("system-entities", []):
        if "mount-point" in entity:
            mount_point = Path(entity["mount-point"])
            break

    assert mount_point is not None, "Failed to mount DMG"
    try:
        assert (mount_point / "Aether.app").exists(), "Aether.app not found in mounted DMG"
        apps_link = mount_point / "Applications"
        assert apps_link.exists() or apps_link.is_symlink(), "Applications link not found in mounted DMG"
        print(f"✓ DMG volume verified at {mount_point}")
    finally:
        subprocess.run(["hdiutil", "detach", str(mount_point)], check=True)

    app_size_mb = sum(
        os.path.getsize(os.path.join(dirpath, f))
        for dirpath, _, filenames in os.walk(APP_OUTPUT)
        for f in filenames
        if not os.path.islink(os.path.join(dirpath, f))
    ) / (1024 * 1024)

    dmg_size_mb = os.path.getsize(DMG_OUTPUT) / (1024 * 1024)

    print("\n" + "=" * 70)
    print("SUCCESS: Aether Desktop Distribution Pipeline Completed!")
    print(f"App Bundle:    {APP_OUTPUT} ({app_size_mb:.2f} MB)")
    print(f"DMG Installer: {DMG_OUTPUT} ({dmg_size_mb:.2f} MB)")
    print("=" * 70)


def main():
    print("=" * 70)
    print("AETHER DESKTOP DISTRIBUTION PIPELINE (DSK-04A)")
    print("=" * 70)

    # Step 1: Build Aether.app
    run_command([sys.executable, str(BUILD_DESKTOP_SCRIPT)])

    # Step 2: Create Aether.dmg
    create_dmg()

    # Step 3: Validate
    validate_distribution()


if __name__ == "__main__":
    main()
