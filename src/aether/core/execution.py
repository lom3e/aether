from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

import json
from aether.agents.lifecycle import AgentLifecycleState
from aether.memory.base import Memory
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aether.skills.registry import SkillRegistry
    from aether.skills.skill import Skill
    from aether.tools.registry import ToolRegistry
    from aether.core.interrupts import AgentInterrupt


@dataclass(slots=True)
class Message:
    """
    A single message in a conversation.
    """

    role: str
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

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
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        return d




@dataclass(slots=True)
class ToolCall:
    """
    A request by the LLM to execute a tool.
    """

    call_id: str
    tool_name: str
    arguments: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.arguments, dict):
            raise TypeError(
                f"ToolCall.arguments must be a dict, got {type(self.arguments).__name__}"
            )



@dataclass(slots=True)
class ToolResult:
    """
    The result of executing a ToolCall.
    """

    call_id: str
    output: str
    error: str | None = None
    success: bool = True



class ExecutionMode(StrEnum):
    """Execution mode handled by the unified Aether runtime."""
    ANSWER = "answer"      # Read-only / conversational synthesis
    DO = "do"              # Safe local mutation / document operations
    ACT = "act"            # Sensitive / external mutation (requires safety approval)
    DELEGATE = "delegate"  # Multi-agent workforce delegation
    TOOL = "tool"          # Canonical tool invocation


@dataclass(slots=True)
class Task:
    """
    Canonical work unit / execution request assigned to an agent or the Aether runtime.
    """

    instruction: str
    agent_name: str = "unknown"
    id: str = field(default_factory=lambda: uuid4().hex)
    workspace_id: str | None = None
    session_id: str | None = None
    parent_id: str | None = None
    mission_id: str | None = None
    mode: ExecutionMode | str | None = None
    action_id: str | None = None
    action_args: dict[str, Any] = field(default_factory=dict)
    context_data: dict[str, Any] = field(default_factory=dict)
    expected_output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    authority: ExecutionAuthority | None = None


# Canonical alias for unified execution requests
ExecutionRequest = Task


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
    authority: ExecutionAuthority | None = None


class ExecutionStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


@dataclass(slots=True)
class ExecutionResult:
    """
    Standard result returned by the execution pipeline.
    """

    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    status: ExecutionStatus = ExecutionStatus.COMPLETED
    interrupt: AgentInterrupt | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    deliverables: list[dict[str, Any]] = field(default_factory=list)
    child_execution_ids: list[str] = field(default_factory=list)
    execution_id: str | None = None
    mission_id: str | None = None

    def __post_init__(self):
        # Backward compatibility: automatically set status if not provided explicitly
        if not self.success and self.status == ExecutionStatus.COMPLETED:
            self.status = ExecutionStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": dict(self.metadata),
            "status": self.status.value if isinstance(self.status, ExecutionStatus) else str(self.status),
            "artifacts": list(self.artifacts),
            "deliverables": list(self.deliverables),
            "child_execution_ids": list(self.child_execution_ids),
            "execution_id": self.execution_id,
            "mission_id": self.mission_id,
        }


@dataclass(slots=True)
class ExecutionSession:
    """
    State of an active or suspended cognitive loop execution.
    """
    id: str
    goal: Any  # Actually Goal, but avoiding cyclic imports here
    context: ExecutionContext
    cognitive_plan: Any | None = None
    step_idx: int = 0
    interrupt: AgentInterrupt | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, goal: Any, context: ExecutionContext) -> ExecutionSession:
        return cls(
            id=uuid4().hex,
            goal=goal,
            context=context,
        )


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
    artifacts: list[dict[str, Any]] = field(default_factory=list)

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
            authority=context.authority,
            messages=messages or [],
        )

class ActionClassification(StrEnum):
    READ = "read"
    SAFE = "safe"
    UNKNOWN = "unknown"
    MUTATION = "mutation"
    DELEGATE = "delegate"
    EXTERNAL = "external"
    AUTONOMOUS = "autonomous"

class UnauthorizedExecutionError(Exception):
    """Raised when an operation is attempted without proper ExecutionAuthority."""
    pass

