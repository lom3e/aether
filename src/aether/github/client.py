"""
Isolated GitHub API Client abstraction for Aether Project integration (P3-03).
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import urllib.error
import urllib.request
from typing import Any

from aether.github.models import (
    GitHubAuthError,
    GitHubIntegrationError,
    GitHubNotFoundError,
    GitHubRepository,
    GitHubValidationError,
)


class GitHubRepositoryClient:
    """
    Client for interacting with the GitHub REST API.

    SECURITY INVARIANTS:
    - Never persists or logs authentication tokens.
    - Resolves tokens from function arguments -> GITHUB_TOKEN -> GH_TOKEN.
    - Sanitizes all exceptions to prevent credential leakage.
    - Restricts target requests strictly to valid GitHub API endpoints.
    """
    DEFAULT_BASE_URL: str = "https://api.github.com"
    DEFAULT_TIMEOUT: float = 10.0

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _resolve_token(self, explicit_token: str | None = None) -> str | None:
        """Resolve GitHub access token with precedence: explicit > GITHUB_TOKEN > GH_TOKEN."""
        if explicit_token and isinstance(explicit_token, str) and explicit_token.strip():
            return explicit_token.strip()
        env_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if env_token and env_token.strip():
            return env_token.strip()
        return None

    def _build_headers(self, token: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Aether-AI-Workforce",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        effective_token = self._resolve_token(token)
        if effective_token:
            headers["Authorization"] = f"Bearer {effective_token}"
        return headers

    def get_repository(
        self,
        owner: str,
        repository: str,
        token: str | None = None,
    ) -> GitHubRepository:
        """
        Fetch repository metadata from GitHub.

        Parameters:
            owner: GitHub organization or username.
            repository: Repository name.
            token: Optional Personal Access Token.

        Returns:
            A populated GitHubRepository domain instance.
        """
        # Validate owner and repo names before dispatching request
        dummy_repo = GitHubRepository(owner=owner, repository=repository)
        clean_owner = dummy_repo.owner
        clean_repo = dummy_repo.repository

        url = f"{self.base_url}/repos/{clean_owner}/{clean_repo}"
        headers = self._build_headers(token)
        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise GitHubAuthError(
                    f"GitHub authentication failed or access forbidden for '{clean_owner}/{clean_repo}'. "
                    "Ensure a valid Personal Access Token with repository read permissions is provided."
                ) from None
            elif exc.code == 404:
                raise GitHubNotFoundError(
                    f"Repository '{clean_owner}/{clean_repo}' not found on GitHub or is private."
                ) from None
            else:
                raise GitHubIntegrationError(
                    f"GitHub API request failed with status code {exc.code}."
                ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GitHubIntegrationError(
                "Unable to reach GitHub API. Please verify network connectivity."
            ) from None
        except Exception as exc:
            raise GitHubIntegrationError(
                f"Unexpected error communicating with GitHub: {type(exc).__name__}"
            ) from None

        default_branch = str(payload.get("default_branch") or "main").strip()
        is_private = bool(payload.get("private", False))
        html_url = str(payload.get("html_url") or f"https://github.com/{clean_owner}/{clean_repo}")
        description = str(payload.get("description") or "")

        metadata = {
            "id": payload.get("id"),
            "stargazers_count": payload.get("stargazers_count", 0),
            "forks_count": payload.get("forks_count", 0),
            "open_issues_count": payload.get("open_issues_count", 0),
            "visibility": payload.get("visibility", "private" if is_private else "public"),
            "archived": bool(payload.get("archived", False)),
            "disabled": bool(payload.get("disabled", False)),
        }

        now = datetime.now(timezone.utc).isoformat()
        return GitHubRepository(
            owner=clean_owner,
            repository=clean_repo,
            provider="github",
            default_branch=default_branch,
            connected=True,
            url=html_url,
            private=is_private,
            connected_at=now,
            verified_at=now,
            description=description,
            metadata=metadata,
        )

    def verify_connection(
        self,
        owner: str,
        repository: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        """
        Verify that a GitHub repository is accessible and return its live verification status.
        """
        repo = self.get_repository(owner=owner, repository=repository, token=token)
        return {
            "connected": True,
            "accessible": True,
            "owner": repo.owner,
            "repository": repo.repository,
            "full_name": repo.full_name,
            "default_branch": repo.default_branch,
            "private": repo.private,
            "url": repo.url,
            "verified_at": repo.verified_at or datetime.now(timezone.utc).isoformat(),
            "description": repo.description,
            "metadata": repo.metadata,
        }
