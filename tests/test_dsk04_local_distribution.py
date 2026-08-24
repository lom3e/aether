"""
Test suite for DSK-04A: Local macOS Distribution & DMG.

Covers:
- DSK-04-A: Existence and size of build/Aether.dmg
- DSK-04-B: Mountability and volume structure of Aether.dmg
- DSK-04-C: Presence of Applications drag-and-drop symlink in DMG
- DSK-04-D: Presence and metadata of Aether.app within mounted DMG
- DSK-04-E: Executable permissions of bundled binaries and sidecar within DMG
- DSK-04-F: Unmount clean detachment
- DSK-04-G: End-to-end installation from DMG to isolated target directory
- DSK-04-H: Execution of installed app from DMG with sanitized environment and user data isolation
"""
import json
import os
import plistlib
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
import pytest


def _get_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "src").exists():
            return current
        current = current.parent
    return Path.cwd()


def _get_dmg_path() -> Path:
    repo_root = _get_repo_root()
    return repo_root / "build" / "Aether.dmg"


def test_dsk_04_dmg_exists_and_size():
    """Verify that build/Aether.dmg exists and is a valid non-empty file."""
    dmg_path = _get_dmg_path()
    assert dmg_path.exists(), f"Aether.dmg not found at {dmg_path}"
    dmg_size_mb = os.path.getsize(dmg_path) / (1024 * 1024)
    assert dmg_size_mb > 10, f"Aether.dmg is unexpectedly small ({dmg_size_mb:.2f} MB)"


def test_dsk_04_dmg_mount_structure_and_app():
    """Mount Aether.dmg, verify volume layout, Applications link, and Info.plist."""
    dmg_path = _get_dmg_path()
    assert dmg_path.exists()

    # Mount DMG via hdiutil
    mount_out = subprocess.check_output(["hdiutil", "attach", str(dmg_path), "-plist"]).decode()
    plist_data = plistlib.loads(mount_out.encode("utf-8"))

    mount_point = None
    for entity in plist_data.get("system-entities", []):
        if "mount-point" in entity:
            mount_point = Path(entity["mount-point"])
            break

    assert mount_point is not None, "Failed to mount DMG volume"

    try:
        app_in_dmg = mount_point / "Aether.app"
        apps_link = mount_point / "Applications"

        # Check App bundle in DMG
        assert app_in_dmg.exists(), "Aether.app missing in DMG root"
        assert apps_link.exists() or apps_link.is_symlink(), "Applications link missing in DMG root"

        # Check Info.plist
        info_plist = app_in_dmg / "Contents" / "Info.plist"
        assert info_plist.exists()
        with open(info_plist, "rb") as f:
            meta = plistlib.load(f)

        assert meta.get("CFBundleIdentifier") == "com.aether.desktop"
        assert meta.get("CFBundleName") == "Aether"
        assert meta.get("CFBundleDisplayName") == "Aether"
        assert meta.get("CFBundleShortVersionString") in ["1.4.0", "1.5.0"]

        # Check main binary & sidecar permissions
        main_bin = app_in_dmg / "Contents" / "MacOS" / "aether-desktop"
        assert main_bin.exists()
        assert os.access(main_bin, os.X_OK)

        sidecar_bin = app_in_dmg / "Contents" / "Resources" / "aether-runtime" / "aether-runtime"
        if not sidecar_bin.exists():
            sidecar_bin = app_in_dmg / "Contents" / "Resources" / "resources" / "aether-runtime" / "aether-runtime"
        assert sidecar_bin.exists()
        assert os.access(sidecar_bin, os.X_OK)

        # Check app icon
        icon_file = app_in_dmg / "Contents" / "Resources" / "icon.icns"
        assert icon_file.exists()

    finally:
        # Detach cleanly
        subprocess.run(["hdiutil", "detach", str(mount_point)], check=True)


def test_dsk_04_install_from_dmg_and_execute(tmp_path):
    """
    Simulates mounting the DMG, dragging Aether.app to a target directory,
    unmounting the DMG, and launching the installed app with full data isolation.
    """
    dmg_path = _get_dmg_path()
    assert dmg_path.exists()

    # 1. Mount DMG
    mount_out = subprocess.check_output(["hdiutil", "attach", str(dmg_path), "-plist"]).decode()
    plist_data = plistlib.loads(mount_out.encode("utf-8"))

    mount_point = None
    for entity in plist_data.get("system-entities", []):
        if "mount-point" in entity:
            mount_point = Path(entity["mount-point"])
            break

    assert mount_point is not None

    install_dest = tmp_path / "Applications_Test"
    install_dest.mkdir(parents=True, exist_ok=True)
    installed_app = install_dest / "Aether.app"

    try:
        # 2. Drag & drop simulation (copy Aether.app from mounted volume)
        shutil.copytree(mount_point / "Aether.app", installed_app, symlinks=True)
    finally:
        # 3. Unmount DMG
        subprocess.run(["hdiutil", "detach", str(mount_point)], check=True)

    # 4. Verify installed app is intact
    assert installed_app.exists()
    main_bin = installed_app / "Contents" / "MacOS" / "aether-desktop"
    assert main_bin.exists()

    # 5. Launch installed app with isolated data dir
    user_data = tmp_path / "user_data"
    user_data.mkdir(parents=True, exist_ok=True)

    clean_env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "AETHER_DATA_DIR": str(user_data),
    }

    proc = subprocess.Popen(
        [str(main_bin)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=str(install_dest),
        env=clean_env,
    )

    bound_port = None
    for _ in range(25):
        line = proc.stdout.readline()
        if "Detected assigned backend port:" in line:
            bound_port = int(line.split(":")[-1].strip())
            break

    assert bound_port is not None, "Failed to capture port from installed Aether.app"

    try:
        # 6. Verify health endpoint
        req = urllib.request.Request(f"http://127.0.0.1:{bound_port}/api/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200
            data = json.loads(resp.read())
            assert data["status"] == "ok"
            assert data["version"] in ["1.4.0", "1.5.0"]

        # 7. Verify user data isolation
        assert user_data.exists()
        assert not (installed_app / "Contents" / "Resources" / "config.json").exists()

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
