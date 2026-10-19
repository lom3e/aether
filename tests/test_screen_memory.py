"""'Remember this screen': one previewed capture becomes a short expiring text note; the image is never stored."""
from __future__ import annotations

import asyncio
import base64
import sqlite3
import struct
import time
import zlib
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from aether.knowledge.screen_memory import ScreenMemory, screen_memory_for
from aether.providers.mock import MockProvider
from aether.providers.types import ProviderConfig
from aether.server.app import app
from aether.server.routes import ScreenRememberPayload, companion_vision_remember_route, screen_memory_forget_route, screen_memory_list_route
from aether.workspace.workspace import Workspace


def _png_b64(w=120, h=80) -> str:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x30\x60\x90" * w for _ in range(h))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    return base64.b64encode(png).decode()


@pytest.fixture
def ws(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    w = Workspace.init(tmp_path / "ws", name="Screen Memory")
    app.state.workspace = w
    yield w
    w.close()


def _req(method="POST", path="/api/personal/companion/vision/remember") -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": [], "app": app})


def test_a_note_is_stored_searchable_and_forgotten_with_verification(ws):
    mem = screen_memory_for(ws)
    item = mem.remember("Invoice page of ACME, total 1,240.00 EUR due on 5 November.", ttl_days=7, title="ACME invoice", workspace_id=ws.id)
    assert item["expires_at"] - item["created_at"] == pytest.approx(7 * 86400, abs=2)
    chunks = ws.knowledge.get_by_source(item["source"])
    assert chunks and "ACME" in chunks[0].content
    assert [i["id"] for i in mem.list()] == [item["id"]]
    res = mem.forget(item["id"])
    assert res["verified_gone"] is True and ws.knowledge.get_by_source(item["source"]) == [] and mem.list() == []
    assert mem.forget(item["id"])["reason"] == "not_found"


def test_only_7_or_30_days_and_never_an_empty_note(ws):
    mem = screen_memory_for(ws)
    for bad in (0, 1, 365):
        with pytest.raises(ValueError):
            mem.remember("x", ttl_days=bad)
    with pytest.raises(ValueError):
        mem.remember("   ", ttl_days=7)


def test_expired_notes_are_removed_from_text_and_record(ws):
    mem = screen_memory_for(ws)
    keep = mem.remember("keep me", ttl_days=30)
    old = mem.remember("old note about a login page", ttl_days=7)
    with sqlite3.connect(mem.path) as c:
        c.execute("UPDATE screen_memories SET expires_at=? WHERE id=?", (time.time() - 5, old["id"]))
    assert mem.sweep() == 1
    assert ws.knowledge.get_by_source(old["source"]) == [] and ws.knowledge.get_by_source(keep["source"])
    assert [i["id"] for i in mem.list()] == [keep["id"]]


def test_route_needs_a_vision_model_and_stores_text_only(ws):
    ws.personal.runtime.provider = MockProvider(config=ProviderConfig(model="llama-3.3-70b-versatile"), responses=["x"])
    out = asyncio.run(companion_vision_remember_route(_req(), ScreenRememberPayload(image_base64=_png_b64())))
    assert out["status"] == "unavailable" and out["reason"] == "model_without_vision" and screen_memory_for(ws).list() == []

    seen = MockProvider(config=ProviderConfig(model="gpt-4o"), responses=["Settings page of the app, dark theme, language set to Italian."], vision=True)
    ws.personal.runtime.provider = seen
    image = _png_b64()
    out = asyncio.run(companion_vision_remember_route(_req(), ScreenRememberPayload(image_base64=image, ttl_days=30, language="en")))
    assert out["status"] == "ok" and out["item"]["id"].startswith("scr-")
    assert seen.calls[0][-1].images, "the vision model really received the image"
    items = asyncio.run(screen_memory_list_route(_req("GET", "/api/screen-memory")))["items"]
    assert len(items) == 1
    for db in (Path(ws.conversations_db_path).parent).glob("*.db"):
        assert image.encode()[:60] not in db.read_bytes() and b"\x89PNG" not in db.read_bytes(), f"{db.name} must not hold the image"
    res = asyncio.run(screen_memory_forget_route(_req("DELETE", "/api/screen-memory/x"), out["item"]["id"]))
    assert res["verified_gone"] is True
    with pytest.raises(HTTPException) as e:
        asyncio.run(screen_memory_forget_route(_req("DELETE", "/api/screen-memory/x"), out["item"]["id"]))
    assert e.value.status_code == 404


def test_bad_ttl_and_bad_image_are_rejected(ws):
    ws.personal.runtime.provider = MockProvider(config=ProviderConfig(model="gpt-4o"), vision=True)
    with pytest.raises(HTTPException) as e:
        asyncio.run(companion_vision_remember_route(_req(), ScreenRememberPayload(image_base64=_png_b64(), ttl_days=3)))
    assert e.value.status_code == 422 and e.value.detail["code"] == "bad_ttl"
    with pytest.raises(HTTPException) as e2:
        asyncio.run(companion_vision_remember_route(_req(), ScreenRememberPayload(image_base64="@@@")))
    assert e2.value.status_code == 422 and e2.value.detail["code"] == "bad_base64"
