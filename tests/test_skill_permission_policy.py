"""Tests for SkillPermissionPolicy."""

from __future__ import annotations

import pytest

from aether.errors import SkillPermissionDeniedError
from aether.skills.policy import SkillPermissionPolicy
from aether.skills.skill import SkillPermission


# ── Helpers ──────────────────────────────────────────────────────────────────

def _perm(identifier: str) -> SkillPermission:
    return SkillPermission.from_value(identifier)


# ── allow_all ────────────────────────────────────────────────────────────────


def test_allow_all_permits_any_permission() -> None:
    policy = SkillPermissionPolicy.allow_all()
    # Should not raise for any permission.
    policy.check([_perm("filesystem.read")])
    policy.check([_perm("network.connect"), _perm("filesystem.write")])
    policy.check([])  # empty list always OK


def test_allow_all_permits_unknown_permission() -> None:
    policy = SkillPermissionPolicy.allow_all()
    policy.check([_perm("totally.unknown")])


# ── deny_all ─────────────────────────────────────────────────────────────────


def test_deny_all_blocks_any_permission() -> None:
    policy = SkillPermissionPolicy.deny_all()
    with pytest.raises(SkillPermissionDeniedError):
        policy.check([_perm("filesystem.read")])


def test_deny_all_blocks_even_with_empty_permissions() -> None:
    """deny_all has special sentinel — but empty list has nothing to iterate, so no error."""
    policy = SkillPermissionPolicy.deny_all()
    # Empty list: nothing to block.
    policy.check([])  # should not raise


# ── Explicit denied set ───────────────────────────────────────────────────────


def test_denied_permission_raises() -> None:
    policy = SkillPermissionPolicy(denied={"filesystem.write"})
    with pytest.raises(SkillPermissionDeniedError, match="filesystem.write"):
        policy.check([_perm("filesystem.write")])


def test_non_denied_permission_passes() -> None:
    policy = SkillPermissionPolicy(denied={"filesystem.write"})
    policy.check([_perm("filesystem.read")])  # not denied


def test_denied_takes_priority_over_allowed() -> None:
    policy = SkillPermissionPolicy(
        allowed={"filesystem.read", "filesystem.write"},
        denied={"filesystem.write"},
    )
    with pytest.raises(SkillPermissionDeniedError, match="filesystem.write"):
        policy.check([_perm("filesystem.write")])


# ── Explicit allowed set ──────────────────────────────────────────────────────


def test_allowed_set_permits_listed_permissions() -> None:
    policy = SkillPermissionPolicy(allowed={"filesystem.read"})
    policy.check([_perm("filesystem.read")])  # in allowlist


def test_allowed_set_blocks_unlisted_permissions() -> None:
    policy = SkillPermissionPolicy(allowed={"filesystem.read"})
    with pytest.raises(SkillPermissionDeniedError, match="network.connect"):
        policy.check([_perm("network.connect")])


def test_unknown_permission_with_allowlist_raises() -> None:
    policy = SkillPermissionPolicy(allowed={"filesystem.read"})
    with pytest.raises(SkillPermissionDeniedError):
        policy.check([_perm("totally.unknown")])


def test_empty_allowlist_allows_only_empty_permissions() -> None:
    policy = SkillPermissionPolicy(allowed=set())
    policy.check([])  # empty perms pass
    with pytest.raises(SkillPermissionDeniedError):
        policy.check([_perm("filesystem.read")])


# ── Multiple permissions ──────────────────────────────────────────────────────


def test_first_denied_permission_raises() -> None:
    policy = SkillPermissionPolicy(denied={"filesystem.write"})
    with pytest.raises(SkillPermissionDeniedError):
        policy.check([_perm("filesystem.read"), _perm("filesystem.write")])


def test_all_allowed_passes_multiple() -> None:
    policy = SkillPermissionPolicy(allowed={"filesystem.read", "network.connect"})
    policy.check([_perm("filesystem.read"), _perm("network.connect")])
