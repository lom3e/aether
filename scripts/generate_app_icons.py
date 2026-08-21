#!/usr/bin/env python3
"""
App Icon Generation Pipeline for Aether Desktop (DSK-04A).
Source of truth: website/public/brand/aether_emblem_3d.png
Output: src-tauri/icons/ (icon.icns, icon.ico, icon.png, 32x32.png, 128x128.png, etc.)
Applies Apple Human Interface Guidelines (HIG) macOS Squircle master composition:
- 1024x1024 master canvas
- 824x824 squircle tile with Apple superellipse continuous corner radius (r=185)
- Ambient + directional soft drop shadows
- Clean white to ultra-light silver subtle gradient background
- 3D purple ribbon emblem optically centered with balanced margins
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


def build_macos_squircle_master(emblem_path: Path, output_master_path: Path):
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        print("ERROR: Pillow is required. Run 'pip install pillow'.", file=sys.stderr)
        sys.exit(1)

    canvas_size = 1024
    tile_size = 824
    radius = 185

    # 1. Base transparent canvas
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))

    # 2. Generate smooth anti-aliased squircle mask (4x supersampling)
    ss = 4
    ss_tile = tile_size * ss
    ss_rad = radius * ss
    mask_hi = Image.new("L", (ss_tile, ss_tile), 0)
    draw_mask = ImageDraw.Draw(mask_hi)
    draw_mask.rounded_rectangle([0, 0, ss_tile - 1, ss_tile - 1], radius=ss_rad, fill=255)
    tile_mask = mask_hi.resize((tile_size, tile_size), Image.Resampling.LANCZOS)

    # 3. macOS HIG Ambient & Directional drop shadows
    # Ambient soft shadow
    shadow_mask_ambient = Image.new("L", (canvas_size, canvas_size), 0)
    shadow_mask_ambient.paste(tile_mask, (100, 100 + 16))
    shadow_mask_ambient = shadow_mask_ambient.filter(ImageFilter.GaussianBlur(radius=22))
    ambient_layer = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, int(255 * 0.16)))
    canvas.paste(ambient_layer, (0, 0), shadow_mask_ambient)

    # Direct directional shadow
    shadow_mask_direct = Image.new("L", (canvas_size, canvas_size), 0)
    shadow_mask_direct.paste(tile_mask, (100, 100 + 6))
    shadow_mask_direct = shadow_mask_direct.filter(ImageFilter.GaussianBlur(radius=8))
    direct_layer = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, int(255 * 0.10)))
    canvas.paste(direct_layer, (0, 0), shadow_mask_direct)

    # 4. Create Tile Background with subtle Apple-style gradient
    tile_bg = Image.new("RGBA", (tile_size, tile_size), (255, 255, 255, 255))
    for y in range(tile_size):
        factor = y / float(tile_size)
        v = int(255 - factor * 8)
        for x in range(tile_size):
            tile_bg.putpixel((x, y), (v, v, v, 255))

    # Subtle inner border
    draw_tile = ImageDraw.Draw(tile_bg)
    draw_tile.rounded_rectangle([0, 0, tile_size - 1, tile_size - 1], radius=radius, outline=(0, 0, 0, 16), width=1)

    # 5. Composite 3D emblem
    emblem = Image.open(emblem_path).convert("RGBA")
    bbox = emblem.getbbox()
    if bbox:
        emblem = emblem.crop(bbox)

    ew, eh = emblem.size
    target_ew = 580
    target_eh = int(round(eh * (target_ew / float(ew))))
    emblem_resized = emblem.resize((target_ew, target_eh), Image.Resampling.LANCZOS)

    ex = (tile_size - target_ew) // 2
    ey = (tile_size - target_eh) // 2 - 4  # Optical lift for triangle center of gravity

    tile_with_emblem = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    tile_with_emblem.paste(tile_bg, (0, 0))
    tile_with_emblem.paste(emblem_resized, (ex, ey), emblem_resized)

    # Apply squircle mask to the tile
    canvas.paste(tile_with_emblem, (100, 100), tile_mask)

    canvas.save(output_master_path, format="PNG")
    print(f"✓ Created master Apple squircle icon: {output_master_path}")


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

        # 1. Build master Apple squircle 1024x1024 icon
        build_macos_squircle_master(SOURCE_EMBLEM, master_png)

        # Also save a copy in website brand assets
        website_brand_icon = REPO_ROOT / "website" / "public" / "brand" / "aether_macos_app_icon_1024.png"
        shutil.copy(master_png, website_brand_icon)

        # 2. Run Tauri icon generator from master squircle PNG
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
