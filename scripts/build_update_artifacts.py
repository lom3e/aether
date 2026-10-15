#!/usr/bin/env python3
"""Create the signed update package and manifest for a built `Aether.app` (release step, needs the private key).

    python scripts/build_update_artifacts.py --base-url https://updates.example.com/stable/ [--notes "..."]

Produces in build/updates/:  Aether_<version>_<arch>.app.tar.gz, its .sig, and latest.json.

The private key is read from --key-file (default ~/.aether-signing/aether-updater.key) and its password from
TAURI_SIGNING_PRIVATE_KEY_PASSWORD or --password-file. Neither is printed, logged, copied into build/ or passed on a
command line. Nothing is uploaded: publishing is a separate, deliberate step. `--local-test-url` accepts a
http://127.0.0.1 base URL so the flow can be exercised against a local server.
"""
from __future__ import annotations

import argparse
import json
import os
import platform as _platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_update_manifest import build_manifest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KEY = Path.home() / ".aether-signing" / "aether-updater.key"


def detect_platform() -> str:
    machine = _platform.machine().lower()
    return "darwin-aarch64" if machine in {"arm64", "aarch64"} else "darwin-x86_64"


def app_version(app: Path) -> str:
    plist = app / "Contents" / "Info.plist"
    out = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print :CFBundleShortVersionString", str(plist)],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def make_archive(app: Path, dest: Path) -> None:
    env = dict(os.environ, COPYFILE_DISABLE="1")  # no AppleDouble files in the archive
    subprocess.run(["tar", "-czf", str(dest), "-C", str(app.parent), app.name], check=True, env=env)


def sign(archive: Path, key_file: Path, password: str | None, version: str) -> str:
    env = dict(os.environ)
    env.pop("TAURI_SIGNING_PRIVATE_KEY", None)
    env["TAURI_SIGNING_PRIVATE_KEY_PATH"] = str(key_file)
    if password is not None:
        env["TAURI_SIGNING_PRIVATE_KEY_PASSWORD"] = password
    cli = ROOT / "ui" / "node_modules" / ".bin" / "tauri"
    # Output is captured so nothing from the signer can end up in logs.
    # --app-version binds the signature to the release, so a manifest cannot pair a newer version number with an older package.
    r = subprocess.run([str(cli), "signer", "sign", "--app-version", version, str(archive)], env=env, capture_output=True, text=True)
    sig = Path(str(archive) + ".sig")
    if r.returncode != 0 or not sig.exists():
        raise SystemExit("signing failed (check the key file and password; details are intentionally not printed)")
    return sig.read_text().strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default=str(ROOT / "build" / "Aether.app"))
    ap.add_argument("--out-dir", default=str(ROOT / "build" / "updates"))
    ap.add_argument("--base-url", required=True, help="Directory URL where the archive will be hosted (https)")
    ap.add_argument("--local-test-url", action="store_true", help="allow an http://127.0.0.1 base URL (tests only)")
    ap.add_argument("--version", help="defaults to the bundle's CFBundleShortVersionString")
    ap.add_argument("--platform", default=detect_platform())
    ap.add_argument("--notes", default="")
    ap.add_argument("--key-file", default=str(DEFAULT_KEY))
    ap.add_argument("--password-file")
    a = ap.parse_args()

    app = Path(a.app)
    key = Path(a.key_file)
    if not app.exists():
        raise SystemExit(f"app bundle not found: {app}")
    if not key.exists():
        raise SystemExit(f"signing key not found: {key} (generate one with `tauri signer generate`; keep it outside the repository)")
    version = a.version or app_version(app)
    password = os.environ.get("TAURI_SIGNING_PRIVATE_KEY_PASSWORD")
    if password is None and a.password_file:
        password = Path(a.password_file).read_text()
    elif password is None and (key.parent / "aether-updater.password").exists():
        password = (key.parent / "aether-updater.password").read_text()

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    arch = "aarch64" if a.platform.endswith("aarch64") else "x86_64"
    archive = out / f"Aether_{version}_{arch}.app.tar.gz"
    make_archive(app, archive)
    signature = sign(archive, key, password, version)
    url = a.base_url.rstrip("/") + "/" + archive.name
    manifest_path = out / "latest.json"
    existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    manifest = build_manifest(version, a.platform, url, signature, a.notes, existing=existing, allow_local_http=a.local_test_url)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"archive:  {archive}\nmanifest: {manifest_path}\nversion={version} platform={a.platform} (nothing was uploaded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
