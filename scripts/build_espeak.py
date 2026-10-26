"""Builds the `espeak-ng` program that Aether's natural voice uses to turn text into phonemes, for the app bundle.

espeak-ng is GPL-3.0: Aether (MIT) ships it as a separate program it runs (text on stdin, phonemes on stdout), never linked
into Aether's own code, together with its license and the exact source it was built from (see THIRD_PARTY below).

Output: build/espeak-ng/{bin/espeak-ng, share/espeak-ng-data/(it, en only), COPYING, SOURCE.txt}. build_python_runtime.py
bundles that folder when it exists. Static, no audio output, arm64, macOS 11+ (the app's minimum).

    python3 scripts/build_espeak.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "1.52.0"
URL = f"https://github.com/espeak-ng/espeak-ng/archive/refs/tags/{VERSION}.tar.gz"
SHA256 = "bb4338102ff3b49a81423da8a1a158b420124b055b60fa76cfb4b18677130a23"
REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "build" / "espeak-ng"
# what `espeak-ng -v it|en-us --ipa` needs: phoneme tables, intonation, the two dictionaries and the voice definitions
DATA_FILES = ("phontab", "phonindex", "phondata", "intonations", "it_dict", "en_dict")
DATA_DIRS = ("lang",)


def main() -> int:
    if sys.platform != "darwin":
        print("macOS only (the Windows build does not ship the natural voice yet).", file=sys.stderr)
        return 1
    if not shutil.which("cmake"):
        print("cmake is needed: brew install cmake", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="aether-espeak-") as tmp:
        t = Path(tmp)
        tarball = t / "src.tar.gz"
        print(f"Downloading espeak-ng {VERSION}…")
        with urllib.request.urlopen(URL, timeout=120) as r:  # noqa: S310 - fixed https URL, pinned hash below
            tarball.write_bytes(r.read())
        digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
        if digest != SHA256:
            print(f"Checksum mismatch: {digest}", file=sys.stderr)
            return 1
        with tarfile.open(tarball) as tf:
            tf.extractall(t, filter="data")
        src, build, prefix = t / f"espeak-ng-{VERSION}", t / "b", t / "inst"
        env = {**os.environ, "MACOSX_DEPLOYMENT_TARGET": "11.0"}
        subprocess.run(["cmake", "-S", str(src), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                        "-DCMAKE_OSX_DEPLOYMENT_TARGET=11.0", "-DCMAKE_OSX_ARCHITECTURES=arm64", "-DBUILD_SHARED_LIBS=OFF",
                        "-DUSE_ASYNC=OFF", "-DUSE_MBROLA=OFF", "-DUSE_LIBSONIC=OFF", "-DUSE_LIBPCAUDIO=OFF", "-DUSE_KLATT=OFF",
                        "-DUSE_SPEECHPLAYER=OFF", "-DESPEAK_BUILD_MANPAGES=OFF", f"-DCMAKE_INSTALL_PREFIX={prefix}"],
                       check=True, env=env)
        subprocess.run(["cmake", "--build", str(build), "-j", str(os.cpu_count() or 4)], check=True, env=env)
        subprocess.run(["cmake", "--install", str(build)], check=True, env=env)

        data = prefix / "share" / "espeak-ng-data"
        shutil.rmtree(OUT, ignore_errors=True)
        (OUT / "bin").mkdir(parents=True)
        (OUT / "share" / "espeak-ng-data").mkdir(parents=True)
        shutil.copy2(prefix / "bin" / "espeak-ng", OUT / "bin" / "espeak-ng")
        for name in DATA_FILES:
            shutil.copy2(data / name, OUT / "share" / "espeak-ng-data" / name)
        for name in DATA_DIRS:
            shutil.copytree(data / name, OUT / "share" / "espeak-ng-data" / name)
        shutil.copy2(src / "COPYING", OUT / "COPYING")
        (OUT / "SOURCE.txt").write_text(
            f"espeak-ng {VERSION}, GPL-3.0-or-later. Unmodified source: {URL} (sha256 {SHA256}).\n"
            "Built with scripts/build_espeak.py from the Aether repository. Run by Aether as a separate program.\n")

    prog = OUT / "bin" / "espeak-ng"
    out = subprocess.run([str(prog), f"--path={OUT / 'share'}", "-q", "--ipa", "-v", "it"], input="Ciao, sono pronta.",
                         capture_output=True, text=True, check=True).stdout.strip()
    deps = subprocess.run(["otool", "-L", str(prog)], capture_output=True, text=True).stdout
    if "/opt/homebrew" in deps or "/usr/local" in deps:
        print(f"The program links to a local library, it would not run on other Macs:\n{deps}", file=sys.stderr)
        return 1
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"OK: {OUT} ({size / 1e6:.1f} MB) — test: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
