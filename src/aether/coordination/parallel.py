from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aether.core.execution import ExecutionResult

if TYPE_CHECKING:
    from aether.coordination.coordinator import Coordinator
    from aether.core.communication import DelegationContext


@dataclass(slots=True)
class RetryPolicy:
    max_retries: int = 1
    backoff_factor: float = 0.5


def execute_with_retry(
    coordinator: Coordinator,
    agent_name: str,
    instruction: str,
    parent_task_id: str | None = None,
    parent_agent_name: str | None = None,
    delegation_context: DelegationContext | None = None,
    retry_policy: RetryPolicy | None = None,
) -> ExecutionResult:
    """
    Executes a single delegation using Coordinator.delegate, retrying on failure
    according to the specified RetryPolicy.
    """
    max_retries = retry_policy.max_retries if retry_policy else 1
    backoff_factor = retry_policy.backoff_factor if retry_policy else 0.5

    last_result = ExecutionResult(success=False, error="No execution attempt made")
    for attempt in range(max_retries):
        last_result = coordinator.delegate(
            agent_name=agent_name,
            instruction=instruction,
            parent_task_id=parent_task_id,
            parent_agent_name=parent_agent_name,
            delegation_context=delegation_context,
        )
        if last_result.success:
            return last_result

        if attempt < max_retries - 1:
            sleep_time = backoff_factor * (2**attempt)
            time.sleep(sleep_time)

    return last_result
