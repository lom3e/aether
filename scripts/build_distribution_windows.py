#!/usr/bin/env python3
"""
Production Distribution and Build Script for Aether Desktop Windows (P3-07).
Automates the full Windows release pipeline:
1. Generates multi-resolution Windows app icons (icon.ico, 32x32.png, 128x128.png, icon.png)
2. Builds React Frontend UI bundle (Vite + TypeScript)
3. Freezes Standalone Python Runtime sidecar (PyInstaller onedir -> aether-runtime.exe)
4. Synchronizes sidecar to src-tauri/resources/ and src-tauri/binaries/
5. Builds Tauri production release NSIS installer bundle
6. Validates bundle integrity and exports installer to build/Aether-x64-setup.exe
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"
TAURI_DIR = REPO_ROOT / "src-tauri"
RESOURCES_DIR = TAURI_DIR / "resources"
FROZEN_RUNTIME_DIR = BUILD_DIR / "aether-runtime"
TAURI_NSIS_OUTPUT_DIR = TAURI_DIR / "target" / "release" / "bundle" / "nsis"
FINAL_INSTALLER_OUTPUT = BUILD_DIR / "Aether-x64-setup.exe"


def run_command(cmd, cwd=REPO_ROOT, env=None):
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    print(f"\n[WIN BUILD STEP] Running: {cmd_str}")
    current_env = os.environ.copy()
    if env:
        current_env.update(env)

    # Ensure Cargo/Rust binaries are in PATH if available
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.exists():
        path_var = current_env.get("PATH", "")
        current_env["PATH"] = f"{cargo_bin}{os.pathsep}{path_var}"

    result = subprocess.run(cmd, cwd=str(cwd), env=current_env, shell=isinstance(cmd, str))
    if result.returncode != 0:
        print(f"ERROR: Step failed with return code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def build_windows_distribution(skip_tauri_on_non_windows: bool = True) -> Path | None:
    print("=" * 70)
    print("AETHER DESKTOP WINDOWS NSIS INSTALLER PRODUCTION BUILD PIPELINE")
    print("=" * 70)

    # 1. Generate App Icons (including icon.ico)
    print("\n--- 1. Generating Windows App Icons (icon.ico + PNGs) ---")
    gen_icons_script = REPO_ROOT / "scripts" / "generate_app_icons.py"
    run_command([sys.executable, str(gen_icons_script)])

    # 2. Build React UI
    print("\n--- 2. Building React Frontend UI Bundle ---")
    run_command(["npm", "--prefix", "ui", "run", "build"])

    # Synchronize built UI to Python backend static directory
    ui_dist_dir = REPO_ROOT / "ui" / "dist"
    server_static_dir = REPO_ROOT / "src" / "aether" / "server" / "static"
    if ui_dist_dir.exists():
        print(f"Synchronizing {ui_dist_dir} -> {server_static_dir}...")
        if server_static_dir.exists():
            shutil.rmtree(server_static_dir, ignore_errors=True)
        shutil.copytree(ui_dist_dir, server_static_dir, symlinks=True)

    # 3. Build Python Standalone Runtime (PyInstaller onedir)
    print("\n--- 3. Freezing Standalone Python Runtime ---")
    build_py_script = REPO_ROOT / "scripts" / "build_python_runtime.py"
    run_command([sys.executable, str(build_py_script)])

    # 4. Synchronize Sidecar to Tauri Resources Directory
    print("\n--- 4. Synchronizing Sidecar to Tauri Resources ---")
    if not FROZEN_RUNTIME_DIR.exists():
        print(f"ERROR: Expected frozen runtime at {FROZEN_RUNTIME_DIR}", file=sys.stderr)
        sys.exit(1)

    dest_runtime_dir = RESOURCES_DIR / "aether-runtime"
    if dest_runtime_dir.exists():
        shutil.rmtree(dest_runtime_dir, ignore_errors=True)
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Copying {FROZEN_RUNTIME_DIR} -> {dest_runtime_dir}...")
    shutil.copytree(FROZEN_RUNTIME_DIR, dest_runtime_dir, symlinks=True)

    # Also prepare binaries folder for target externalBin
    binaries_dir = TAURI_DIR / "binaries"
    binaries_dir.mkdir(parents=True, exist_ok=True)
    sidecar_bin_name = "aether-runtime.exe" if (FROZEN_RUNTIME_DIR / "aether-runtime.exe").exists() else "aether-runtime"
    target_sidecar_bin = binaries_dir / "aether-runtime-x86_64-pc-windows-msvc.exe"
    shutil.copy2(FROZEN_RUNTIME_DIR / sidecar_bin_name, target_sidecar_bin)

    # 5. Build Tauri NSIS Installer on Windows
    if sys.platform != "win32" and skip_tauri_on_non_windows:
        print("\n[NOTE] Current environment is non-Windows host (cross-compilation target).")
        print("Python runtime, UI bundle, icons, and Tauri resources staged successfully.")
        print("To build the final NSIS installer .exe, run this pipeline on a Windows host or CI runner.")
        return None

    print("\n--- 5. Building Tauri Production NSIS Installer ---")
    run_command(["npx", "--prefix", "ui", "tauri", "build", "--bundles", "nsis"])

    # 6. Verify & Export Installer
    print("\n--- 6. Verifying & Exporting Windows Installer ---")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    nsis_installers = list(TAURI_NSIS_OUTPUT_DIR.glob("*.exe"))
    if not nsis_installers:
        print(f"ERROR: No NSIS installer found in {TAURI_NSIS_OUTPUT_DIR}", file=sys.stderr)
        sys.exit(1)

    source_installer = nsis_installers[0]
    shutil.copy2(source_installer, FINAL_INSTALLER_OUTPUT)
    installer_size_mb = FINAL_INSTALLER_OUTPUT.stat().st_size / (1024 * 1024)

    print(f"\n==================================================")
    print(f"SUCCESS: Windows NSIS Installer built successfully!")
    print(f"Installer: {FINAL_INSTALLER_OUTPUT} ({installer_size_mb:.1f} MB)")
    print(f"==================================================\n")
    return FINAL_INSTALLER_OUTPUT


if __name__ == "__main__":
    build_windows_distribution(skip_tauri_on_non_windows=False if "--force-tauri" in sys.argv else True)
