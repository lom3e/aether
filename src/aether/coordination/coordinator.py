from __future__ import annotations

from typing import Any
from uuid import uuid4

from aether.agents.registry import AgentRegistry
from aether.core.communication import DelegationContext, DelegationError
from aether.core.execution import Task, ExecutionResult
from aether.coordination.events import EventEmitter, AgentEvent, EventType
from aether.coordination.task_tracker import TaskTracker, TaskState
from aether.coordination.message_bus import AgentMessageBus


class Coordinator:
    """
    Structured orchestrator coordinating multi-agent task execution, tracking, and event emission.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        message_bus: AgentMessageBus | None = None,
        tracker: TaskTracker | None = None,
        emitter: EventEmitter | None = None,
    ) -> None:
        self.registry = registry
        self.message_bus = message_bus
        self.tracker = tracker
        self.emitter = emitter

    def delegate(
        self,
        agent_name: str,
        instruction: str,
        parent_task_id: str | None = None,
        parent_agent_name: str | None = None,
        delegation_context: DelegationContext | None = None,
    ) -> ExecutionResult:
        """
        Delegate a task to a registered child agent with tracking, isolation, and safety checks.
        """
        # 1. Resolve agent
        try:
            agent = self.registry.resolve(agent_name)
        except (KeyError, ValueError) as exc:
            return ExecutionResult(
                success=False,
                error=f"Failed to resolve agent '{agent_name}': {str(exc)}",
            )

        task_id = uuid4().hex

        # 2. Track creation
        if self.tracker is not None:
            self.tracker.create(task_id, parent_task_id, agent_name)
            self.tracker.transition(task_id, TaskState.ASSIGNED)

        # 3. Emit delegated event
        if self.emitter is not None:
            self.emitter.emit(
                AgentEvent(
                    event_type=EventType.TASK_DELEGATED,
                    agent_name=agent_name,
                    task_id=task_id,
                    metadata={"parent_task_id": parent_task_id, "instruction": instruction},
                )
            )

        # 4. Delegation context safety check
        if delegation_context is not None:
            try:
                child_ctx = delegation_context.delegate(agent_name)
            except DelegationError as exc:
                if self.tracker is not None:
                    self.tracker.transition(task_id, TaskState.FAILED, error=str(exc))
                if self.emitter is not None:
                    self.emitter.emit(
                        AgentEvent(
                            event_type=EventType.AGENT_FAILED,
                            agent_name=agent_name,
                            task_id=task_id,
                            metadata={"error": str(exc)},
                        )
                    )
                return ExecutionResult(
                    success=False,
                    error=f"[DELEGATION ERROR] {str(exc)}",
                )
        else:
            p_name = parent_agent_name or "Coordinator"
            child_ctx = DelegationContext(
                current_agent=agent_name,
                parent_agent=p_name,
                depth=1,
                chain=[p_name, agent_name],
            )

        # Propagate delegation context to any AgentTool the child agent may have
        if agent.tool_registry:
            for tool in agent.tool_registry.list_tools():
                from aether.tools.agent_tool import AgentTool
                if isinstance(tool, AgentTool):
                    tool._delegation_context = child_ctx

        # 5. Run the agent
        if self.tracker is not None:
            self.tracker.transition(task_id, TaskState.RUNNING)

        if self.emitter is not None:
            self.emitter.emit(
                AgentEvent(
                    event_type=EventType.AGENT_STARTED,
                    agent_name=agent_name,
                    task_id=task_id,
                )
            )

        sub_task = Task(
            agent_name=agent_name,
            instruction=instruction,
            id=task_id,
            metadata={
                "parent_task_id": parent_task_id,
                "delegation_depth": child_ctx.depth,
                "delegation_chain": child_ctx.chain,
            },
        )

        try:
            result = agent.execute(sub_task)
        except Exception as exc:
            if self.tracker is not None:
                self.tracker.transition(task_id, TaskState.FAILED, error=str(exc))
            if self.emitter is not None:
                self.emitter.emit(
                    AgentEvent(
                        event_type=EventType.AGENT_FAILED,
                        agent_name=agent_name,
                        task_id=task_id,
                        metadata={"error": str(exc)},
                    )
                )
            return ExecutionResult(
                success=False,
                error=f"[AGENT ERROR] {str(exc)}",
            )

        # 6. Finalize tracking and events
        if result.success:
            if self.tracker is not None:
                self.tracker.transition(task_id, TaskState.COMPLETED, result=result.output)
            if self.emitter is not None:
                self.emitter.emit(
                    AgentEvent(
                        event_type=EventType.TASK_COMPLETED,
                        agent_name=agent_name,
                        task_id=task_id,
                        metadata={"output": result.output},
                    )
                )
        else:
            if self.tracker is not None:
                self.tracker.transition(task_id, TaskState.FAILED, error=result.error)
            if self.emitter is not None:
                self.emitter.emit(
                    AgentEvent(
                        event_type=EventType.AGENT_FAILED,
                        agent_name=agent_name,
                        task_id=task_id,
                        metadata={"error": result.error},
                    )
                )

        return result
