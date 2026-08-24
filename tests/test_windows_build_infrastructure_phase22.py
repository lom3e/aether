"""
Test suite for P3-07: Windows Build Infrastructure.
Validates:
1. Windows distribution build script (scripts/build_distribution_windows.py).
2. Tauri Windows & NSIS bundle configuration (src-tauri/tauri.conf.json).
3. Rust supervisor cross-platform paths (%APPDATA%, aether-runtime.exe, Scripts/python.exe).
4. Cross-platform PyInstaller path separator handling (os.pathsep).
5. GitHub Actions Windows CI pipeline workflow (.github/workflows/windows-build.yml).
6. Comprehensive documentation (docs/product/windows-packaging.md).
"""
import json
from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_windows_distribution_script_contract():
    """Verify scripts/build_distribution_windows.py existence, structure, and functions."""
    win_script = REPO_ROOT / "scripts" / "build_distribution_windows.py"
    assert win_script.exists(), "scripts/build_distribution_windows.py must exist"

    script_content = win_script.read_text(encoding="utf-8")
    assert "build_windows_distribution" in script_content
    assert "build_python_runtime.py" in script_content
    assert "generate_app_icons.py" in script_content
    assert "aether-runtime-x86_64-pc-windows-msvc.exe" in script_content
    assert "Aether-x64-setup.exe" in script_content
    assert "nsis" in script_content


def test_tauri_conf_windows_and_nsis_contract():
    """Verify that src-tauri/tauri.conf.json contains Windows and NSIS targets and ico icons."""
    tauri_conf_path = REPO_ROOT / "src-tauri" / "tauri.conf.json"
    assert tauri_conf_path.exists(), "src-tauri/tauri.conf.json must exist"

    with open(tauri_conf_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    bundle = config.get("bundle", {})
    targets = bundle.get("targets", [])
    assert "nsis" in targets, "targets must include 'nsis'"
    assert "app" in targets, "targets must include 'app' for macOS"

    icons = bundle.get("icon", [])
    assert "icons/icon.ico" in icons, "icon list must include 'icons/icon.ico'"

    windows_conf = bundle.get("windows", {})
    assert "digestAlgorithm" in windows_conf


def test_tauri_rust_main_windows_support():
    """Verify that src-tauri/src/main.rs handles Windows paths, APPDATA, and exe candidates."""
    main_rs = REPO_ROOT / "src-tauri" / "src" / "main.rs"
    assert main_rs.exists()

    content = main_rs.read_text(encoding="utf-8")
    assert 'cfg(target_os = "windows")' in content
    assert "APPDATA" in content
    assert "USERPROFILE" in content
    assert "aether-runtime.exe" in content
    assert "Scripts" in content and "python.exe" in content


def test_pyinstaller_cross_platform_pathsep():
    """Verify that build_python_runtime.py uses os.pathsep for cross-platform add-data."""
    py_script = REPO_ROOT / "scripts" / "build_python_runtime.py"
    assert py_script.exists()

    content = py_script.read_text(encoding="utf-8")
    assert "os.pathsep" in content or "pathsep" in content
    assert "aether-runtime.exe" in content


def test_github_actions_windows_workflow_contract():
    """Verify that .github/workflows/windows-build.yml is configured properly for CI."""
    workflow_path = REPO_ROOT / ".github" / "workflows" / "windows-build.yml"
    assert workflow_path.exists(), ".github/workflows/windows-build.yml must exist"

    content = workflow_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)

    assert "jobs" in parsed
    build_job = parsed["jobs"].get("build-windows", {})
    assert build_job.get("runs-on") == "windows-latest"

    steps = build_job.get("steps", [])
    step_names = [s.get("name", "") for s in steps]

    assert any("Checkout" in name for name in step_names)
    assert any("Python" in name for name in step_names)
    assert any("Node" in name for name in step_names)
    assert any("Rust" in name for name in step_names)
    assert any("Windows Desktop Build" in name or "Build Windows" in name for name in step_names)
    assert any("Upload" in name for name in step_names)


def test_windows_packaging_documentation():
    """Verify that docs/product/windows-packaging.md exists and covers key packaging topics."""
    doc_path = REPO_ROOT / "docs" / "product" / "windows-packaging.md"
    assert doc_path.exists()

    content = doc_path.read_text(encoding="utf-8")
    assert "Aether Desktop" in content
    assert "%APPDATA%" in content
    assert "NSIS" in content
    assert "build_distribution_windows.py" in content
    assert "GitHub Actions" in content
