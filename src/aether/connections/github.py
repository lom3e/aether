"""
GitHub Connector for Aether (Phase C & Sprint 1).
Provides real read and mutation capabilities against GitHub repositories with audit,
credential isolation, and normalized error handling.
"""
from __future__ import annotations

import logging
from typing import Any

from aether.connections.base import (
    BaseConnector,
    ConnectorAuthError,
    ConnectorConfigurationError,
    ConnectorError,
    ConnectorHealth,
    ConnectorNotFoundError,
    ConnectorResult,
    CredentialRequirement,
)
from aether.connections.models import ConnectionStatus
from aether.github.branch import format_aether_branch_name, validate_branch_name
from aether.github.client import GitHubRepositoryClient
from aether.github.models import (
    GitHubAuthError,
    GitHubIntegrationError,
    GitHubNotFoundError,
    GitHubValidationError,
)

logger = logging.getLogger(__name__)


class GitHubConnector(BaseConnector):
    """
    Real GitHub connector implementing repository reads and external mutations.
    """

    def __init__(
        self,
        auth_metadata: dict[str, Any] | None = None,
        default_owner: str | None = None,
        default_repo: str | None = None,
        client: GitHubRepositoryClient | None = None,
    ) -> None:
        self._auth_metadata = dict(auth_metadata or {})
        self.default_owner = default_owner
        self.default_repo = default_repo
        self.client = client or GitHubRepositoryClient()

    @property
    def provider(self) -> str:
        return "github"

    @property
    def capabilities(self) -> list[str]:
        return [
            "github.inspect_repo",
            "github.list_branches",
            "github.get_branch",
            "github.create_branch",
            "github.list_issues",
            "github.get_issue",
            "github.create_issue",
            "github.update_issue",
            "github.list_pull_requests",
            "github.get_pull_request",
            "github.create_pull_request",
            "github.add_comment",
            "github.get_file",
        ]

    @property
    def credential_requirements(self) -> list[CredentialRequirement]:
        return [
            CredentialRequirement(
                key="token",
                label="Personal Access Token (PAT)",
                description="GitHub token with repo permissions (e.g. ghp_... or github_pat_...).",
                required=True,
                secret=True,
            ),
            CredentialRequirement(
                key="default_owner",
                label="Default Owner / Org",
                description="Optional default repository owner or organization.",
                required=False,
                secret=False,
            ),
            CredentialRequirement(
                key="default_repo",
                label="Default Repository",
                description="Optional default repository name.",
                required=False,
                secret=False,
            ),
        ]

    def _get_token(self, params: dict[str, Any] | None = None) -> str | None:
        explicit = None
        if params and "token" in params:
            explicit = str(params["token"]).strip()
        if not explicit:
            explicit = str(self._auth_metadata.get("token") or self._auth_metadata.get("pat") or "").strip()
        return explicit or None

    def _resolve_target(self, params: dict[str, Any]) -> tuple[str, str]:
        owner = str(params.get("owner") or self.default_owner or self._auth_metadata.get("default_owner") or "").strip()
        repo = str(params.get("repository") or params.get("repo") or self.default_repo or self._auth_metadata.get("default_repo") or "").strip()
        
        # Support full_name (e.g. "lom3e/aether")
        full_name = str(params.get("full_name") or "").strip()
        if "/" in full_name:
            p_owner, p_repo = full_name.split("/", 1)
            owner, repo = p_owner.strip(), p_repo.strip()
        elif "/" in owner and not repo:
            p_owner, p_repo = owner.split("/", 1)
            owner, repo = p_owner.strip(), p_repo.strip()

        if not owner or not repo:
            raise ConnectorConfigurationError(
                "Both repository owner and name are required for this GitHub operation.",
                provider=self.provider,
            )
        return owner, repo

    def verify(self, auth_metadata: dict[str, Any] | None = None, live_check: bool = False) -> tuple[bool, str]:
        meta = auth_metadata or self._auth_metadata
        token = str(meta.get("token") or meta.get("pat") or meta.get("api_key") or "").strip()
        if not token:
            return False, "GitHub Personal Access Token (PAT) is required."
        if not (token.startswith("ghp_") or token.startswith("github_pat_") or len(token) >= 20):
            return False, "Invalid GitHub token format. Must be a Personal Access Token (e.g. starting with 'ghp_' or 'github_pat_')."

        if live_check or meta.get("live_check"):
            try:
                user_data = self.client.get_authenticated_user(token=token)
                login = user_data.get("login") or "user"
                return True, f"GitHub authentication verified for @{login}."
            except GitHubAuthError as exc:
                return False, str(exc)
            except Exception as exc:
                return False, f"GitHub live verification failed: {exc}"

        return True, "GitHub Personal Access Token format verified."

    def get_health(self) -> ConnectorHealth:
        token = self._get_token()
        if not token:
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.NEEDS_AUTH,
                message="GitHub token is not configured.",
            )
        valid, msg = self.verify()
        return ConnectorHealth(
            healthy=valid,
            status=ConnectionStatus.CONNECTED if valid else ConnectionStatus.ERROR,
            message=msg,
        )

    def execute(self, operation: str, params: dict[str, Any]) -> ConnectorResult:
        token = self._get_token(params)
        clean_op = operation.lower().strip()

        try:
            if clean_op in ("github.inspect_repo", "inspect_repo", "get_repository"):
                owner, repo = self._resolve_target(params)
                repo_obj = self.client.get_repository(owner, repo, token=token)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data=repo_obj.to_dict(),
                )

            elif clean_op in ("github.list_branches", "list_branches"):
                owner, repo = self._resolve_target(params)
                branches = self.client.list_branches(owner, repo, token=token)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data={"branches": branches, "count": len(branches)},
                )

            elif clean_op in ("github.get_branch", "get_branch"):
                owner, repo = self._resolve_target(params)
                branch_name = str(params.get("branch") or params.get("branch_name") or "main").strip()
                branch_data = self.client.get_branch(owner, repo, branch_name, token=token)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data=branch_data,
                )

            elif clean_op in ("github.create_branch", "create_branch"):
                owner, repo = self._resolve_target(params)
                branch_name = str(params.get("branch_name") or params.get("branch") or "").strip()
                if not branch_name:
                    raise ConnectorError("branch_name is required.", provider=self.provider)
                # Auto-format to valid aether branch if purpose string given
                if not branch_name.startswith("aether/") and not validate_branch_name(branch_name, require_aether_prefix=False):
                    branch_name = format_aether_branch_name(branch_name)

                from_branch = params.get("from_branch")
                sha = params.get("sha")
                created = self.client.create_branch(owner, repo, branch_name, from_branch=from_branch, sha=sha, token=token)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data={
                        "ref": created.get("ref", f"refs/heads/{branch_name}"),
                        "branch_name": branch_name,
                        "node_id": created.get("node_id"),
                        "url": created.get("url"),
                        "status": "created",
                    },
                )

            elif clean_op in ("github.list_issues", "list_issues"):
                owner, repo = self._resolve_target(params)
                state = str(params.get("state", "open")).strip()
                limit = int(params.get("limit", 30))
                issues = self.client.list_issues(owner, repo, state=state, limit=limit, token=token)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data={"issues": issues, "count": len(issues)},
                )

            elif clean_op in ("github.get_issue", "get_issue"):
                owner, repo = self._resolve_target(params)
                number = int(params.get("issue_number") or params.get("number") or 0)
                if not number:
                    raise ConnectorError("issue_number is required.", provider=self.provider)
                issue = self.client.get_issue(owner, repo, number, token=token)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data=issue,
                )

            elif clean_op in ("github.create_issue", "create_issue"):
                owner, repo = self._resolve_target(params)
                title = str(params.get("title") or "").strip()
                if not title:
                    raise ConnectorError("Issue title is required.", provider=self.provider)
                body = str(params.get("body") or "")
                labels = params.get("labels")
                assignees = params.get("assignees")
                created_issue = self.client.create_issue(
                    owner, repo, title=title, body=body, labels=labels, assignees=assignees, token=token
                )
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data={
                        "id": created_issue.get("id"),
                        "number": created_issue.get("number"),
                        "title": created_issue.get("title"),
                        "html_url": created_issue.get("html_url"),
                        "state": created_issue.get("state", "open"),
                        "status": "created",
                    },
                )

            elif clean_op in ("github.update_issue", "update_issue"):
                owner, repo = self._resolve_target(params)
                number = int(params.get("issue_number") or params.get("number") or 0)
                if not number:
                    raise ConnectorError("issue_number is required.", provider=self.provider)
                updated = self.client.update_issue(
                    owner, repo, number,
                    title=params.get("title"),
                    body=params.get("body"),
                    state=params.get("state"),
                    labels=params.get("labels"),
                    token=token,
                )
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data=updated,
                )

            elif clean_op in ("github.list_pull_requests", "list_pull_requests"):
                owner, repo = self._resolve_target(params)
                state = str(params.get("state", "open")).strip()
                limit = int(params.get("limit", 30))
                prs = self.client.list_pull_requests(owner, repo, state=state, limit=limit, token=token)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data={"pull_requests": prs, "count": len(prs)},
                )

            elif clean_op in ("github.get_pull_request", "get_pull_request"):
                owner, repo = self._resolve_target(params)
                number = int(params.get("pull_number") or params.get("number") or 0)
                if not number:
                    raise ConnectorError("pull_number is required.", provider=self.provider)
                pr = self.client.get_pull_request(owner, repo, number, token=token)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data=pr,
                )

            elif clean_op in ("github.create_pull_request", "create_pull_request"):
                owner, repo = self._resolve_target(params)
                title = str(params.get("title") or "").strip()
                head = str(params.get("head") or "").strip()
                if not title or not head:
                    raise ConnectorError("PR title and head branch are required.", provider=self.provider)
                base = params.get("base")
                body = str(params.get("body") or "")
                draft = bool(params.get("draft", False))
                created_pr = self.client.create_pull_request(
                    owner, repo, title=title, head=head, base=base, body=body, draft=draft, token=token
                )
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data={
                        "id": created_pr.get("id"),
                        "number": created_pr.get("number"),
                        "title": created_pr.get("title"),
                        "html_url": created_pr.get("html_url"),
                        "head": head,
                        "base": base,
                        "status": "created",
                    },
                )

            elif clean_op in ("github.add_comment", "add_comment"):
                owner, repo = self._resolve_target(params)
                number = int(params.get("issue_or_pr_number") or params.get("number") or params.get("issue_number") or 0)
                body = str(params.get("body") or "").strip()
                if not number or not body:
                    raise ConnectorError("issue_or_pr_number and body are required.", provider=self.provider)
                comment = self.client.add_comment(owner, repo, number, body, token=token)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data={"id": comment.get("id"), "url": comment.get("html_url"), "status": "posted"},
                )

            elif clean_op in ("github.get_file", "get_file_contents", "get_file"):
                owner, repo = self._resolve_target(params)
                path = str(params.get("path") or "").strip()
                if not path:
                    raise ConnectorError("File path is required.", provider=self.provider)
                ref = params.get("ref")
                content = self.client.get_file_contents(owner, repo, path, ref=ref, token=token)
                return ConnectorResult(
                    success=True,
                    operation=operation,
                    provider=self.provider,
                    data=content,
                )

            else:
                raise ConnectorError(f"Unsupported GitHub operation: '{operation}'", provider=self.provider)

        except GitHubAuthError as exc:
            raise ConnectorAuthError(str(exc), provider=self.provider) from None
        except GitHubNotFoundError as exc:
            raise ConnectorNotFoundError(str(exc), provider=self.provider) from None
        except (GitHubValidationError, ConnectorConfigurationError) as exc:
            raise ConnectorError(str(exc), provider=self.provider) from None
        except GitHubIntegrationError as exc:
            raise ConnectorError(str(exc), provider=self.provider) from None
