from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


from enum import StrEnum


class ToolClassification(StrEnum):
    READ_ONLY = "read_only"
    LOCAL_MUTATION = "local_mutation"
    EXTERNAL_MUTATION = "external_mutation"
    SENSITIVE_MUTATION = "sensitive_mutation"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, val: str) -> ToolClassification:
        try:
            return cls(str(val).lower().strip())
        except (ValueError, AttributeError):
            return cls.UNKNOWN


@dataclass(slots=True)
class ToolExecutionContext:
    """
    Minimal context passed to tools when they are executed.
    """

    agent_name: str | None = None
    task_id: str | None = None
    workspace_id: str | None = None
    authority: Any = None
    store: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)


class Tool(ABC):
    """
    Contract for tools available to agents.
    """

    name: str
    description: str = ""
    classification: ToolClassification = ToolClassification.UNKNOWN

    @abstractmethod
    def execute(self, input_data: str, context: ToolExecutionContext | None = None) -> str:
        raise NotImplementedError

    def to_json_schema(self) -> dict[str, Any]:
        """
        Return the JSON Schema representation of this tool's parameters.
        Default implementation assumes a single required 'input_data' string parameter.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_data": {
                            "type": "string",
                            "description": "Input data for the tool.",
                        }
                    },
                    "required": ["input_data"],
                },
            },
        }

