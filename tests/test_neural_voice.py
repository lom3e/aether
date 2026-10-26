"""Aether's natural voice (Kokoro on the Mac): espeak runs as a separate program with the text on stdin, punctuation survives
for the model's pauses, our own name is said right, the model is downloaded once and checked against its hash, and the voice
is picked automatically only once it is ready."""
from __future__ import annotations

import hashlib
import http.server
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from aether.personal import neural_voice as nv
from aether.personal import voice_engine as ve


@pytest.fixture
def fake_espeak(tmp_path, monkeypatch):
    """A stand-in espeak-ng: records argv and stdin, answers with fixed IPA."""
    log = tmp_path / "calls.txt"
    prog = tmp_path / "espeak-ng"
    prog.write_text(f"#!/bin/sh\necho \"$@\" >> '{log}'\ncat >> '{log}'\necho '---' >> '{log}'\necho 'tʃˈao (en)wˈɜːld(it) 123'\n")
    prog.chmod(0o755)
    monkeypatch.setenv("AETHER_ESPEAK_NG", str(prog))
    return log


def test_phonemes_keep_punctuation_and_text_stays_off_the_command_line(fake_espeak):
    out = nv.phonemize("Ciao mondo, come stai? Bene!", "it")
    assert out == "tʃˈao wˈɜːld, tʃˈao wˈɜːld? tʃˈao wˈɜːld!"  # language marks and digits (not in the vocabulary) dropped
    calls = fake_espeak.read_text()
    assert "-q --ipa -v it" in calls
    assert "Ciao mondo" in calls.split("---")[0].splitlines()[1]  # on stdin, not in argv
    assert not any("Ciao" in line and "--ipa" in line for line in calls.splitlines())


def test_name_and_round_hours_are_read_right():
    assert nv._normalize("Sono Aether, alle 18:00 e alle 9:30.", "it") == "Sono Ìter, alle 18 e alle 9:30."
    assert nv._normalize("I'm Aether at 18:00.", "en") == "I'm Aether at 18:00."


def test_long_phonemes_are_cut_after_punctuation():
    text = ("a" * 300 + ", ") + ("b" * 300 + ".")
    parts = nv._batches(text)
    assert len(parts) == 2 and parts[0].endswith(",") and all(len(p) <= nv.MAX_TOKENS for p in parts)
    assert all(len(p) <= nv.MAX_TOKENS for p in nv._batches("c" * 1200))


def test_voices_per_language_and_default():
    assert [v["name"] for v in nv.voices("it")] == ["Sara", "Nicola"]
    assert nv.voice_for("it", "im_nicola") == "im_nicola"
    assert nv.voice_for("it", "af_heart") == "if_sara"  # an English voice never reads Italian
    assert nv.voice_for("en") == "af_heart"


def test_unavailable_without_espeak(monkeypatch):
    monkeypatch.setattr(nv, "espeak", lambda: None)
    assert nv.state() == "unavailable"


@pytest.fixture
def model_server(tmp_path, monkeypatch):
    files = {"m.onnx": b"model-bytes" * 100, "v.bin": b"voices" * 50}
    root = tmp_path / "srv"
    root.mkdir()
    for name, data in files.items():
        (root / name).write_bytes(data)

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(root), **kw)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(nv, "_BASE", f"http://127.0.0.1:{srv.server_address[1]}/")
    monkeypatch.setattr(nv, "FILES", {k: {"name": n, "size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
                                      for k, (n, d) in zip(("model", "voices"), files.items())})
    monkeypatch.setattr(nv, "DOWNLOAD_BYTES", sum(len(d) for d in files.values()))
    monkeypatch.setattr(nv, "model_dir", lambda: tmp_path / "voices" / "kokoro")
    nv._dl.update(state="idle", done=0, error="", cancel=False)
    yield root
    srv.shutdown()


def _wait(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end and not pred():
        time.sleep(0.02)
    return pred()


def test_download_verifies_the_hash_and_installs(model_server):
    assert not nv.installed()
    nv.start_download()
    assert _wait(lambda: nv._dl["state"] != "downloading")
    assert nv.download_status()["state"] == "ready" and nv.installed()
    assert not list(nv.model_dir().glob("*.part"))
    nv.remove()
    assert not nv.installed()


def test_a_tampered_file_is_refused(model_server, monkeypatch):
    bad = dict(nv.FILES)
    bad["model"] = {**bad["model"], "sha256": "0" * 64}
    monkeypatch.setattr(nv, "FILES", bad)
    nv.start_download()
    assert _wait(lambda: nv._dl["state"] != "downloading")
    st = nv.download_status()
    assert (st["state"], st["error"]) == ("error", "checksum")
    assert not nv.installed() and not (nv.model_dir() / bad["model"]["name"]).exists()


@pytest.fixture
def ws(tmp_path, monkeypatch):
    for k in ("GROQ_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    return SimpleNamespace(id="w", conversations_db_path=str(tmp_path / "c.db"), secret_store=None)


def test_the_natural_voice_is_used_once_ready_and_can_be_chosen(ws, monkeypatch):
    monkeypatch.setattr(nv, "state", lambda: "missing")
    assert ve.tts_engine(ws, "it") != "neural"
    assert ve.status(ws, "it")["tts"]["neural"]["state"] == "missing"
    monkeypatch.setattr(nv, "state", lambda: "ready")
    assert ve.tts_engine(ws, "it") == "neural"
    ve.update_settings(ws, tts="neural", neural_voice="im_nicola")
    st = ve.status(ws, "it")
    assert st["tts"]["engine"] == "neural" and st["tts"]["voice"] == "im_nicola" and st["tts"]["quality"] == "natural"
    assert "neural" in st["tts"]["available"] and not st["tts"]["needs_better_voice"]
    with pytest.raises(ValueError):
        ve.update_settings(ws, neural_voice="zz_nobody")

    seen = {}

    def fake_synth(text, language, voice):
        seen.update(text=text, voice=voice)
        return b"RIFFwav"

    monkeypatch.setattr(nv, "synthesize", fake_synth)
    assert ve.synthesize(ws, "**Ciao** Matteo", "it") == (b"RIFFwav", "audio/wav")
    assert seen == {"text": "Ciao Matteo", "voice": "im_nicola"}


def test_a_failing_natural_voice_falls_back_to_the_device(ws, monkeypatch):
    monkeypatch.setattr(nv, "state", lambda: "ready")

    def boom(*a, **kw):
        raise nv.NeuralVoiceError("not_installed")

    monkeypatch.setattr(nv, "synthesize", boom)
    with pytest.raises(ve.VoiceError) as e:
        ve.synthesize(ws, "Ciao", "it")
    assert e.value.code == "use_device"


def test_real_model_speaks(monkeypatch):  # pragma: no cover - only where the model is installed (AETHER_TEST_VOICE_DIR)
    import os

    d = os.environ.get("AETHER_TEST_VOICE_DIR", "")
    if not d or nv.espeak() is None:
        pytest.skip("the real model is not downloaded on this machine")
    monkeypatch.setattr(nv, "model_dir", lambda: Path(d))
    monkeypatch.setattr(nv, "_engine", None)
    wav = nv.synthesize("Ciao, sono Aether.", "it")
    assert wav[:4] == b"RIFF" and len(wav) > 24000
