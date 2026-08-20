#!/usr/bin/env python3
"""
App Icon Generation Script for Aether Desktop (DSK-04A).
Source of truth: website/public/brand/favicon.svg
Output: src-tauri/icons/ (icon.icns, icon.ico, icon.png, 32x32.png, 128x128.png, etc.)
Applies optical centering and standard macOS padding (~80% footprint on 1024x1024 canvas)
so that the icon sits beautifully and perfectly centered inside the macOS Dock and squircle tiles.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SVG = REPO_ROOT / "website" / "public" / "brand" / "favicon.svg"
ICONS_DIR = REPO_ROOT / "src-tauri" / "icons"


def decode_png(png_bytes):
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    ihdr = None
    idat = bytearray()
    while pos < len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos:pos+4])[0]
        ctype = png_bytes[pos+4:pos+8]
        if ctype == b"IHDR":
            w, h = struct.unpack(">II", png_bytes[pos+8:pos+8+8])
            ihdr = (w, h)
        elif ctype == b"IDAT":
            idat.extend(png_bytes[pos+8:pos+8+length])
        pos += 8 + length + 4

    w, h = ihdr
    raw = zlib.decompress(idat)
    bpp = 4
    stride = w * bpp
    prev_row = bytearray(stride)
    current_row = bytearray(stride)
    pixels = bytearray(w * h * 4)

    pos = 0
    for y in range(h):
        filter_type = raw[pos]
        pos += 1
        row_bytes = raw[pos:pos+stride]
        pos += stride
        if filter_type == 0:
            current_row[:] = row_bytes
        elif filter_type == 1:
            for i in range(stride):
                left = current_row[i - bpp] if i >= bpp else 0
                current_row[i] = (row_bytes[i] + left) & 0xff
        elif filter_type == 2:
            for i in range(stride):
                up = prev_row[i]
                current_row[i] = (row_bytes[i] + up) & 0xff
        elif filter_type == 3:
            for i in range(stride):
                left = current_row[i - bpp] if i >= bpp else 0
                up = prev_row[i]
                current_row[i] = (row_bytes[i] + ((left + up) >> 1)) & 0xff
        elif filter_type == 4:
            for i in range(stride):
                left = current_row[i - bpp] if i >= bpp else 0
                up = prev_row[i]
                upper_left = prev_row[i - bpp] if i >= bpp else 0
                p = left + up - upper_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - upper_left)
                pr = left if pa <= pb and pa <= pc else (up if pb <= pc else upper_left)
                current_row[i] = (row_bytes[i] + pr) & 0xff
        pixels[y * stride : (y + 1) * stride] = current_row
        prev_row[:] = current_row
    return w, h, pixels


def encode_png(w, h, rgba_bytes):
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw.extend(rgba_bytes[y * stride : (y + 1) * stride])
    compressed = zlib.compress(bytes(raw), 9)

    out = bytearray(b"\x89PNG\r\n\x1a\n")
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    out.extend(struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc))
    idat_crc = zlib.crc32(b"IDAT" + compressed)
    out.extend(struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc))
    iend_crc = zlib.crc32(b"IEND")
    out.extend(struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc))
    return bytes(out)


def center_and_scale_icon(input_png_path, output_png_path, target_canvas=1024, target_glyph_w=800, optical_y_lift=10):
    with open(input_png_path, "rb") as f:
        w, h, raw_rgba = decode_png(f.read())

    scale = target_glyph_w / float(w)
    target_glyph_h = int(round(h * scale))

    offset_x = (target_canvas - target_glyph_w) // 2
    offset_y = (target_canvas - target_glyph_h) // 2 - optical_y_lift

    new_canvas = bytearray(target_canvas * target_canvas * 4)

    for dy in range(target_glyph_h):
        sy = dy / scale
        sy0 = int(sy)
        sy1 = min(sy0 + 1, h - 1)
        fy = sy - sy0

        dest_y = offset_y + dy
        if dest_y < 0 or dest_y >= target_canvas:
            continue

        for dx in range(target_glyph_w):
            sx = dx / scale
            sx0 = int(sx)
            sx1 = min(sx0 + 1, w - 1)
            fx = sx - sx0

            dest_x = offset_x + dx
            if dest_x < 0 or dest_x >= target_canvas:
                continue

            idx00 = (sy0 * w + sx0) * 4
            idx01 = (sy0 * w + sx1) * 4
            idx10 = (sy1 * w + sx0) * 4
            idx11 = (sy1 * w + sx1) * 4

            dest_idx = (dest_y * target_canvas + dest_x) * 4

            for c in range(4):
                val0 = raw_rgba[idx00 + c] * (1.0 - fx) + raw_rgba[idx01 + c] * fx
                val1 = raw_rgba[idx10 + c] * (1.0 - fx) + raw_rgba[idx11 + c] * fx
                final_val = int(round(val0 * (1.0 - fy) + val1 * fy))
                new_canvas[dest_idx + c] = max(0, min(255, final_val))

    out_png = encode_png(target_canvas, target_canvas, new_canvas)
    with open(output_png_path, "wb") as f:
        f.write(out_png)


def generate_icons():
    print("=" * 70)
    print("AETHER DESKTOP APP ICON GENERATION PIPELINE")
    print("=" * 70)
    print(f"Source SVG: {SOURCE_SVG}")
    print(f"Target Dir: {ICONS_DIR}")

    if not SOURCE_SVG.exists():
        print(f"ERROR: Source icon {SOURCE_SVG} does not exist!", file=sys.stderr)
        sys.exit(1)

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        raw_png = tmp_path / "raw_1024.png"
        master_centered_png = tmp_path / "icon_master_1024.png"

        # 1. Rasterize SVG to high-res master PNG via macOS qlmanage
        print("Rasterizing SVG source vector paths...")
        subprocess.run(
            ["qlmanage", "-t", "-s", "1024", "-o", str(tmp_path), str(SOURCE_SVG)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        generated_thumb = tmp_path / "favicon.svg.png"
        if not generated_thumb.exists():
            print(f"ERROR: Failed to generate thumbnail at {generated_thumb}", file=sys.stderr)
            sys.exit(1)

        shutil.move(generated_thumb, raw_png)

        # 2. Scale & optically center glyph with standard macOS padding
        print("Scaling and optically centering emblem on 1024x1024 canvas...")
        center_and_scale_icon(raw_png, master_centered_png, target_canvas=1024, target_glyph_w=800, optical_y_lift=10)

        # 3. Run Tauri icon generator from master centered PNG
        print("Running Tauri icon generator...")
        env = os.environ.copy()
        cargo_bin = Path.home() / ".cargo" / "bin"
        if cargo_bin.exists():
            env["PATH"] = f"{cargo_bin}:{env.get('PATH', '')}"

        subprocess.run(
            ["npm", "--prefix", "ui", "exec", "--", "tauri", "icon", str(master_centered_png), "-o", str(ICONS_DIR)],
            cwd=str(REPO_ROOT),
            check=True,
            env=env,
        )

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
