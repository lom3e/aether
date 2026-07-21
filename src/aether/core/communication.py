from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class MessageType(Enum):
    """Types of inter-agent messages."""
    TASK_DELEGATION = "task_delegation"
    TASK_RESULT = "task_result"
    INFO = "info"


@dataclass(slots=True)
class AgentMessage:
    """
    Provider-agnostic communication contract between agents.
    """

    sender: str
    receiver: str
    content: str
    message_type: MessageType = MessageType.INFO
    parent_task_id: str | None = None
    message_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "parent_task_id": self.parent_task_id,
            "message_type": self.message_type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentMessage:
        return cls(
            message_id=data["message_id"],
            sender=data["sender"],
            receiver=data["receiver"],
            parent_task_id=data.get("parent_task_id"),
            message_type=MessageType(data["message_type"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )



# Backward compatibility re-export
from .delegation import DelegationContext, DelegationError

__all__ = [
    "MessageType",
    "AgentMessage",
    "DelegationContext",
    "DelegationError",
]
