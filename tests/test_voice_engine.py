"""Aether's voice: Whisper with the user's key when there is one (else the Mac's dictation), the best installed Mac voice
(novelty voices never), OpenAI's voice only with a key, every cloud call in the privacy ledger, and the text of an answer
never on a command line."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from aether.personal import voice_engine as ve

LISTING = """Albert              en_US    # Hello! My name is Albert.
Alice (Italiano (Italia)) it_IT    # Ciao! Mi chiamo Alice.
Eddy (Italiano (Italia)) it_IT    # Ciao! Mi chiamo Eddy.
Federica (Premium)  it_IT    # Ciao! Mi chiamo Federica.
Luca                it_IT    # Ciao! Mi chiamo Luca.
Samantha            en_US    # Hello! My name is Samantha.
Zoe (Enhanced)      en_US    # Hello! My name is Zoe.
Bad News            en_US    # Hello! My name is Bad News.
"""


class Secrets:
    def __init__(self, keys):
        self.keys = keys

    def get_secret(self, name):
        return self.keys.get(name.split(":", 1)[1])


class Ledger:
    def __init__(self):
        self.rows = []

    def record(self, **kw):
        self.rows.append(kw)


@pytest.fixture
def ws(tmp_path, monkeypatch):
    for k in ("GROQ_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    ledger = Ledger()
    monkeypatch.setattr("aether.privacy.audit.ledger_for", lambda w: ledger)
    monkeypatch.setattr(ve.neural_voice, "state", lambda: "missing")  # the natural voice is covered in test_neural_voice
    w = SimpleNamespace(id="w", conversations_db_path=str(tmp_path / "c.db"), secret_store=Secrets({}), ledger=ledger)
    return w


def test_only_good_voices_are_offered_never_basic_or_novelty_ones():
    it = ve.system_voices("it", LISTING)
    assert [v["name"] for v in it] == ["Federica (Premium)"]
    en = ve.system_voices("en", LISTING)
    assert [v["name"] for v in en] == ["Zoe (Enhanced)"]


def test_hearing_uses_whisper_with_a_key_and_the_mac_without(ws, monkeypatch):
    assert ve.stt_engine(ws) == "device"
    with pytest.raises(ve.VoiceError) as e:
        ve.transcribe(ws, b"abc", "audio/mp4", "it")
    assert e.value.code == "use_device"
    ws.secret_store.keys["groq"] = "gsk_test"
    sent = {}

    def fake_http(req, timeout=30):
        sent.update(url=req.full_url, auth=req.headers["Authorization"], body=req.data, ctype=req.headers["Content-type"])
        return json.dumps({"text": "  Ricordami di chiamare   Rossi alle 10. "}).encode()

    monkeypatch.setattr(ve, "_http", fake_http)
    out = ve.transcribe(ws, b"AUDIO", "audio/mp4;codecs=mp4a", "it")
    assert out["text"] == "Ricordami di chiamare Rossi alle 10." and out["engine"] == "groq"
    assert sent["url"].startswith("https://api.groq.com/") and sent["auth"] == "Bearer gsk_test"
    assert b"whisper-large-v3-turbo" in sent["body"] and b'name="language"\r\n\r\nit' in sent["body"] and b"AUDIO" in sent["body"]
    assert ws.ledger.rows[-1]["purpose"] == "voice_transcription" and ws.ledger.rows[-1]["provider"] == "groq"
    assert "gsk_test" not in json.dumps(ws.ledger.rows)
    ve.update_settings(ws, stt="device")
    assert ve.stt_engine(ws) == "device", "the user can keep the voice on the Mac"
    with pytest.raises(ValueError):
        ve.update_settings(ws, stt="somewhere")


def test_speaking_picks_the_installed_voice_and_passes_text_through_a_file(ws, monkeypatch):
    monkeypatch.setattr(ve, "_say_listing", lambda: LISTING)
    monkeypatch.setattr(ve.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        out = cmd[cmd.index("-o") + 1]
        open(out, "wb").write(b"RIFF....WAVE")
        assert open(cmd[cmd.index("-f") + 1], encoding="utf-8").read() == "Hai promesso a Mario il preventivo."
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ve.subprocess, "run", fake_run)
    audio, mime = ve.synthesize(ws, "Hai promesso a **Mario** il preventivo.", "it")
    assert mime == "audio/wav" and audio.startswith(b"RIFF")
    assert calls[0][1:3] == ["-v", "Federica (Premium)"] and "Mario" not in " ".join(calls[0])
    assert ve.tts_engine(ws, "it") == "system" and ws.ledger.rows == [], "a local voice sends nothing anywhere"
    st = ve.status(ws, "it")
    assert st["tts"]["voice"] == "Federica (Premium)" and st["tts"]["needs_better_voice"] is False


def test_basic_voice_only_suggests_a_better_one_and_openai_needs_a_key(ws, monkeypatch):
    monkeypatch.setattr(ve, "_say_listing", lambda: "Alice (Italiano (Italia)) it_IT    # Ciao!\n")
    monkeypatch.setattr(ve.shutil, "which", lambda name: f"/usr/bin/{name}")
    st = ve.status(ws, "it")
    assert st["tts"]["engine"] == "device" and st["tts"]["voices"] == [] and st["tts"]["needs_better_voice"] is True
    with pytest.raises(ve.VoiceError) as e:
        ve.synthesize(ws, "Ciao", "it", engine="openai")
    assert e.value.code == "no_key"
    ws.secret_store.keys["openai"] = "sk-test"
    assert ve.tts_engine(ws, "it") == "openai", "with only a basic Mac voice, a natural voice is used when there is a key"
    seen = {}
    monkeypatch.setattr(ve, "_http", lambda req, timeout=30: seen.update(body=json.loads(req.data)) or b"ID3mp3")
    audio, mime = ve.synthesize(ws, "Ciao **Matteo**", "it")
    assert mime == "audio/mpeg" and seen["body"]["input"] == "Ciao Matteo" and seen["body"]["voice"] == "coral"
    assert ws.ledger.rows[-1]["purpose"] == "voice_speech" and ws.ledger.rows[-1]["chars"] == len("Ciao Matteo")
