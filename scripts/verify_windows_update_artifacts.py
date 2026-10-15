#!/usr/bin/env python3
"""Checks that the Windows build is compatible with the signed-update flow, with a THROWAWAY key (never the production key).

    python scripts/verify_windows_update_artifacts.py --installer build/Aether-x64-setup.exe

  1. tauri.conf.json: NSIS target present, updater plugin has a public key, requireSignedVersion on, no production endpoint
     configured here, the official build does not require the private key.
  2. Signs the installer with a temporary key (`tauri signer sign --app-version`) and checks the signature binds the version.
  3. Builds a `windows-x86_64` manifest entry with build_update_artifacts.py and validates it.
It does NOT install an update on Windows; that end-to-end step is not covered here.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--installer", required=True)
    a = ap.parse_args()
    installer = Path(a.installer)
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text())
    upd = (conf.get("plugins") or {}).get("updater") or {}
    check("config: NSIS bundle target", "nsis" in (conf.get("bundle") or {}).get("targets", []))
    check("config: updater public key present and decodes as minisign", base64.b64decode(upd.get("pubkey", "")).startswith(b"untrusted comment:"))
    check("config: requireSignedVersion enabled", upd.get("requireSignedVersion") is True)
    check("config: official build does not require the private key", not (conf.get("bundle") or {}).get("createUpdaterArtifacts"))
    check("config: no production endpoint configured by this test", all(not str(e).startswith("http://") for e in upd.get("endpoints", [])))
    if not installer.is_file():
        check("installer exists", False, str(installer))
        return 1
    cli = ROOT / "ui" / "node_modules" / ".bin" / ("tauri.cmd" if sys.platform == "win32" else "tauri")
    with tempfile.TemporaryDirectory(prefix="aether_win_upd_") as tmp:
        tmp_path = Path(tmp)
        key, pw = tmp_path / "throwaway.key", "throwaway-" + os.urandom(6).hex()
        g = subprocess.run([str(cli), "signer", "generate", "--ci", "-p", pw, "-w", str(key)], capture_output=True, text=True)
        check("throwaway signing key generated", g.returncode == 0 and key.exists())
        out = tmp_path / "updates"
        env = dict(os.environ, TAURI_SIGNING_PRIVATE_KEY_PASSWORD=pw)
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_update_artifacts.py"), "--installer", str(installer), "--out-dir", str(out),
                            "--base-url", "http://127.0.0.1:9", "--local-test-url", "--key-file", str(key)], env=env, capture_output=True, text=True)
        check("installer signed and manifest written", r.returncode == 0, (r.stderr or r.stdout)[-150:] if r.returncode else "")
        manifest_path = out / "latest.json"
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text())
            entry = m["platforms"].get("windows-x86_64", {})
            check("manifest has a windows-x86_64 entry with url and signature", bool(entry.get("url")) and bool(entry.get("signature")))
            sig_text = base64.b64decode(entry["signature"]).decode(errors="replace") if entry.get("signature") else ""
            check("signature binds the app version (trusted comment)", f"version:{m['version']}" in sig_text, m["version"])
            check("update package is the NSIS installer itself", entry.get("url", "").endswith("-setup.exe"))
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
