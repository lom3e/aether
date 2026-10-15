#!/usr/bin/env python3
"""Repeatable smoke test of the Windows NSIS installer (run on a real Windows host or the CI runner).

    python scripts/smoke_desktop_windows.py [--installer build/Aether-x64-setup.exe] [--work-dir DIR]

Everything lives under a temporary work directory: the app is installed silently into <work>/install and run with
APPDATA / LOCALAPPDATA / USERPROFILE / HOME / TEMP pointing into <work>/profile, so no real user data is touched.
Only processes whose executable lives under the work directory are ever stopped.

  A. Installer: exists, is a PE file, silent install works, layout (main exe, frozen sidecar, presets).
  B. App:       launch -> sidecar child appears and listens, /api/health, native window titled "Aether", the WebView2
                process talks to the sidecar (UI -> runtime), data dir under the isolated APPDATA, then the desktop
                process is terminated hard (no signals exist on Windows) -> the sidecar must exit by itself (watchdog).
  C. Runtime:   frozen sidecar started directly with a known token: health, UI + asset, token enforcement, workspace
                creation, chat without a provider in it/en, authenticated shutdown, clean exit.
  D. Uninstall: silent uninstall removes the program but keeps the user data.
  E. No process under the work directory is left running.
Exit code 0 only if every executed check passed.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_desktop_app import check, http, record, results, wait_gone  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IS_WIN = sys.platform == "win32"


def ps_json(script: str):
    """Run a PowerShell snippet that prints JSON and return it parsed ([] when empty)."""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=120)
    out = r.stdout.strip()
    if not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


def processes_under(root: Path) -> list[dict]:
    prefix = str(root).replace("'", "''")
    return ps_json(
        "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith('"
        + prefix + "', [System.StringComparison]::OrdinalIgnoreCase) } | "
        "Select-Object ProcessId,Name,ParentProcessId,ExecutablePath | ConvertTo-Json -Compress"
    )


def child_processes(pid: int) -> list[dict]:
    return ps_json(f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' | Select-Object ProcessId,Name | ConvertTo-Json -Compress")


def listening_port(pid: int) -> int | None:
    rows = ps_json(f"Get-NetTCPConnection -State Listen -OwningProcess {pid} -ErrorAction SilentlyContinue | Select-Object LocalPort | ConvertTo-Json -Compress")
    return int(rows[0]["LocalPort"]) if rows else None


def webview_connected_to(port: int) -> bool:
    rows = ps_json(
        f"Get-NetTCPConnection -RemotePort {port} -State Established -ErrorAction SilentlyContinue | "
        "ForEach-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName } | ConvertTo-Json -Compress"
    )
    return any(isinstance(n, str) and "webview" in n.lower() for n in rows)


def pid_alive(pid: int) -> bool:
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore[attr-defined]
    if not handle:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))  # type: ignore[attr-defined]
    ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
    return code.value == 259


def window_titles(pid: int) -> list[str]:
    titles: list[str] = []
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value:
                titles.append(buf.value)
        return True

    user32.EnumWindows(enum_proc(cb), 0)
    return titles


def wait_until(fn, timeout: float, step: float = 1.0):
    end = time.time() + timeout
    while time.time() < end:
        val = fn()
        if val:
            return val
        time.sleep(step)
    return fn()


def isolated_env(profile: Path, **extra) -> dict:
    env = dict(os.environ)
    for key, sub in (("APPDATA", "AppData/Roaming"), ("LOCALAPPDATA", "AppData/Local"), ("USERPROFILE", ""), ("HOME", ""), ("TEMP", "AppData/Local/Temp"), ("TMP", "AppData/Local/Temp")):
        d = profile / sub if sub else profile
        d.mkdir(parents=True, exist_ok=True)
        env[key] = str(d)
    env.update({k: str(v) for k, v in extra.items()})
    return env


def kill_under(root: Path) -> None:
    for _ in range(2):
        for p in processes_under(root):
            subprocess.run(["taskkill", "/F", "/PID", str(p["ProcessId"])], capture_output=True)
        time.sleep(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--installer", default=str(ROOT / "build" / "Aether-x64-setup.exe"))
    ap.add_argument("--work-dir")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if not IS_WIN:
        print("This smoke test must run on Windows. Nothing was executed (a macOS build is never proof for Windows).")
        return 3
    installer = Path(a.installer)
    work = Path(a.work_dir or tempfile.mkdtemp(prefix="aether_win_smoke_")).resolve()
    work.mkdir(parents=True, exist_ok=True)
    install, profile = work / "install", work / "profile"
    try:
        # ---------------- A. installer ----------------
        if not check("A: installer exists", installer.is_file(), str(installer)):
            return 1
        check("A: installer is a Windows executable (MZ header)", installer.read_bytes()[:2] == b"MZ", f"{installer.stat().st_size / 1e6:.1f} MB")
        env = isolated_env(profile)
        r = subprocess.run([str(installer), "/S", f"/D={install}"], env=env, timeout=600)
        check("A: silent install succeeds", r.returncode == 0 and install.exists(), f"rc={r.returncode}")
        exes = [p for p in install.glob("*.exe") if "uninstall" not in p.name.lower()]
        main_exe = exes[0] if exes else None
        check("A: main executable installed", main_exe is not None, main_exe.name if main_exe else "")
        sidecars = list(install.rglob("aether-runtime.exe"))
        check("A: frozen sidecar installed", bool(sidecars), str(sidecars[0].relative_to(install)) if sidecars else "")
        check("A: builtin presets installed", any(install.rglob("manifest.yaml")))
        check("A: uninstaller installed", any(install.glob("uninstall*.exe")))
        if not main_exe or not sidecars:
            return 1

        # ---------------- B. the app ----------------
        proc = subprocess.Popen([str(main_exe)], env=env, cwd=str(install))
        sidecar_pid = None
        try:
            def find_sidecar():
                for c in child_processes(proc.pid):
                    if str(c.get("Name", "")).lower() == "aether-runtime.exe":
                        return int(c["ProcessId"])
                return None

            sidecar_pid = wait_until(find_sidecar, 90)
            check("B: sidecar child process started", sidecar_pid is not None)
            port = wait_until(lambda: listening_port(sidecar_pid) if sidecar_pid else None, 60)
            check("B: sidecar is listening on a loopback port", port is not None, str(port))
            if port:
                st, body = wait_until(lambda: (lambda s: s if s[0] == 200 else None)(http(f"http://127.0.0.1:{port}/api/health")), 60) or (0, "")
                check("B: /api/health 200", st == 200, body[:60])
            titles = wait_until(lambda: [t for t in window_titles(proc.pid) if "aether" in t.lower()], 60)
            if titles:
                check("B: native window titled 'Aether' exists", True, ", ".join(titles))
            else:
                check("B: native window titled 'Aether' exists", False, "no top-level window with that title (is WebView2 installed / is there an interactive desktop?)")
            if port:
                check("B: WebView2 is connected to the runtime (UI -> sidecar)", bool(wait_until(lambda: webview_connected_to(port), 45)))
            data_dir = Path(env["APPDATA"]) / "Aether"
            check("B: data directory is under the isolated APPDATA", wait_until(data_dir.is_dir, 30) is True, str(data_dir))
            check("B: app and sidecar run from the install directory only",
                  all(str(p["ExecutablePath"]).lower().startswith(str(install).lower()) or "webview" in str(p["Name"]).lower() for p in processes_under(install) if p["ProcessId"] in {proc.pid, sidecar_pid}))
            # Windows has no SIGTERM for GUI processes: a hard kill is the worst case, so the sidecar must stop on its own.
            subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True)
            check("B: desktop process gone", wait_gone(proc.pid, 15, proc))
            if sidecar_pid:
                gone = wait_until(lambda: not pid_alive(sidecar_pid), 40)
                check("B: sidecar stops by itself after a hard kill (parent watchdog)", bool(gone))
        finally:
            kill_under(install)

        # ---------------- C. runtime on its own ----------------
        token = "smoke-" + os.urandom(8).hex()
        rt_env = isolated_env(work / "profile_rt", AETHER_SESSION_TOKEN=token, AETHER_DESKTOP_RUNTIME="1", AETHER_APP_BUNDLE="1", PYTHONUNBUFFERED="1")
        log = work / "runtime.log"
        rt = subprocess.Popen([str(sidecars[0]), "--host", "127.0.0.1", "--port", "0", "--data-dir", str(work / "rt_data"), "--token", token, "--no-browser"],
                              env=rt_env, stdout=open(log, "wb"), stderr=subprocess.STDOUT)
        try:
            ok = wait_until(lambda: re.search(r"ready at: http://127\.0\.0\.1:(\d+)", log.read_text(errors="replace")), 90)
            if check("C: runtime reports ready", bool(ok)):
                base = f"http://127.0.0.1:{ok.group(1)}"
                check("C: /api/health ok", http(base + "/api/health")[0] == 200)
                check("C: API requires the session token", http(base + "/api/workspace")[0] in (401, 403))
                st, html = http(base + "/")
                asset = re.search(r'src="(/assets/[^"]+\.js)"', html)
                check("C: UI index served", st == 200 and asset is not None)
                if asset:
                    check("C: UI asset served", http(base + asset.group(1))[0] == 200)
                ws_dir = work / "ws"
                st, body = http(base + "/api/workspaces", "POST", {"name": "Smoke", "path": str(ws_dir)}, token)
                check("C: workspace creation via API (Windows path)", st in (200, 201), f"{st} {body[:80]}")
                for lang, expected in (("it", "Nessun provider AI configurato"), ("en", "No AI provider configured")):
                    st, body = http(base + "/api/personal/chat", "POST", {"prompt": "Ciao, chi sei?", "language": lang}, token, timeout=60)
                    check(f"C: chat without provider answers in '{lang}'", st == 200 and expected in body, str(st))
                check("C: authenticated shutdown accepted", http(base + "/api/system/shutdown", "POST", {}, token)[0] == 200)
                check("C: runtime exits after shutdown", wait_gone(rt.pid, 30, rt))
        finally:
            if rt.poll() is None:
                rt.kill()

        # ---------------- D. uninstall keeps user data ----------------
        unins = next(iter(install.glob("uninstall*.exe")), None)
        if unins:
            subprocess.run([str(unins), "/S"], env=env, timeout=300)
            gone = wait_until(lambda: not main_exe.exists(), 60)
            check("D: uninstall removes the program", bool(gone))
            check("D: uninstall keeps the user data directory", (Path(env["APPDATA"]) / "Aether").is_dir())
        else:
            record("D: uninstall", "SKIP", "no uninstaller found")
    finally:
        kill_under(work)
        left = processes_under(work)
        check("E: no process left under the work directory", not left, ", ".join(str(p["Name"]) for p in left))
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)
    failed = [n for n, s, _ in results if s == "FAIL"]
    print(f"\n{sum(1 for _, s, _ in results if s == 'PASS')} passed, {len(failed)} failed, {sum(1 for _, s, _ in results if s == 'SKIP')} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
