"""
Base connector contract and normalized execution types for Aether Connections (Phase C).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from aether.connections.models import ConnectionStatus


class ConnectorError(Exception):
    """Base exception for all connector operations."""
    def __init__(self, message: str, provider: str = "", details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.details = details or {}


class ConnectorAuthError(ConnectorError):
    """Raised when authentication fails or credentials are invalid."""
    pass


class ConnectorNotFoundError(ConnectorError):
    """Raised when a remote entity or repository is not found."""
    pass


class ConnectorConfigurationError(ConnectorError):
    """Raised when required connector credentials or settings are missing."""
    pass


class ConnectorExecutionError(ConnectorError):
    """Raised when an operation fails during execution on the external system."""
    pass


@dataclass(slots=True)
class CredentialRequirement:
    """Specification of a credential field required to configure a connector."""
    key: str
    label: str
    description: str = ""
    required: bool = True
    secret: bool = True
    default: Any = None
    options: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "required": self.required,
            "secret": self.secret,
            "default": self.default,
            "options": self.options,
        }


@dataclass(slots=True)
class ConnectorHealth:
    """Result of a connector health or verification check."""
    healthy: bool
    status: ConnectionStatus
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "status": self.status.value if isinstance(self.status, ConnectionStatus) else str(self.status),
            "message": self.message,
            "timestamp": self.timestamp,
            "details": self.details,
        }


@dataclass(slots=True)
class ConnectorResult:
    """Normalized outcome returned from any connector operation."""
    success: bool
    operation: str
    provider: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "provider": self.provider,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class BaseConnector(ABC):
    """
    Abstract base class for all Aether external service connectors.
    Provides standard interfaces for credentials, capabilities, health, and operations.
    """

    @property
    def auth_metadata(self) -> dict[str, Any]:
        """Access connector authentication and configuration metadata."""
        return getattr(self, "_auth_metadata", {})

    @auth_metadata.setter
    def auth_metadata(self, val: dict[str, Any]) -> None:
        self._auth_metadata = dict(val or {})

    @property
    @abstractmethod
    def provider(self) -> str:
        """Unique provider identifier (e.g. 'github', 'email', 'slack', 'http', 'calendar')."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """List of supported operation identifiers."""
        ...

    @property
    @abstractmethod
    def credential_requirements(self) -> list[CredentialRequirement]:
        """List of credential requirements needed by this connector."""
        ...

    @abstractmethod
    def verify(self, auth_metadata: dict[str, Any] | None = None) -> tuple[bool, str]:
        """Verifies credential format and/or tests connectivity with the external service."""
        ...

    @abstractmethod
    def get_health(self) -> ConnectorHealth:
        """Performs a live health check of the connection."""
        ...

    @abstractmethod
    def execute(self, operation: str, params: dict[str, Any]) -> ConnectorResult:
        """Executes a specific operation on the external service."""
        ...
