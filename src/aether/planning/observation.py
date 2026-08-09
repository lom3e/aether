from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from aether.planning.types import Observation
from aether.core.execution import ExecutionResult


class ObservationBudget(ABC):
    """Abstract base class for observation capacity limits."""

    @abstractmethod
    def enforce(self, payload: Any) -> tuple[Any, bool]:
        """
        Enforces the budget on the given payload.
        Returns a tuple of (enforced_payload, was_truncated).
        """
        pass


class CharacterBudget(ObservationBudget):
    """A budget based on the maximum number of characters."""

    def __init__(self, max_chars: int = 50000) -> None:
        self.max_chars = max_chars

    def enforce(self, payload: Any) -> tuple[Any, bool]:
        is_structured = isinstance(payload, (dict, list))
        
        # Convert payload to string to measure characters
        if isinstance(payload, str):
            text = payload
        else:
            try:
                text = json.dumps(payload, ensure_ascii=False)
            except Exception:
                text = str(payload)
                is_structured = False # If it couldn't be json dumped, treat as string fallback

        if len(text) <= self.max_chars:
            return payload, False

        # If truncated, we return a diagnostic structure for dict/list, or string for string
        if is_structured:
            fallback = {
                "error": "payload_truncated",
                "reason": "character_budget_exceeded",
                "original_size": len(text)
            }
            return fallback, True
        else:
            truncated_text = text[:self.max_chars]
            return truncated_text, True


class ObservationFactory:
    """
    Constructs Observations, applying budgets
    and attaching technical metadata.
    Does NOT contain cognitive logic or LLM-specific hints.
    """

    def __init__(self, budget: ObservationBudget | None = None) -> None:
        # Default to a safe limit if no budget is provided
        self.budget = budget or CharacterBudget(max_chars=50000)

    def create(
        self,
        plan_id: str,
        step_id: str,
        action_taken: str,
        payload: Any,
        is_error: bool = False,
    ) -> Observation:
        """
        Creates an Observation from arbitrary payload.
        """
        # Apply budget
        enforced_payload, was_truncated = self.budget.enforce(payload)

        # Build technical metadata
        metadata: dict[str, Any] = {}
        if was_truncated:
            metadata["truncated"] = True
            
            # Try to guess original size for technical metadata
            if isinstance(payload, str):
                metadata["original_size"] = len(payload)
            else:
                try:
                    metadata["original_size"] = len(json.dumps(payload))
                except Exception:
                    metadata["original_size"] = len(str(payload))

        return Observation(
            plan_id=plan_id,
            step_id=step_id,
            action_taken=action_taken,
            result=enforced_payload,
            is_error=is_error,
            metadata=metadata,
        )

