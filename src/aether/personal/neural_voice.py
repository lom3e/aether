"""Aether's natural voice: Kokoro (82M parameters, Apache-2.0) running on this Mac with onnxruntime. Nothing leaves the computer.

The model is not shipped with the app: the user downloads it once from Settings (~120 MB, checked against a pinned SHA-256).
Text becomes phonemes through the `espeak-ng` program (a separate executable, run with the text on stdin), then the model turns
phonemes into 24 kHz audio. We drive the ONNX model directly instead of using the `kokoro-onnx` package: its bundled espeak
library ignores the data path on macOS, and loading GPL code in-process is not something an MIT app should do.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import wave
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = {
    "model": {"name": "kokoro-v1.0.int8.onnx", "size": 92361271,
              "sha256": "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb"},
    "voices": {"name": "voices-v1.0.bin", "size": 28214398,
               "sha256": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"},
}
DOWNLOAD_BYTES = sum(f["size"] for f in FILES.values())
SAMPLE_RATE = 24000
MAX_TOKENS = 510
# the voices offered per language, the first is the default
VOICES = {"it": (("if_sara", "Sara"), ("im_nicola", "Nicola")), "en": (("af_heart", "Heart"), ("am_michael", "Michael"))}
ALL_VOICE_IDS = tuple(v for vs in VOICES.values() for v, _ in vs)
_ESPEAK_LANG = {"it": "it", "en": "en-us"}

# Kokoro's phoneme vocabulary (from the model config): every other character is dropped before tokenizing
VOCAB = {";": 1, ":": 2, ",": 3, ".": 4, "!": 5, "?": 6, "—": 9, "…": 10, "\"": 11, "(": 12, ")": 13, "“": 14, "”": 15, " ": 16,
         "̃": 17, "ʣ": 18, "ʥ": 19, "ʦ": 20, "ʨ": 21, "ᵝ": 22, "ꭧ": 23, "A": 24, "I": 25, "O": 31, "Q": 33, "S": 35, "T": 36, "W": 39,
         "Y": 41, "ᵊ": 42, "a": 43, "b": 44, "c": 45, "d": 46, "e": 47, "f": 48, "h": 50, "i": 51, "j": 52, "k": 53, "l": 54, "m": 55,
         "n": 56, "o": 57, "p": 58, "q": 59, "r": 60, "s": 61, "t": 62, "u": 63, "v": 64, "w": 65, "x": 66, "y": 67, "z": 68, "ɑ": 69,
         "ɐ": 70, "ɒ": 71, "æ": 72, "β": 75, "ɔ": 76, "ɕ": 77, "ç": 78, "ɖ": 80, "ð": 81, "ʤ": 82, "ə": 83, "ɚ": 85, "ɛ": 86, "ɜ": 87,
         "ɟ": 90, "ɡ": 92, "ɥ": 99, "ɨ": 101, "ɪ": 102, "ʝ": 103, "ɯ": 110, "ɰ": 111, "ŋ": 112, "ɳ": 113, "ɲ": 114, "ɴ": 115, "ø": 116,
         "ɸ": 118, "θ": 119, "œ": 120, "ɹ": 123, "ɾ": 125, "ɻ": 126, "ʁ": 128, "ɽ": 129, "ʂ": 130, "ʃ": 131, "ʈ": 132, "ʧ": 133, "ʊ": 135,
         "ʋ": 136, "ʌ": 138, "ɣ": 139, "ɤ": 140, "χ": 142, "ʎ": 143, "ʒ": 147, "ʔ": 148, "ˈ": 156, "ˌ": 157, "ː": 158, "ʰ": 162,
         "ʲ": 164, "↓": 169, "→": 171, "↗": 172, "↘": 173, "ᵻ": 177}


class NeuralVoiceError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


def _lang(language: str) -> str:
    return "it" if str(language).lower().startswith("it") else "en"


def voices(language: str) -> list[dict[str, str]]:
    return [{"id": v, "name": n} for v, n in VOICES[_lang(language)]]


def voice_for(language: str, chosen: str = "") -> str:
    ids = [v for v, _ in VOICES[_lang(language)]]
    return chosen if chosen in ids else ids[0]


# -- where things live -----------------------------------------------------------------------------------------------------
def model_dir() -> Path:
    from aether.core.paths import get_aether_data_dir

    return get_aether_data_dir() / "voices" / "kokoro"


def espeak() -> tuple[str, str | None] | None:
    """(program, data dir or None). The app bundles its own copy; a development Mac can use Homebrew's."""
    env = os.environ.get("AETHER_ESPEAK_NG", "").strip()
    candidates: list[tuple[Path, Path | None]] = []
    if env:
        candidates.append((Path(env), None))
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append((Path(bundle) / "espeak-ng" / "bin" / "espeak-ng", Path(bundle) / "espeak-ng" / "share"))
    found = shutil.which("espeak-ng")
    for p in ([found] if found else []) + ["/opt/homebrew/bin/espeak-ng", "/usr/local/bin/espeak-ng"]:
        candidates.append((Path(p), None))
    for prog, data in candidates:
        if prog.is_file() and os.access(prog, os.X_OK):
            return str(prog), (str(data) if data and data.is_dir() else None)
    return None


