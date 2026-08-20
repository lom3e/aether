#!/usr/bin/env python3
"""
Production Build Script for Aether Desktop macOS .app Bundle (DSK-03 / DSK-04A).
Automates the full pipeline:
1. Generates official multi-resolution icon set from website/public/brand/favicon.svg
2. Builds React UI bundle (Vite + TypeScript)
3. Builds Python standalone frozen runtime (PyInstaller onedir)
4. Copies frozen runtime into src-tauri/resources/aether-runtime/
5. Builds Tauri production release .app bundle
6. Verifies bundle structure, permissions, and exports to build/Aether.app
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
TAURI_APP_OUTPUT = TAURI_DIR / "target" / "release" / "bundle" / "macos" / "Aether.app"
FINAL_APP_OUTPUT = BUILD_DIR / "Aether.app"


def run_command(cmd, cwd=REPO_ROOT, env=None):
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    print(f"\n[BUILD STEP] Running: {cmd_str}")
    current_env = os.environ.copy()
    if env:
        current_env.update(env)
    # Ensure Cargo is in PATH
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.exists():
        current_env["PATH"] = f"{cargo_bin}:{current_env.get('PATH', '')}"

    result = subprocess.run(cmd, cwd=str(cwd), env=current_env, shell=isinstance(cmd, str))
    if result.returncode != 0:
        print(f"ERROR: Step failed with return code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def main():
    print("=" * 70)
    print("AETHER DESKTOP macOS .app BUNDLE PRODUCTION BUILD PIPELINE")
    print("=" * 70)

    # 1. Generate App Icons from Source of Truth SVG
    print("\n--- 1. Generating App Icons from website/public/brand/favicon.svg ---")
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

    # Also prepare binaries folder for any externalBin fallback
    binaries_dir = TAURI_DIR / "binaries"
    binaries_dir.mkdir(parents=True, exist_ok=True)
    target_sidecar_bin = binaries_dir / "aether-runtime-aarch64-apple-darwin"
    shutil.copy2(FROZEN_RUNTIME_DIR / "aether-runtime", target_sidecar_bin)
    os.chmod(target_sidecar_bin, 0o755)

    # 5. Build Tauri Release App Bundle
    print("\n--- 5. Building Tauri Production .app Bundle ---")
    run_command(["npx", "--prefix", "ui", "tauri", "build", "--bundles", "app"])

    # 6. Verify & Copy Output to build/Aether.app
    print("\n--- 6. Verifying & Exporting Aether.app ---")
    if not TAURI_APP_OUTPUT.exists():
        print(f"ERROR: Tauri .app bundle not found at {TAURI_APP_OUTPUT}", file=sys.stderr)
        sys.exit(1)

    if FINAL_APP_OUTPUT.exists():
        shutil.rmtree(FINAL_APP_OUTPUT, ignore_errors=True)
    shutil.copytree(TAURI_APP_OUTPUT, FINAL_APP_OUTPUT, symlinks=True)

    # Ensure a direct symlink/copy of aether-runtime under Contents/Resources/aether-runtime if nested
    app_contents = FINAL_APP_OUTPUT / "Contents"
    macos_dir = app_contents / "MacOS"
    resources_dir = app_contents / "Resources"
    info_plist = app_contents / "Info.plist"

    # Find the main executable in Contents/MacOS/
    executables = [f for f in macos_dir.iterdir() if f.is_file() and os.access(f, os.X_OK)]
    if not executables:
        print(f"ERROR: No executable found in {macos_dir}", file=sys.stderr)
        sys.exit(1)
    main_executable = executables[0]

    # Ensure direct path Contents/Resources/aether-runtime exists
    direct_res_runtime = resources_dir / "aether-runtime"
    nested_res_runtime = resources_dir / "resources" / "aether-runtime"
    if not direct_res_runtime.exists() and nested_res_runtime.exists():
        try:
            os.symlink("resources/aether-runtime", direct_res_runtime)
        except Exception:
            shutil.copytree(nested_res_runtime, direct_res_runtime, symlinks=True)

    # Ensure icon.icns is in Contents/Resources/
    bundled_icon = resources_dir / "icon.icns"
    if not bundled_icon.exists() and (TAURI_DIR / "icons" / "icon.icns").exists():
        shutil.copy2(TAURI_DIR / "icons" / "icon.icns", bundled_icon)

    assert info_plist.exists(), "Contents/Info.plist missing"
    assert main_executable.exists(), f"Main binary missing at {main_executable}"

    # Ensure executable permissions on all bundled binaries
    for root, _, files in os.walk(FINAL_APP_OUTPUT):
        for f in files:
            p = Path(root) / f
            if f in ["aether-desktop", "Aether", "aether-runtime"] or f.endswith(".dylib") or f.endswith(".so"):
                try:
                    os.chmod(p, 0o755)
                except Exception:
                    pass

    total_size = sum(
        os.path.getsize(os.path.join(dirpath, f))
        for dirpath, _, filenames in os.walk(FINAL_APP_OUTPUT)
        for f in filenames
        if not os.path.islink(os.path.join(dirpath, f))
    )
    total_size_mb = total_size / (1024 * 1024)

    sidecar_path = resources_dir / "aether-runtime"
    if not sidecar_path.exists():
        sidecar_path = nested_res_runtime
    sidecar_size = sum(
        os.path.getsize(os.path.join(dirpath, f))
        for dirpath, _, filenames in os.walk(sidecar_path)
        for f in filenames
        if not os.path.islink(os.path.join(dirpath, f))
    )
    sidecar_size_mb = sidecar_size / (1024 * 1024)

    print("\n" + "=" * 70)
    print("SUCCESS: Aether.app Production Bundle Created!")
    print(f"Location:      {FINAL_APP_OUTPUT}")
    print(f"Main Binary:   {main_executable}")
    print(f"Total Size:    {total_size_mb:.2f} MB")
    print(f"Sidecar Size:  {sidecar_size_mb:.2f} MB")
    print("=" * 70)
    return FINAL_APP_OUTPUT


if __name__ == "__main__":
    main()
