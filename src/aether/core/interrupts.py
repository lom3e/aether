from __future__ import annotations

import uuid
from typing import Any


class AgentInterrupt(Exception):
    """
    Base class for cognitive interrupts.
    Raised when the agent must yield control to an external entity (e.g. human-in-the-loop)
    before continuing execution.
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.id = uuid.uuid4().hex
        self.message = message
        self.context = context or {}
        self.type = self.__class__.__name__


class RequireApproval(AgentInterrupt):
    """
    Raised when an action requires explicit human approval to proceed.
    """
    pass


class RequireInput(AgentInterrupt):
    """
    Raised when the agent requires specific missing input from a human to proceed.
    """
    def __init__(self, message: str, key: str, context: dict[str, Any] | None = None) -> None:
        ctx = context or {}
        ctx["input_key"] = key
        super().__init__(message, context=ctx)
        self.key = key
