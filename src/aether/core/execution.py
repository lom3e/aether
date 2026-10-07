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

def compute_args_digest(input_data: dict[str, Any] | None) -> str:
    """Computes a deterministic SHA-256 digest of action/tool arguments."""
    import hashlib
    import json
    if not input_data:
        return hashlib.sha256(b"{}").hexdigest()
    try:
        canonical = json.dumps(input_data, sort_keys=True, default=str).encode("utf-8")
    except Exception:
        canonical = str(sorted(input_data.items())).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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
    expires_at: str | None = None
    step_id: str | None = None
    args_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "proposal_id": self.proposal_id,
            "proposal_version": self.proposal_version,
            "workspace_id": self.workspace_id,
            "granted_at": self.granted_at,
        }
        if self.expires_at is not None:
            d["expires_at"] = self.expires_at
        if self.step_id is not None:
            d["step_id"] = self.step_id
        if self.args_digest is not None:
            d["args_digest"] = self.args_digest
        return d

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
            expires_at=str(data["expires_at"]) if data.get("expires_at") else None,
            step_id=str(data["step_id"]) if data.get("step_id") else None,
            args_digest=str(data["args_digest"]) if data.get("args_digest") else None,
        )


class ExecutionBoundary:
    """
    Canonical persistent execution boundary.
    Merely possessing or constructing an ExecutionAuthority object is never sufficient.
    validate_authority() revalidates existence, workspace ownership, version match,
    and ACCEPTED lifecycle state against persistent storage before any mutation or delegation.
    """

    @classmethod
    def issue_authority(
        cls,
        proposal: Any,
        expires_at: str | None = None,
        step_id: str | None = None,
        args_digest: str | None = None,
    ) -> ExecutionAuthority:
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

        # Ensure proposal is not completely unconstrained / blanket authority
        proposed_steps = getattr(proposal, "proposed_steps", None) or []
        required_approvals = getattr(proposal, "required_approvals", None) or []
        raw_constraints = getattr(proposal, "constraints", None) or []
        has_scope_constraint = any(bool(str(c).strip()) for c in raw_constraints)
        if not proposed_steps and not required_approvals and not has_scope_constraint:
            raise UnauthorizedExecutionError(
                f"Blanket/unbounded execution authority is prohibited for proposal '{getattr(proposal, 'id', 'unknown')}'. "
                f"Proposal must specify proposed steps, required approvals, or explicit scoping constraints."
            )

        # Extract expiry from constraints if not explicitly passed
        authority_expiry = expires_at
        if not authority_expiry:
            for c in getattr(proposal, "constraints", []) or []:
                c_clean = str(c).strip()
                if c_clean.lower().startswith("expires_at:"):
                    authority_expiry = c_clean[len("expires_at:"):].strip()
                    break

        # Extract args_digest from constraints if not explicitly passed
        authority_digest = args_digest
        if not authority_digest:
            for c in getattr(proposal, "constraints", []) or []:
                c_clean = str(c).strip()
                if c_clean.lower().startswith("args_digest:"):
                    raw = c_clean[len("args_digest:"):].strip()
                    authority_digest = raw.split(":")[-1].strip()
                    break

        return ExecutionAuthority(
            proposal_id=proposal.id,
            proposal_version=proposal.version,
            workspace_id=proposal.workspace_id,
            granted_at=datetime.now(timezone.utc).isoformat(),
            expires_at=authority_expiry,
            step_id=step_id,
            args_digest=authority_digest,
        )

    @classmethod
    def validate_authority(
        cls,
        authority: ExecutionAuthority | None,
        workspace_id: str,
        store: Any,
        action_or_boundary: str | None = None,
        input_data: dict[str, Any] | None = None,
        step_id: str | None = None,
    ) -> Any:
        """
        Validates the authority against persistent proposal state in PersonalStore.
        Revalidates:
        1. authority is provided and is an ExecutionAuthority instance
        2. authority.workspace_id matches workspace_id
        3. authority.expires_at is validated (fails closed on expired or malformed)
        4. proposal exists in store and belongs to workspace_id
        5. proposal.version matches authority.proposal_version
        6. proposal.status is ACCEPTED (not DRAFT, REVOKED, SUPERSEDED, etc.)
        7. Negative and allowed-scope constraints (explicit or derived from proposed steps)
        8. Arguments digest binding (against authority.args_digest and args_digest constraints)
        9. Step execution idempotency and single_use constraints
        """
        op_name = action_or_boundary or "operation"
        if not authority:
            raise UnauthorizedExecutionError(f"Execution of '{op_name}' requires valid execution authority.")
        if not isinstance(authority, ExecutionAuthority):
            raise UnauthorizedExecutionError(
                f"Invalid authority type for '{op_name}': expected ExecutionAuthority, got {type(authority).__name__}."
            )
        ws_matches = (authority.workspace_id == workspace_id)
        if not ws_matches:
            from aether.workspace.workspace import Workspace
            ws_inst = Workspace.get(workspace_id)
            if ws_inst and authority.workspace_id in (ws_inst.id, ws_inst.name, ws_inst.root.name, str(ws_inst.root)):
                ws_matches = True
            else:
                auth_ws_inst = Workspace.get(authority.workspace_id)
                if auth_ws_inst and workspace_id in (auth_ws_inst.id, auth_ws_inst.name, auth_ws_inst.root.name, str(auth_ws_inst.root)):
                    ws_matches = True

        if not ws_matches:
            raise UnauthorizedExecutionError(
                f"Authority workspace '{authority.workspace_id}' does not match execution workspace '{workspace_id}' for '{op_name}'."
            )

        # 1. Authority expiration check
        if authority.expires_at:
            try:
                from datetime import datetime, timezone
                auth_exp_dt = datetime.fromisoformat(authority.expires_at)
                if auth_exp_dt.tzinfo is None:
                    auth_exp_dt = auth_exp_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > auth_exp_dt:
                    raise UnauthorizedExecutionError(
                        f"Execution authority for proposal '{authority.proposal_id}' expired at '{authority.expires_at}'."
                    )
            except UnauthorizedExecutionError:
                raise
            except Exception as e:
                raise UnauthorizedExecutionError(
                    f"Execution authority for proposal '{authority.proposal_id}' has invalid expiration '{authority.expires_at}': {e}"
                )

        # Resolve personal_store from store or workspace
        personal_store = getattr(store, "personal_store", store)
        if personal_store is None or not hasattr(personal_store, "get_proposal"):
            raise UnauthorizedExecutionError(
                f"No persistent PersonalStore available to validate execution authority for '{op_name}'."
            )

        proposal = personal_store.get_proposal(authority.proposal_id, workspace_id=authority.workspace_id)
        if not proposal:
            proposal = personal_store.get_proposal(authority.proposal_id, workspace_id=workspace_id)
        if not proposal:
            raise UnauthorizedExecutionError(
                f"Referenced proposal '{authority.proposal_id}' does not exist in workspace '{workspace_id}'."
            )
        prop_ws_matches = (proposal.workspace_id == workspace_id or proposal.workspace_id == authority.workspace_id)
        if not prop_ws_matches:
            from aether.workspace.workspace import Workspace
            ws_chk = Workspace.get(workspace_id)
            if ws_chk and proposal.workspace_id in (ws_chk.id, ws_chk.name, ws_chk.root.name):
                prop_ws_matches = True
        if not prop_ws_matches:
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

        constraints = getattr(proposal, "constraints", []) or []

        # 2. Proposal expiration constraints check
        for c in constraints:
            c_clean = str(c).strip()
            if c_clean.lower().startswith("expires_at:"):
                exp_str = c_clean[len("expires_at:"):].strip()
                try:
                    from datetime import datetime, timezone
                    exp_dt = datetime.fromisoformat(exp_str)
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > exp_dt:
                        raise UnauthorizedExecutionError(
                            f"Proposal '{proposal.id}' execution authority expired at '{exp_str}'."
                        )
                except UnauthorizedExecutionError:
                    raise
                except (ValueError, TypeError) as e:
                    raise UnauthorizedExecutionError(
                        f"Proposal '{proposal.id}' has invalid expires_at constraint '{exp_str}': {e}"
                    )

        # 3. Step idempotency and single-use checks
        target_step_id = step_id or (authority.step_id if authority else None) or action_or_boundary
        if target_step_id:
            already_run = False
            if hasattr(proposal, "executed_steps") and target_step_id in proposal.executed_steps:
                already_run = True
            elif hasattr(personal_store, "is_step_executed") and personal_store.is_step_executed(proposal.id, target_step_id):
                already_run = True
            if already_run:
                raise UnauthorizedExecutionError(
                    f"Step '{target_step_id}' of proposal '{proposal.id}' has already been executed."
                )

        if authority.args_digest and hasattr(personal_store, "is_action_executed"):
            if personal_store.is_action_executed(proposal.id, action_or_boundary or "", authority.args_digest):
                raise UnauthorizedExecutionError(
                    f"Action '{action_or_boundary}' with args_digest '{authority.args_digest}' has already been executed for proposal '{proposal.id}'."
                )

        for c in constraints:
            c_clean = str(c).strip().lower()
            if c_clean in ("single_use", "once", "single-use"):
                has_run = False
                if hasattr(proposal, "executed_steps") and proposal.executed_steps:
                    has_run = True
                elif hasattr(personal_store, "list_executed_steps") and personal_store.list_executed_steps(proposal.id):
                    has_run = True
                if has_run:
                    raise UnauthorizedExecutionError(
                        f"Proposal '{proposal.id}' has single_use constraint and has already executed an action."
                    )

        # 4. Scope and constraint validation
        if action_or_boundary:
            act_clean = action_or_boundary.strip()

            # A. Negative constraint check (explicit deny/prohibit/disallow)
            for c in constraints:
                c_clean = str(c).strip()
                for prefix in ("prohibit:", "deny:", "disallow:", "blocked:"):
                    if c_clean.lower().startswith(prefix):
                        prohibited_act = c_clean[len(prefix):].strip()
                        if prohibited_act and (act_clean == prohibited_act or act_clean.startswith(f"{prohibited_act}.") or act_clean.startswith(f"{prohibited_act}:")):
                            raise UnauthorizedExecutionError(
                                f"Action '{act_clean}' is explicitly prohibited by proposal '{proposal.id}' constraints: '{c}'."
                            )

            # B. Strict allow-list constraint check (explicit or derived)
            allowed_constraints = [
                str(c).strip() for c in constraints
                if str(c).strip().lower().startswith("allow:") or str(c).strip().lower().startswith("scope:")
            ]
            if allowed_constraints:
                allowed_actions = set()
                for c in allowed_constraints:
                    prefix = "allow:" if c.lower().startswith("allow:") else "scope:"
                    items = [a.strip() for a in c[len(prefix):].split(",") if a.strip()]
                    allowed_actions.update(items)
            else:
                # Derive allowed actions from proposal's proposed_steps and required_approvals
                derived_actions = set()
                for s in getattr(proposal, "proposed_steps", []) or []:
                    for req in getattr(s, "required_tools_or_actions", []) or []:
                        if req and str(req).strip():
                            derived_actions.add(str(req).strip())
                for req_appr in getattr(proposal, "required_approvals", []) or []:
                    act = getattr(req_appr, "action_or_boundary", None)
                    if act and str(act).strip():
                        derived_actions.add(str(act).strip())
                for c in constraints:
                    c_clean = str(c).strip()
                    for prefix in ("mission_id:", "bind_mission:"):
                        if c_clean.lower().startswith(prefix):
                            b_id = c_clean[len(prefix):].strip()
                            if b_id:
                                derived_actions.add(f"mission.*:{b_id}")
                                derived_actions.add("mission.*")
                allowed_actions = derived_actions

            if allowed_actions:
                base_act = act_clean.split(":")[0] if ":" in act_clean else act_clean
                has_match = False
                if act_clean in allowed_actions or base_act in allowed_actions:
                    has_match = True
                else:
                    for allowed in allowed_actions:
                        if allowed in ("*", "all"):
                            has_match = True
                            break
                        if allowed.endswith(".*") and act_clean.startswith(allowed[:-2]):
                            has_match = True
                            break
                        if ":" in act_clean and act_clean.split(":", 1)[0] == allowed:
                            has_match = True
                            break
                        if ":" in allowed and allowed.split(":", 1)[0] == act_clean:
                            has_match = True
                            break
                        # Handle agent.external and agents.delegate_external equivalence
                        if (act_clean.startswith("agent.external") and "agents.delegate_external" in allowed_actions) or \
                           (act_clean == "agents.delegate_external" and any(a.startswith("agent.external") for a in allowed_actions)):
                            has_match = True
                            break
                if not has_match:
                    raise UnauthorizedExecutionError(
                        f"Execution of '{act_clean}' is outside the authorized scope of proposal '{proposal.id}'. "
                        f"Authorized scope: {sorted(allowed_actions)}."
                    )
            else:
                # Fail-closed: unconstrained proposals without steps or scoping constraints cannot authorize execution
                raise UnauthorizedExecutionError(
                    f"Execution of '{act_clean}' rejected: proposal '{proposal.id}' has no defined action scope or steps."
                )

            # C. Mission binding check
            if act_clean.startswith("mission.") and ":" in act_clean:
                target_mid = act_clean.split(":", 1)[1]
                for c in constraints:
                    c_clean = str(c).strip()
                    for prefix in ("mission_id:", "bind_mission:"):
                        if c_clean.lower().startswith(prefix):
                            bound_mid = c_clean[len(prefix):].strip()
                            if bound_mid and bound_mid != target_mid:
                                raise UnauthorizedExecutionError(
                                    f"Proposal '{proposal.id}' is bound to mission '{bound_mid}', "
                                    f"cannot authorize execution for mission '{target_mid}'."
                                )

        # 5. Argument binding / digest verification
        computed_digest = compute_args_digest(input_data) if input_data is not None else None

        if authority.args_digest:
            if input_data is None:
                raise UnauthorizedExecutionError(
                    f"Execution authority for proposal '{proposal.id}' is bound to args_digest '{authority.args_digest}', "
                    f"but no arguments were provided for verification."
                )
            if computed_digest != authority.args_digest:
                raise UnauthorizedExecutionError(
                    f"Execution arguments digest mismatch for proposal '{proposal.id}'. "
                    f"Expected '{authority.args_digest}', got '{computed_digest}'."
                )

        for c in constraints:
            c_clean = str(c).strip()
            if c_clean.lower().startswith("args_digest:"):
                expected_digest = c_clean[len("args_digest:"):].strip()
                if ":" in expected_digest:
                    parts = expected_digest.split(":", 1)
                    target_scope = parts[0].strip()
                    digest_val = parts[1].strip()
                    applies = False
                    if action_or_boundary and (action_or_boundary == target_scope or action_or_boundary.split(":")[0] == target_scope):
                        applies = True
                    if target_step_id and target_step_id == target_scope:
                        applies = True
                    if applies:
                        if input_data is None:
                            raise UnauthorizedExecutionError(
                                f"Proposal '{proposal.id}' constraint '{c}' requires argument verification for '{target_scope}', "
                                f"but no arguments were provided."
                            )
                        if computed_digest != digest_val:
                            raise UnauthorizedExecutionError(
                                f"Execution arguments digest mismatch for proposal '{proposal.id}' on '{target_scope}'. "
                                f"Constraint requires '{digest_val}', got '{computed_digest}'."
                            )
                else:
                    if input_data is None:
                        raise UnauthorizedExecutionError(
                            f"Proposal '{proposal.id}' constraint '{c}' requires argument verification, "
                            f"but no arguments were provided."
                        )
                    if computed_digest != expected_digest:
                        raise UnauthorizedExecutionError(
                            f"Execution arguments digest mismatch for proposal '{proposal.id}'. "
                            f"Constraint requires '{expected_digest}', got '{computed_digest}'."
                        )

        return proposal

