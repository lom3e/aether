"""
Branch naming conventions and validation for Aether GitHub workflows (P3-03).
"""
from __future__ import annotations

import re
from aether.github.models import GitHubValidationError

AETHER_BRANCH_PREFIX = "aether/"

# Git branch naming restrictions (ref: git check-ref-format)
_ILLEGAL_GIT_CHARS = re.compile(r"[\s~^:?*\[\\@{]|//|\.\.|\.lock$")


def format_aether_branch_name(purpose: str) -> str:
    """
    Format a human-readable purpose into a valid, canonical Aether branch name.

    Examples:
        format_aether_branch_name("feature login") -> "aether/feature-login"
        format_aether_branch_name("fix: auth token!") -> "aether/fix-auth-token"
        format_aether_branch_name("aether/refactor-api") -> "aether/refactor-api"
    """
    clean = str(purpose or "").strip()
    if clean.startswith(AETHER_BRANCH_PREFIX):
        clean = clean[len(AETHER_BRANCH_PREFIX):]

    # Convert non-alphanumerics (excluding hyphens/underscores) to hyphens
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", clean)
    # Collapse multiple consecutive hyphens or underscores
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-._").lower()

    if not slug:
        raise GitHubValidationError("Branch purpose cannot be empty or consist only of special characters.")

    return f"{AETHER_BRANCH_PREFIX}{slug}"


def validate_branch_name(branch_name: str, require_aether_prefix: bool = True) -> bool:
    """
    Validate that a branch name conforms to Git standards and Aether conventions.

    Parameters:
        branch_name: The branch name string to check.
        require_aether_prefix: When True, enforces that the branch starts with 'aether/'.
    """
    if not branch_name or not isinstance(branch_name, str):
        return False

    name = branch_name.strip()
    if not name or len(name) > 250:
        return False

    if require_aether_prefix:
        if not name.startswith(AETHER_BRANCH_PREFIX):
            return False
        sub = name[len(AETHER_BRANCH_PREFIX):]
        if not sub or sub.startswith("/") or sub.endswith("/"):
            return False

    # Git ref format rules:
    # 1. Cannot start or end with a slash or period
    if name.startswith("/") or name.endswith("/") or name.startswith(".") or name.endswith("."):
        return False

    # 2. Cannot contain illegal git characters
    if _ILLEGAL_GIT_CHARS.search(name):
        return False

    # 3. Cannot contain control characters (ASCII 0-31 or 127)
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        return False

    return True
