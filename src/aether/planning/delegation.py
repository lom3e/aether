from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DelegationRequest:
    """
    Rappresenta l'intenzione cognitiva del parent agent di delegare un task.
    """
    goal_description: str
    success_criteria: list[str] | None = None
    constraints: list[str] | None = None
    reasoning: str | None = None
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class DelegationResult:
    """
    Rappresenta l'esito della delegazione restituito dal sub-agent.
    Mantiene l'output strutturato senza convertirlo in stringa.
    """
    success: bool
    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)
