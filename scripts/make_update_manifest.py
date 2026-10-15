#!/usr/bin/env python3
"""Build the static Tauri updater manifest (`latest.json`) for one release channel.

The signature must come from `tauri signer sign` / the Tauri bundler (`*.app.tar.gz.sig`); this script never
signs anything and refuses empty signatures and non-HTTPS URLs.

Usage: python scripts/make_update_manifest.py --version 1.6.1 --platform darwin-aarch64 \
    --artifact-url https://example.com/Aether_1.6.1_aarch64.app.tar.gz \
    --signature-file Aether.app.tar.gz.sig [--notes "..."] [--channel stable] --output latest.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
PLATFORMS = {"darwin-aarch64", "darwin-x86_64", "windows-x86_64"}


def _is_local_http(url: str) -> bool:
    return re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?/", url) is not None


def build_manifest(version: str, platform: str, artifact_url: str, signature: str, notes: str = "",
                   pub_date: str | None = None, existing: dict | None = None, allow_local_http: bool = False) -> dict:
    if not SEMVER.match(version):
        raise ValueError(f"invalid version: {version!r}")
    if platform not in PLATFORMS:
        raise ValueError(f"unsupported platform: {platform!r}")
    if not artifact_url.startswith("https://") and not (allow_local_http and _is_local_http(artifact_url)):
        raise ValueError("artifact URL must use https (plain http is only accepted for 127.0.0.1/localhost in local tests)")
    signature = signature.strip()
    if not signature:
        raise ValueError("empty signature: updates must be signed")
    manifest = dict(existing or {})
    if manifest and manifest.get("version") != version:
        manifest = {}  # a new version starts a fresh manifest; platforms are added one by one
    manifest.update({
        "version": version,
        "notes": notes or manifest.get("notes", ""),
        "pub_date": pub_date or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    manifest.setdefault("platforms", {})[platform] = {"signature": signature, "url": artifact_url}
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--platform", required=True)
    ap.add_argument("--artifact-url", required=True)
    ap.add_argument("--signature-file", required=True)
    ap.add_argument("--notes", default="")
    ap.add_argument("--channel", default="stable", choices=["stable"])
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    out = Path(a.output)
    existing = json.loads(out.read_text()) if out.exists() else None
    try:
        m = build_manifest(a.version, a.platform, a.artifact_url, Path(a.signature_file).read_text(), a.notes, existing=existing)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out.write_text(json.dumps(m, indent=2) + "\n")
    print(f"wrote {out} (channel={a.channel}, version={m['version']}, platforms={sorted(m['platforms'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
