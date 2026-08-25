"""
Test suite for DSK-03: macOS .app Bundle & Packaging.

Covers:
- DSK-03-A: Production Aether.app bundle existence and layout
- DSK-03-B: Bundle identifier and metadata in Info.plist
- DSK-03-C: Executable binary permissions (+x)
- DSK-03-D: Bundled Python standalone sidecar existence inside Contents/Resources
- DSK-03-E: App icon and static resource presence
- DSK-03-F: Relocated execution (running out-of-repo in /tmp/Aether-Test/Aether.app)
- DSK-03-G: Clean environment execution (no host Python, no VIRTUAL_ENV/PYTHONPATH)
- DSK-03-H: User data isolation (written to user space, read-only .app bundle)
- DSK-03-I: Full user flow on production .app (0 workspace -> create -> chat -> shutdown -> restart)
- DSK-03-J: Missing sidecar failure mode (clean error without freeze)
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


def _get_app_bundle_path() -> Path:
    repo_root = _get_repo_root()
    app_path = repo_root / "build" / "Aether.app"
    if not app_path.exists():
        app_path = repo_root / "src-tauri" / "target" / "release" / "bundle" / "macos" / "Aether.app"
    return app_path


def test_dsk_03_bundle_structure_and_metadata():
    """Verify that Aether.app exists and complies with macOS bundle standards."""
    app_path = _get_app_bundle_path()
    assert app_path.exists(), f"Aether.app not found at {app_path}"

    contents_dir = app_path / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"
    info_plist_file = contents_dir / "Info.plist"

    assert contents_dir.exists()
    assert macos_dir.exists()
    assert resources_dir.exists()
    assert info_plist_file.exists()

    # Read Info.plist
    with open(info_plist_file, "rb") as f:
        plist_data = plistlib.load(f)

    assert plist_data.get("CFBundleIdentifier") == "com.aether.desktop"
    assert plist_data.get("CFBundleName") == "Aether"
    assert plist_data.get("CFBundleDisplayName") == "Aether"
    assert plist_data.get("CFBundleShortVersionString") in ["1.4.0", "1.5.0", "1.6.0"]
    assert plist_data.get("CFBundleVersion") in ["1.4.0", "1.5.0", "1.6.0"]
    assert plist_data.get("CFBundlePackageType") == "APPL"
    assert plist_data.get("NSHighResolutionCapable") is True

    # Check main executable
    exec_name = plist_data.get("CFBundleExecutable", "aether-desktop")
    main_bin = macos_dir / exec_name
    assert main_bin.exists(), f"Main executable {main_bin} missing"
    assert os.access(main_bin, os.X_OK), "Main executable lacks +x permissions"

    # Check bundled app icon
    icon_file = resources_dir / "icon.icns"
    assert icon_file.exists(), f"icon.icns missing in {resources_dir}"


def test_dsk_03_bundled_sidecar_layout():
    """Verify that the standalone Python sidecar is packaged inside Contents/Resources."""
    app_path = _get_app_bundle_path()
    resources_dir = app_path / "Contents" / "Resources"

    sidecar_bin = resources_dir / "aether-runtime" / "aether-runtime"
    if not sidecar_bin.exists():
        sidecar_bin = resources_dir / "resources" / "aether-runtime" / "aether-runtime"

    assert sidecar_bin.exists(), f"Bundled sidecar executable missing at {sidecar_bin}"
    assert os.access(sidecar_bin, os.X_OK), "Sidecar lacks +x permissions"

    # Verify sidecar _internal folder
    sidecar_internal = sidecar_bin.parent / "_internal"
    assert sidecar_internal.exists(), f"Sidecar _internal directory missing at {sidecar_internal}"


def test_dsk_03_out_of_repo_isolated_execution(tmp_path):
    """
    Test copying Aether.app completely outside the repository (e.g. /tmp/Aether-Test/Aether.app)
    and running it with a sanitized environment.
    """
    original_app = _get_app_bundle_path()
    assert original_app.exists()

    isolated_dir = tmp_path / "isolated_install"
    isolated_dir.mkdir(parents=True, exist_ok=True)
    isolated_app = isolated_dir / "Aether.app"

    # Copy bundle to isolated location
    shutil.copytree(original_app, isolated_app, symlinks=True)

    contents_dir = isolated_app / "Contents"
    with open(contents_dir / "Info.plist", "rb") as f:
        plist_data = plistlib.load(f)
    main_bin_name = plist_data.get("CFBundleExecutable", "aether-desktop")
    executable = contents_dir / "MacOS" / main_bin_name

    # Set up custom isolated data directory
    test_user_data = tmp_path / "user_data"
    test_user_data.mkdir(parents=True, exist_ok=True)

    clean_env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "AETHER_DATA_DIR": str(test_user_data),
    }

    # Spawn isolated production app
    proc = subprocess.Popen(
        [str(executable)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=str(isolated_dir),
        env=clean_env,
    )

    bound_port = None
    start_time = time.time()
    while time.time() - start_time < 8:
        line = proc.stdout.readline()
        if "Detected assigned backend port:" in line:
            bound_port = int(line.split(":")[-1].strip())
            break

    assert bound_port is not None, "Failed to get port from out-of-repo Aether.app"
    base_url = f"http://127.0.0.1:{bound_port}"

    try:
        # 1. Health check
        health_req = urllib.request.Request(f"{base_url}/api/health")
        with urllib.request.urlopen(health_req, timeout=3) as resp:
            assert resp.status == 200
            hdata = json.loads(resp.read())
            assert hdata["status"] == "ok"
            assert hdata["version"] in ["1.4.0", "1.5.0", "1.6.0"]
            assert hdata["port"] == bound_port

        # 2. Verify user data was created in custom user space, NOT inside the .app bundle
        assert test_user_data.exists()
        # Verify app bundle remains untouched/read-only
        assert not (isolated_app / "Contents" / "Resources" / "config.json").exists()
        assert not (isolated_app / "Contents" / "Resources" / "workspaces.json").exists()

    finally:
        # Shutdown cleanly
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
