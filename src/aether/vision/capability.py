"""
Which configured models can really take an image. The decision is made per provider *and model* from a conservative
allow-list: an unknown model is treated as text-only, so an image is never sent to something that may not understand it
(the user is told instead). A provider can still reject an image at call time; that error is reported as is.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_OPENAI = re.compile(r"^(gpt-4o|gpt-4\.1|gpt-4\.5|gpt-4-turbo|gpt-4-vision|gpt-5|chatgpt-4o|o1(?!-mini|-preview)|o3(?!-mini)|o4)", re.I)
_ANTHROPIC = re.compile(r"^claude-(?!2|instant|1)", re.I)
_GEMINI = re.compile(r"^(models/)?gemini-(?!1\.0|embedding|2\.0-flash-lite-001$)", re.I)
_GROQ = re.compile(r"(llama-4-(scout|maverick)|llama-3\.2-\d+b-vision|vision)", re.I)
_OLLAMA = re.compile(r"(llava|bakllava|moondream|minicpm-v|[-.]vl\b|vl:|-vision|vision:|llama3\.2-vision|gemma3|granite3\.2-vision|qwen\d*(\.\d+)?-?vl|pixtral|mistral-small3)", re.I)

_PATTERNS = {"openai": _OPENAI, "anthropic": _ANTHROPIC, "gemini": _GEMINI, "groq": _GROQ, "ollama": _OLLAMA}


def model_supports_vision(provider: str | None, model: str | None) -> bool:
    pattern = _PATTERNS.get((provider or "").strip().lower())
    return bool(pattern and model and pattern.search(model.strip()))


@dataclass(frozen=True)
class VisionSupport:
    supported: bool
    reason: str  # ok | no_provider | provider_unusable | model_without_vision | no_model
    provider: str = ""
    model: str = ""


def _provider_name(provider: Any) -> str:
    explicit = getattr(provider, "provider_name", None) or getattr(provider, "name", None)
    if isinstance(explicit, str) and explicit:
        return explicit.lower()
    cls = type(provider).__name__.lower()
    for key in _PATTERNS:
        if cls.startswith(key):
            return key
    return cls.replace("provider", "")


def vision_support_for(provider: Any | None) -> VisionSupport:
    """Checks the concretely resolved provider instance (never a guess about what might be configured)."""
    if provider is None:
        return VisionSupport(False, "no_provider")
    from aether.providers.unresolved import UnresolvedProvider

    name = _provider_name(provider)
    cfg = getattr(provider, "config", None)
    model = getattr(cfg, "model", None) or ""
    if isinstance(provider, UnresolvedProvider):
        return VisionSupport(False, "provider_unusable", name, model or "")
    caps = getattr(provider, "capabilities", None)
    if caps is not None and getattr(caps, "vision", False):
        return VisionSupport(True, "ok", name, model)
    if not model:
        return VisionSupport(False, "no_model", name, "")
    return VisionSupport(False, "model_without_vision", name, model)
