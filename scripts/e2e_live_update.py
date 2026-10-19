#!/usr/bin/env python3
"""Live update check: an older build (production public key, the REAL endpoint) updates itself from the latest GitHub release.

    python scripts/e2e_live_update.py [--old-version 1.7.0] [--expect 1.7.1] [--keep]

Builds a test binary of --old-version (feature `updater-e2e`, which applies an update on start when AETHER_E2E_UPDATE=1),
puts it into a copy of build/Aether.app, runs it with an isolated HOME and expects it to download, verify (production
minisign key + signed version) and install --expect from the published release, relaunch and find nothing newer.
Nothing is published and no private key is used. It downloads the real release archive (~50 MB).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_update_flow as e2e  # noqa: E402

ROOT = e2e.ROOT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-version", default="1.7.0")
    ap.add_argument("--expect", default="1.7.1")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text())
    upd = conf["plugins"]["updater"]
    if not upd.get("endpoints"):
        print("No updater endpoint configured in tauri.conf.json")
        return 2
    work = Path(tempfile.mkdtemp(prefix="aether_live_update_")).resolve()
    print(f"work dir: {work}\nendpoint: {upd['endpoints'][0]}", flush=True)
    import os
    import subprocess
    cfg = {"version": a.old_version, "plugins": {"updater": {"pubkey": upd["pubkey"], "endpoints": upd["endpoints"], "requireSignedVersion": True}}}
    env = dict(os.environ, TAURI_CONFIG=json.dumps(cfg), CARGO_TARGET_DIR=str(work / "target"))
    env["PATH"] = f"{Path.home()/'.cargo'/'bin'}:{env['PATH']}"
    subprocess.run(["cargo", "build", "--release", "--offline", "--features", "tauri/custom-protocol,updater-e2e"], cwd=ROOT / "src-tauri", env=env, check=True)
    binary = work / "old_binary"
    shutil.copy2(work / "target" / "release" / "aether-desktop", binary)
    app = e2e.assemble_app(binary, a.old_version, work / "run" / "Aether.app")
    old_sha = e2e.sha(app / "Contents" / "MacOS" / "aether-desktop")
    log = work / "live.log"
    try:
        e2e.launch(app, work / "home", log)
        e2e.check("old app started and its sidecar passed the readiness probe", e2e.wait_for(log, r"passed readiness", 60))
        e2e.check(f"update to {a.expect} installed from the published release", e2e.wait_for(log, r"Installed version " + re.escape(a.expect), 240))
        e2e.check("app relaunched with a second healthy sidecar", e2e.wait_for(log, r"passed readiness", 90, 2) and e2e.last_health(log))
        time.sleep(3)
        e2e.check("installed binary differs from the old one", e2e.sha(app / "Contents" / "MacOS" / "aether-desktop") != old_sha)
        # The installed app is the published release build (no e2e hook), so its own health endpoint tells the version.
        ports = re.findall(r"ready at: http://127\.0\.0\.1:(\d+)", log.read_text(errors="replace"))
        version = ""
        try:
            version = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{ports[-1]}/api/health", timeout=5).read()).get("version", "")
        except Exception:  # noqa: BLE001
            pass
        e2e.check(f"relaunched runtime reports version {a.expect}", version == a.expect, version)
        plist = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print :CFBundleShortVersionString", str(app / "Contents" / "Info.plist")],
                               capture_output=True, text=True).stdout.strip()
        e2e.check("bundle version is the published one", plist == a.expect, plist)
        e2e.stop_all(work / "run")
        e2e.check("no process left after shutdown", e2e.pids_under(work / "run") == [])
    finally:
        e2e.stop_all(work / "run")
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)
    failed = [n for n, ok, _ in e2e.results if not ok]
    print(f"\n{len(e2e.results) - len(failed)}/{len(e2e.results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
