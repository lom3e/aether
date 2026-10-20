#!/usr/bin/env python3
"""Run the packaged Aether for hands-on testing with a FIXED dev profile, so nothing has to be set up again between runs.

    python scripts/dev_app.py              # opens build/Aether.app with the dev profile
    python scripts/dev_app.py --headless   # only the runtime (no window), for scripted checks; prints the base URL, not the token

The dev profile lives in ~/.aether-dev (its own HOME and data dir: your real Aether data is never touched). The Groq key is read
from ~/.aether-dev/groq.key (chmod 600, outside the repo) and stored once in the dev profile's encrypted store through the normal
settings route; it is never printed, logged or passed on a command line. Real-provider runs always name provider and model.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "build" / "Aether.app"
DEV = Path.home() / ".aether-dev"
KEY_FILE = DEV / "groq.key"
MASTER_FILE = DEV / "master.key"
PROVIDER, MODEL = "groq", "openai/gpt-oss-120b"  # the older llama models are retired on Groq; this one is live for the dev key


def _call(base: str, token: str, path: str, method="GET", body: dict | None = None):
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("X-Aether-Session-Token", token)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode() or "{}")


def ensure_provider(base: str, token: str) -> str:
    if not KEY_FILE.is_file():
        return f"no key file at {KEY_FILE}: set the provider from the app"
    cur = _call(base, token, "/api/settings/provider")
    if cur.get("provider") == PROVIDER and cur.get("model") == MODEL and cur.get("configured", {}).get(PROVIDER):
        return "groq already configured in the dev profile"
    _call(base, token, "/api/settings/provider", "POST", {"provider": PROVIDER, "model": MODEL, "api_key": KEY_FILE.read_text().strip(), "apply_to_all_agents": True})
    return f"groq / {MODEL} configured in the dev profile"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args()
    home, data = DEV / "home", DEV / "data"
    home.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    if not MASTER_FILE.exists():  # a stable vault key for the dev profile (no Keychain prompts, nothing to re-enter)
        import secrets
        MASTER_FILE.write_text(secrets.token_hex(32))
        MASTER_FILE.chmod(0o600)
    env = {**os.environ, "AETHER_MASTER_KEY": MASTER_FILE.read_text().strip(), "HOME": str(home), "AETHER_DATA_DIR": str(data), "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring"}
    env.pop("GROQ_API_KEY", None)
    if a.headless:
        cmd = [str(APP / "Contents" / "Resources" / "aether-runtime" / "aether-runtime"), "--host", "127.0.0.1", "--port", "0", "--data-dir", str(data), "--token", "dev-headless-token", "--no-browser"]
    else:
        cmd = [str(APP / "Contents" / "MacOS" / "aether-desktop")]
    if not Path(cmd[0]).exists():
        print(f"{cmd[0]} not found: run scripts/build_distribution.py first")
        return 2
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    base = token = None
    configured = False
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            if "Session token" in line:
                token = line.split(":", 1)[1].strip()
                line = "  ► Session token: (hidden)\n"
            m = re.search(r"ready at: (http://127\.0\.0\.1:\d+)", line)
            if m:
                base = m.group(1)
            if "token=" in line:
                line = re.sub(r"token=[^ &\"]+", "token=(hidden)", line)
            sys.stdout.write(line)
            if a.headless and "--token" in cmd:
                token = "dev-headless-token"
            if base and token and not configured:
                configured = True
                time.sleep(1.5)
                try:
                    print(f"[dev] {ensure_provider(base, token)}")
                except Exception as exc:  # noqa: BLE001
                    print(f"[dev] could not configure the provider: {type(exc).__name__}")
                if a.headless:
                    print(f"[dev] headless runtime at {base}")
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
