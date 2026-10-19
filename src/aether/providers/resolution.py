"""
Deterministic Provider & Model Resolution Contract for Aether.
Ensures single, unified precedence across Agent, Team, Workspace, and Runtime:
1. Explicit Agent configuration (agent.provider, agent.model)
2. Inherited Team / Workspace default configuration (default_provider, default_model)
3. Credentials the user stored for exactly a provider (workspace SecretStore, then the provider's own *_API_KEY
   environment variable), tried in the fixed order openai, anthropic, gemini, groq
No local provider is ever chosen implicitly: when nothing above names a provider the result is ``None`` (the
documented "no provider configured" state) and nothing is contacted. Ollama is used only when it is named
explicitly (agent, team, workspace, CLI flag or API parameter). A named provider that cannot be built becomes an
``UnresolvedProvider`` that fails every call with the real reason: there is no substitution.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from aether.providers.base import AIProvider
from aether.providers.types import ProviderConfig

logger = logging.getLogger(__name__)


def _workspace_max_tokens(workspace: Any | None) -> int | None:
    """
    Optional, EXPLICIT output cap from the workspace settings (``workspace.default_max_tokens``). Some providers/tiers
    refuse a request whose estimated output exceeds a per-minute budget unless the caller sets a cap; this is how a
    user sets one. Absent or invalid -> None (nothing is assumed).
    """
    try:
        cfg = getattr(workspace, "config", None)
        value = (cfg.get("workspace", {}) if isinstance(cfg, dict) else {}).get("default_max_tokens")
        return int(value) if value is not None and int(value) > 0 else None
    except (TypeError, ValueError):
        return None


def _resolve_provider_unaudited(
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
        if not provider_name and hasattr(workspace, "load_team"):
            try:
                loaded_team = workspace.load_team()
                if loaded_team and getattr(loaded_team, "config", None):
                    provider_name = getattr(loaded_team.config, "default_provider", None)
                    if not model_name:
                        model_name = getattr(loaded_team.config, "default_model", None)
            except Exception:
                pass

    from aether.providers.manager import ProviderManager
    mgr = provider_manager or ProviderManager()

    s_store = getattr(workspace, "secret_store", None) if workspace else None

    if provider_name:
        # User/agent/team explicitly specified provider_name
        api_key = None
        if s_store:
            api_key = s_store.get_secret(f"provider_api_key:{provider_name.lower()}")
        cfg = ProviderConfig(model=model_name, api_key=api_key, timeout=timeout or 60.0, max_tokens=_workspace_max_tokens(workspace))
        try:
            return mgr.get(provider_name, config=cfg)
        except Exception as e:
            # Explicitly configured but unusable: keep the identity visible and fail loudly at use time.
            from aether.providers.groq_provider import redact
            from aether.providers.unresolved import UnresolvedProvider
            logger.warning("Could not resolve configured provider '%s': %s", provider_name, type(e).__name__)
            return UnresolvedProvider(provider_name, model_name, redact(str(e), api_key))

    # 4. Workspace SecretStore / Global environment key based resolution
    for p_name, env_var in (("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY"), ("gemini", "GEMINI_API_KEY"), ("groq", "GROQ_API_KEY")):
        key = None
        if s_store:
            key = s_store.get_secret(f"provider_api_key:{p_name}")
        if not key:
            key = os.environ.get(env_var)
        if key:
            try:
                return mgr.get(p_name, ProviderConfig(model=model_name, api_key=key, timeout=timeout or 60.0, max_tokens=_workspace_max_tokens(workspace)))
            except Exception as e:
                from aether.providers.groq_provider import redact
                from aether.providers.unresolved import UnresolvedProvider
                logger.warning("Could not build provider '%s' from stored credentials: %s", p_name, type(e).__name__)
                return UnresolvedProvider(p_name, model_name, redact(str(e), key))

    # No provider named and no stored credential: do NOT guess a local service. "Not configured" is an explicit state
    # that callers report to the user (they never receive a provider they did not choose).
    return None


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
    Same contract as above, plus the privacy layer: a provider that this function BUILDS (never an instance injected by
    the caller, and never the unresolved stub) is instrumented so that cloud calls are masked and every call is recorded
    in the workspace's egress ledger.
    """
    provider = _resolve_provider_unaudited(
        explicit_provider, agent_config, team_config, workspace, provider_manager,
        preferred_provider_name, preferred_model_name, timeout,
    )
    if provider is None or provider is explicit_provider or workspace is None:
        return provider
    try:
        from aether.providers.unresolved import UnresolvedProvider
        if isinstance(provider, UnresolvedProvider):
            return provider
        from aether.privacy.audit import instrument_provider, ledger_for
        ledger = ledger_for(workspace)
        if ledger is not None:
            instrument_provider(provider, ledger, getattr(workspace, "id", None))
    except Exception as exc:  # noqa: BLE001 - never let auditing stop the user from reaching a model
        logger.warning("egress auditing unavailable: %s", type(exc).__name__)
    return provider
