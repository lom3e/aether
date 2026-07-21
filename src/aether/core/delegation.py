from __future__ import annotations

from dataclasses import dataclass, field


class DelegationError(Exception):
    """Raised when a delegation constraint is violated."""
    pass


@dataclass(slots=True)
class DelegationContext:
    """
    Tracks the delegation chain between agents to prevent infinite loops
    and enforce depth limits.
    """

    current_agent: str
    parent_agent: str | None = None
    depth: int = 0
    max_depth: int = 5
    chain: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.chain:
            self.chain = [self.current_agent]

    def delegate(self, child_agent_name: str) -> DelegationContext:
        """
        Create a new DelegationContext for a child agent.

        Raises DelegationError if:
        - The child agent is already in the delegation chain (circular delegation).
        - The maximum delegation depth would be exceeded.
        """
        new_depth = self.depth + 1
        if new_depth > self.max_depth:
            raise DelegationError(
                f"Maximum delegation depth ({self.max_depth}) exceeded. "
                f"Chain: {' -> '.join(self.chain)} -> {child_agent_name}"
            )

        if child_agent_name in self.chain:
            raise DelegationError(
                f"Circular delegation detected: {child_agent_name} is already "
                f"in the delegation chain: {' -> '.join(self.chain)}"
            )

        return DelegationContext(
            current_agent=child_agent_name,
            parent_agent=self.current_agent,
            depth=new_depth,
            max_depth=self.max_depth,
            chain=list(self.chain) + [child_agent_name],
        )
