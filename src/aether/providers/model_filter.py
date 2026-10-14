"""
Separates conversational models from the rest of a provider's catalogue.

Provider model listings mix chat models with speech-to-text, text-to-speech, embeddings, moderation/safety classifiers
and image/video generators. Offering a Whisper or a prompt-guard model as "the model that answers my chat" produces
errors the user cannot explain, so the model picker only shows models that can plausibly hold a conversation. The
excluded ids are still reported, and a user can always type a custom id explicitly.
"""
from __future__ import annotations

import re

_NON_CHAT_RE = re.compile(
    r"(?:whisper|transcri|orpheus|\btts\b|[-_/.]tts\b|playai|speech|embed|rerank|moderation|omni-moderation|"
    r"prompt-guard|llama-guard|safeguard|\bguard\b|-guard-|dall-e|gpt-image|imagen|veo[-\d]|sora|stable-diffusion|"
    r"text-to-image|aqa|realtime-preview|audio-preview|clip\b)",
    re.IGNORECASE,
)


def is_chat_model(model_id: str) -> bool:
    return not _NON_CHAT_RE.search(model_id or "")


def split_chat_models(models: list[str]) -> tuple[list[str], list[str]]:
    """(chat-capable models in their original order, excluded models)."""
    chat = [m for m in models if is_chat_model(m)]
    excluded = [m for m in models if not is_chat_model(m)]
    return chat, excluded
