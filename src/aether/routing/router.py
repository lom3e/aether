"""
Model Router: Analyzes task requirements, agent roles, and prompt complexity
to determine the optimal model routing tier and fallback chain.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from aether.routing.models import ModelRoutingConfig, RouteDecision, RoutingTier

logger = logging.getLogger(__name__)


class ModelRouter:
    """Intelligently routes tasks to the most cost-effective and capable model tier."""

    def __init__(self, config: ModelRoutingConfig | None = None) -> None:
        self.config = config or ModelRoutingConfig()

    def classify_tier(
        self,
        prompt: str,
        role: str | None = None,
        tools: list[Any] | None = None,
    ) -> RoutingTier:
        """Determines the appropriate RoutingTier based on role, tools, and prompt content."""
        p_lower = prompt.lower()
        r_lower = (role or "").lower()

        # 1. Reasoning & Quality Gate Review Check
        reasoning_keywords = [
            "review", "audit", "quality gate", "evaluate", "synthesize", "architecture",
            "tradeoff", "trade-off", "conflict resolution", "security audit", "deep analysis",
            "valuta", "revisiona", "architettura", "sicurezza",
        ]
        reasoning_roles = ["reviewer", "architect", "auditor", "evaluator", "security"]
        if any(r in r_lower for r in reasoning_roles) or any(k in p_lower for k in reasoning_keywords):
            return RoutingTier.REASONING

        # 2. Coding & Implementation Check
        coding_keywords = [
            "implement", "refactor", "bug", "fix", "function", "class", "syntax",
            "python", "typescript", "javascript", "rust", "go", "sql", "patch", "endpoint",
            "codice", "scrivi funzione", "implementa", "correggi bug",
        ]
        coding_roles = ["coder", "developer", "engineer", "programmer", "backend", "frontend"]
        if any(r in r_lower for r in coding_roles) or any(k in p_lower for k in coding_keywords):
            return RoutingTier.CODING

        # 3. Fast / Lightweight Check
        fast_keywords = [
            "plan", "outline", "list", "summarize", "quick", "decompose", "status",
            "pianifica", "elenca", "riassumi", "schema",
        ]
        has_tools = bool(tools and len(tools) > 0)
        if not has_tools and (len(prompt.split()) < 25 or any(k in p_lower for k in fast_keywords)):
            return RoutingTier.FAST

        # 4. Default to Balanced (tool-calling & general workflows)
        return RoutingTier.BALANCED

    def route(
        self,
        prompt: str,
        role: str | None = None,
        tools: list[Any] | None = None,
        override_tier: RoutingTier | None = None,
    ) -> RouteDecision:
        """Produces a RouteDecision with recommended primary provider/model and fallback chain."""
        tier = override_tier or self.classify_tier(prompt=prompt, role=role, tools=tools)
        chain = self.config.get_chain_for_tier(tier)

        if not chain:
            chain = [("ollama", "llama3.1:8b")]

        primary_provider, primary_model = chain[0]
        fallbacks = chain[1:]

        rationale = f"Selected tier '{tier.value}' based on role '{role or 'general'}' and prompt complexity."
        cost_tier = "low" if tier in (RoutingTier.FAST, RoutingTier.BALANCED) else ("medium" if tier == RoutingTier.CODING else "high")

        return RouteDecision(
            tier=tier,
            provider_name=primary_provider,
            model_name=primary_model,
            fallback_chain=fallbacks,
            rationale=rationale,
            estimated_cost_tier=cost_tier,
        )
