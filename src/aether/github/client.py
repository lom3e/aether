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
    GitHubRateLimitError,
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
            err_body = ""
            try:
                err_data = json.loads(exc.read().decode("utf-8"))
                err_body = err_data.get("message", "")
            except Exception:
                pass

            is_rate_limit = exc.code == 429 or (
                exc.code == 403 and (
                    getattr(exc, "headers", None) and exc.headers.get("x-ratelimit-remaining") == "0"
                    or "rate limit" in err_body.lower()
                    or "rate limit" in str(getattr(exc, "reason", "")).lower()
                )
            )
            if is_rate_limit:
                msg = f"GitHub API rate limit exceeded (HTTP {exc.code})."
                reset_ts = exc.headers.get("x-ratelimit-reset") if getattr(exc, "headers", None) else None
                if reset_ts:
                    msg += f" Resets at Unix timestamp {reset_ts}."
                if err_body:
                    msg += f" GitHub: {err_body}"
                raise GitHubRateLimitError(msg) from None

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

    def _http_request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> Any:
        """Internal helper for dispatching GitHub REST API requests."""
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        headers = self._build_headers(token)
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                resp_bytes = response.read()
                if not resp_bytes:
                    return {}
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_data = json.loads(exc.read().decode("utf-8"))
                err_body = err_data.get("message", "")
            except Exception:
                pass

            is_rate_limit = exc.code == 429 or (
                exc.code == 403 and (
                    getattr(exc, "headers", None) and exc.headers.get("x-ratelimit-remaining") == "0"
                    or "rate limit" in err_body.lower()
                    or "rate limit" in str(getattr(exc, "reason", "")).lower()
                )
            )
            if is_rate_limit:
                msg = f"GitHub API rate limit exceeded (HTTP {exc.code})."
                reset_ts = exc.headers.get("x-ratelimit-reset") if getattr(exc, "headers", None) else None
                if reset_ts:
                    msg += f" Resets at Unix timestamp {reset_ts}."
                if err_body:
                    msg += f" GitHub: {err_body}"
                raise GitHubRateLimitError(msg) from None

            if exc.code in (401, 403):
                msg = f"GitHub authentication failed (HTTP {exc.code}). Verify Personal Access Token permissions."
                if err_body:
                    msg += f" GitHub: {err_body}"
                raise GitHubAuthError(msg) from None
            elif exc.code == 404:
                msg = f"Target GitHub resource not found (HTTP 404)."
                if err_body:
                    msg += f" GitHub: {err_body}"
                raise GitHubNotFoundError(msg) from None
            elif exc.code == 422:
                msg = f"GitHub validation failed (HTTP 422): {err_body or 'Invalid input parameters.'}"
                raise GitHubValidationError(msg) from None
            else:
                msg = f"GitHub API request failed with status code {exc.code}."
                if err_body:
                    msg += f" GitHub: {err_body}"
                raise GitHubIntegrationError(msg) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GitHubIntegrationError(
                "Unable to reach GitHub API. Please verify network connectivity."
            ) from None
        except Exception as exc:
            raise GitHubIntegrationError(
                f"Unexpected error communicating with GitHub: {type(exc).__name__}"
            ) from None

    def get_authenticated_user(self, token: str | None = None) -> dict[str, Any]:
        """Fetch the authenticated GitHub user profile (GET /user)."""
        return self._http_request("GET", "/user", token=token)

    def list_branches(
        self,
        owner: str,
        repository: str,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        """List branches in a repository (GET /repos/{owner}/{repo}/branches)."""
        res = self._http_request("GET", f"/repos/{owner}/{repository}/branches", token=token)
        return res if isinstance(res, list) else []

    def get_branch(
        self,
        owner: str,
        repository: str,
        branch: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Get branch details and commit SHA (GET /repos/{owner}/{repo}/branches/{branch})."""
        return self._http_request("GET", f"/repos/{owner}/{repository}/branches/{branch}", token=token)

    def create_branch(
        self,
        owner: str,
        repository: str,
        branch_name: str,
        from_branch: str | None = None,
        sha: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new branch in the repository (POST /repos/{owner}/{repo}/git/refs).
        If sha is not given, resolves commit SHA from from_branch or default branch.
        """
        target_sha = sha
        if not target_sha:
            base_ref = from_branch or "main"
            try:
                base_data = self.get_branch(owner, repository, base_ref, token=token)
                target_sha = base_data.get("commit", {}).get("sha")
            except Exception:
                # Try repository default branch
                repo_info = self.get_repository(owner, repository, token=token)
                base_data = self.get_branch(owner, repository, repo_info.default_branch, token=token)
                target_sha = base_data.get("commit", {}).get("sha")

        if not target_sha:
            raise GitHubValidationError(f"Could not resolve base commit SHA to create branch '{branch_name}'.")

        clean_ref = branch_name if branch_name.startswith("refs/heads/") else f"refs/heads/{branch_name}"
        payload = {"ref": clean_ref, "sha": target_sha}
        return self._http_request("POST", f"/repos/{owner}/{repository}/git/refs", data=payload, token=token)

    def list_issues(
        self,
        owner: str,
        repository: str,
        state: str = "open",
        limit: int = 30,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        """List issues in a repository (GET /repos/{owner}/{repo}/issues)."""
        res = self._http_request("GET", f"/repos/{owner}/{repository}/issues?state={state}&per_page={limit}", token=token)
        # GitHub /issues endpoint includes PRs unless filtered; filter them if needed
        return res if isinstance(res, list) else []

    def get_issue(
        self,
        owner: str,
        repository: str,
        issue_number: int,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Get a single issue (GET /repos/{owner}/{repo}/issues/{issue_number})."""
        return self._http_request("GET", f"/repos/{owner}/{repository}/issues/{issue_number}", token=token)

    def create_issue(
        self,
        owner: str,
        repository: str,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Create a new issue (POST /repos/{owner}/{repo}/issues)."""
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
        return self._http_request("POST", f"/repos/{owner}/{repository}/issues", data=payload, token=token)

    def update_issue(
        self,
        owner: str,
        repository: str,
        issue_number: int,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing issue (PATCH /repos/{owner}/{repo}/issues/{issue_number})."""
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if labels is not None:
            payload["labels"] = labels
        return self._http_request("PATCH", f"/repos/{owner}/{repository}/issues/{issue_number}", data=payload, token=token)

    def list_pull_requests(
        self,
        owner: str,
        repository: str,
        state: str = "open",
        limit: int = 30,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        """List pull requests in a repository (GET /repos/{owner}/{repo}/pulls)."""
        res = self._http_request("GET", f"/repos/{owner}/{repository}/pulls?state={state}&per_page={limit}", token=token)
        return res if isinstance(res, list) else []

    def get_pull_request(
        self,
        owner: str,
        repository: str,
        pull_number: int,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Get pull request details (GET /repos/{owner}/{repo}/pulls/{pull_number})."""
        return self._http_request("GET", f"/repos/{owner}/{repository}/pulls/{pull_number}", token=token)

    def create_pull_request(
        self,
        owner: str,
        repository: str,
        title: str,
        head: str,
        base: str | None = None,
        body: str = "",
        draft: bool = False,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Create a pull request (POST /repos/{owner}/{repo}/pulls)."""
        base_branch = base
        if not base_branch:
            repo_info = self.get_repository(owner, repository, token=token)
            base_branch = repo_info.default_branch

        payload = {
            "title": title,
            "head": head,
            "base": base_branch,
            "body": body,
            "draft": draft,
        }
        return self._http_request("POST", f"/repos/{owner}/{repository}/pulls", data=payload, token=token)

    def add_comment(
        self,
        owner: str,
        repository: str,
        issue_or_pr_number: int,
        body: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Add a comment to an issue or pull request (POST /repos/{owner}/{repo}/issues/{number}/comments)."""
        payload = {"body": body}
        return self._http_request("POST", f"/repos/{owner}/{repository}/issues/{issue_or_pr_number}/comments", data=payload, token=token)

    def get_file_contents(
        self,
        owner: str,
        repository: str,
        path: str,
        ref: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """Fetch file metadata and decoded content from repository (GET /repos/{owner}/{repo}/contents/{path})."""
        import base64
        url_path = f"/repos/{owner}/{repository}/contents/{path.lstrip('/')}"
        if ref:
            url_path += f"?ref={ref}"
        data = self._http_request("GET", url_path, token=token)
        if isinstance(data, dict) and data.get("encoding") == "base64" and data.get("content"):
            try:
                decoded = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                data["decoded_content"] = decoded
            except Exception:
                pass
        return data

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
