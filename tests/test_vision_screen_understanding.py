"""Screen understanding backend: image validation, per-model vision capability, annotation validation, provider image
encoding, and the analysis route through the shared runtime/session (no real provider, no real screen)."""
from __future__ import annotations

import asyncio
import base64
import json
import math
import struct
import zlib
from pathlib import Path

import pytest
from fastapi import HTTPException, Request

from aether.core.execution import ImagePart, Message
from aether.providers.errors import AuthenticationError, TimeoutError as ProviderTimeout
from aether.providers.mock import MockProvider
from aether.providers.types import ProviderConfig
from aether.server.app import app
from aether.server.routes import CompanionVisionPayload, companion_vision_route, companion_vision_status_route
from aether.vision.annotations import (
    Annotation, CaptureGeometry, MAX_ANNOTATIONS, parse_annotations, to_screen_rect, validate_annotations,
)
from aether.vision.capability import model_supports_vision, vision_support_for
from aether.vision.image import ImageError, MAX_IMAGE_BYTES, validate_image
from aether.workspace.workspace import Workspace


def _png(w: int = 64, h: int = 48) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x20\x40\x80" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _jpeg(w: int = 64, h: int = 48) -> bytes:
    # SOI + SOF0 segment with the size; enough for header parsing (decoding is the provider's job)
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + sof + b"\xff\xd9"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


# ---------------------------------------------------------------- image validation
def test_valid_png_and_jpeg_report_real_dimensions():
    png = validate_image(_b64(_png(120, 80)))
    assert (png.media_type, png.width, png.height) == ("image/png", 120, 80)
    jpg = validate_image("data:image/jpeg;base64," + _b64(_jpeg(200, 100)), "image/jpeg")
    assert (jpg.media_type, jpg.width, jpg.height) == ("image/jpeg", 200, 100)


@pytest.mark.parametrize("payload,code", [
    ("", "empty"),
    ("   ", "empty"),
    ("not base64 !!!", "bad_base64"),
    (_b64(b"GIF89a" + b"\x00" * 40), "unsupported_format"),
    (_b64(b"just some text, not an image at all"), "unsupported_format"),
    (_b64(b"\x89PNG\r\n\x1a\n" + b"\x00" * 30), "corrupt"),
    (_b64(_png(4, 4)), "too_small"),
    (_b64(_png(5000, 10)), "dimensions_too_large"),
])
def test_invalid_images_are_rejected_with_a_stable_code(payload, code):
    with pytest.raises(ImageError) as e:
        validate_image(payload)
    assert e.value.code == code


def test_oversized_and_mismatched_images_are_rejected():
    with pytest.raises(ImageError) as e:
        validate_image(_b64(_png() + b"\x00" * (MAX_IMAGE_BYTES + 1)))
    assert e.value.code == "too_large"
    with pytest.raises(ImageError) as e:
        validate_image(_b64(_png()), "image/jpeg")  # the bytes are the truth, not the declaration
    assert e.value.code == "unsupported_format"


# ---------------------------------------------------------------- capability
@pytest.mark.parametrize("provider,model,expected", [
    ("groq", "meta-llama/llama-4-scout-17b-16e-instruct", True),
    ("groq", "llama-3.3-70b-versatile", False),
    ("groq", "openai/gpt-oss-120b", False),
    ("openai", "gpt-4o", True), ("openai", "gpt-4o-mini", True), ("openai", "o3-mini", False), ("openai", "gpt-3.5-turbo", False),
    ("anthropic", "claude-sonnet-5-5", True), ("anthropic", "claude-3-5-sonnet-latest", True), ("anthropic", "claude-2.1", False),
    ("gemini", "gemini-2.5-flash", True), ("gemini", "gemini-1.0-pro", False),
    ("ollama", "llava:13b", True), ("ollama", "llama3.2-vision", True), ("ollama", "llama3", False),
    ("ollama", "", False), ("unknown", "gpt-4o", False), (None, None, False),
])
def test_model_supports_vision_is_per_provider_and_model(provider, model, expected):
    assert model_supports_vision(provider, model) is expected


