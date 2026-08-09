from __future__ import annotations

import time
from dataclasses import dataclass


from aether.errors import RuntimeSafetyError as BaseRuntimeSafetyError

class RuntimeSafetyError(BaseRuntimeSafetyError):
    """Raised when a runtime safety constraint is violated."""
    pass


@dataclass(frozen=True)
class Deadline:
    """Represents an absolute deadline in time."""
    timestamp: float

    @classmethod
    def from_timeout(cls, timeout_seconds: float) -> Deadline:
        return cls(timestamp=time.time() + timeout_seconds)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.timestamp

    @property
    def remaining(self) -> float:
        return max(0.0, self.timestamp - time.time())


class RuntimeSafetyPolicy:
    """
    Enforces objective runtime safety constraints on agent execution,
    such as maximum cognitive cycles, replans, and deadlines.
    It does NOT evaluate cognitive progress or reasoning.
    """

    def __init__(
        self,
        max_cognitive_cycles: int = 30,
        max_replans: int = 5,
        deadline: Deadline | None = None,
    ) -> None:
        self.max_cognitive_cycles = max_cognitive_cycles
        self.max_replans = max_replans
        self.deadline = deadline

        self._current_cycles = 0
        self._current_replans = 0

    def before_cycle(self) -> None:
        """Called at the beginning of each cognitive cycle."""
        self.check_deadline()
        self._current_cycles += 1
        if self._current_cycles > self.max_cognitive_cycles:
            raise RuntimeSafetyError(
                f"Maximum cognitive cycles ({self.max_cognitive_cycles}) exceeded."
            )

    def after_cycle(self) -> None:
        """Called at the end of each cognitive cycle."""
        self.check_deadline()

    def before_replan(self) -> None:
        """Called when a REPLAN decision is made or validation fails."""
        self.check_deadline()
        self._current_replans += 1
        if self._current_replans > self.max_replans:
            raise RuntimeSafetyError(
                f"Maximum replan attempts ({self.max_replans}) exceeded."
            )
            
    def reset_replans(self) -> None:
        """Called when a successful action occurs, resetting the replan counter."""
        self._current_replans = 0

    def check_deadline(self) -> None:
        """Checks if the absolute deadline has been exceeded."""
        if self.deadline and self.deadline.is_expired:
            raise RuntimeSafetyError("Absolute deadline exceeded.")
