"""
Models and types for Dynamic Adaptive Model Routing and Resilient Fallbacks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RoutingTier(str, Enum):
    """Execution tiers for adaptive model selection."""
    FAST = "fast"                    # Lightweight, low-latency, planning, task decomposition, simple parsing
    BALANCED = "balanced"            # General-purpose, tool-calling, data retrieval, connectors
    CODING = "coding"                # Specialized coding, patch generation, syntax/security verification
    REASONING = "reasoning"          # Deep synthesis, architectural design, quality gate reviews, conflict resolution


@dataclass
class RouteDecision:
    """Outcome of model routing analysis for a task or prompt."""
    tier: RoutingTier
    provider_name: str
    model_name: str
    fallback_chain: list[tuple[str, str]] = field(default_factory=list)
    rationale: str = ""
    estimated_cost_tier: str = "low"  # low, medium, high

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value if hasattr(self.tier, "value") else str(self.tier),
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "fallback_chain": self.fallback_chain,
            "rationale": self.rationale,
            "estimated_cost_tier": self.estimated_cost_tier,
        }


@dataclass
class FallbackEvent:
    """Record of a dynamic provider or model switch triggered by failure."""
    from_provider: str
    from_model: str
    to_provider: str
    to_model: str
    error_reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_provider": self.from_provider,
            "from_model": self.from_model,
            "to_provider": self.to_provider,
            "to_model": self.to_model,
            "error_reason": self.error_reason,
            "timestamp": self.timestamp,
        }


@dataclass
class ModelRoutingConfig:
    """Configurable routing preferences per tier."""
    fast_chain: list[tuple[str, str]] = field(
        default_factory=lambda: [
            ("ollama", "llama3.2:latest"),
            ("gemini", "gemini-1.5-flash"),
            ("openai", "gpt-4o-mini"),
        ]
    )
    balanced_chain: list[tuple[str, str]] = field(
        default_factory=lambda: [
            ("ollama", "llama3.1:8b"),
            ("gemini", "gemini-1.5-flash"),
            ("openai", "gpt-4o"),
        ]
    )
    coding_chain: list[tuple[str, str]] = field(
        default_factory=lambda: [
            ("ollama", "qwen2.5-coder:7b"),
            ("anthropic", "claude-3-5-sonnet-20241022"),
            ("openai", "gpt-4o"),
        ]
    )
    reasoning_chain: list[tuple[str, str]] = field(
        default_factory=lambda: [
            ("anthropic", "claude-3-5-sonnet-20241022"),
            ("openai", "gpt-4o"),
            ("gemini", "gemini-1.5-pro"),
        ]
    )

    def get_chain_for_tier(self, tier: RoutingTier) -> list[tuple[str, str]]:
        if tier == RoutingTier.FAST:
            return list(self.fast_chain)
        elif tier == RoutingTier.BALANCED:
            return list(self.balanced_chain)
        elif tier == RoutingTier.CODING:
            return list(self.coding_chain)
        elif tier == RoutingTier.REASONING:
            return list(self.reasoning_chain)
        return list(self.balanced_chain)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fast": self.fast_chain,
            "balanced": self.balanced_chain,
            "coding": self.coding_chain,
            "reasoning": self.reasoning_chain,
        }
