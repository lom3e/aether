from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


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
