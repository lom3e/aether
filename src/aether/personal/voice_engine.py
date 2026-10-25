"""Aether's voice: how it hears you (speech to text) and how it answers (text to speech).

Hearing: Whisper through the provider key the user already stored (Groq ``whisper-large-v3-turbo``, or OpenAI), which is far
more accurate than the browser dictation, especially in Italian; without a key the app falls back to the dictation of the
Mac ("device"). Speaking: the best voice installed on this Mac (Premium / Enhanced voices are neural and local, nothing leaves
the computer), or OpenAI's natural voice when the user has an OpenAI key and picks it. Every cloud call is written to the
privacy ledger like any other request that leaves the computer (kind and size, never the audio or the text).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STT_ENGINES = ("auto", "device", "groq", "openai")
TTS_ENGINES = ("auto", "system", "openai")
STT_MODELS = {"groq": "whisper-large-v3-turbo", "openai": "gpt-4o-mini-transcribe"}
STT_URLS = {"groq": "https://api.groq.com/openai/v1/audio/transcriptions", "openai": "https://api.openai.com/v1/audio/transcriptions"}
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_VOICES = ("coral", "nova", "sage", "alloy", "ash", "ballad", "echo", "shimmer", "verse")
DEFAULTS = {"stt": "auto", "tts": "auto", "system_voice": "", "openai_voice": "coral"}
MAX_AUDIO_BYTES = 12 * 1024 * 1024
MAX_SPEAK_CHARS = 1500

# novelty and "Eloquence" voices: they exist on every Mac but sound like a toy or a 1990s robot
_NOVELTY = {"albert", "bad news", "bahh", "bells", "boing", "bubbles", "cellos", "wobble", "fred", "good news", "jester", "junior",
            "kathy", "organ", "superstar", "ralph", "trinoids", "whisper", "zarvox", "eddy", "flo", "grandma", "grandpa", "reed",
            "rocko", "sandy", "shelley"}
_GOOD_COMPACT = {"it": ("federica", "alice", "emma", "luca", "paola"), "en": ("ava", "samantha", "allison", "zoe", "tom", "evan", "nathan", "susan")}


class VoiceError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


# -- settings ------------------------------------------------------------------------------------------------------------
def _settings_path(ws: Any) -> Path:
    return Path(ws.conversations_db_path).parent / "voice.json"


def settings(ws: Any) -> dict[str, Any]:
    out = dict(DEFAULTS)
    try:
        out.update({k: v for k, v in json.loads(_settings_path(ws).read_text()).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return out


def update_settings(ws: Any, **values: Any) -> dict[str, Any]:
    cur = settings(ws)
    if values.get("stt") is not None and values["stt"] not in STT_ENGINES:
        raise ValueError(f"stt must be one of {STT_ENGINES}")
    if values.get("tts") is not None and values["tts"] not in TTS_ENGINES:
        raise ValueError(f"tts must be one of {TTS_ENGINES}")
    if values.get("openai_voice") is not None and values["openai_voice"] not in OPENAI_VOICES:
        raise ValueError("unknown OpenAI voice")
    cur.update({k: v for k, v in values.items() if k in DEFAULTS and v is not None})
    p = _settings_path(ws)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cur))
    return cur


# -- keys ----------------------------------------------------------------------------------------------------------------
def _key(ws: Any, provider: str) -> str:
    store = getattr(ws, "secret_store", None)
    key = ""
    try:
        key = (store.get_secret(f"provider_api_key:{provider}") if store else "") or ""
    except Exception:  # noqa: BLE001 - a locked or broken store means "no key", never a crash
        key = ""
    return (key or os.environ.get(f"{provider.upper()}_API_KEY") or "").strip()


def stt_engine(ws: Any) -> str:
    """The engine that will actually transcribe: the user's pick if usable, else the most accurate one available."""
    pick = settings(ws)["stt"]
    if pick == "device":
        return "device"
    if pick in ("groq", "openai"):
        return pick if _key(ws, pick) else "device"
    for p in ("groq", "openai"):
        if _key(ws, p):
            return p
    return "device"


# -- system voices (macOS `say`) -------------------------------------------------------------------------------------------
_LINE = re.compile(r"^(?P<name>.+?)\s+(?P<lang>[a-z]{2,3}_[A-Z0-9]{2,3})\s+#")


def _quality(name: str) -> str:
    n = name.lower()
    if "premium" in n:
        return "premium"
    if any(w in n for w in ("enhanced", "avanzat", "migliorat", "siri")):
        return "enhanced"
    return "basic"


