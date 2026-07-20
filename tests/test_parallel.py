from __future__ import annotations

import random
import threading
import time
import pytest

from aether.agents.agent import Agent
from aether.agents.registry import AgentRegistry
from aether.core.communication import DelegationContext
from aether.core.execution import Message, Task
from aether.coordination import (
    Coordinator,
    TaskTracker,
    TaskState,
    EventEmitter,
    RetryPolicy,
)
from aether.memory.semantic import SemanticMemory
from aether.memory.base import MemoryDocument
from aether.providers.base import AIProvider
from aether.providers.types import ProviderResponse
from aether.tools.agent_tool import AgentTool


# ---------------------------------------------------------------------------
# Timing Provider for Parallel Verification
# ---------------------------------------------------------------------------

class TimingProvider(AIProvider):
    @property
    def capabilities(self):
        from aether.providers.capabilities import ProviderCapabilities
        return ProviderCapabilities()

    def __init__(self, delay: float = 0.2):
        super().__init__(config=None)
        self.delay = delay
        self.start_times: list[float] = []
        self._lock = threading.Lock()

    def generate(self, messages, tools=None, output_schema=None) -> ProviderResponse:
        with self._lock:
            self.start_times.append(time.time())
        time.sleep(self.delay)
        msg = Message(role="assistant", content="timing complete")
        return ProviderResponse(
            content="timing complete",
            model="timing-model",
            usage={},
            finish_reason="stop",
            message=msg,
        )


# ---------------------------------------------------------------------------
# Failing Provider for Retry Verification
# ---------------------------------------------------------------------------

class RetryFailingProvider(AIProvider):
    @property
    def capabilities(self):
        from aether.providers.capabilities import ProviderCapabilities
        return ProviderCapabilities()

    def __init__(self, fail_count: int = 1):
        super().__init__(config=None)
        self.fail_count = fail_count
        self.attempts = 0
        self._lock = threading.Lock()

    def generate(self, messages, tools=None, output_schema=None) -> ProviderResponse:
        with self._lock:
            self.attempts += 1
            if self.attempts <= self.fail_count:
                raise RuntimeError(f"Simulated failure {self.attempts}")
        msg = Message(role="assistant", content="success after retries")
        return ProviderResponse(
            content="success after retries",
            model="retry-model",
            usage={},
            finish_reason="stop",
            message=msg,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_parallel_execution_timing() -> None:
    """
    Verify that 3 agents execute concurrently, starting at almost the exact same time
    and completing in a total time significantly less than sequential execution.
    """
    registry = AgentRegistry()
    timing_provider = TimingProvider(delay=0.3)
    
    agent_a = Agent(name="AgentA", role="worker", provider=timing_provider)
    agent_b = Agent(name="AgentB", role="worker", provider=timing_provider)
    agent_c = Agent(name="AgentC", role="worker", provider=timing_provider)
    
    registry.register(agent_a)
    registry.register(agent_b)
    registry.register(agent_c)
    
    coordinator = Coordinator(registry=registry)
    
    delegations = [
        {"agent_name": "AgentA", "instruction": "Task A"},
        {"agent_name": "AgentB", "instruction": "Task B"},
        {"agent_name": "AgentC", "instruction": "Task C"},
    ]
    
    start_wall = time.time()
    results = coordinator.delegate_parallel(delegations)
    end_wall = time.time()
    
    assert len(results) == 3
    for r in results:
        assert r.success is True
        assert r.output == "timing complete"
        
    # Check execution duration: sequentially it would be >= 0.9s
    # Concurrently it should be ~0.3s (plus thread overhead, definitely < 0.6s)
    total_time = end_wall - start_wall
    assert total_time < 0.6, f"Execution was too slow: {total_time:.2f}s"
    
    # Check start times: they should be within 50ms of each other
    start_times = timing_provider.start_times
    assert len(start_times) == 3
    start_times.sort()
    time_diff = start_times[-1] - start_times[0]
    assert time_diff < 0.05, f"Start times were not concurrent: difference was {time_diff:.4f}s"


def test_parallel_timeout() -> None:
    """
    Verify that tasks exceeding the specified timeout are marked as failed with a timeout error,
    without brutally crashing the threads.
    """
    registry = AgentRegistry()
    slow_provider = TimingProvider(delay=1.0)
    agent = Agent(name="SlowAgent", role="worker", provider=slow_provider)
    registry.register(agent)
    
    coordinator = Coordinator(registry=registry)
    delegations = [{"agent_name": "SlowAgent", "instruction": "Wait long"}]
    
    results = coordinator.delegate_parallel(delegations, timeout=0.1)
    
    assert len(results) == 1
    assert results[0].success is False
    assert "timed out" in results[0].error


def test_parallel_retry_success() -> None:
    """
    Verify that a failing agent delegation is successfully retried and eventually completes.
    """
    registry = AgentRegistry()
    retry_provider = RetryFailingProvider(fail_count=2)
    agent = Agent(name="RetryAgent", role="worker", provider=retry_provider)
    registry.register(agent)
    
    coordinator = Coordinator(registry=registry)
    delegations = [{"agent_name": "RetryAgent", "instruction": "Try again"}]
    
    # Max retries = 3 means 3 attempts total. It fails 2 times, then succeeds on attempt 3.
    policy = RetryPolicy(max_retries=3, backoff_factor=0.01)
    results = coordinator.delegate_parallel(delegations, retry_policy=policy)
    
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].output == "success after retries"