def _runtime_ok() -> bool:
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def installed() -> bool:
    d = model_dir()
    return all((d / f["name"]).is_file() and (d / f["name"]).stat().st_size == f["size"] for f in FILES.values())


# -- download --------------------------------------------------------------------------------------------------------------
_dl_lock = threading.Lock()
_dl: dict[str, Any] = {"state": "idle", "done": 0, "error": ""}


def _fetch(url: str, dest: Path, sha256: str, size: int, base_done: int) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "Aether"})
    with urllib.request.urlopen(req, timeout=60) as r, part.open("wb") as out:  # noqa: S310 - fixed https URL, pinned hash
        got = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
            got += len(chunk)
            _dl["done"] = base_done + got
            if _dl.get("cancel"):
                raise NeuralVoiceError("cancelled")
    if got != size or h.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise NeuralVoiceError("checksum", dest.name)
    part.replace(dest)


def _download_worker() -> None:
    d = model_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        done = 0
        for f in FILES.values():
            dest = d / f["name"]
            if not (dest.is_file() and dest.stat().st_size == f["size"]):
                _fetch(_BASE + f["name"], dest, f["sha256"], f["size"], done)
            done += f["size"]
            _dl["done"] = done
        _dl.update(state="ready", error="")
    except NeuralVoiceError as e:
        _dl.update(state="idle" if e.code == "cancelled" else "error", error=e.code)
    except Exception as e:  # noqa: BLE001 - network or disk: reported to the UI, never raised into the server
        logger.warning("voice model download failed: %s", type(e).__name__)
        _dl.update(state="error", error="network")
    finally:
        for p in d.glob("*.part"):
            p.unlink(missing_ok=True)


def start_download() -> dict[str, Any]:
    with _dl_lock:
        if _dl["state"] == "downloading":
            return download_status()
        if installed():
            _dl.update(state="ready", done=DOWNLOAD_BYTES, error="")
            return download_status()
        _dl.update(state="downloading", done=0, error="", cancel=False)
        threading.Thread(target=_download_worker, name="aether-voice-download", daemon=True).start()
    return download_status()


def cancel_download() -> None:
    _dl["cancel"] = True


def remove() -> None:
    global _engine
    with _engine_lock:
        _engine = None
    shutil.rmtree(model_dir(), ignore_errors=True)
    _dl.update(state="idle", done=0, error="")


def download_status() -> dict[str, Any]:
    return {"state": _dl["state"], "done": _dl["done"], "total": DOWNLOAD_BYTES, "error": _dl["error"]}


def state() -> str:
    """ready | missing (can be downloaded) | downloading | unavailable (this build/Mac cannot run it)."""
    if not _runtime_ok() or espeak() is None:
        return "unavailable"
    if _dl["state"] == "downloading":
        return "downloading"
    return "ready" if installed() else "missing"


def status(language: str = "it") -> dict[str, Any]:
    return {"state": state(), "voices": voices(language), "download": download_status(), "size_mb": round(DOWNLOAD_BYTES / 1e6)}


# -- speaking --------------------------------------------------------------------------------------------------------------
_CLAUSE = re.compile(r"(.+?)([.,!?;:…]+(?=\s|$)|$)", re.S)


