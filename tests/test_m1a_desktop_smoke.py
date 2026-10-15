"""Runs the packaged-app smoke test (scripts/smoke_desktop_app.py) when a build exists; opt-in because it launches the app."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS app bundle")
@pytest.mark.skipif(os.environ.get("AETHER_RUN_DESKTOP_SMOKE") != "1", reason="set AETHER_RUN_DESKTOP_SMOKE=1 to launch the packaged app")
@pytest.mark.skipif(not (ROOT / "build" / "Aether.app").exists(), reason="build/Aether.app missing (run scripts/build_distribution.py)")
def test_packaged_app_smoke():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "smoke_desktop_app.py")], capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]
