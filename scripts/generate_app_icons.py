#!/usr/bin/env python3
"""
App Icon Generation Pipeline for Aether Desktop (DSK-04A).
Source of truth: website/public/brand/aether_emblem_3d.png
Output: src-tauri/icons/ (icon.icns, icon.ico, icon.png, 32x32.png, 128x128.png, etc.)
Takes the original 3D emblem image at MAXIMUM size directly onto the 1024x1024 white squircle canvas
without any cropping or artificial downscaling, utilizing the image's built-in natural margins.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_EMBLEM = REPO_ROOT / "website" / "public" / "brand" / "aether_emblem_3d.png"
ICONS_DIR = REPO_ROOT / "src-tauri" / "icons"


def build_macos_max_squircle_master(emblem_path: Path, output_master_path: Path):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("ERROR: Pillow is required. Run 'pip install pillow'.", file=sys.stderr)
        sys.exit(1)

    canvas_size = 1024
    radius = 224

    # 1. Anti-aliased squircle mask (4x supersampling)
    ss = 4
    ss_size = canvas_size * ss
    ss_rad = radius * ss
    mask_hi = Image.new("L", (ss_size, ss_size), 0)
    draw_mask = ImageDraw.Draw(mask_hi)
    draw_mask.rounded_rectangle([0, 0, ss_size - 1, ss_size - 1], radius=ss_rad, fill=255)
    tile_mask = mask_hi.resize((canvas_size, canvas_size), Image.Resampling.LANCZOS)

    # 2. Pure clean white background
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))

    # 3. Load original emblem image and scale to MAXIMUM canvas dimensions (no cropping)
    emblem_orig = Image.open(emblem_path).convert("RGBA")
    w, h = emblem_orig.size
    scale = canvas_size / float(max(w, h))
    nw = int(round(w * scale))
    nh = int(round(h * scale))
    emblem_max = emblem_orig.resize((nw, nh), Image.Resampling.LANCZOS)

    ox = (canvas_size - nw) // 2
    oy = (canvas_size - nh) // 2
    canvas.paste(emblem_max, (ox, oy), emblem_max)

    # 4. Apply squircle mask
    final_icon = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    final_icon.paste(canvas, (0, 0), tile_mask)
    final_icon.save(output_master_path, format="PNG")
    print(f"✓ Created maximum-size squircle master icon: {output_master_path}")


def build_macos_icns(master_png: Path, output_icns: Path):
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow is required. Run 'pip install pillow'.", file=sys.stderr)
        sys.exit(1)

    print("Building native macOS .icns via iconutil to bypass padding...")

    with tempfile.TemporaryDirectory() as temp_dir:
        iconset_dir = Path(temp_dir) / "icon.iconset"
        iconset_dir.mkdir(parents=True, exist_ok=True)

        sizes = [
            ("icon_16x16.png", 16),
            ("icon_16x16@2x.png", 32),
            ("icon_32x32.png", 32),
            ("icon_32x32@2x.png", 64),
            ("icon_128x128.png", 128),
            ("icon_128x128@2x.png", 256),
            ("icon_256x256.png", 256),
            ("icon_256x256@2x.png", 512),
            ("icon_512x512.png", 512),
            ("icon_512x512@2x.png", 1024),
        ]

        master_img = Image.open(master_png)
        for filename, size in sizes:
            resized_img = master_img.resize((size, size), Image.Resampling.LANCZOS)
            resized_img.save(iconset_dir / filename, format="PNG")

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_icns)],
            check=True
        )
        print(f"✓ Created native unpadded macOS icon: {output_icns}")


def generate_icons():
    print("=" * 70)
    print("AETHER DESKTOP APP ICON GENERATION PIPELINE")
    print("=" * 70)
    print(f"Source Emblem: {SOURCE_EMBLEM}")
    print(f"Target Dir:    {ICONS_DIR}")

    if not SOURCE_EMBLEM.exists():
        print(f"ERROR: Source emblem {SOURCE_EMBLEM} does not exist!", file=sys.stderr)
        sys.exit(1)

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        master_png = tmp_path / "icon_master_1024.png"

        # 1. Build maximum-size Apple squircle master
        build_macos_max_squircle_master(SOURCE_EMBLEM, master_png)

        # Update website public brand assets
        website_brand_icon = REPO_ROOT / "website" / "public" / "brand" / "aether_macos_app_icon_1024.png"
        shutil.copy(master_png, website_brand_icon)

        # 2. Run Tauri icon generator (for Windows/Linux ICO and PNG variants)
        print("Running Tauri icon generator to produce ICO, and PNG variants...")
        env = os.environ.copy()
        cargo_bin = Path.home() / ".cargo" / "bin"
        if cargo_bin.exists():
            env["PATH"] = f"{cargo_bin}:{env.get('PATH', '')}"

        subprocess.run(
            ["npm", "--prefix", "ui", "exec", "--", "tauri", "icon", str(master_png), "-o", str(ICONS_DIR)],
            cwd=str(REPO_ROOT),
            check=True,
            env=env,
        )

        # 3. Overwrite the Tauri-generated icon.icns with our native unpadded one
        build_macos_icns(master_png, ICONS_DIR / "icon.icns")

    # 4. Verify generated artifacts
    icns_file = ICONS_DIR / "icon.icns"
    png_file = ICONS_DIR / "icon.png"
    assert icns_file.exists(), f"Missing {icns_file}"
    assert png_file.exists(), f"Missing {png_file}"

    icns_size_kb = os.path.getsize(icns_file) / 1024.0
    print(f"✓ icon.icns successfully generated ({icns_size_kb:.1f} KB)")
    print(f"✓ icon.png successfully generated ({os.path.getsize(png_file) / 1024.0:.1f} KB)")
    print("=" * 70)


if __name__ == "__main__":
    generate_icons()
