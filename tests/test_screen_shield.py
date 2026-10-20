"""Screen Shield: OCR words+boxes -> regions to hide, using the same detectors as outgoing-text masking."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from aether.privacy.screen_shield import find_regions
from aether.server.routes import ScreenShieldPayload, privacy_screen_shield_route

# Output of the real `aether-vision ocr` helper on a generated image (an invoice line, a tax code, a harmless sentence).
OCR = json.loads((Path(__file__).parent / "fixtures" / "ocr_invoice.json").read_text())


def _word(text, x, y, w=0.08, h=0.05):
    return {"text": text, "x": x, "y": y, "w": w, "h": h}


def test_real_ocr_output_hides_the_iban_and_the_tax_code_but_not_the_rest():
    out = find_regions(OCR["words"])
    kinds = sorted(r["kind"] for r in out["regions"])
    assert kinds == ["iban", "tax_id"], out
    iban = next(r for r in out["regions"] if r["kind"] == "iban")
    assert iban["x"] < 0.38 + 0.01 and iban["x"] + iban["w"] > 0.96 - 0.01 and 0.2 < iban["y"] < 0.24
    assert out["counts"] == {"iban": 1, "tax_id": 1} and out["total"] == 2


def test_an_iban_split_in_groups_by_the_ocr_is_covered_by_one_region():
    groups = ["IT60", "X054", "2811", "1010", "0000", "0123", "456"]
    words = [_word(g, 0.1 + i * 0.09, 0.3) for i, g in enumerate(groups)]
    out = find_regions(words)
    assert out["total"] == 1 and out["regions"][0]["kind"] == "iban"
    r = out["regions"][0]
    assert r["x"] <= 0.1 and r["x"] + r["w"] >= 0.1 + 6 * 0.09 + 0.08


def test_labels_and_opaque_tokens_are_hidden_without_a_known_pattern():
    words = [_word("password:", 0.1, 0.2), _word("hunter2", 0.25, 0.2), _word("Sessione", 0.1, 0.5), _word("a8F3kD9sLq2ZxV7bN4mP1tR6yU0wE5cH", 0.25, 0.5, 0.5)]
    out = find_regions(words)
    assert out["total"] == 2 and {r["kind"] for r in out["regions"]} == {"secret"}
    harmless = find_regions([_word("Ciao,", 0.1, 0.2), _word("il", 0.2, 0.2), _word("totale", 0.25, 0.2), _word("120", 0.4, 0.2), _word("euro", 0.5, 0.2)])
    assert harmless["total"] == 0


def test_malformed_words_are_ignored_and_the_route_is_local():
    bad = [{"text": "IBAN"}, {"text": "x", "x": "a", "y": 0, "w": 1, "h": 1}, {"text": "", "x": 0, "y": 0, "w": 0.1, "h": 0.1}, {"text": "ok", "x": 9, "y": 0, "w": 0.1, "h": 0.1}]
    assert find_regions(bad)["total"] == 0
    out = asyncio.run(privacy_screen_shield_route(ScreenShieldPayload(words=OCR["words"])))
    assert out["total"] == 2
