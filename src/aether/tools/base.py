from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolExecutionContext:
    """
    Minimal context passed to tools when they are executed.
    """

    agent_name: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """
    Contract for tools available to agents.
    """

    name: str
    description: str = ""

    @abstractmethod
    def execute(self, input_data: str, context: ToolExecutionContext | None = None) -> str:
        raise NotImplementedError