_listing_cache: dict[str, Any] = {"at": 0.0, "text": ""}


def _say_listing() -> str:
    """`say -v ?` takes most of a second: cached for a minute (a voice installed meanwhile shows up right after)."""
    if time.time() - _listing_cache["at"] < 60 and _listing_cache["text"]:
        return _listing_cache["text"]
    say = shutil.which("say")
    if not say:
        return ""
    try:
        text = subprocess.run([say, "-v", "?"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    _listing_cache.update(at=time.time(), text=text)
    return text


def system_voices(language: str = "it", listing: str | None = None) -> list[dict[str, Any]]:
    """Installed voices for the language, best first. `listing` is the output of `say -v ?` (injected in tests)."""
    if listing is None:
        listing = _say_listing()
    prefix = "it" if str(language).lower().startswith("it") else "en"
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for line in listing.splitlines():
        m = _LINE.match(line)
        if not m or not m["lang"].lower().startswith(prefix) or m["name"] in seen:
            continue
        name = m["name"].strip()
        seen.add(name)
        base = re.sub(r"\s*\(.*$", "", name).strip().lower()
        if base in _NOVELTY:
            continue
        q = _quality(name)
        rank = {"premium": 0, "enhanced": 1}.get(q, 2 if base in _GOOD_COMPACT[prefix] else 3)
        out.append({"name": name, "lang": m["lang"], "quality": q, "rank": rank})
    out.sort(key=lambda v: (v["rank"], _GOOD_COMPACT[prefix].index(re.sub(r"\s*\(.*$", "", v["name"]).lower())
                            if re.sub(r"\s*\(.*$", "", v["name"]).lower() in _GOOD_COMPACT[prefix] else 99, v["name"]))
    return out


def _system_voice(ws: Any, language: str) -> dict[str, Any] | None:
    voices = system_voices(language)
    chosen = settings(ws)["system_voice"]
    return next((v for v in voices if v["name"] == chosen), None) or (voices[0] if voices else None)


def tts_engine(ws: Any, language: str = "it") -> str:
    pick = settings(ws)["tts"]
    if pick == "openai" and _key(ws, "openai"):
        return "openai"
    if pick == "system":
        return "system" if shutil.which("say") else "device"
    # auto: the Mac's own neural voice when one is installed (local, free); a natural cloud voice only when the user has an
    # OpenAI key AND no good local voice; otherwise the best local voice there is
    say = shutil.which("say")
    if say and ((_system_voice(ws, language) or {}).get("quality") in ("premium", "enhanced")):
        return "system"
    if _key(ws, "openai"):
        return "openai"
    return "system" if say and system_voices(language) else "device"


def status(ws: Any, language: str = "it") -> dict[str, Any]:
    voices = system_voices(language)
    cfg = settings(ws)
    best = _system_voice(ws, language)
    tts = tts_engine(ws, language)
    return {
        "settings": cfg,
        "stt": {"engine": stt_engine(ws), "available": ["device"] + [p for p in ("groq", "openai") if _key(ws, p)],
                "model": STT_MODELS.get(stt_engine(ws), "")},
        "tts": {"engine": tts, "available": (["system"] if voices else []) + (["openai"] if _key(ws, "openai") else []),
                "voice": (best or {}).get("name", "") if tts == "system" else cfg["openai_voice"],
                "quality": "cloud" if tts == "openai" else (best or {}).get("quality", "none"),
                "voices": [{"name": v["name"], "quality": v["quality"]} for v in voices[:12]],
                "openai_voices": list(OPENAI_VOICES),
                "needs_better_voice": tts == "system" and (best or {}).get("quality", "basic") == "basic"},
    }


# -- ledger ----------------------------------------------------------------------------------------------------------------
def _record(ws: Any, provider: str, model: str, purpose: str, chars: int, status_: str = "ok", error_kind: str | None = None) -> None:
    try:
        from aether.privacy.audit import ledger_for

        ledger = ledger_for(ws)
        if ledger is not None:
            ledger.record(provider=provider, model=model, local=False, workspace_id=getattr(ws, "id", None), purpose=purpose,
                          messages=1, chars=chars, status=status_, error_kind=error_kind)
    except Exception:  # noqa: BLE001 - the ledger must never block the voice
        logger.debug("voice ledger write failed", exc_info=True)


def _http(req: urllib.request.Request, timeout: float = 30) -> bytes:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https provider URLs
            return r.read()
    except urllib.error.HTTPError as e:
        body = e.read()[:400].decode("utf-8", "replace")
        raise VoiceError("provider_error", f"{e.code}: {body}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise VoiceError("network", type(e).__name__) from None


# -- hearing ---------------------------------------------------------------------------------------------------------------
_EXT = {"audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3"}


def transcribe(ws: Any, audio: bytes, mime: str = "audio/mp4", language: str = "it") -> dict[str, Any]:
    engine = stt_engine(ws)
    if engine == "device":
        raise VoiceError("use_device")
    if not audio:
        return {"text": "", "engine": engine}
    if len(audio) > MAX_AUDIO_BYTES:
        raise VoiceError("too_long")
    mime = (mime or "audio/mp4").split(";")[0].strip().lower()
    ext = _EXT.get(mime, "m4a")
    model = STT_MODELS[engine]
    boundary = uuid.uuid4().hex
    lang = "it" if str(language).lower().startswith("it") else "en"
    fields = {"model": model, "language": lang, "response_format": "json", "temperature": "0"}
    body = b"".join(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode() for k, v in fields.items())
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"voice.{ext}\"\r\nContent-Type: {mime}\r\n\r\n".encode()
    body += audio + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(STT_URLS[engine], data=body, method="POST", headers={
        "Authorization": f"Bearer {_key(ws, engine)}", "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "Aether"})
    t0 = time.time()
    try:
        data = json.loads(_http(req) or b"{}")
    except VoiceError as e:
        _record(ws, engine, model, "voice_transcription", 0, "error", e.code)
        raise
    text = re.sub(r"\s+", " ", str(data.get("text") or "")).strip()
    _record(ws, engine, model, "voice_transcription", len(text))
    return {"text": text, "engine": engine, "model": model, "seconds": round(time.time() - t0, 2)}


# -- speaking --------------------------------------------------------------------------------------------------------------
def _clean(text: str) -> str:
    t = re.sub(r"```[\s\S]*?```", " ", text or "")
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"\*\*|__|\*|(?<!\w)_|_(?!\w)", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()[:MAX_SPEAK_CHARS]


def synthesize(ws: Any, text: str, language: str = "it", voice: str | None = None, engine: str | None = None) -> tuple[bytes, str]:
    """Returns (audio bytes, mime type). `voice`/`engine` let Settings preview a voice before choosing it."""
    clean = _clean(text)
    if not clean:
        raise VoiceError("empty")
    engine = engine or tts_engine(ws, language)
    if engine == "openai":
        if not _key(ws, "openai"):
            raise VoiceError("no_key")
        it = str(language).lower().startswith("it")
        payload = {"model": OPENAI_TTS_MODEL, "voice": voice if voice in OPENAI_VOICES else settings(ws)["openai_voice"], "input": clean,
                   "response_format": "mp3",
                   "instructions": ("Parla in italiano naturale, caldo e sicuro, come un assistente personale; ritmo scorrevole."
                                    if it else "Speak naturally, warm and confident, like a personal assistant; brisk pace.")}
        req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=json.dumps(payload).encode(), method="POST", headers={
            "Authorization": f"Bearer {_key(ws, 'openai')}", "Content-Type": "application/json", "User-Agent": "Aether"})
        try:
            audio = _http(req, timeout=45)
        except VoiceError as e:
            _record(ws, "openai", OPENAI_TTS_MODEL, "voice_speech", len(clean), "error", e.code)
            raise
        _record(ws, "openai", OPENAI_TTS_MODEL, "voice_speech", len(clean))
        return audio, "audio/mpeg"
    if engine == "system":
        say = shutil.which("say")
        if not say:
            raise VoiceError("use_device")
        chosen = next((v for v in system_voices(language) if v["name"] == voice), None) if voice else _system_voice(ws, language)
        with tempfile.TemporaryDirectory(prefix="aether-voice-") as d:
            src, out = Path(d) / "in.txt", Path(d) / "out.wav"
            src.write_text(clean, encoding="utf-8")  # through a file: the text never becomes a command-line argument
            cmd = [say, "-f", str(src), "-o", str(out), "--file-format=WAVE", "--data-format=LEI16@24000"]
            if chosen:
                cmd[1:1] = ["-v", chosen["name"]]
            try:
                subprocess.run(cmd, capture_output=True, timeout=60, check=True)
                return out.read_bytes(), "audio/wav"
            except (OSError, subprocess.SubprocessError) as e:
                raise VoiceError("system_voice_failed", type(e).__name__) from None
    raise VoiceError("use_device")
