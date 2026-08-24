"""
Domain models and exception hierarchy for GitHub repository integration (P3-03).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any


class GitHubIntegrationError(Exception):
    """Base exception for all GitHub integration operations."""
    pass


class GitHubAuthError(GitHubIntegrationError):
    """Raised when GitHub authentication fails or credentials lack permissions."""
    pass


class GitHubNotFoundError(GitHubIntegrationError):
    """Raised when the target repository does not exist or is inaccessible."""
    pass


class GitHubValidationError(GitHubIntegrationError):
    """Raised when repository names, owners, or branch names fail validation."""
    pass


_OWNER_REPO_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+$")


@dataclass
class GitHubRepository:
    """
    Structured identity and metadata for a connected GitHub repository.

    CRITICAL SECURITY INVARIANT:
    This model and its serialization formats NEVER store or persist access tokens.
    Authentication tokens are resolved separately at runtime.
    """
    owner: str
    repository: str
    provider: str = "github"
    default_branch: str = "main"
    connected: bool = True
    url: str = ""
    private: bool = False
    connected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verified_at: str | None = None
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.owner = str(self.owner).strip()
        self.repository = str(self.repository).strip()
        self.provider = str(self.provider or "github").strip().lower()
        self.default_branch = str(self.default_branch or "main").strip()

        if not self.url:
            self.url = f"https://github.com/{self.owner}/{self.repository}"

        self.validate()

    @property
    def full_name(self) -> str:
        """Return 'owner/repository' identifier."""
        return f"{self.owner}/{self.repository}"

    def validate(self) -> None:
        """Validate owner and repository name invariants."""
        if not self.owner:
            raise GitHubValidationError("Repository owner cannot be empty.")
        if not self.repository:
            raise GitHubValidationError("Repository name cannot be empty.")
        if len(self.owner) > 100 or len(self.repository) > 100:
            raise GitHubValidationError("Repository owner or name exceeds maximum length of 100 characters.")
        if not _OWNER_REPO_REGEX.match(self.owner):
            raise GitHubValidationError(f"Invalid repository owner '{self.owner}'. Only alphanumeric characters, '.', '_' and '-' are allowed.")
        if not _OWNER_REPO_REGEX.match(self.repository):
            raise GitHubValidationError(f"Invalid repository name '{self.repository}'. Only alphanumeric characters, '.', '_' and '-' are allowed.")
        if not self.default_branch:
            raise GitHubValidationError("Default branch cannot be empty.")

    def to_dict(self) -> dict[str, Any]:
        """Convert repository metadata to dictionary representation."""
        return {
            "provider": self.provider,
            "owner": self.owner,
            "repository": self.repository,
            "full_name": self.full_name,
            "default_branch": self.default_branch,
            "connected": self.connected,
            "url": self.url,
            "private": self.private,
            "connected_at": self.connected_at,
            "verified_at": self.verified_at,
            "description": self.description,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GitHubRepository:
        """Build a GitHubRepository instance from a dictionary."""
        if not isinstance(data, dict):
            raise GitHubValidationError("Repository data must be a dictionary.")

        owner = str(data.get("owner", "")).strip()
        repository = str(data.get("repository", data.get("name", ""))).strip()

        # Handle full_name shorthand (e.g. "lom3e/aether")
        if "/" in owner and not repository:
            parts = owner.split("/", 1)
            owner, repository = parts[0].strip(), parts[1].strip()

        return cls(
            owner=owner,
            repository=repository,
            provider=str(data.get("provider", "github")).strip(),
            default_branch=str(data.get("default_branch", "main")).strip(),
            connected=bool(data.get("connected", True)),
            url=str(data.get("url", "")).strip(),
            private=bool(data.get("private", False)),
            connected_at=str(data.get("connected_at") or datetime.now(timezone.utc).isoformat()),
            verified_at=str(data.get("verified_at")) if data.get("verified_at") else None,
            description=str(data.get("description", "")),
            metadata=dict(data.get("metadata") or {}),
        )
