#!/usr/bin/env python3
"""End-to-end test of the signed update flow, against a LOCAL server and a THROWAWAY key.

Nothing is published and the real signing key is never used. The script
  1. generates a temporary minisign keypair,
  2. builds two test binaries of the desktop supervisor (old/new version) whose embedded updater config points to
     http://127.0.0.1:<port> and trusts only the temporary public key (via TAURI_CONFIG at build time, feature
     `updater-e2e`, separate target dir; the official build is untouched),
  3. puts them into copies of build/Aether.app, signs the new one with build_update_artifacts.py, serves it locally,
  4. launches the old app (isolated HOME) and checks:
       positive  : old -> new installs, relaunches, new sidecar is healthy;
       negative  : tampered archive, wrong signing key, manifest version != signed version, unreachable endpoint
                   -> the update is refused/skipped and the running old app and its sidecar stay healthy.
Usage: python scripts/e2e_update_flow.py [--keep]    (needs build/Aether.app and ui/dist from the official build)
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
TAURI = ROOT / "ui" / "node_modules" / ".bin" / "tauri"
OLD_V, NEW_V = "1.6.0", "1.6.1"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def gen_key(d: Path, name: str) -> tuple[Path, str, str]:
    key = d / f"{name}.key"
    pw = "e2e-" + hashlib.sha256(name.encode()).hexdigest()[:12]
    subprocess.run([str(TAURI), "signer", "generate", "--ci", "-p", pw, "-w", str(key)], check=True, capture_output=True)
    return key, pw, (d / f"{name}.key.pub").read_text().strip()


def build_binary(version: str, target: Path, pubkey: str, port: int) -> Path:
    cfg = {"version": version, "plugins": {"updater": {
        "pubkey": pubkey, "endpoints": [f"http://127.0.0.1:{port}/latest.json"],
        "dangerousInsecureTransportProtocol": True, "requireSignedVersion": True}}}
    env = dict(os.environ, TAURI_CONFIG=json.dumps(cfg), CARGO_TARGET_DIR=str(target))
    env["PATH"] = f"{Path.home()/'.cargo'/'bin'}:{env['PATH']}"
    subprocess.run(["cargo", "build", "--release", "--offline", "--features", "tauri/custom-protocol,updater-e2e"],
                   cwd=ROOT / "src-tauri", env=env, check=True)
    return target / "release" / "aether-desktop"


def assemble_app(binary: Path, version: str, dest: Path) -> Path:
    shutil.copytree(ROOT / "build" / "Aether.app", dest, symlinks=True)
    shutil.copy2(binary, dest / "Contents" / "MacOS" / "aether-desktop")
    plist = dest / "Contents" / "Info.plist"
    for k in ("CFBundleShortVersionString", "CFBundleVersion"):
        subprocess.run(["/usr/libexec/PlistBuddy", "-c", f"Set :{k} {version}", str(plist)], check=True)
    subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(dest)], check=True, capture_output=True)
    return dest


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Server:
    def __init__(self, directory: Path, port: int):
        handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **k)  # noqa: E731
        http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()


def publish(out: Path, app: Path, key: Path, pw: str, port: int, version: str) -> None:
    shutil.rmtree(out, ignore_errors=True)
    env = dict(os.environ, TAURI_SIGNING_PRIVATE_KEY_PASSWORD=pw)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_update_artifacts.py"), "--app", str(app), "--out-dir", str(out),
                    "--base-url", f"http://127.0.0.1:{port}", "--local-test-url", "--key-file", str(key), "--version", version,
                    "--notes", "e2e"], check=True, env=env, capture_output=True)


def launch(app: Path, home: Path, log: Path) -> subprocess.Popen:
    home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, HOME=str(home), AETHER_E2E_UPDATE="1")
    return subprocess.Popen([str(app / "Contents" / "MacOS" / "aether-desktop")], env=env,
                            stdout=open(log, "ab"), stderr=subprocess.STDOUT, start_new_session=True)


def wait_for(log: Path, pattern: str, timeout: float, count: int = 1) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if len(re.findall(pattern, log.read_text(errors="replace"))) >= count:
            return True
        time.sleep(0.5)
    return False


def last_health(log: Path) -> bool:
    ports = re.findall(r"ready at: http://127\.0\.0\.1:(\d+)", log.read_text(errors="replace"))
    if not ports:
        return False
    try:
        return urllib.request.urlopen(f"http://127.0.0.1:{ports[-1]}/api/health", timeout=3).status == 200
    except Exception:
        return False


def pids_under(path: Path) -> list[int]:
    out = subprocess.run(["pgrep", "-f", str(path)], capture_output=True, text=True).stdout.split()
    return [int(x) for x in out if int(x) != os.getpid()]


def stop_all(path: Path) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in pids_under(path):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        time.sleep(2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if not (ROOT / "build" / "Aether.app").exists() or not (ROOT / "ui" / "dist").exists():
        print("Run the official build first (build/Aether.app and ui/dist are required).")
        return 2
    # resolve(): the updater refuses an executable path that contains a symlink (/var -> /private/var on macOS)
    work = Path(tempfile.mkdtemp(prefix="aether_update_e2e_")).resolve()
    port = free_port()
    print(f"work dir: {work}  port: {port}", flush=True)
    key_ok, pw_ok, pub_ok = gen_key(work, "good")
    key_bad, pw_bad, _ = gen_key(work, "attacker")
    target = work / "target"
    old_bin = build_binary(OLD_V, target, pub_ok, port)
    old_copy = work / "old_binary"
    shutil.copy2(old_bin, old_copy)
    new_bin = build_binary(NEW_V, target, pub_ok, port)
    new_copy = work / "new_binary"
    shutil.copy2(new_bin, new_copy)
    new_app = assemble_app(new_copy, NEW_V, work / "new" / "Aether.app")
    new_sha = sha(new_app / "Contents" / "MacOS" / "aether-desktop")
    served = work / "served"
    server = Server(served, port)
    served.mkdir(exist_ok=True)
    try:
        # ---------------- positive: old -> new ----------------
        publish(served, new_app, key_ok, pw_ok, port, NEW_V)
        app = assemble_app(old_copy, OLD_V, work / "run_pos" / "Aether.app")
        log = work / "pos.log"
        launch(app, work / "home_pos", log)
        # the update starts right after launch, so only readiness (not a later health probe) is stable to assert here
        check("positive: old app started and its sidecar passed the readiness probe", wait_for(log, r"passed readiness", 60))
        check("positive: update installed", wait_for(log, r"Installed version " + re.escape(NEW_V), 120), "")
        check("positive: app relaunched with a second healthy sidecar", wait_for(log, r"passed readiness", 90, 2) and last_health(log))
        time.sleep(3)
        installed = app / "Contents" / "MacOS" / "aether-desktop"
        check("positive: installed binary is the new version", sha(installed) == new_sha)
        check("positive: relaunched app finds no further update", wait_for(log, r"no update was applied", 60))
        stop_all(work / "run_pos")
        check("positive: no process left after shutdown", pids_under(work / "run_pos") == [])

        # ---------------- negatives ----------------
        def negative(name: str, expect: str, setup) -> None:
            run = work / f"run_{name}" / "Aether.app"
            assemble_app(old_copy, OLD_V, run)
            old_sha = sha(run / "Contents" / "MacOS" / "aether-desktop")
            setup()
            nlog = work / f"{name}.log"
            proc = launch(run, work / f"home_{name}", nlog)
            started = wait_for(nlog, r"passed readiness", 60)
            got = wait_for(nlog, r"E2E error: " + expect if expect != "none" else r"no update was applied", 90)
            alive = proc.poll() is None
            healthy = last_health(nlog)
            unchanged = sha(run / "Contents" / "MacOS" / "aether-desktop") == old_sha
            check(f"{name}: refused as '{expect}', old app still running and healthy, binary untouched",
                  started and got and alive and healthy and unchanged, f"started={started} got={got} alive={alive} healthy={healthy} unchanged={unchanged}")
            stop_all(work / f"run_{name}")
            check(f"{name}: no process left", pids_under(work / f"run_{name}") == [])

        def tampered():
            publish(served, new_app, key_ok, pw_ok, port, NEW_V)
            arc = next(served.glob("*.tar.gz"))
            arc.write_bytes(arc.read_bytes() + b"tampered")

        def wrong_key():
            publish(served, new_app, key_bad, pw_bad, port, NEW_V)

        def version_lie():
            publish(served, new_app, key_ok, pw_ok, port, NEW_V)
            m = json.loads((served / "latest.json").read_text())
            m["version"] = "9.9.9"  # claims a newer version than the one the signature covers
            (served / "latest.json").write_text(json.dumps(m))

        def unreachable():
            shutil.rmtree(served, ignore_errors=True)
            served.mkdir()

        negative("tampered", "signature", tampered)
        negative("wrong_key", "signature", wrong_key)
        negative("version_lie", "signature", version_lie)
        negative("unreachable", "network", unreachable)
    finally:
        server.stop()
        for d in work.glob("run_*"):
            stop_all(d)
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
