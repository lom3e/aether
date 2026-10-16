"""Validation of an image received from the UI before it is ever shown to a model. Pure Python, no imaging library."""
from __future__ import annotations

import base64
import binascii
import struct
from dataclasses import dataclass

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # decoded
MAX_IMAGE_DIMENSION = 4096  # px, either side
MIN_IMAGE_DIMENSION = 8


class ImageError(ValueError):
    """The image cannot be sent. ``code`` is stable (the UI localizes it); the message is for logs."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedImage:
    media_type: str
    data_b64: str
    width: int
    height: int
    size_bytes: int


def _png_size(raw: bytes) -> tuple[int, int] | None:
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR" or len(raw) < 24:
        return None
    return struct.unpack(">II", raw[16:24])


def _jpeg_size(raw: bytes) -> tuple[int, int] | None:
    if raw[:2] != b"\xff\xd8":
        return None
    i, n = 2, len(raw)
    while i + 9 < n:
        if raw[i] != 0xFF:
            i += 1
            continue
        marker = raw[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xFF:
            i += 1
            continue
        seglen = struct.unpack(">H", raw[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", raw[i + 5:i + 9])
            return w, h
        i += 2 + seglen
    return None


def _webp_size(raw: bytes) -> tuple[int, int] | None:
    if raw[:4] != b"RIFF" or raw[8:12] != b"WEBP" or len(raw) < 30:
        return None
    kind = raw[12:16]
    if kind == b"VP8X":
        return 1 + int.from_bytes(raw[24:27], "little"), 1 + int.from_bytes(raw[27:30], "little")
    if kind == b"VP8 ":
        w, h = struct.unpack("<HH", raw[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if kind == b"VP8L":
        b = raw[21:25]
        bits = int.from_bytes(b, "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


_SNIFFERS = (("image/png", _png_size), ("image/jpeg", _jpeg_size), ("image/webp", _webp_size))


def validate_image(content_base64: str, declared_media_type: str | None = None) -> ValidatedImage:
    """
    Decodes and checks an image. The real format comes from the bytes, never from the declared type; a mismatch or an
    unknown format is rejected. Raises ImageError(code) with code in: empty, bad_base64, too_large, unsupported_format,
    corrupt, too_small, dimensions_too_large.
    """
    payload = (content_base64 or "").strip()
    if payload.startswith("data:"):
        payload = payload.split(",", 1)[-1]
    if not payload:
        raise ImageError("empty", "No image data was provided.")
    # Cheap upper bound before decoding a huge string.
    if len(payload) > MAX_IMAGE_BYTES * 4 // 3 + 16:
        raise ImageError("too_large", f"Image exceeds {MAX_IMAGE_BYTES} bytes.")
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ImageError("bad_base64", "Image data is not valid base64.") from None
    if not raw:
        raise ImageError("empty", "No image data was provided.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageError("too_large", f"Image exceeds {MAX_IMAGE_BYTES} bytes.")
    media_type, size = None, None
    for mt, sniff in _SNIFFERS:
        try:
            got = sniff(raw)
        except (struct.error, IndexError):
            got = None
        if got:
            media_type, size = mt, got
            break
    if media_type is None or size is None:
        sniffed_any = raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:2] == b"\xff\xd8" or raw[:4] == b"RIFF"
        raise ImageError("corrupt" if sniffed_any else "unsupported_format", "The image is not a readable PNG, JPEG or WebP.")
    if declared_media_type and declared_media_type != media_type:
        raise ImageError("unsupported_format", f"Declared type {declared_media_type} does not match the image ({media_type}).")
    width, height = int(size[0]), int(size[1])
    if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
        raise ImageError("too_small", "The image is too small to be useful.")
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ImageError("dimensions_too_large", f"Image side exceeds {MAX_IMAGE_DIMENSION}px.")
    return ValidatedImage(media_type=media_type, data_b64=base64.b64encode(raw).decode("ascii"), width=width, height=height, size_bytes=len(raw))
