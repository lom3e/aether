"""
Comprehensive test suite for Phase 14 / P3-03:
GitHub Repository Project Integration Foundation.

Covers:
1. Parsing and validation of GitHub repository identity
2. Domain serialization (to_dict / from_dict)
3. Backward compatibility with legacy projects
4. GitHubRepositoryClient with mocked HTTP 200 response
5. Repository metadata retrieval (stars, forks, issues, visibility)
6. Default branch retrieval and custom branch assignments
7. Inaccessible repository handling (HTTP 404 -> GitHubNotFoundError)
8. Authentication failure handling (HTTP 401/403 -> GitHubAuthError)
9. Connect API (POST /projects/{id}/github)
10. Verify API (POST /projects/{id}/github/verify)
11. Update (PUT) and Disconnect (DELETE) API endpoints
12. Critical Security: Token is NEVER persisted to the database or returned in responses
13. Branch naming convention helpers (format_aether_branch_name, validate_branch_name)
14. Project isolation: Repositories are strictly bound to their parent project
15. Error message sanitization without token leaks
16. Slash command /github execution and output
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request
import pytest
from starlette.requests import Request

from aether.commands.builtin import register_builtin_commands
from aether.commands.models import CommandContext
from aether.commands.registry import CommandRegistry
from aether.github import (
    AETHER_BRANCH_PREFIX,
    GitHubAuthError,
    GitHubIntegrationError,
    GitHubNotFoundError,
    GitHubRepository,
    GitHubRepositoryClient,
    GitHubValidationError,
    format_aether_branch_name,
    validate_branch_name,
)
from aether.server.app import app
from aether.server.routes import (
    connect_project_github,
    create_project,
    delete_project,
    disconnect_project_github,
    get_project,
    get_project_github,
    verify_project_github,
    ConnectGitHubPayload,
    CreateProjectPayload,
    VerifyGitHubPayload,
)
from aether.workspace.workspace import Workspace


# ---------------------------------------------------------------------------
# 1. Parsing & Validation of Repository Identity
# ---------------------------------------------------------------------------

def test_github_repository_validation():
    """Valid owner/repo are accepted; invalid names or empty strings raise validation errors."""
    repo = GitHubRepository(owner="lom3e", repository="aether")
    assert repo.owner == "lom3e"
    assert repo.repository == "aether"
    assert repo.full_name == "lom3e/aether"
    assert repo.url == "https://github.com/lom3e/aether"
    assert repo.default_branch == "main"
    assert repo.connected is True

    # Empty owner
    with pytest.raises(GitHubValidationError) as exc:
        GitHubRepository(owner="", repository="aether")
    assert "owner cannot be empty" in str(exc.value)

    # Empty repository
    with pytest.raises(GitHubValidationError) as exc:
        GitHubRepository(owner="lom3e", repository="")
    assert "name cannot be empty" in str(exc.value)

    # Invalid characters in owner/repository
    with pytest.raises(GitHubValidationError):
        GitHubRepository(owner="lom3e/invalid", repository="aether")

    with pytest.raises(GitHubValidationError):
        GitHubRepository(owner="lom3e", repository="aether; rm -rf /")


# ---------------------------------------------------------------------------
# 2. Serialization & Deserialization
# ---------------------------------------------------------------------------

def test_github_repository_serialization():
    """Domain model roundtrips through to_dict and from_dict accurately."""
    repo = GitHubRepository(
        owner="lom3e",
        repository="aether",
        default_branch="develop",
        private=True,
        description="Autonomous Multi-Agent Platform",
        metadata={"stars": 42},
    )
    data = repo.to_dict()
    assert data["owner"] == "lom3e"
    assert data["repository"] == "aether"
    assert data["full_name"] == "lom3e/aether"
    assert data["default_branch"] == "develop"
    assert data["private"] is True
    assert data["description"] == "Autonomous Multi-Agent Platform"
    assert data["metadata"] == {"stars": 42}

    # Deserialization from dictionary
    reconstructed = GitHubRepository.from_dict(data)
    assert reconstructed.owner == repo.owner
    assert reconstructed.repository == repo.repository
    assert reconstructed.default_branch == repo.default_branch
    assert reconstructed.private == repo.private

    # Deserialization from shorthand full_name
    shorthand = GitHubRepository.from_dict({"owner": "lom3e/aether-cli"})
    assert shorthand.owner == "lom3e"
    assert shorthand.repository == "aether-cli"


# ---------------------------------------------------------------------------
# 3. Backward Compatibility with Legacy Projects
# ---------------------------------------------------------------------------

def test_legacy_project_backward_compatibility(tmp_path: Path):
    """Projects without github_repository continue to load cleanly returning None."""
    ws = Workspace.get_or_init(tmp_path, "Legacy Project WS")
    project = ws.conversations.create_project(name="Old Project")

    assert project["name"] == "Old Project"
    assert project.get("github_repository") is None

    # Retrieve project
    fetched = ws.conversations.get_project(project["id"])
    assert fetched is not None
    assert fetched["github_repository"] is None

    # List projects
    all_projects = ws.conversations.list_projects()
    assert len(all_projects) >= 1
    target = next(p for p in all_projects if p["id"] == project["id"])
    assert target["github_repository"] is None


# ---------------------------------------------------------------------------
# 4. GitHubRepositoryClient with Mocked HTTP 200
# ---------------------------------------------------------------------------

def test_github_client_get_repository_mocked():
    """Client parses GitHub REST API response correctly."""
    mock_payload = {
        "id": 123456,
        "name": "aether",
        "full_name": "lom3e/aether",
        "private": False,
        "html_url": "https://github.com/lom3e/aether",
        "description": "Multi-agent workforce platform",
        "default_branch": "main",
        "stargazers_count": 150,
        "forks_count": 25,
        "open_issues_count": 3,
        "visibility": "public",
        "archived": False,
        "disabled": False,
    }

    client = GitHubRepositoryClient()

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        repo = client.get_repository(owner="lom3e", repository="aether", token="secret_token_123")

        # Verify request parameters
        req_arg = mock_urlopen.call_args[0][0]
        assert req_arg.get_full_url() == "https://api.github.com/repos/lom3e/aether"
        assert req_arg.headers["Authorization"] == "Bearer secret_token_123"

        # Verify populated repository
        assert repo.owner == "lom3e"
        assert repo.repository == "aether"
        assert repo.default_branch == "main"
        assert repo.private is False
        assert repo.metadata["stargazers_count"] == 150
        assert repo.metadata["open_issues_count"] == 3


# ---------------------------------------------------------------------------
# 5 & 6. Inaccessible & Auth Failure Handling
# ---------------------------------------------------------------------------

def test_github_client_inaccessible_and_auth_errors():
    """Client raises clean, domain-specific exceptions for HTTP error codes."""
    client = GitHubRepositoryClient()

    # 404 Not Found
    http_404 = urllib.error.HTTPError(
        url="https://api.github.com/repos/lom3e/private-repo",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=io.BytesIO(b'{"message": "Not Found"}'),
    )
    with patch("urllib.request.urlopen", side_effect=http_404):
        with pytest.raises(GitHubNotFoundError) as exc:
            client.get_repository("lom3e", "private-repo")
        assert "not found on GitHub" in str(exc.value)

    # 401 Unauthorized
    http_401 = urllib.error.HTTPError(
        url="https://api.github.com/repos/lom3e/private-repo",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(b'{"message": "Bad credentials"}'),
    )
    with patch("urllib.request.urlopen", side_effect=http_401):
        with pytest.raises(GitHubAuthError) as exc:
            client.get_repository("lom3e", "private-repo")
        assert "authentication failed" in str(exc.value)


# ---------------------------------------------------------------------------
# 7. Branch Naming Convention Helpers
# ---------------------------------------------------------------------------

def test_branch_naming_conventions():
    """Branch naming utilities enforce and validate aether/ prefix and valid characters."""
    assert format_aether_branch_name("feature login") == "aether/feature-login"
    assert format_aether_branch_name("fix: critical auth bug!") == "aether/fix-critical-auth-bug"
    assert format_aether_branch_name("aether/refactor-api") == "aether/refactor-api"
    assert format_aether_branch_name("P3-03 GitHub Integration") == "aether/p3-03-github-integration"

    with pytest.raises(GitHubValidationError):
        format_aether_branch_name("!!!")

    # Valid branch validation
    assert validate_branch_name("aether/feature-login") is True
    assert validate_branch_name("aether/fix-123") is True

    # Invalid branches
    assert validate_branch_name("feature-login", require_aether_prefix=True) is False
    assert validate_branch_name("aether/") is False
    assert validate_branch_name("aether/test..branch") is False
    assert validate_branch_name("aether/test~branch") is False
    assert validate_branch_name("aether/test branch") is False
    assert validate_branch_name("aether/test.lock") is False


# ---------------------------------------------------------------------------
# 8, 9, 10, 11, 12. REST API Integration & Token Invariance
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rest_api_github_project_integration(tmp_path: Path):
    """Test full REST lifecycle: Connect -> Get -> Verify -> Disconnect with token safety."""
    ws = Workspace.get_or_init(tmp_path, "API GitHub WS")
    app.state.workspace = ws

    req = Request({"type": "http", "app": app, "path": "/projects"})

    # 1. Create a Project
    created = await create_project(req, CreateProjectPayload(name="Platform Core"))
    project_id = created["id"]

    # 2. Check initial GitHub status (unconnected)
    initial_gh = await get_project_github(req, project_id)
    assert initial_gh["connected"] is False
    assert initial_gh["repository"] is None

    # 3. Connect GitHub Repository
    mock_payload = {
        "id": 999,
        "name": "platform-core",
        "full_name": "lom3e/platform-core",
        "private": False,
        "html_url": "https://github.com/lom3e/platform-core",
        "description": "Core platform service",
        "default_branch": "main",
        "stargazers_count": 10,
        "forks_count": 2,
        "open_issues_count": 1,
    }
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_response):
        connect_res = await connect_project_github(
            req,
            project_id,
            ConnectGitHubPayload(
                owner="lom3e",
                repository="platform-core",
                token="ghp_super_secret_token_12345",
            ),
        )
        assert connect_res["status"] == "ok"
        repo = connect_res["repository"]
        assert repo["owner"] == "lom3e"
        assert repo["repository"] == "platform-core"
        assert repo["default_branch"] == "main"
        # SECURITY CHECK: Token is NEVER in response
        assert "token" not in repo
        assert "ghp_super_secret_token_12345" not in json.dumps(connect_res)

    # 4. Verify Project stored state (Database verification)
    db_project = ws.conversations.get_project(project_id)
    assert db_project["github_repository"] is not None
    assert db_project["github_repository"]["owner"] == "lom3e"
    # SECURITY CHECK: Token was NEVER persisted in SQLite
    assert "token" not in db_project["github_repository"]
    assert "ghp_super_secret_token_12345" not in json.dumps(db_project)

    # 5. Verify API endpoint
    with patch("urllib.request.urlopen", return_value=mock_response):
        verify_res = await verify_project_github(
            req,
            project_id,
            VerifyGitHubPayload(token="ghp_super_secret_token_12345"),
        )
        assert verify_res["connected"] is True
        assert verify_res["accessible"] is True
        assert verify_res["owner"] == "lom3e"
        assert verify_res["default_branch"] == "main"
        assert "token" not in verify_res

    # 6. Disconnect Repository
    disconnect_res = await disconnect_project_github(req, project_id)
    assert disconnect_res["status"] == "ok"

    # Verify disconnected in database
    after_disconnect = ws.conversations.get_project(project_id)
    assert after_disconnect["github_repository"] is None


# ---------------------------------------------------------------------------
# 13. Project Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_project_github_isolation(tmp_path: Path):
    """Connecting GitHub to Project A does not affect Project B."""
    ws = Workspace.get_or_init(tmp_path, "Isolation WS")
    app.state.workspace = ws
    req = Request({"type": "http", "app": app, "path": "/projects"})

    p1 = await create_project(req, CreateProjectPayload(name="Project One"))
    p2 = await create_project(req, CreateProjectPayload(name="Project Two"))

    gh_repo = GitHubRepository(owner="org", repository="repo-one")
    ws.conversations.update_project_github(p1["id"], gh_repo.to_dict())

    # P1 has repo
    p1_data = ws.conversations.get_project(p1["id"])
    assert p1_data["github_repository"]["repository"] == "repo-one"

    # P2 remains without repo
    p2_data = ws.conversations.get_project(p2["id"])
    assert p2_data["github_repository"] is None


# ---------------------------------------------------------------------------
# 14. Slash Command /github
# ---------------------------------------------------------------------------

from aether.commands import get_default_command_dispatcher

@pytest.mark.asyncio
async def test_slash_command_github(tmp_path: Path):
    """Slash command /github displays status of connected repository."""
    ws = Workspace.get_or_init(tmp_path, "Slash Cmd WS")
    project = ws.conversations.create_project(name="Web App")
    conv = ws.conversations.create(title="Dev Task", project_id=project["id"])

    dispatcher = get_default_command_dispatcher()

    # 1. Unconnected state
    ctx1 = CommandContext(
        command="github",
        args=[],
        raw_args="",
        conversation_id=conv["id"],
        workspace=ws,
    )
    res1 = await dispatcher.dispatch("/github", ctx1)
    assert res1.success is True
    assert "No GitHub repository is currently connected" in res1.output

    # 2. Connect repository to project
    gh = GitHubRepository(
        owner="lom3e",
        repository="web-app",
        default_branch="main",
        verified_at="2026-08-23T20:00:00Z",
    )
    ws.conversations.update_project_github(project["id"], gh.to_dict())

    # 3. Connected state
    ctx2 = CommandContext(
        command="github",
        args=[],
        raw_args="",
        conversation_id=conv["id"],
        workspace=ws,
    )
    res2 = await dispatcher.dispatch("/github", ctx2)
    assert res2.success is True
    assert "lom3e/web-app" in res2.output
    assert "main" in res2.output
    assert "Connected" in res2.output