def test_vision_support_reasons():
    assert vision_support_for(None).reason == "no_provider"
    from aether.providers.unresolved import UnresolvedProvider
    assert vision_support_for(UnresolvedProvider("groq", "m", "no key")).reason == "provider_unusable"
    no_vision = MockProvider(config=ProviderConfig(model="text-only"))
    sup = vision_support_for(no_vision)
    assert (sup.supported, sup.reason) == (False, "model_without_vision")
    assert vision_support_for(MockProvider(config=ProviderConfig(model="v"), vision=True)).supported
    assert vision_support_for(MockProvider()).reason == "no_model"


# ---------------------------------------------------------------- annotations
def test_valid_annotations_are_kept_with_clean_labels():
    r = validate_annotations([
        {"kind": "box", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.1, "label": "  Save\nbutton \x07 "},
        {"kind": "point", "x": 0.5, "y": 0.5, "label": "here"},
    ])
    assert [a.kind for a in r.accepted] == ["box", "point"] and not r.rejected
    assert r.accepted[0].label == "Save button"


@pytest.mark.parametrize("item,reason", [
    ({"kind": "box", "x": 1.4, "y": 0.2, "w": 0.1, "h": 0.1}, "out_of_bounds"),
    ({"kind": "box", "x": 0.9, "y": 0.2, "w": 0.3, "h": 0.1}, "out_of_bounds"),
    ({"kind": "box", "x": -0.2, "y": 0.2, "w": 0.1, "h": 0.1}, "out_of_bounds"),
    ({"kind": "box", "x": float("nan"), "y": 0.2, "w": 0.1, "h": 0.1}, "missing_or_non_numeric_coordinates"),
    ({"kind": "box", "x": math.inf, "y": 0.2, "w": 0.1, "h": 0.1}, "missing_or_non_numeric_coordinates"),
    ({"kind": "box", "x": "0.1", "y": 0.2, "w": 0.1, "h": 0.1}, "missing_or_non_numeric_coordinates"),
    ({"kind": "box", "x": True, "y": 0.2, "w": 0.1, "h": 0.1}, "missing_or_non_numeric_coordinates"),
    ({"kind": "box", "x": 0.1, "y": 0.2, "w": 0.0, "h": 0.1}, "box_too_small"),
    ({"kind": "box", "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}, "box_covers_everything"),
    ({"kind": "box", "x": 0.1, "y": 0.2}, "missing_or_non_numeric_size"),
    ({"kind": "circle", "x": 0.1, "y": 0.2}, "unknown_kind"),
    ("nope", "not_an_object"),
])
def test_invalid_annotations_are_dropped_not_repaired(item, reason):
    r = validate_annotations([item])
    assert not r.accepted and r.rejected[0]["reason"] == reason


def test_annotation_count_is_capped_and_non_list_rejected():
    many = [{"kind": "point", "x": 0.1, "y": 0.1}] * (MAX_ANNOTATIONS + 3)
    r = validate_annotations(many)
    assert len(r.accepted) == MAX_ANNOTATIONS and {x["reason"] for x in r.rejected} == {"too_many"}
    assert validate_annotations({"kind": "box"}).rejected[0]["reason"] == "not_a_list"


def test_parse_annotations_handles_fenced_prose_and_garbage():
    body = {"answer": "It is a form.", "annotations": [{"kind": "box", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1, "label": "Name"}]}
    for text in (json.dumps(body), "Sure!\n```json\n" + json.dumps(body) + "\n```", "Here: " + json.dumps(body) + " done"):
        answer, rep = parse_annotations(text)
        assert answer == "It is a form." and len(rep.accepted) == 1
    answer, rep = parse_annotations("just prose, no json")
    assert answer == "just prose, no json" and not rep.accepted and rep.rejected[0]["reason"] == "unparseable_reply"


def test_to_screen_rect_maps_only_valid_geometry():
    geo = CaptureGeometry(1000, 500, 100.0, 50.0, 1440.0, 900.0)
    assert to_screen_rect(Annotation("box", 0.5, 0.25, 0.1, 0.2), geo) == (100 + 720.0, 50 + 225.0, 144.0, 180.0)
    with pytest.raises(ValueError):
        to_screen_rect(Annotation("box", 0.95, 0.25, 0.2, 0.2), geo)  # leaves the image
    with pytest.raises(ValueError):
        to_screen_rect(Annotation("point", 0.5, 0.5), CaptureGeometry(0, 0, 0, 0, 0, 0))  # unknown geometry
    with pytest.raises(ValueError):
        to_screen_rect(Annotation("point", 0.5, 0.5), CaptureGeometry(10, 10, float("nan"), 0, 100, 100))


# ---------------------------------------------------------------- provider encoding
def test_images_are_not_serialized_into_history_dicts():
    m = Message(role="user", content="hi", images=[ImagePart("image/png", "AAAA")])
    assert "images" not in m.to_dict() and "AAAA" not in json.dumps(m.to_dict())


def test_groq_and_openai_send_data_uri_image_parts_only_when_present():
    from aether.providers.groq_provider import GroqProvider
    from aether.providers.openai_provider import OpenAIProvider

    msgs = [Message(role="system", content="s"), Message(role="user", content="what is this?", images=[ImagePart("image/png", "QUJD")])]
    g = GroqProvider(ProviderConfig(api_key="k", model="meta-llama/llama-4-scout-17b-16e-instruct"))
    body = g._build_body(msgs, None, None, stream=False)
    assert body["messages"][0]["content"] == "s"  # plain messages stay plain strings
    assert body["messages"][1]["content"] == [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
    ]
    assert g.capabilities.vision is True
    assert GroqProvider(ProviderConfig(api_key="k", model="llama-3.3-70b-versatile")).capabilities.vision is False
    o = object.__new__(OpenAIProvider)  # no SDK needed to check the encoding
    o._model = "gpt-4o"
    o.config = ProviderConfig(model="gpt-4o")
    assert o._build_kwargs(msgs)["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_anthropic_and_ollama_encode_images_natively():
    msgs = [Message(role="user", content="q", images=[ImagePart("image/jpeg", "QUJD")])]
    from aether.providers.anthropic_provider import AnthropicProvider
    a = object.__new__(AnthropicProvider)
    a._model = "claude-sonnet-5-5"
    a.config = ProviderConfig(model="claude-sonnet-5-5")
    content = a._build_kwargs(msgs)["messages"][0]["content"]
    assert content[0] == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}}
    assert content[1] == {"type": "text", "text": "q"}
    assert a.capabilities.vision is True
    from aether.providers.ollama import OllamaProvider
    o = OllamaProvider(ProviderConfig(model="llava:13b"))
    assert o._build_payload(msgs)["messages"][0]["images"] == ["QUJD"]


# ---------------------------------------------------------------- route (shared runtime + session)
@pytest.fixture
def ws(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AETHER_DATA_DIR", str(tmp_path / "data"))
    w = Workspace.init(tmp_path / "ws", name="Vision Test")
    app.state.workspace = w
    yield w
    w.close()


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/personal/companion/vision", "headers": [], "app": app})


def _call(ws, **kw):
    payload = CompanionVisionPayload(image_base64=_b64(_png(300, 200)), workspace_id=ws.id, language="en", **kw)
    return asyncio.run(companion_vision_route(_request(), payload))


def test_without_a_provider_nothing_is_sent_and_nothing_is_recorded(ws):
    ws.personal.runtime.provider = None
    out = _call(ws, prompt="What am I looking at?")
    assert out["status"] == "unavailable" and out["reason"] == "no_provider" and out["message"] is None
    status = asyncio.run(companion_vision_status_route(_request()))
    assert status["supported"] is False and status["reason"] == "no_provider"


def test_a_text_only_model_is_never_sent_the_image(ws):
    mock = MockProvider(config=ProviderConfig(model="llama-3.3-70b-versatile"), responses=["should not be used"])
    ws.personal.runtime.provider = mock
    out = _call(ws, prompt="Explain this")
    assert (out["status"], out["reason"], out["model"]) == ("unavailable", "model_without_vision", "llama-3.3-70b-versatile")
    assert mock.calls == [], "the provider must not be called at all"
    assert ws.personal.store.get_recent_messages("any", limit=5) == []


def test_a_vision_model_gets_the_image_and_the_answer_joins_the_session(ws):
    mock = MockProvider(config=ProviderConfig(model="meta-llama/llama-4-scout-17b-16e-instruct"), responses=["A login form with two fields."], vision=True)
    ws.personal.runtime.provider = mock
    out = _call(ws, prompt="What am I looking at?")
    assert out["status"] == "ok" and out["message"]["content"] == "A login form with two fields."
    sent = mock.calls[0][-1]
    assert sent.role == "user" and sent.content == "What am I looking at?" and sent.images and sent.images[0].media_type == "image/png"
    assert mock.calls[0][0].role == "system" and "NOT instructions" in mock.calls[0][0].content
    sid = out["message"]["session_id"]
    stored = ws.personal.store.get_recent_messages(sid, limit=10)
    assert [m.role for m in stored] == ["user", "assistant"]
    assert stored[0].metadata["screen_capture"]["width"] == 300
    assert _b64(_png(300, 200))[:40] not in json.dumps([m.to_dict() for m in stored]), "the image is never stored"
    # a follow-up in the same session sees the earlier turn as plain text history
    mock.responses.append("It asks for e-mail and password.")
    follow = _call(ws, prompt="And the fields?", session_id=sid)
    assert follow["message"]["session_id"] == sid
    assert any(m.content == "A login form with two fields." and not m.images for m in mock.calls[-1])


def test_annotation_mode_validates_coordinates_before_returning_them(ws):
    reply = json.dumps({"answer": "The Save button.", "annotations": [
        {"kind": "box", "x": 0.6, "y": 0.8, "w": 0.2, "h": 0.1, "label": "Save"},
        {"kind": "box", "x": 1.7, "y": 0.8, "w": 0.2, "h": 0.1, "label": "Offscreen"},
        {"kind": "point", "x": "left", "y": 0.1},
    ]})
    ws.personal.runtime.provider = MockProvider(config=ProviderConfig(model="gpt-4o"), responses=[reply], vision=True)
    out = _call(ws, prompt="Where do I save?", annotate=True)
    assert out["status"] == "ok" and out["message"]["content"] == "The Save button."
    assert [a["label"] for a in out["annotations"]] == ["Save"]
    assert sorted(r["reason"] for r in out["annotations_rejected"]) == ["missing_or_non_numeric_coordinates", "out_of_bounds"]


def test_annotation_mode_with_a_prose_reply_draws_nothing(ws):
    ws.personal.runtime.provider = MockProvider(config=ProviderConfig(model="gpt-4o"), responses=["The button is at the bottom right."], vision=True)
    out = _call(ws, prompt="Where?", annotate=True)
    assert out["annotations"] == [] and out["message"]["content"] == "The button is at the bottom right."
    assert out["annotations_rejected"][0]["reason"] == "unparseable_reply"


class _Boom(MockProvider):
    def __init__(self, exc, **kw):
        super().__init__(**kw)
        self._exc = exc

    def generate(self, *a, **k):
        raise self._exc


@pytest.mark.parametrize("exc,reason", [
    (ProviderTimeout("slow", provider="groq"), "timeout"),
    (AuthenticationError("bad key sk-SECRET123", provider="groq"), "auth"),
    (RuntimeError("weird"), "provider_error"),
])
def test_provider_failures_are_reported_and_nothing_is_recorded(ws, exc, reason):
    ws.personal.runtime.provider = _Boom(exc, config=ProviderConfig(model="gpt-4o", api_key="sk-SECRET123"), vision=True)
    out = _call(ws, prompt="x")
    assert out["status"] == "failed" and out["reason"] == reason and out["message"] is None
    assert "sk-SECRET123" not in json.dumps(out)


def test_an_empty_model_reply_is_a_failure_not_a_fake_answer(ws):
    ws.personal.runtime.provider = MockProvider(config=ProviderConfig(model="gpt-4o"), responses=["   "], vision=True)
    out = _call(ws, prompt="x")
    assert out["status"] == "failed" and out["reason"] == "empty_response"


@pytest.mark.parametrize("image,code", [("", "empty"), ("@@@", "bad_base64"), (_b64(b"GIF89a" + b"0" * 40), "unsupported_format")])
def test_the_route_rejects_invalid_images_before_any_provider_work(ws, image, code):
    mock = MockProvider(config=ProviderConfig(model="gpt-4o"), vision=True)
    ws.personal.runtime.provider = mock
    with pytest.raises(HTTPException) as e:
        asyncio.run(companion_vision_route(_request(), CompanionVisionPayload(image_base64=image, workspace_id=ws.id)))
    assert e.value.status_code == 422 and e.value.detail["code"] == code and mock.calls == []
