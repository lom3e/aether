"""
Local detection and reversible masking of sensitive values before text leaves the computer.

Everything is pattern + checksum based and runs locally; nothing here calls a model. Detectors are deliberately
conservative (a checksum or an unmistakable shape is required) so ordinary numbers are not mangled, and they are NOT a
guarantee: names, addresses and free-form secrets are not detected. Callers present this as "common identifiers and
keys are masked", never as anonymization.

A masked value is replaced by a placeholder such as ``<IBAN_1>``; :class:`MaskMap` restores the originals in the
model's reply locally, so the answer still reads naturally.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

KINDS = ("secret", "iban", "card", "tax_id", "email", "phone", "vat")

_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"),  # JWT
]
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b")
_CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
_TAX_ID = re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b", re.I)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}\b")
_PHONE_INTL = re.compile(r"(?<![\w+])\+\d{1,3}[ .\-]?\d{2,4}(?:[ .\-]?\d{2,4}){2,4}(?!\w)")
_PHONE_IT_MOBILE = re.compile(r"(?<![\w.])3\d{2}[ .\-]?\d{6,7}(?![\w.])")
_VAT = re.compile(r"(?i)\b(?:p\.?\s?iva|partita\s+iva|vat(?:\s+(?:number|no\.?|id))?)[\s:.#-]*((?:IT)?\d{11})\b")


def iban_valid(value: str) -> bool:
    s = re.sub(r"\s+", "", value).upper()
    if not 15 <= len(s) <= 34 or not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", s):
        return False
    rearranged = s[4:] + s[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def luhn_valid(number: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", number)]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_CF_ODD = {**dict(zip("0123456789", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21])), **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]))}
_CF_EVEN = {**{str(i): i for i in range(10)}, **{chr(65 + i): i for i in range(26)}}


def tax_id_valid(value: str) -> bool:
    """Italian codice fiscale (16 characters) check letter."""
    s = value.upper()
    if len(s) != 16:
        return False
    try:
        total = sum(_CF_ODD[c] if i % 2 == 0 else _CF_EVEN[c] for i, c in enumerate(s[:15]))
    except KeyError:
        return False
    return chr(65 + total % 26) == s[15]


def vat_valid(value: str) -> bool:
    """Italian partita IVA: 11 digits with a Luhn-like check digit."""
    d = re.sub(r"\D", "", value)[-11:]
    if len(d) != 11:
        return False
    total = 0
    for i, ch in enumerate(d[:10]):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(d[10])


@dataclass(frozen=True)
class Finding:
    kind: str
    start: int
    end: int


def _overlaps(a: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    return any(a[0] < t[1] and t[0] < a[1] for t in taken)


def find_sensitive(text: str) -> list[Finding]:
    """All sensitive spans, longest-first by detector priority, never overlapping, sorted by position."""
    if not text:
        return []
    found: list[Finding] = []
    taken: list[tuple[int, int]] = []

    def add(kind: str, start: int, end: int) -> None:
        span = (start, end)
        if not _overlaps(span, taken):
            taken.append(span)
            found.append(Finding(kind, start, end))

    for pat in _SECRET_PATTERNS:
        for m in pat.finditer(text):
            add("secret", m.start(), m.end())
    for m in _IBAN.finditer(text):
        if iban_valid(m.group(0)):
            add("iban", m.start(), m.end())
    for m in _TAX_ID.finditer(text):
        if tax_id_valid(m.group(0)):
            add("tax_id", m.start(), m.end())
    for m in _CARD.finditer(text):
        if luhn_valid(m.group(0)):
            add("card", m.start(), m.end())
    for m in _VAT.finditer(text):
        if vat_valid(m.group(1)):
            add("vat", m.start(1), m.end(1))
    for m in _EMAIL.finditer(text):
        add("email", m.start(), m.end())
    for pat in (_PHONE_INTL, _PHONE_IT_MOBILE):
        for m in pat.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if 9 <= len(digits) <= 15:
                add("phone", m.start(), m.end())
    return sorted(found, key=lambda f: f.start)


@dataclass
class MaskMap:
    """Placeholder -> original, plus counts per kind. Lives only for the duration of one request."""

    originals: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    _by_value: dict[tuple[str, str], str] = field(default_factory=dict)

    def placeholder(self, kind: str, value: str) -> str:
        key = (kind, value)
        if key in self._by_value:
            return self._by_value[key]
        n = self.counts.get(kind, 0) + 1
        self.counts[kind] = n
        ph = f"<{kind.upper()}_{n}>"
        self._by_value[key] = ph
        self.originals[ph] = value
        return ph

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def restore(self, text: str) -> str:
        if not self.originals or not text:
            return text
        for ph, original in self.originals.items():
            text = text.replace(ph, original)
        return text


def mask_text(text: str, mapping: MaskMap | None = None) -> tuple[str, MaskMap]:
    mapping = mapping if mapping is not None else MaskMap()
    findings = find_sensitive(text)
    if not findings:
        return text, mapping
    out: list[str] = []
    last = 0
    for f in findings:
        out.append(text[last:f.start])
        out.append(mapping.placeholder(f.kind, text[f.start:f.end]))
        last = f.end
    out.append(text[last:])
    return "".join(out), mapping


class StreamRestorer:
    """Restores placeholders in streamed text without ever emitting half a placeholder."""

    def __init__(self, mapping: MaskMap) -> None:
        self.mapping = mapping
        self._buf = ""

    def feed(self, chunk: str) -> str:
        self._buf += chunk or ""
        cut = self._buf.rfind("<")
        if cut != -1 and ">" not in self._buf[cut:] and len(self._buf) - cut < 24:
            safe, self._buf = self._buf[:cut], self._buf[cut:]
        else:
            safe, self._buf = self._buf, ""
        return self.mapping.restore(safe)

    def flush(self) -> str:
        rest, self._buf = self._buf, ""
        return self.mapping.restore(rest)
