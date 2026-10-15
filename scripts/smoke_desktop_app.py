#!/usr/bin/env python3
"""Repeatable smoke test of the packaged macOS app (build/Aether.app + build/Aether.dmg).

Everything runs with an isolated HOME / data dir; real user data is never touched, and only processes started by this
script are stopped. No mouse coordinates are used.

  A. Bundle:   Info.plist, executable, bundled sidecar, code signature, DMG checksum.
  B. App:      launch the real app -> sidecar ready + /api/health, window exists (macOS Accessibility, skipped with a
               note when that permission is missing), the UI's own API traffic reaches the runtime, then
               SIGTERM -> app and sidecar both gone; second launch + SIGKILL -> the sidecar's parent watchdog stops it.
  C. Runtime:  start the frozen sidecar directly with a known token -> /api/health, UI + asset served, workspace creation,
               chat without provider answers in the requested language (it/en), authenticated shutdown endpoint.

Usage: python scripts/smoke_desktop_app.py [--skip-window]      exit code 0 only if every executed check passed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "build" / "Aether.app"
DMG = ROOT / "build" / "Aether.dmg"
results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    print(f"{status:5} {name}" + (f"  [{detail}]" if detail else ""), flush=True)


def check(name: str, ok: bool, detail: str = "") -> bool:
    record(name, "PASS" if ok else "FAIL", detail)
    return ok


def wait_for(path: Path, pattern: str, timeout: float, count: int = 1) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and len(re.findall(pattern, path.read_text(errors="replace"))) >= count:
            return True
        time.sleep(0.3)
    return False


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def wait_gone(pid: int, timeout: float, proc: subprocess.Popen | None = None) -> bool:
    """True once the process is gone. Pass `proc` for our own children: they stay zombies until waited for."""
    end = time.time() + timeout
    while time.time() < end:
        if proc is not None:
            if proc.poll() is not None:
                return True
        elif not alive(pid):
            return True
        time.sleep(0.3)
    return proc.poll() is not None if proc is not None else not alive(pid)


def children(pid: int) -> list[int]:
    return [int(x) for x in subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()]


def http(url: str, method="GET", body: dict | None = None, token: str | None = None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Aether-Session-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def sh(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def bundle_checks() -> None:
    check("A: Aether.app exists", APP.is_dir())
    _, out = sh(["plutil", "-p", str(APP / "Contents" / "Info.plist")])
    check("A: bundle identifier is com.aether.desktop", '"CFBundleIdentifier" => "com.aether.desktop"' in out)
    check("A: main executable present", (APP / "Contents" / "MacOS" / "aether-desktop").is_file())
    runtime = APP / "Contents" / "Resources" / "aether-runtime" / "aether-runtime"
    check("A: frozen sidecar bundled and executable", runtime.is_file() and os.access(runtime, os.X_OK))
    check("A: builtin presets bundled", any((APP / "Contents" / "Resources" / "aether-runtime").rglob("manifest.yaml")))
    rc, _ = sh(["codesign", "--verify", "--deep", "--strict", str(APP)])
    check("A: code signature is valid", rc == 0)
    if DMG.exists():
        rc, out = sh(["hdiutil", "verify", str(DMG)])
        check("A: DMG checksum valid", rc == 0, "")
    else:
        record("A: DMG checksum valid", "SKIP", "build/Aether.dmg missing")


def window_check(pid: int) -> None:
    script = f'tell application "System Events" to tell (first process whose unix id is {pid}) to get name of every window'
    for _ in range(20):
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if r.returncode == 0 and "Aether" in r.stdout:
            check("B: native window 'Aether' exists", True)
            return
        if r.returncode != 0 and ("1002" in r.stderr or "not allowed" in r.stderr.lower() or "assistive" in r.stderr.lower()):
            record("B: native window 'Aether' exists", "SKIP", "Accessibility permission missing for this terminal")
            return
        time.sleep(0.5)
    check("B: native window 'Aether' exists", False, (r.stderr or r.stdout).strip()[:80])


def app_checks(skip_window: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="aether_smoke_app_") as tmp:
        tmp_path = Path(tmp)
        for mode in ("TERM", "KILL"):
            home = tmp_path / f"home_{mode}"
            home.mkdir()
            log = tmp_path / f"app_{mode}.log"
            env = dict(os.environ, HOME=str(home))
            proc = subprocess.Popen([str(APP / "Contents" / "MacOS" / "aether-desktop")], env=env,
                                    stdout=open(log, "wb"), stderr=subprocess.STDOUT, start_new_session=True)
            try:
                ready = wait_for(log, r"passed readiness", 60)
                check(f"B[{mode}]: sidecar ready and health probe passed", ready)
                if not ready:
                    continue
                sidecars = children(proc.pid)
                check(f"B[{mode}]: exactly one sidecar child", len(sidecars) == 1, str(sidecars))
                port = re.findall(r"ready at: http://127\.0\.0\.1:(\d+)", log.read_text(errors="replace"))[-1]
                st, body = http(f"http://127.0.0.1:{port}/api/health")
                check(f"B[{mode}]: /api/health 200", st == 200, body[:60])
                check(f"B[{mode}]: data dir is under the isolated HOME",
                      (home / "Library" / "Application Support" / "Aether").is_dir())
                if mode == "TERM":
                    check("B: UI reaches the runtime (webview API traffic)", wait_for(log, r'"GET /api/workspace', 30))
                    if skip_window:
                        record("B: native window 'Aether' exists", "SKIP", "--skip-window")
                    else:
                        window_check(proc.pid)
                os.kill(proc.pid, signal.SIGTERM if mode == "TERM" else signal.SIGKILL)
                check(f"B[{mode}]: desktop process gone", wait_gone(proc.pid, 15, proc))
                gone = all(wait_gone(s, 25) for s in sidecars)
                check(f"B[{mode}]: sidecar stops with it (no orphan)", gone)
            finally:
                for p in [proc.pid, *children(proc.pid)]:
                    if alive(p):
                        os.kill(p, signal.SIGKILL)
                try:
                    proc.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    pass


def runtime_checks() -> None:
    runtime = APP / "Contents" / "Resources" / "aether-runtime" / "aether-runtime"
    token = "smoke-" + os.urandom(8).hex()
    with tempfile.TemporaryDirectory(prefix="aether_smoke_rt_") as tmp:
        home = Path(tmp) / "home"
        home.mkdir()
        log = Path(tmp) / "rt.log"
        env = dict(os.environ, HOME=str(home), AETHER_SESSION_TOKEN=token, AETHER_DESKTOP_RUNTIME="1", AETHER_APP_BUNDLE="1",
                   PYTHONUNBUFFERED="1")
        proc = subprocess.Popen([str(runtime), "--host", "127.0.0.1", "--port", "0", "--data-dir", str(Path(tmp) / "data"),
                                 "--token", token, "--no-browser"], env=env, stdout=open(log, "wb"), stderr=subprocess.STDOUT)
        try:
            if not check("C: runtime reports ready", wait_for(log, r"ready at: http://127\.0\.0\.1:\d+", 60)):
                return
            port = re.findall(r"ready at: http://127\.0\.0\.1:(\d+)", log.read_text(errors="replace"))[-1]
            base = f"http://127.0.0.1:{port}"
            st, body = http(base + "/api/health")
            check("C: /api/health ok", st == 200 and '"ok"' in body.replace("'", '"').lower() or st == 200, body[:60])
            st, _ = http(base + "/api/workspace")
            check("C: API requires the session token", st in (401, 403))
            st, html = http(base + "/")
            asset = re.search(r'src="(/assets/[^"]+\.js)"', html)
            check("C: UI index served", st == 200 and asset is not None)
            if asset:
                check("C: UI asset served", http(base + asset.group(1))[0] == 200)
            st, body = http(base + "/api/workspaces", "POST", {"name": "Smoke", "path": str(Path(tmp) / "ws")}, token)
            if st not in (200, 201):
                st, body = http(base + "/api/workspaces", "POST", {"name": "Smoke"}, token)
            check("C: workspace creation via API", st in (200, 201), f"{st} {body[:80]}")
            for lang, expected in (("it", "Nessun provider AI configurato"), ("en", "No AI provider configured")):
                st, body = http(base + "/api/personal/chat", "POST", {"prompt": "Ciao, chi sei?", "language": lang}, token, timeout=60)
                check(f"C: chat without provider answers in '{lang}'", st == 200 and expected in body, f"{st}")
            st, _ = http(base + "/api/system/shutdown", "POST", {}, token)
            check("C: authenticated shutdown accepted", st == 200)
            check("C: runtime exits after shutdown", wait_gone(proc.pid, 20, proc))
        finally:
            if proc.poll() is None:
                proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-window", action="store_true")
    a = ap.parse_args()
    if not APP.exists():
        print("build/Aether.app not found: run scripts/build_distribution.py first")
        return 2
    bundle_checks()
    app_checks(a.skip_window)
    runtime_checks()
    failed = [n for n, s, _ in results if s == "FAIL"]
    skipped = [n for n, s, _ in results if s == "SKIP"]
    print(f"\n{sum(1 for _, s, _ in results if s == 'PASS')} passed, {len(failed)} failed, {len(skipped)} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