def test_parallel_retry_failure() -> None:
    """
    Verify that if the failure count exceeds max retries, the final ExecutionResult is returned with error.
    """
    registry = AgentRegistry()
    retry_provider = RetryFailingProvider(fail_count=3)
    agent = Agent(name="FailingRetryAgent", role="worker", provider=retry_provider)
    registry.register(agent)
    
    coordinator = Coordinator(registry=registry)
    delegations = [{"agent_name": "FailingRetryAgent", "instruction": "Fail anyway"}]
    
    # Max retries = 2. Attempts 1 & 2 fail. Attempt 3 won't happen.
    policy = RetryPolicy(max_retries=2, backoff_factor=0.01)
    results = coordinator.delegate_parallel(delegations, retry_policy=policy)
    
    assert len(results) == 1
    assert results[0].success is False
    assert "Simulated failure 2" in results[0].error


def test_semantic_memory_thread_safety() -> None:
    """
    Concurrently write, search, and clear SemanticMemory to verify SQLite lock protection.
    """
    mem = SemanticMemory()
    errors: list[Exception] = []
    
    def worker() -> None:
        try:
            for _ in range(50):
                action = random.choice(["add", "search", "clear"])
                if action == "add":
                    doc = MemoryDocument(content=f"content {random.randint(1, 100)}")
                    mem.add(doc)
                elif action == "search":
                    mem.search("content")
                elif action == "clear":
                    mem.clear()
        except Exception as exc:
            errors.append(exc)
            
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    assert len(errors) == 0, f"Concurrent database exceptions: {errors}"


def test_task_id_isolation() -> None:
    """
    Verify that parallel coordinator delegations have unique, isolated task IDs.
    """
    registry = AgentRegistry()
    timing_provider = TimingProvider(delay=0.1)
    agent_a = Agent(name="AgentA", role="worker", provider=timing_provider)
    agent_b = Agent(name="AgentB", role="worker", provider=timing_provider)
    
    registry.register(agent_a)
    registry.register(agent_b)
    
    tracker = TaskTracker()
    coordinator = Coordinator(registry=registry, tracker=tracker)
    
    delegations = [
        {"agent_name": "AgentA", "instruction": "Task A"},
        {"agent_name": "AgentB", "instruction": "Task B"},
    ]
    
    results = coordinator.delegate_parallel(delegations)
    assert len(results) == 2
    
    records = tracker.get_children(None)
    assert len(records) == 2
    assert records[0].task_id != records[1].task_id
    assert records[0].state == TaskState.COMPLETED
    assert records[1].state == TaskState.COMPLETED


def test_retrocompatibility_agent_tool() -> None:
    """
    Ensure that AgentTool still works correctly with v0.14.0 updates.
    """
    child = Agent(name="ChildAgent", role="worker", provider=TimingProvider(delay=0.01))
    tool = AgentTool(agent=child)
    res = tool.execute("Some instruction")
    assert res == "timing complete"


