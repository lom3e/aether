from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import json
from aether.agents.lifecycle import AgentLifecycleState
from aether.memory.base import Memory
from aether.skills.registry import SkillRegistry
from aether.skills.skill import Skill
from aether.tools.registry import ToolRegistry


@dataclass(slots=True)
class Message:
    """
    A single message in a conversation.
    """

    role: str
    content: str
    tool_calls: list[ToolCall] | None = None

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict for HTTP payloads."""
        d = {"role": self.role, "content": self.content}
        if self.tool_calls is not None:
            d["tool_calls"] = [
                {
                    "id": tc.call_id,
                    "type": "function",
                    "function": {
                        "name": tc.tool_name,
                        "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        return d



@dataclass(slots=True)
class ToolCall:
    """
    A request by the LLM to execute a tool.
    """

    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ToolResult:
    """
    The result of executing a ToolCall.
    """

    call_id: str
    output: str
    error: str | None = None
    success: bool = True



@dataclass(slots=True)
class Task:
    """
    Minimal work unit assigned to an agent.
    """

    agent_name: str
    instruction: str
    id: str = field(default_factory=lambda: uuid4().hex)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionContext:
    """
    Runtime context available during task execution.
    """

    task: Task
    agent_name: str
    agent_state: AgentLifecycleState | None = None
    memory: Memory | None = None
    skill_registry: SkillRegistry | None = None
    tool_registry: ToolRegistry | None = None
    skills: tuple[Skill, ...] = ()
    tools: tuple[str, ...] = ()
    provider_config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionResult:
    """
    Standard result returned by the execution pipeline.
    """

    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentContext(ExecutionContext):
    """
    Mutable context tracking temporary conversation/execution state for a single run.
    """

    messages: list[Message] = field(default_factory=list)
    token_usage: dict[str, int] = field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )
    execution_state: str = "pending"
    current_turn: int = 0

    @classmethod
    def from_context(
        cls,
        context: ExecutionContext,
        messages: list[Message] | None = None,
    ) -> AgentContext:
        return cls(
            task=context.task,
            agent_name=context.agent_name,
            agent_state=context.agent_state,
            memory=context.memory,
            skill_registry=context.skill_registry,
            tool_registry=context.tool_registry,
            skills=context.skills,
            tools=context.tools,
            provider_config=context.provider_config,
            metadata=context.metadata,
            messages=messages or [],
        )

