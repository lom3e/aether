from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


class Memory(ABC):
    """
    Base contract for agent memory.
    """

    @abstractmethod
    def remember(self, key: str, value: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def recall(self, key: str, default: Any | None = None) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    def forget(self, key: str) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class MemoryDocument:
    """
    Represent a unit of long-term semantic memory.
    """
    content: str
    id: str = field(default_factory=lambda: uuid4().hex)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class BaseMemoryStore(ABC):
    """
    Base abstract class for Aether memory stores.
    """
    pass