@dataclass(frozen=True, slots=True)
class ExecutionAuthority:
    """
    Opaque execution reference bound to an accepted MissionProposal.
    ExecutionAuthority is an internal reference token, NOT proof of authorization.
    All execution sinks MUST validate the authority against persistent storage via ExecutionBoundary.
    """
    proposal_id: str
    proposal_version: int
    workspace_id: str
    granted_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposal_version": self.proposal_version,
            "workspace_id": self.workspace_id,
            "granted_at": self.granted_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionAuthority:
        if not isinstance(data, dict):
            raise UnauthorizedExecutionError("ExecutionAuthority data must be a dictionary.")
        for k in ("proposal_id", "proposal_version", "workspace_id", "granted_at"):
            if k not in data or data[k] is None:
                raise UnauthorizedExecutionError(f"ExecutionAuthority missing required field '{k}'.")
        return cls(
            proposal_id=str(data["proposal_id"]),
            proposal_version=int(data["proposal_version"]),
            workspace_id=str(data["workspace_id"]),
            granted_at=str(data["granted_at"]),
        )


class ExecutionBoundary:
    """
    Canonical persistent execution boundary.
    Merely possessing or constructing an ExecutionAuthority object is never sufficient.
    validate_authority() revalidates existence, workspace ownership, version match,
    and ACCEPTED lifecycle state against persistent storage before any mutation or delegation.
    """

    @classmethod
    def issue_authority(cls, proposal: Any) -> ExecutionAuthority:
        """Issues an ExecutionAuthority for an ACCEPTED proposal."""
        from aether.planning.contracts import ProposalStatus
        status_val = getattr(proposal, "status", None)
        if isinstance(status_val, ProposalStatus):
            status_str = status_val.value
        else:
            status_str = str(status_val) if status_val is not None else ""
        if status_str != ProposalStatus.ACCEPTED.value:
            raise UnauthorizedExecutionError(
                f"Cannot issue ExecutionAuthority for proposal '{getattr(proposal, 'id', 'unknown')}' in status '{status_str}'. "
                f"Must be '{ProposalStatus.ACCEPTED.value}'."
            )
        from datetime import datetime, timezone
        return ExecutionAuthority(
            proposal_id=proposal.id,
            proposal_version=proposal.version,
            workspace_id=proposal.workspace_id,
            granted_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def validate_authority(
        cls,
        authority: ExecutionAuthority | None,
        workspace_id: str,
        store: Any,
        action_or_boundary: str | None = None,
    ) -> Any:
        """
        Validates the authority against persistent proposal state in PersonalStore.
        Revalidates:
        1. authority is provided and is an ExecutionAuthority instance
        2. authority.workspace_id matches workspace_id
        3. proposal exists in store
        4. proposal belongs to workspace_id
        5. proposal.version matches authority.proposal_version
        6. proposal.status is ACCEPTED (not DRAFT, REVOKED, SUPERSEDED, etc.)
        """
        op_name = action_or_boundary or "operation"
        if not authority:
            raise UnauthorizedExecutionError(f"Execution of '{op_name}' requires valid execution authority.")
        if not isinstance(authority, ExecutionAuthority):
            raise UnauthorizedExecutionError(
                f"Invalid authority type for '{op_name}': expected ExecutionAuthority, got {type(authority).__name__}."
            )
        if authority.workspace_id != workspace_id:
            raise UnauthorizedExecutionError(
                f"Authority workspace '{authority.workspace_id}' does not match execution workspace '{workspace_id}' for '{op_name}'."
            )

        # Resolve personal_store from store or workspace
        personal_store = getattr(store, "personal_store", store)
        if personal_store is None or not hasattr(personal_store, "get_proposal"):
            raise UnauthorizedExecutionError(
                f"No persistent PersonalStore available to validate execution authority for '{op_name}'."
            )

        proposal = personal_store.get_proposal(authority.proposal_id, workspace_id=workspace_id)
        if not proposal:
            raise UnauthorizedExecutionError(
                f"Referenced proposal '{authority.proposal_id}' does not exist in workspace '{workspace_id}'."
            )
        if proposal.workspace_id != workspace_id:
            raise UnauthorizedExecutionError(
                f"Proposal workspace '{proposal.workspace_id}' does not match execution workspace '{workspace_id}'."
            )
        if proposal.version != authority.proposal_version:
            raise UnauthorizedExecutionError(
                f"Authority version {authority.proposal_version} does not match persisted proposal version {proposal.version}."
            )

        from aether.planning.contracts import ProposalStatus
        status_val = getattr(proposal, "status", None)
        if isinstance(status_val, ProposalStatus):
            status_str = status_val.value
        else:
            status_str = str(status_val) if status_val is not None else ""

        if status_str != ProposalStatus.ACCEPTED.value:
            raise UnauthorizedExecutionError(
                f"Proposal '{proposal.id}' is not in '{ProposalStatus.ACCEPTED.value}' state (current status: '{status_str}'). "
                f"Unaccepted or revoked proposals cannot authorize execution."
            )

        return proposal

