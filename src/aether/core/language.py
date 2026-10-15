"""Tiny language guess used for fixed-text replies and proposal wording (Italian vs English)."""
from __future__ import annotations

import re
from contextvars import ContextVar, Token

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


# UI language of the current request ("it" / "en"), set by the HTTP layer; falls back to guessing from the text.
_ui_language: ContextVar[str | None] = ContextVar("aether_ui_language", default=None)


def set_ui_language(language: str | None) -> Token:
    code = (language or "").strip().lower()[:2]
    return _ui_language.set(code if code in {"it", "en"} else None)


def reset_ui_language(token: Token) -> None:
    _ui_language.reset(token)


def prefers_english(text: str) -> bool:
    """The active UI language when known, otherwise the language the user wrote in."""
    ui = _ui_language.get()
    if ui:
        return ui == "en"
    return looks_english(text)


def no_provider_message(text: str = "", *, drafting_document: bool = False) -> str:
    """Fixed reply when no AI provider is configured, in the active language."""
    if prefers_english(text):
        what = " to draft document content" if drafting_document else ""
        return f"No AI provider configured{what}. Open Settings → Provider."
    what = " per scrivere il contenuto del documento" if drafting_document else ""
    return f"Nessun provider AI configurato{what}. Apri Impostazioni → Provider."
