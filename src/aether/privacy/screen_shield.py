"""Screen Shield: which regions of a screenshot must be hidden before it leaves the computer.

Input is what the local OCR (the bundled `aether-vision` helper) read: words with boxes normalised to the image (0..1, origin
top-left). The words are joined into lines of text, the SAME detectors that mask outgoing text (`find_sensitive`) run on them,
and each finding is mapped back to the boxes of the words it covers. Pure and local: nothing here reads an image or the network.

Honest limits: OCR + patterns. It misses names, addresses, handwriting and anything the OCR cannot read; the user can add a
blur by hand or send the image unmasked for one request.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from aether.privacy.redaction import find_sensitive

MAX_WORDS = 6000
PAD = 0.004  # normalised padding around a hidden word, so the glyph edges are covered too

# A label that announces a secret on the SAME line: the next token is hidden whatever it looks like.
_LABELS = re.compile(r"^(?:password|passwd|pwd|pin|cvv|cvc|cvv2|otp|token|secret|segreto|puk)[:=]?$", re.I)
# Long opaque strings (hex / base64 / mixed-case-digit tokens) are almost always keys, hashes or session ids.
_OPAQUE = re.compile(r"^(?=[A-Za-z0-9+/_\-=]{28,}$)(?=.*[A-Za-z])(?=.*\d)")


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return {"x": round(self.x, 5), "y": round(self.y, 5), "w": round(self.w, 5), "h": round(self.h, 5), "kind": self.kind}


def _clean(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for w in words[:MAX_WORDS]:
        try:
            text = str(w["text"])
            x, y, bw, bh = (float(w[k]) for k in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError):
            continue
        if text.strip() and all(0.0 <= v <= 1.5 for v in (x, y, bw, bh)) and bw > 0 and bh > 0:
            out.append({"text": text, "x": x, "y": y, "w": bw, "h": bh})
    return out


def _lines(words: list[dict[str, Any]]) -> list[list[int]]:
    """Indices of words grouped into reading lines (similar vertical centre), left to right."""
    order = sorted(range(len(words)), key=lambda i: (words[i]["y"] + words[i]["h"] / 2, words[i]["x"]))
    lines: list[list[int]] = []
    for i in order:
        cy = words[i]["y"] + words[i]["h"] / 2
        if lines:
            last = lines[-1][-1]
            ly = words[last]["y"] + words[last]["h"] / 2
            if abs(cy - ly) <= max(words[i]["h"], words[last]["h"]) * 0.6:
                lines[-1].append(i)
                continue
        lines.append([i])
    return [sorted(line, key=lambda j: words[j]["x"]) for line in lines]


def _rect_for(words: list[dict[str, Any]], idx: list[int], kind: str) -> Rect:
    x0 = min(words[i]["x"] for i in idx) - PAD
    y0 = min(words[i]["y"] for i in idx) - PAD
    x1 = max(words[i]["x"] + words[i]["w"] for i in idx) + PAD
    y1 = max(words[i]["y"] + words[i]["h"] for i in idx) + PAD
    x0, y0 = max(0.0, x0), max(0.0, y0)
    return Rect(x0, y0, min(1.0, x1) - x0, min(1.0, y1) - y0, kind)


def find_regions(raw_words: list[dict[str, Any]]) -> dict[str, Any]:
    words = _clean(raw_words)
    rects: list[Rect] = []
    for line in _lines(words):
        text, spans = "", []  # spans[k] = (start, end) of word line[k] inside `text`
        for i in line:
            if text:
                text += " "
            spans.append((len(text), len(text) + len(words[i]["text"])))
            text += words[i]["text"]
        covered: set[int] = set()
        for f in find_sensitive(text):
            idx = [line[k] for k, (s, e) in enumerate(spans) if s < f.end and f.start < e]
            if idx:
                rects.append(_rect_for(words, idx, f.kind))
                covered.update(idx)
        for k, i in enumerate(line):
            if i in covered:
                continue
            tok = words[i]["text"]
            if _OPAQUE.match(tok):
                rects.append(_rect_for(words, [i], "secret"))
            elif k > 0 and _LABELS.match(words[line[k - 1]]["text"]) and k < len(line):
                rects.append(_rect_for(words, [i], "secret"))
    counts: dict[str, int] = {}
    for r in rects:
        counts[r.kind] = counts.get(r.kind, 0) + 1
    return {"regions": [r.to_dict() for r in rects], "counts": counts, "total": len(rects), "words": len(words)}
