#!/usr/bin/env python3
"""Report, truthfully and read-only, what stands between the current build and a signed, notarized,
auto-updatable release. Secret values are never printed; only whether they are present.

Usage: python scripts/check_release_readiness.py [--app build/Aether.app] [--json] [--strict]
Exit code is 0 unless --strict is given and a check fails.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTARY_ENV_SETS = (
    ("APPLE_ID", "APPLE_PASSWORD", "APPLE_TEAM_ID"),
    ("APPLE_API_KEY", "APPLE_API_ISSUER", "APPLE_API_KEY_PATH"),
)
UPDATER_KEY_FILE = Path.home() / ".aether-signing" / "aether-updater.key"


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout + p.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def classify_signature(codesign_output: str) -> str:
    """'unsigned' | 'adhoc' | 'developer-id' | 'other' from `codesign -dv` output."""
    if "code object is not signed" in codesign_output:
        return "unsigned"
    if "Signature=adhoc" in codesign_output:
        return "adhoc"
    if "Authority=Developer ID Application" in codesign_output:
        return "developer-id"
    return "other"


def notary_env_ready(env: dict[str, str]) -> bool:
    return any(all(env.get(k) for k in group) for group in NOTARY_ENV_SETS)


def updater_configured(conf: dict, cargo_toml: str) -> dict[str, bool]:
    upd = (conf.get("plugins") or {}).get("updater") or {}
    return {
        "plugin_dependency": "tauri-plugin-updater" in cargo_toml,
        "public_key": bool(upd.get("pubkey")),
        "require_signed_version": bool(upd.get("requireSignedVersion")),
        "endpoints_configured": bool(upd.get("endpoints")),
    }


def collect(app: Path, env: dict[str, str] | None = None) -> dict:
    env = dict(os.environ) if env is None else env
    report: dict = {}
    code, out = _run(["security", "find-identity", "-v", "-p", "codesigning"])
    report["developer_id_identity_in_keychain"] = bool(re.search(r"Developer ID Application", out))
    report["notarization_credentials_in_env"] = notary_env_ready(env)
    report["updater_private_key_available"] = bool(env.get("TAURI_SIGNING_PRIVATE_KEY")) or bool(env.get("TAURI_SIGNING_PRIVATE_KEY_PATH")) or UPDATER_KEY_FILE.exists()
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text())
    report["updater"] = updater_configured(conf, (ROOT / "src-tauri" / "Cargo.toml").read_text())
    if app.exists():
        _, sig = _run(["codesign", "-dv", "--verbose=2", str(app)])
        report["bundle_signature"] = classify_signature(sig)
        rc, _ = _run(["codesign", "--verify", "--deep", "--strict", str(app)])
        report["bundle_signature_valid"] = rc == 0
        rc, _ = _run(["xcrun", "stapler", "validate", str(app)])
        report["bundle_notarization_ticket_stapled"] = rc == 0
        rc, _ = _run(["spctl", "--assess", "--type", "execute", str(app)])
        report["gatekeeper_accepts_bundle"] = rc == 0
    else:
        report["bundle_signature"] = "missing"
    report["ready_to_notarize"] = report["developer_id_identity_in_keychain"] and report["notarization_credentials_in_env"]
    report["ready_to_publish_updates"] = all(report["updater"].values()) and report["updater_private_key_available"]
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default=str(ROOT / "build" / "Aether.app"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    r = collect(Path(a.app))
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        for k, v in r.items():
            print(f"{k}: {v}")
    ok = r["ready_to_notarize"] and r["ready_to_publish_updates"] and r.get("bundle_notarization_ticket_stapled", False)
    return 1 if (a.strict and not ok) else 0


if __name__ == "__main__":
    sys.exit(main())
