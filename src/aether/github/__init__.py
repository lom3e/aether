"""
Aether GitHub Integration Subsystem (P3-03).
"""
from aether.github.branch import (
    AETHER_BRANCH_PREFIX,
    format_aether_branch_name,
    validate_branch_name,
)
from aether.github.client import GitHubRepositoryClient
from aether.github.models import (
    GitHubAuthError,
    GitHubIntegrationError,
    GitHubNotFoundError,
    GitHubRepository,
    GitHubValidationError,
)

__all__ = [
    "AETHER_BRANCH_PREFIX",
    "GitHubAuthError",
    "GitHubIntegrationError",
    "GitHubNotFoundError",
    "GitHubRepository",
    "GitHubRepositoryClient",
    "GitHubValidationError",
    "format_aether_branch_name",
    "validate_branch_name",
]
