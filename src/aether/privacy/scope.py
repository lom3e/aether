"""Per-request collection of what a request sent out, so the answer can carry it ("what left the computer for this reply")."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class EgressScope:
    session_id: str | None = None
    purpose: str | None = None
    unmasked: bool = False  # the user explicitly chose to send this request without masking
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)

    def summary(self) -> dict[str, Any] | None:
        if not self.entries:
            return None
        cloud = [e for e in self.entries if not e["local"]]
        red: dict[str, int] = {}
        for e in cloud:
            for k, v in e["redactions"].items():
                red[k] = red.get(k, 0) + v
        return {
            "ids": [e["id"] for e in self.entries],
            "requests": len(self.entries),
            "local_only": not cloud,
            "providers": sorted({e["provider"] for e in cloud}) or sorted({e["provider"] for e in self.entries}),
            "models": sorted({e["model"] for e in self.entries if e.get("model")}),
            "images": sum(e["images"] for e in cloud),
            "chars": sum(e["chars"] for e in cloud),
            "redactions": red,
            "redactions_total": sum(red.values()),
            "unmasked": any(e.get("unmasked") for e in cloud),
        }


_current: ContextVar[EgressScope | None] = ContextVar("aether_egress_scope", default=None)


def current_scope() -> EgressScope | None:
    return _current.get()


@contextmanager
def egress_scope(session_id: str | None = None, purpose: str | None = None, unmasked: bool = False) -> Iterator[EgressScope]:
    scope = EgressScope(session_id=session_id, purpose=purpose, unmasked=unmasked)
    token = _current.set(scope)
    try:
        yield scope
    finally:
        _current.reset(token)
