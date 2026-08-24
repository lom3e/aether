"""
Provider health checking subsystem for Aether (P1-03).

Provides structured health status checks, reachable verification,
latency tracking, and caching with TTL to prevent hammering provider APIs.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderHealthStatus:
    """
    Structured health status contract for an AI provider.
    """
    provider: str
    model: str
    status: str  # "connected", "error", "unconfigured", "unknown"
    reachable: bool
    latency_ms: float | None = None
    error: str | None = None
    checked_at: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "reachable": self.reachable,
            "latency_ms": round(self.latency_ms, 2) if self.latency_ms is not None else None,
            "error": self.error,
            "checked_at": self.checked_at,
            "details": self.details,
        }


class ProviderHealthChecker:
    """
    Reusable health check service with in-memory TTL caching.
    """
    DEFAULT_TTL_SECONDS: float = 5.0
    DEFAULT_TIMEOUT_SECONDS: float = 3.0

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, ProviderHealthStatus]] = {}

    def _cache_key(self, provider: str, model: str, base_url: str | None, has_key: bool) -> str:
        return f"{provider.lower()}::{model.lower()}::{base_url or ''}::{has_key}"

    def get_cached_status(self, provider: str, model: str, base_url: str | None = None, has_key: bool = False) -> ProviderHealthStatus | None:
        key = self._cache_key(provider, model, base_url, has_key)
        if key in self._cache:
            ts, status = self._cache[key]
            if time.time() - ts < self.ttl_seconds:
                return status
        return None

    def clear_cache(self) -> None:
        self._cache.clear()

    def check_health(
        self,
        provider: str,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        force_refresh: bool = False,
    ) -> ProviderHealthStatus:
        """
        Perform a synchronous health check on the specified provider/model.
        """
        prov_clean = (provider or "").strip().lower()
        model_clean = (model or "").strip()
        has_key = bool(api_key or os.environ.get(f"{prov_clean.upper()}_API_KEY"))

        if not force_refresh:
            cached = self.get_cached_status(prov_clean, model_clean, base_url, has_key)
            if cached:
                return cached

        status = self._do_check(prov_clean, model_clean, api_key, base_url, timeout)
        key = self._cache_key(prov_clean, model_clean, base_url, has_key)
        self._cache[key] = (time.time(), status)
        return status

    async def acheck_health(
        self,
        provider: str,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        force_refresh: bool = False,
    ) -> ProviderHealthStatus:
        """
        Perform an asynchronous health check.
        """
        return await asyncio.to_thread(
            self.check_health,
            provider,
            model,
            api_key,
            base_url,
            timeout,
            force_refresh,
        )

    def _do_check(
        self,
        provider: str,
        model: str,
        api_key: str | None,
        base_url: str | None,
        timeout: float,
    ) -> ProviderHealthStatus:
        if not provider:
            return ProviderHealthStatus(
                provider="",
                model=model or "",
                status="unknown",
                reachable=False,
                error="No provider specified.",
            )

        if provider == "mock":
            return ProviderHealthStatus(
                provider="mock",
                model=model or "mock-model",
                status="connected",
                reachable=True,
                latency_ms=0.5,
                details={"type": "mock", "ready": True},
            )

        if provider == "ollama":
            return self._check_ollama(model, base_url, timeout)

        if provider in ("openai", "anthropic", "gemini"):
            return self._check_cloud_provider(provider, model, api_key, base_url, timeout)

        return ProviderHealthStatus(
            provider=provider,
            model=model,
            status="unknown",
            reachable=False,
            error=f"Unsupported provider '{provider}'.",
        )

    def _check_ollama(self, model: str, base_url: str | None, timeout: float) -> ProviderHealthStatus:
        url = (base_url or "http://localhost:11434").rstrip("/")
        version_endpoint = f"{url}/api/version"
        tags_endpoint = f"{url}/api/tags"

        start = time.perf_counter()
        try:
            req = urllib.request.Request(version_endpoint, headers={"User-Agent": "Aether-HealthCheck"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                latency_ms = (time.perf_counter() - start) * 1000.0
                version_info = json.loads(raw) if raw else {}

            details: dict[str, Any] = {"server_version": version_info.get("version", "unknown")}

            # Check if model is listed if model name is supplied
            if model:
                try:
                    tags_req = urllib.request.Request(tags_endpoint, headers={"User-Agent": "Aether-HealthCheck"})
                    with urllib.request.urlopen(tags_req, timeout=timeout) as tags_resp:
                        tags_raw = tags_resp.read().decode("utf-8")
                        tags_data = json.loads(tags_raw) if tags_raw else {}
                        models_list = [m.get("name") for m in tags_data.get("models", []) if isinstance(m, dict)]
                        details["installed_models"] = models_list
                        # Check match
                        if models_list:
                            match = any(m.lower().startswith(model.lower().split(":")[0]) for m in models_list)
                            details["model_available"] = match
                except Exception:
                    pass

            return ProviderHealthStatus(
                provider="ollama",
                model=model or "default",
                status="connected",
                reachable=True,
                latency_ms=latency_ms,
                details=details,
            )

        except urllib.error.URLError as exc:
            reason = str(exc.reason) if hasattr(exc, "reason") else str(exc)
            if "Connection refused" in reason or "Errno 61" in reason or "Errno 111" in reason:
                err_msg = f"Ollama server not reachable at {url} (Connection refused). Is Ollama running?"
            else:
                err_msg = f"Ollama connection error: {reason}"
            return ProviderHealthStatus(
                provider="ollama",
                model=model or "default",
                status="error",
                reachable=False,
                error=err_msg,
            )
        except Exception as exc:
            return ProviderHealthStatus(
                provider="ollama",
                model=model or "default",
                status="error",
                reachable=False,
                error=f"Ollama check failed: {exc}",
            )

    def _check_cloud_provider(
        self,
        provider: str,
        model: str,
        api_key: str | None,
        base_url: str | None,
        timeout: float,
    ) -> ProviderHealthStatus:
        effective_key = api_key or os.environ.get(f"{provider.upper()}_API_KEY")
        if not effective_key or not effective_key.strip():
            return ProviderHealthStatus(
                provider=provider,
                model=model or "default",
                status="unconfigured",
                reachable=False,
                error=f"{provider.capitalize()} API key not configured.",
            )

        start = time.perf_counter()
        try:
            if provider == "openai":
                endpoint = (base_url or "https://api.openai.com/v1").rstrip("/") + "/models"
                req = urllib.request.Request(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {effective_key.strip()}",
                        "User-Agent": "Aether-HealthCheck",
                    },
                )
            elif provider == "anthropic":
                endpoint = (base_url or "https://api.anthropic.com/v1").rstrip("/") + "/models"
                req = urllib.request.Request(
                    endpoint,
                    headers={
                        "x-api-key": effective_key.strip(),
                        "anthropic-version": "2023-06-01",
                        "User-Agent": "Aether-HealthCheck",
                    },
                )
            elif provider == "gemini":
                endpoint = f"https://generativelanguage.googleapis.com/v1beta/models?key={effective_key.strip()}"
                req = urllib.request.Request(
                    endpoint,
                    headers={"User-Agent": "Aether-HealthCheck"},
                )
            else:
                return ProviderHealthStatus(
                    provider=provider,
                    model=model,
                    status="unknown",
                    reachable=False,
                    error=f"Unsupported cloud provider '{provider}'.",
                )

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                _ = resp.read()
                latency_ms = (time.perf_counter() - start) * 1000.0

            return ProviderHealthStatus(
                provider=provider,
                model=model or "default",
                status="connected",
                reachable=True,
                latency_ms=latency_ms,
            )

        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                err_msg = f"{provider.capitalize()} authentication failed (HTTP {exc.code}): Invalid API key."
            elif exc.code == 429:
                err_msg = f"{provider.capitalize()} rate limit exceeded or quota exhausted (HTTP 429)."
            else:
                err_msg = f"{provider.capitalize()} API error: HTTP {exc.code} {exc.reason}."
            return ProviderHealthStatus(
                provider=provider,
                model=model or "default",
                status="error",
                reachable=False,
                error=err_msg,
            )
        except urllib.error.URLError as exc:
            reason = str(exc.reason) if hasattr(exc, "reason") else str(exc)
            return ProviderHealthStatus(
                provider=provider,
                model=model or "default",
                status="error",
                reachable=False,
                error=f"{provider.capitalize()} network error: {reason}",
            )
        except Exception as exc:
            return ProviderHealthStatus(
                provider=provider,
                model=model or "default",
                status="error",
                reachable=False,
                error=f"{provider.capitalize()} health check failed: {exc}",
            )


# Default singleton instance
_default_health_checker: ProviderHealthChecker | None = None


def get_default_health_checker() -> ProviderHealthChecker:
    global _default_health_checker
    if _default_health_checker is None:
        _default_health_checker = ProviderHealthChecker()
    return _default_health_checker
