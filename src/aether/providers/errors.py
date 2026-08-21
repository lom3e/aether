"""
Standard exception hierarchy for AI provider errors in Aether.

All provider implementations must raise only these exceptions, allowing the
Agent and future retry/fallback logic to handle failures uniformly without
being coupled to provider-specific SDK exceptions.
"""

from __future__ import annotations

from aether.errors import ProviderError as BaseProviderError

class ProviderError(BaseProviderError):
    """
    Base class for all provider-related errors.

    All concrete provider exceptions inherit from this class, allowing callers
    to catch the entire hierarchy with a single ``except ProviderError``.
    """

    def __init__(self, message: str, *, provider: str = "unknown") -> None:
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class AuthenticationError(ProviderError):
    """
    Raised when the provider rejects authentication credentials.

    Typically caused by a missing or invalid API key.
    """


class RateLimitError(ProviderError):
    """
    Raised when the provider rate-limits the request.

    Callers may implement exponential back-off and retry on this error.
    """


class TimeoutError(ProviderError):
    """
    Raised when the provider does not respond within the configured timeout.
    """


class ProviderNotFoundError(ProviderError):
    """
    Raised by ProviderManager when the requested provider name is not registered.
    """


class ProviderConnectionError(ProviderError):
    """
    Raised when the provider endpoint cannot be reached (network error).
    """


class ModelNotFoundError(ProviderError):
    """
    Raised when the requested model is not found or not available.
    """


def normalize_provider_error(
    exc: Exception | str,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Normalize any exception or error string into a structured, user-facing error contract.
    """
    from typing import Any

    error_str = str(exc) if exc is not None else "Unknown error"
    err_lower = error_str.lower()

    # Defaults
    code = "TASK_FAILED"
    message = "L'attività non è stata completata a causa di un errore imprevisto."
    retryable = True
    prov = provider or "ollama"
    mod = model

    # Check for specific error types or message patterns
    if isinstance(exc, AuthenticationError) or "401" in error_str or "unauthorized" in err_lower or "api key" in err_lower or "authentication" in err_lower:
        code = "AUTHENTICATION_ERROR"
        message = "Credenziali non valide o API key mancante. Controlla le impostazioni del provider."
        retryable = False
    elif isinstance(exc, RateLimitError) or "429" in error_str or "rate limit" in err_lower:
        code = "RATE_LIMIT_ERROR"
        message = "Limite di richieste superato per il provider. Attendi qualche istante prima di riprovare."
        retryable = True
    elif isinstance(exc, TimeoutError) or "timeout" in err_lower or "timed out" in err_lower:
        code = "TIMEOUT"
        message = f"Il provider {prov.capitalize()} non ha risposto entro il tempo limite."
        retryable = True
    elif isinstance(exc, ModelNotFoundError) or "not found" in err_lower or "404" in error_str:
        code = "MODEL_UNAVAILABLE"
        if mod:
            message = f"Modello '{mod}' non trovato in {prov.capitalize()}. Assicurati che sia installato o seleziona un altro modello."
        else:
            message = f"Modello non disponibile in {prov.capitalize()}."
        retryable = True
    elif isinstance(exc, ProviderConnectionError) or isinstance(exc, (ConnectionRefusedError, OSError)) or "connection" in err_lower or "could not connect" in err_lower or "refused" in err_lower or "urlerror" in err_lower:
        code = "PROVIDER_UNAVAILABLE"
        message = f"Impossibile connettersi a {prov.capitalize()}. Assicurati che il servizio sia avviato."
        retryable = True
    elif isinstance(exc, ProviderNotFoundError) or "provider not found" in err_lower:
        code = "PROVIDER_NOT_FOUND"
        message = f"Provider '{prov}' non trovato o non registrato."
        retryable = False

    return {
        "code": code,
        "message": message,
        "provider": prov,
        "model": mod,
        "retryable": retryable,
        "technical_details": error_str,
    }
