from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aether.agents.lifecycle import AgentLifecycleState
from aether.core.execution import ExecutionContext
from aether.skills.skill import Skill


@dataclass(slots=True)
class ExecutionPolicy:
    """
    Minimal execution policy for skill validation.

    The policy is intentionally conservative and only provides a timeout
    placeholder plus basic metadata-driven validation for the v0.6 foundation.
    """

    timeout_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeout_ms is not None and self.timeout_ms <= 0:
            raise ValueError("ExecutionPolicy timeout_ms must be positive when provided.")

        self.metadata = dict(self.metadata)

    def validate(self, skill: Skill, context: ExecutionContext) -> None:
        if not skill.name.strip():
            raise ValueError("ExecutionPolicy requires a valid skill.")

        if not context.agent_name.strip():
            raise ValueError("ExecutionPolicy requires a valid agent name.")

        if context.agent_state is not None and not isinstance(context.agent_state, AgentLifecycleState):
            raise ValueError("ExecutionPolicy requires a valid agent lifecycle state.")


# ── SkillPermissionPolicy ────────────────────────────────────────────────────


class SkillPermissionPolicy:
    """
    Runtime authorization policy for executable skills.

    The policy decides whether a skill is permitted to load based on the
    permissions it declares in its manifest.  This check happens **before**
    any skill code is imported or executed.

    Usage::

        policy = SkillPermissionPolicy(denied={"filesystem.write"})
        policy.check(skill_permissions)  # raises SkillPermissionDeniedError if blocked

    Parameters:
        allowed: Explicit allowlist of permission identifiers.  When ``None``
            (the default), every permission is allowed unless it is in *denied*.
        denied: Set of permission identifiers that are always blocked, regardless
            of *allowed*.  Takes precedence over *allowed*.
    """

    def __init__(
        self,
        allowed: set[str] | None = None,
        denied: set[str] | None = None,
    ) -> None:
        self._allowed = allowed
        self._denied: set[str] = denied or set()

    # ── Factory helpers ───────────────────────────────────────────────────────

    @classmethod
    def allow_all(cls) -> "SkillPermissionPolicy":
        """Return a policy that permits every permission (no restrictions)."""
        return cls(allowed=None, denied=set())

    @classmethod
    def deny_all(cls) -> "SkillPermissionPolicy":
        """Return a policy that blocks every permission."""
        # Use a sentinel so check() always denies even unknown permissions.
        policy = cls(allowed=set(), denied=set())
        policy._deny_all = True
        return policy

    # ── Core check ───────────────────────────────────────────────────────────

    def check(self, permissions: list) -> None:
        """
        Validate that all *permissions* are allowed by this policy.

        Parameters:
            permissions: A list of :class:`~aether.skills.skill.SkillPermission`
                instances (or any object with an ``identifier`` attribute).

        Raises:
            SkillPermissionDeniedError: if any permission is denied or the policy
                requires an explicit allowlist and the permission is not on it.
        """
        from aether.errors import SkillPermissionDeniedError

        deny_all = getattr(self, "_deny_all", False)

        for perm in permissions:
            identifier = perm.identifier if hasattr(perm, "identifier") else str(perm)

            if deny_all:
                raise SkillPermissionDeniedError(
                    f"Permission '{identifier}' denied: the active policy blocks all permissions."
                )

            if identifier in self._denied:
                raise SkillPermissionDeniedError(
                    f"Permission '{identifier}' is explicitly denied by the active policy."
                )

            if self._allowed is not None and identifier not in self._allowed:
                raise SkillPermissionDeniedError(
                    f"Permission '{identifier}' is not in the allowed set of the active policy. "
                    f"Allowed: {sorted(self._allowed) or '(none)'}."
                )
