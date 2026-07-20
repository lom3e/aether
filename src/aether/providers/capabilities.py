from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    """
    Immutable representation of an AI provider's capabilities.
    This allows Aether to adapt its execution strategy (e.g., using structured
    outputs or tool calling) based on what the underlying model supports.
    """
    tools: bool = False
    vision: bool = False
    structured_output: bool = False
    thinking: bool = False
