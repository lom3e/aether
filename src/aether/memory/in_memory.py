from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aether.memory.base import Memory


@dataclass(slots=True)
class InMemoryMemory(Memory):
    """
    Simple in-memory key-value memory store.
    """

    _store: dict[str, Any] = field(default_factory=dict)

    def remember(self, key: str, value: Any) -> None:
        self._store[key] = value

    def recall(self, key: str, default: Any | None = None) -> Any | None:
        return self._store.get(key, default)

    def forget(self, key: str) -> None:
        self._store.pop(key, None)
