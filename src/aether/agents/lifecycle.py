from __future__ import annotations

from enum import Enum


class AgentLifecycleState(str, Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentLifecycle:
    """
    Minimal lifecycle tracker for agent execution.
    """

    def __init__(self) -> None:
        self.state = AgentLifecycleState.CREATED

    def initialize(self) -> AgentLifecycleState:
        self.state = AgentLifecycleState.INITIALIZED
        return self.state

    def ready(self) -> AgentLifecycleState:
        self.state = AgentLifecycleState.READY
        return self.state

    def start(self) -> AgentLifecycleState:
        self.state = AgentLifecycleState.RUNNING
        return self.state

    def complete(self) -> AgentLifecycleState:
        self.state = AgentLifecycleState.COMPLETED
        return self.state

    def fail(self) -> AgentLifecycleState:
        self.state = AgentLifecycleState.FAILED
        return self.state
