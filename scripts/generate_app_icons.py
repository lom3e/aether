#!/usr/bin/env python3
"""
App Icon Generation Pipeline for Aether Desktop (DSK-04A).

Source of truth:
  src-tauri/icons/source/aether_icon_master_1024.png
  (1024×1024 RGBA, transparent background, no mask, no squircle, no shadow)

The master artwork is pre-optimised for macOS:
  - Symbol at 82% canvas width
  - Optical centering (slightly raised)
  - Apple applies the squircle mask at system level — we do NOT embed it.

Output: src-tauri/icons/ (icon.icns, icon.ico, icon.png, 32x32.png, 128x128.png, etc.)
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Approved master — single source of truth for all icon outputs
MASTER_PNG = REPO_ROOT / "src-tauri" / "icons" / "source" / "aether_icon_master_1024.png"
ICONS_DIR = REPO_ROOT / "src-tauri" / "icons"


def build_macos_icns(master_png: Path, output_icns: Path):
    """Build icon.icns from the master PNG using native macOS iconutil."""
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow is required. Run 'pip install pillow'.", file=sys.stderr)
        sys.exit(1)

    print("Building native macOS .icns via iconutil...")

    with tempfile.TemporaryDirectory() as temp_dir:
        iconset_dir = Path(temp_dir) / "icon.iconset"
        iconset_dir.mkdir(parents=True, exist_ok=True)

        sizes = [
            ("icon_16x16.png",      16),
            ("icon_16x16@2x.png",   32),
            ("icon_32x32.png",      32),
            ("icon_32x32@2x.png",   64),
            ("icon_128x128.png",    128),
            ("icon_128x128@2x.png", 256),
            ("icon_256x256.png",    256),
            ("icon_256x256@2x.png", 512),
            ("icon_512x512.png",    512),
            ("icon_512x512@2x.png", 1024),
        ]

        master_img = Image.open(master_png)
        for filename, size in sizes:
            resized_img = master_img.resize((size, size), Image.Resampling.LANCZOS)
            resized_img.save(iconset_dir / filename, format="PNG")

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_icns)],
            check=True,
        )
        print(f"✓ Created native macOS icon.icns: {output_icns}")


def generate_icons():
    print("=" * 70)
    print("AETHER DESKTOP APP ICON GENERATION PIPELINE")
    print("=" * 70)
    print(f"Master source: {MASTER_PNG}")
    print(f"Target dir:    {ICONS_DIR}")

    if not MASTER_PNG.exists():
        print(
            f"ERROR: Master PNG not found at {MASTER_PNG}\n"
            "Run the artwork generation step first (see src-tauri/icons/source/).",
            file=sys.stderr,
        )
        sys.exit(1)

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Run Tauri icon generator for ICO and PNG variants
    print("\nRunning Tauri icon generator (ICO + PNG variants)...")
    env = os.environ.copy()
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.exists():
        env["PATH"] = f"{cargo_bin}{os.pathsep}{env.get('PATH', '')}"

    npm_bin = shutil.which("npm") or "npm"
    subprocess.run(
        [npm_bin, "--prefix", "ui", "exec", "--", "tauri", "icon", str(MASTER_PNG), "-o", str(ICONS_DIR)],
        cwd=str(REPO_ROOT),
        check=True,
        env=env,
        shell=sys.platform == "win32",
    )

    # 2. Overwrite icon.icns with native iconutil build on macOS (Tauri's icns has extra padding)
    if sys.platform == "darwin" and shutil.which("iconutil"):
        build_macos_icns(MASTER_PNG, ICONS_DIR / "icon.icns")

    # 3. Verify
    icns_file = ICONS_DIR / "icon.icns"
    png_file  = ICONS_DIR / "icon.png"
    ico_file  = ICONS_DIR / "icon.ico"
    assert png_file.exists(), f"Missing {png_file}"
    if ico_file.exists():
        ico_kb = os.path.getsize(ico_file) / 1024.0
        print(f"✓ icon.ico   {ico_kb:.1f} KB")
    if icns_file.exists():
        icns_kb = os.path.getsize(icns_file) / 1024.0
        print(f"✓ icon.icns  {icns_kb:.1f} KB")
    png_kb  = os.path.getsize(png_file)  / 1024.0
    print(f"✓ icon.png   {png_kb:.1f} KB")
    print("=" * 70)


if __name__ == "__main__":
    generate_icons()
