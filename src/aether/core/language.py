"""Tiny language guess used for fixed-text replies and proposal wording (Italian vs English)."""
from __future__ import annotations

import re

_ENGLISH_MARKERS_RE = re.compile(
    r"\b(?:the|and|that|remember|please|with|for|my|is|are|to|of|what|who|when|how|create|write|send|report|about)\b",
    re.IGNORECASE,
)
_ITALIAN_MARKERS_RE = re.compile(
    r"\b(?:il|lo|la|le|gli|che|di|del|della|per|con|mio|mia|ricorda|ricordati|crea|scrivi|cliente|chi|quando|come|un|una|è|sono|su|nel|nella)\b",
    re.IGNORECASE,
)


def looks_english(text: str) -> bool:
    """English only when English markers clearly dominate; ties and empty text default to Italian."""
    return len(_ENGLISH_MARKERS_RE.findall(text or "")) > len(_ITALIAN_MARKERS_RE.findall(text or ""))
