"""
Deterministic Provider & Model Resolution Contract for Aether.
Ensures single, unified precedence across Agent, Team, Workspace, and Runtime:
1. Explicit Agent configuration (agent.provider, agent.model)
2. Inherited Team / Workspace default configuration (default_provider, default_model)
3. Global / default provider configuration (environment variables via ProviderManager)
4. Safe local auto-discovery (Ollama tags if reachable with installed models)
"""
from __future__ import annotations

import logging
import os
from typing import Any

from aether.providers.base import AIProvider
from aether.providers.types import ProviderConfig

logger = logging.getLogger(__name__)


def resolve_provider(
    explicit_provider: AIProvider | None = None,
    agent_config: Any | None = None,
    team_config: Any | None = None,
    workspace: Any | None = None,
    provider_manager: Any | None = None,
    preferred_provider_name: str | None = None,
    preferred_model_name: str | None = None,
    timeout: float | None = None,
) -> AIProvider | None:
    """
    Deterministically resolves an AIProvider adhering to the strict Aether precedence contract.
    """
    # 0. Direct injected provider instance
    if explicit_provider is not None:
        return explicit_provider

    # 1. Explicit Agent configuration
    provider_name = None
    model_name = None

    if agent_config is not None:
        provider_name = getattr(agent_config, "provider", None)
        model_name = getattr(agent_config, "model", None)

    # 2. Preferred parameter overrides if agent config was empty
    if not provider_name and preferred_provider_name:
        provider_name = preferred_provider_name
    if not model_name and preferred_model_name:
        model_name = preferred_model_name

    # 3. Inherited Team / Workspace default configuration
    if not provider_name and team_config is not None:
        provider_name = getattr(team_config, "default_provider", None)
    if not model_name and team_config is not None:
        model_name = getattr(team_config, "default_model", None)

    if not provider_name and workspace is not None:
        ws_cfg = getattr(workspace, "config", {})
        if isinstance(ws_cfg, dict):
            provider_name = ws_cfg.get("workspace", {}).get("default_provider")
            if not model_name:
                model_name = ws_cfg.get("workspace", {}).get("default_model")

    from aether.providers.manager import ProviderManager
    mgr = provider_manager or ProviderManager()

    if provider_name:
        # User/agent/team explicitly specified provider_name
        cfg = ProviderConfig(model=model_name, timeout=timeout or 60.0)
        try:
            return mgr.get(provider_name, config=cfg)
        except Exception as e:
            logger.debug(f"Could not resolve explicit provider '{provider_name}': {e}")
            return None

    # 4. Global / environment key based resolution
    if os.environ.get("OPENAI_API_KEY"):
        return mgr.get("openai", ProviderConfig(model=model_name, api_key=os.environ["OPENAI_API_KEY"], timeout=timeout or 60.0))
    if os.environ.get("ANTHROPIC_API_KEY"):
        return mgr.get("anthropic", ProviderConfig(model=model_name, api_key=os.environ["ANTHROPIC_API_KEY"], timeout=timeout or 60.0))
    if os.environ.get("GEMINI_API_KEY"):
        return mgr.get("gemini", ProviderConfig(model=model_name, api_key=os.environ["GEMINI_API_KEY"], timeout=timeout or 60.0))

    # 5. Safe local auto-discovery: fallback to Ollama if reachable with installed models
    try:
        p = mgr.get("ollama", ProviderConfig(model=model_name, timeout=timeout or 60.0))
        if hasattr(p, "get_available_models") and p.get_available_models():
            return p
    except Exception:
        pass

    return None
