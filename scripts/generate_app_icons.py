#!/usr/bin/env python3
"""
App Icon Generation Pipeline for Aether Desktop (DSK-04A).
Source of truth: website/public/brand/aether_emblem_3d.png
Output: src-tauri/icons/ (icon.icns, icon.ico, icon.png, 32x32.png, 128x128.png, etc.)
Applies Full-Bleed macOS Squircle Specification (1024x1024 canvas with Apple r=224 curvature):
- Fills the 1024x1024 canvas with standard Apple squircle radius (r=224)
- Prevents macOS Finder/Launchpad from nesting the icon inside a secondary grey container
- Provides optimal ~780px footprint for the 3D purple ribbon emblem, perfectly matching
  the visual weight of Google Chrome, Antigravity, Gemini, Spotify, and ChatGPT.
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


def build_macos_full_squircle_master(emblem_path: Path, output_master_path: Path):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("ERROR: Pillow is required. Run 'pip install pillow'.", file=sys.stderr)
        sys.exit(1)

    canvas_size = 1024
    radius = 224  # Standard Apple 1024x1024 squircle radius

    # 1. Supersampled (4x) anti-aliased squircle mask
    ss = 4
    ss_size = canvas_size * ss
    ss_rad = radius * ss
    mask_hi = Image.new("L", (ss_size, ss_size), 0)
    draw_mask = ImageDraw.Draw(mask_hi)
    draw_mask.rounded_rectangle([0, 0, ss_size - 1, ss_size - 1], radius=ss_rad, fill=255)
    tile_mask = mask_hi.resize((canvas_size, canvas_size), Image.Resampling.LANCZOS)

    # 2. Crisp white to subtle platinum vertical gradient
    tile_bg = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))
    for y in range(canvas_size):
        factor = y / float(canvas_size)
        v = int(255 - factor * 8)
        for x in range(canvas_size):
            tile_bg.putpixel((x, y), (v, v, v, 255))

    # 3. Load & crop 3D emblem
    emblem = Image.open(emblem_path).convert("RGBA")
    bbox = emblem.getbbox()
    if bbox:
        emblem = emblem.crop(bbox)

    ew, eh = emblem.size
    target_ew = 780  # Full native visual weight
    target_eh = int(round(eh * (target_ew / float(ew))))
    emblem_resized = emblem.resize((target_ew, target_eh), Image.Resampling.LANCZOS)

    ex = (canvas_size - target_ew) // 2
    ey = (canvas_size - target_eh) // 2 - 8  # Optical lift for triangle center of gravity

    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    canvas.paste(tile_bg, (0, 0))
    canvas.paste(emblem_resized, (ex, ey), emblem_resized)

    # Apply squircle mask
    final_icon = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    final_icon.paste(canvas, (0, 0), tile_mask)
    final_icon.save(output_master_path, format="PNG")
    print(f"✓ Created full-bleed squircle master icon: {output_master_path}")


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

        # 1. Build full-bleed Apple squircle master
        build_macos_full_squircle_master(SOURCE_EMBLEM, master_png)

        # Update website public brand assets
        website_brand_icon = REPO_ROOT / "website" / "public" / "brand" / "aether_macos_app_icon_1024.png"
        shutil.copy(master_png, website_brand_icon)

        # 2. Run Tauri icon generator
        print("Running Tauri icon generator to produce ICNS, ICO, and PNG variants...")
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

    # 3. Verify generated artifacts
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