def _normalize(text: str, language: str) -> str:
    """What espeak reads badly: our own name (Italian reads it "a-e-tèr"), and "18:00" (read "diciotto e zero zero")."""
    if _lang(language) == "it":
        text = re.sub(r"\b[Aa]ether\b", "Ìter", text)
        text = re.sub(r"\b(\d{1,2}):00\b", r"\1", text)
    return text


def phonemize(text: str, language: str = "it") -> str:
    """espeak-ng per clause (its own output drops punctuation, which Kokoro uses for pauses and intonation)."""
    text = _normalize(text, language)
    found = espeak()
    if not found:
        raise NeuralVoiceError("unavailable", "espeak-ng")
    prog, data = found
    cmd = [prog, "-q", "--ipa", "-v", _ESPEAK_LANG[_lang(language)]]
    if data:
        cmd.insert(1, f"--path={data}")
    out: list[str] = []
    for clause, punct in _CLAUSE.findall(text):
        if not clause.strip():
            if punct and out:
                out[-1] += punct
            continue
        try:
            res = subprocess.run(cmd, input=clause, capture_output=True, text=True, timeout=15, check=True)
        except (OSError, subprocess.SubprocessError) as e:
            raise NeuralVoiceError("phonemes", type(e).__name__) from None
        ph = re.sub(r"\([a-z-]+\)", "", res.stdout)  # language-switch marks like "(en)"
        ph = " ".join("".join(c for c in ph if c in VOCAB or c.isspace()).split())
        if ph:
            out.append(ph + punct)
    return " ".join(out)


def _batches(phonemes: str) -> list[str]:
    """Pieces that fit the model's context, cut after punctuation where possible."""
    out: list[str] = []
    cur = ""
    for part in re.findall(r"[^.,!?;:…]+[.,!?;:…]*\s*", phonemes) or [phonemes]:
        while len(part) > MAX_TOKENS:
            out.append(part[:MAX_TOKENS])
            part = part[MAX_TOKENS:]
        if len(cur) + len(part) > MAX_TOKENS:
            out.append(cur)
            cur = ""
        cur += part
    if cur.strip():
        out.append(cur)
    return [b.strip() for b in out if b.strip()]


_engine_lock = threading.Lock()
_engine: Any = None


def _load() -> Any:
    global _engine
    with _engine_lock:
        if _engine is None:
            if not installed():
                raise NeuralVoiceError("not_installed")
            import numpy as np
            import onnxruntime as rt

            d = model_dir()
            opts = rt.SessionOptions()
            opts.log_severity_level = 3
            sess = rt.InferenceSession(str(d / FILES["model"]["name"]), sess_options=opts, providers=["CPUExecutionProvider"])
            styles = dict(np.load(str(d / FILES["voices"]["name"])))
            _engine = (sess, styles, [i.name for i in sess.get_inputs()])
        return _engine


def _trim(audio: Any) -> Any:
    """Leading/trailing silence off (keeps 60 ms), so the pieces of a long answer join without gaps."""
    import numpy as np

    if not len(audio):
        return audio
    loud = np.flatnonzero(np.abs(audio) > max(1e-4, float(np.max(np.abs(audio))) * 0.001))
    if not len(loud):
        return audio[:0]
    pad = int(0.06 * SAMPLE_RATE)
    return audio[max(0, loud[0] - pad): loud[-1] + pad]


def synthesize(text: str, language: str = "it", voice: str = "", speed: float = 1.0) -> bytes:
    """WAV (16-bit mono, 24 kHz) for `text`."""
    import numpy as np

    sess, styles, inputs = _load()
    vid = voice_for(language, voice)
    if vid not in styles:
        raise NeuralVoiceError("unknown_voice", vid)
    phonemes = phonemize(text, language)
    if not phonemes:
        raise NeuralVoiceError("empty")
    parts = []
    for batch in _batches(phonemes):
        tokens = [VOCAB[c] for c in batch]
        style = styles[vid][len(tokens)].astype(np.float32)
        ids = [[0, *tokens, 0]]
        feed = ({"input_ids": ids, "style": style, "speed": np.array([speed], dtype=np.int32)} if "input_ids" in inputs
                else {"tokens": ids, "style": style, "speed": np.array([speed], dtype=np.float32)})
        parts.append(_trim(sess.run(None, feed)[0]))
    pcm = (np.clip(np.concatenate(parts), -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
