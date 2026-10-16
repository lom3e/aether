"""
Annotations that point at things in a captured image.

Coordinates are always NORMALIZED to the captured image (0..1 of its width/height, origin top-left), so they stay
meaningful whatever the display scale. A model may suggest annotations; nothing it says is trusted: every value is
checked, invalid entries are dropped (never clamped into a plausible-looking spot) and the drop is reported.
`to_screen_rect` is the (tested) bridge a future live overlay will use; the capture geometry must be known and the
screen unchanged since the capture, which the caller has to establish, so nothing draws on the live screen yet.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

MAX_ANNOTATIONS = 8
MAX_LABEL_CHARS = 140
MIN_BOX_SIDE = 0.01  # a box thinner than 1% of the image cannot be a real element
MAX_BOX_AREA = 0.85  # a box covering (nearly) everything points at nothing
_TOLERANCE = 0.005  # float noise only; anything further outside the image is rejected

KINDS = ("box", "point")


@dataclass(frozen=True)
class Annotation:
    kind: str  # box | point
    x: float
    y: float
    w: float = 0.0
    h: float = 0.0
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnnotationReport:
    accepted: list[Annotation] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)  # {"index": "2", "reason": "..."}

    def to_dict(self) -> dict[str, Any]:
        return {"accepted": [a.to_dict() for a in self.accepted], "rejected": self.rejected}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    return f if math.isfinite(f) else None


def _label(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", value).strip()
    return text[:MAX_LABEL_CHARS]


def validate_annotations(raw: Any) -> AnnotationReport:
    """Validates a list of untrusted annotation dicts against the image-normalized contract."""
    report = AnnotationReport()
    if not isinstance(raw, list):
        report.rejected.append({"index": "-", "reason": "not_a_list"})
        return report
    for i, item in enumerate(raw):
        idx = str(i)
        if len(report.accepted) >= MAX_ANNOTATIONS:
            report.rejected.append({"index": idx, "reason": "too_many"})
            continue
        if not isinstance(item, dict):
            report.rejected.append({"index": idx, "reason": "not_an_object"})
            continue
        kind = item.get("kind")
        if kind not in KINDS:
            report.rejected.append({"index": idx, "reason": "unknown_kind"})
            continue
        x, y = _num(item.get("x")), _num(item.get("y"))
        if x is None or y is None:
            report.rejected.append({"index": idx, "reason": "missing_or_non_numeric_coordinates"})
            continue
        if not (-_TOLERANCE <= x <= 1 + _TOLERANCE and -_TOLERANCE <= y <= 1 + _TOLERANCE):
            report.rejected.append({"index": idx, "reason": "out_of_bounds"})
            continue
        x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
        if kind == "point":
            report.accepted.append(Annotation("point", round(x, 4), round(y, 4), 0.0, 0.0, _label(item.get("label"))))
            continue
        w, h = _num(item.get("w")), _num(item.get("h"))
        if w is None or h is None:
            report.rejected.append({"index": idx, "reason": "missing_or_non_numeric_size"})
            continue
        if w < MIN_BOX_SIDE or h < MIN_BOX_SIDE:
            report.rejected.append({"index": idx, "reason": "box_too_small"})
            continue
        if x + w > 1 + _TOLERANCE or y + h > 1 + _TOLERANCE:
            report.rejected.append({"index": idx, "reason": "out_of_bounds"})
            continue
        w, h = min(w, 1.0 - x), min(h, 1.0 - y)
        if w * h > MAX_BOX_AREA:
            report.rejected.append({"index": idx, "reason": "box_covers_everything"})
            continue
        report.accepted.append(Annotation("box", round(x, 4), round(y, 4), round(w, 4), round(h, 4), _label(item.get("label"))))
    return report


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Finds the first JSON object in a model reply (raw, fenced, or surrounded by prose). None when there is none."""
    if not text:
        return None
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for cand in candidates:
        start = cand.find("{")
        while start != -1:
            depth, in_str, esc = 0, False, False
            for j in range(start, len(cand)):
                ch = cand[j]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                elif ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(cand[start:j + 1])
                            if isinstance(obj, dict):
                                return obj
                        except json.JSONDecodeError:
                            pass
                        break
            start = cand.find("{", start + 1)
    return None


def parse_annotations(text: str) -> tuple[str, AnnotationReport]:
    """
    Splits a model reply that was asked for ``{"answer": str, "annotations": [...]}``. Returns (answer, report). When the
    reply is not that JSON the whole text is the answer and the report says why nothing was drawn.
    """
    obj = extract_json_object(text)
    if obj is None or "annotations" not in obj:
        report = AnnotationReport()
        report.rejected.append({"index": "-", "reason": "unparseable_reply"})
        return (text or "").strip(), report
    answer = obj.get("answer")
    answer = answer.strip() if isinstance(answer, str) and answer.strip() else ""
    return answer, validate_annotations(obj.get("annotations"))


@dataclass(frozen=True)
class CaptureGeometry:
    """Where the captured image sits on the desktop, in screen POINTS (not pixels) at capture time."""

    image_width: int
    image_height: int
    screen_x: float
    screen_y: float
    screen_width: float
    screen_height: float

    def valid(self) -> bool:
        vals = (self.screen_x, self.screen_y, self.screen_width, self.screen_height)
        return (
            self.image_width > 0 and self.image_height > 0 and self.screen_width > 0 and self.screen_height > 0
            and all(math.isfinite(v) for v in vals)
        )


def to_screen_rect(a: Annotation, geo: CaptureGeometry) -> tuple[float, float, float, float]:
    """Maps a validated annotation to a (x, y, w, h) rect in screen points. Refuses unknown or inconsistent geometry."""
    if not geo.valid():
        raise ValueError("capture geometry is unknown or inconsistent")
    if not (0.0 <= a.x <= 1.0 and 0.0 <= a.y <= 1.0 and 0.0 <= a.x + a.w <= 1.0 + _TOLERANCE and 0.0 <= a.y + a.h <= 1.0 + _TOLERANCE):
        raise ValueError("annotation is outside the captured image")
    return (
        geo.screen_x + a.x * geo.screen_width,
        geo.screen_y + a.y * geo.screen_height,
        a.w * geo.screen_width,
        a.h * geo.screen_height,
    )
