"""
Executor and Safety Gate for Aether Actions (Phase C & Sprint 1).
Enforces confirmation requirements for ACT tier and external/sensitive mutations,
governs auto-approval by security policy, dispatches to real connectors, and logs truthful audit trails.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
from typing import Any
import uuid

from aether.actions.models import (
    ActionDefinition,
    ActionExecution,
    ActionExecutionStatus,
    ActionPermissionLevel,
    ActionTier,
    sanitize_payload,
)
from aether.core.execution import ExecutionAuthority, UnauthorizedExecutionError, ActionClassification
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.activity.models import ActivityCategory, ActivityStatus
from aether.activity.service import ActivityService
from aether.connections.models import ConnectionStatus
from aether.policy.models import PolicyDecision, PolicyOutcome

logger = logging.getLogger(__name__)


class ActionSafetyPolicy:
    """
    Policy governing auto-approval and mandatory safety confirmation requirements.
    Prevents unauthorized bypass of external or sensitive state changes and enforces Autopilot Tiers.
    """

    def __init__(self, policy_service: Any | None = None) -> None:
        self.policy_service = policy_service

    def can_auto_approve(
        self,
        definition: ActionDefinition,
        auto_approve_requested: bool,
        workspace_id: str | None = None,
        cost: float = 0.0,
    ) -> bool:
        if self.policy_service and workspace_id:
            can_auto, _ = self.policy_service.evaluate_action(
                workspace_id=workspace_id,
                action_id=definition.id,
                permission_level=definition.permission_level,
                requires_confirmation=definition.requires_confirmation,
                auto_approve_requested=auto_approve_requested,
                estimated_cost=cost,
            )
            return can_auto

        if not auto_approve_requested:
            return False

        # Sensitive mutations can NEVER be auto-approved
        if definition.permission_level == ActionPermissionLevel.SENSITIVE_MUTATION:
            return False

        # External mutations that explicitly require confirmation cannot be bypassed casually
        if (
            definition.permission_level == ActionPermissionLevel.EXTERNAL_MUTATION
            and definition.requires_confirmation
        ):
            return False

        return True


class ActionExecutor:
    """Executes actions with safety checks, approval workflows, and audit trails."""

    def __init__(
        self,
        registry: ActionRegistry,
        store: ActionStore,
        activity_service: ActivityService | None = None,
        connection_service: Any = None,
        project_path: Any = None,
        safety_policy: ActionSafetyPolicy | None = None,
        workspace: Any = None,
        personal_store: Any = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.activity_service = activity_service
        self.connection_service = connection_service
        self.project_path = Path(project_path) if project_path else None
        self.safety_policy = safety_policy or ActionSafetyPolicy()
        self.workspace = workspace
        self.personal_store = personal_store
        self._approval_lock = threading.RLock()

    def _resolve_personal_store(self, workspace_id: str) -> Any:
        if self.personal_store is not None:
            return self.personal_store
        if self.workspace is not None and hasattr(self.workspace, "personal_store"):
            return self.workspace.personal_store
        from aether.workspace.workspace import Workspace
        ws = Workspace.get(workspace_id)
        if ws is not None and hasattr(ws, "personal_store"):
            return ws.personal_store
        return None

    def _canonical_workspace_id(self, workspace_id: str) -> str:
        canon = getattr(self.workspace, "canonical_id", None)
        if callable(canon):
            try:
                value = canon(workspace_id)
                return value if isinstance(value, str) and value else workspace_id
            except Exception:
                return workspace_id
        return workspace_id

    def _user_files_base(self, ws: Any) -> Path:
        """
        Where documents the user asks for are read and written: an explicitly linked project folder, otherwise the
        workspace's user-facing ``files`` folder. Never the workspace root, which holds its databases and settings
        (the executor is built with the root as a fallback ``project_path``, which is not a user choice).
        """
        explicit = self.project_path
        ws_root = Path(ws.root).resolve() if ws is not None and getattr(ws, "root", None) else None
        if explicit and not (ws_root is not None and Path(explicit).resolve() == ws_root):
            return Path(explicit)
        if ws is not None:
            linked = getattr(ws, "project_path", None)
            if linked:
                return Path(linked)
            if getattr(ws, "files_dir", None):
                return Path(ws.files_dir)
            if ws_root is not None:
                return ws_root
        return Path(explicit) if explicit else Path.cwd()

    def _get_workspace(self, workspace_id: str | None = None) -> Any:
        """Resolves workspace from injected self.workspace or active registry without silent fake fallback."""
        if self.workspace is not None:
            return self.workspace
        from aether.workspace.workspace import Workspace
        if self.project_path:
            ws_by_path = Workspace.get(self.project_path)
            if ws_by_path is not None:
                if not workspace_id or workspace_id in (ws_by_path.name, ws_by_path.id, ws_by_path.root.name):
                    return ws_by_path
        if workspace_id:
            ws = Workspace.get(workspace_id) if hasattr(Workspace, "get") else None
            if ws is not None:
                return ws
        if self.project_path:
            ws = Workspace.get_or_init(self.project_path)
            if ws is not None:
                return ws
        raise RuntimeError("Workspace unavailable for action execution.")

    def execute(
        self,
        action_id: str,
        workspace_id: str,
        input_data: dict[str, Any],
        auto_approve: bool = False,
        metadata: dict[str, Any] | None = None,
        authority: ExecutionAuthority | None = None,
    ) -> ActionExecution:
        """
        Executes an action or queues it for user approval if confirmation is required.
        """
        definition = self.registry.get(action_id)
        if not definition:
            raise ValueError(f"Action '{action_id}' not found in registry")

        # One canonical key per workspace: aliases (display name, folder, "default") map to the immutable id.
        workspace_id = self._canonical_workspace_id(workspace_id)

        # Consent is a structured argument of this call, never a field smuggled inside the action data.
        input_data = {k: v for k, v in (input_data or {}).items() if k != "auto_approve"}

        # Macro-pass 1.2: Enforce execution authority boundary
        # UNKNOWN permission level always fails closed
        if definition.permission_level == ActionPermissionLevel.UNKNOWN:
            raise UnauthorizedExecutionError(f"Action '{action_id}' has unknown permission level and cannot execute.")

        is_read_only = definition.permission_level == ActionPermissionLevel.READ_ONLY
        authorised_paths: list[str] = []

        # HARD BOUNDARY: All non-read-only actions require persistently validated authority
        # This check must occur BEFORE any queueing, approval path, or execution.
        if not is_read_only:
            if not authority:
                raise UnauthorizedExecutionError(
                    f"Action '{action_id}' (permission_level={definition.permission_level.value}) requires execution authority."
                )
            if not isinstance(authority, ExecutionAuthority):
                raise UnauthorizedExecutionError(
                    f"Invalid authority type for '{action_id}': expected ExecutionAuthority, got {type(authority).__name__}."
                )
            # Persistent validation against proposal store
            p_store = self._resolve_personal_store(workspace_id)
            from aether.core.execution import ExecutionBoundary
            if action_id in self._CODING_INTERACTION_ACTIONS:
                self._assert_coding_run_owned(workspace_id, input_data.get("execution_id"), authority)
            proposal_obj = ExecutionBoundary.validate_authority(
                authority=authority,
                workspace_id=workspace_id,
                store=p_store,
                action_or_boundary=action_id,
                input_data=input_data,
                step_id=authority.step_id if authority else None,
                canonicalize=getattr(self.workspace, "canonical_id", None),
            )
            authorised_paths = self._allowed_paths_from(proposal_obj)

        # Persist authority context into execution metadata for later revalidation (approve path)
        exec_meta = dict(metadata or {})
        if not is_read_only and authorised_paths:
            exec_meta["allowed_paths"] = authorised_paths
        if authority is not None:
            exec_meta["authority"] = authority.to_dict()
            exec_meta["proposal_id"] = authority.proposal_id
            exec_meta["proposal_version"] = authority.proposal_version

        execution = ActionExecution(
            id=f"ax-{uuid.uuid4().hex[:12]}",
            action_id=action_id,
            workspace_id=workspace_id,
            provider=definition.provider,
            input_data=dict(input_data),
            metadata=exec_meta,
        )

        # HITL approval logic (separate from proposal authorization)
        requires_gate = (
            definition.requires_confirmation
            or definition.tier == ActionTier.ACT
            or definition.permission_level in (
                ActionPermissionLevel.EXTERNAL_MUTATION,
                ActionPermissionLevel.SENSITIVE_MUTATION,
            )
        )

        decision = self._policy_decision(workspace_id, definition, auto_approve)
        if decision is not None and not decision.is_denied:
            decision = self._parent_denial(workspace_id, definition) or decision
        if decision is not None:
            if decision.is_denied:
                # Hard refusal, identified by a stable typed code: no authority or flag can override it.
                self._fail_by_policy(execution, definition, decision)
                return execution
            can_auto_run = decision.can_auto_execute and (not requires_gate or bool(auto_approve))
        else:
            if not requires_gate:
                can_auto_run = True
            else:
                can_auto_run = bool(auto_approve and self.safety_policy.can_auto_approve(definition, auto_approve, workspace_id=workspace_id))

        if not can_auto_run:
            execution.status = ActionExecutionStatus.WAITING_APPROVAL
            execution.metadata["requires_approval"] = True
            self.store.save_execution(execution)
            if self.activity_service:
                self.activity_service.log(
                    workspace_id=workspace_id,
                    title=f"Approval needed: {definition.name}",
                    description=f"Action '{definition.name}' requires confirmation before proceeding.",
                    category=ActivityCategory.ACTION,
                    status=ActivityStatus.WAITING_APPROVAL,
                    link_view="home",
                    link_id=execution.id,
                    metadata={"action_id": action_id, "execution_id": execution.id, "provider": definition.provider},
                )
            return execution

        if auto_approve or (requires_gate and can_auto_run):
            execution.metadata["auto_approved"] = True
            if not execution.approved_by:
                execution.approved_by = "authority" if authority is not None else "safety_policy"

        # Direct execution
        execution.status = ActionExecutionStatus.RUNNING
        self.store.save_execution(execution)

        return self._dispatch_and_run(definition, execution)

    _CODING_INTERACTION_ACTIONS = ("coding.interact", "coding.send_message", "coding.run_tests", "coding.release_project")

    def _policy_decision(
        self,
        workspace_id: str,
        definition: ActionDefinition,
        auto_approve_requested: bool,
    ) -> PolicyDecision | None:
        """
        Returns the typed policy verdict, or None when no policy service is configured.
        Services that only expose the legacy ``(bool, reason)`` form cannot express a hard denial,
        so a non-allow answer is treated as NEEDS_APPROVAL; the reason text is never parsed.
        """
        svc = getattr(self.safety_policy, "policy_service", None)
        if not svc:
            return None
        kwargs = dict(
            workspace_id=workspace_id,
            action_id=definition.id,
            permission_level=definition.permission_level,
            requires_confirmation=definition.requires_confirmation,
            auto_approve_requested=auto_approve_requested,
        )
        typed = getattr(svc, "evaluate_action_decision", None)
        if callable(typed):
            decision = typed(**kwargs)
            if isinstance(decision, PolicyDecision):
                return decision
        can_auto, reason = svc.evaluate_action(**kwargs)
        if can_auto:
            return PolicyDecision(PolicyOutcome.ALLOW, "LEGACY_ALLOW", str(reason))
        return PolicyDecision(PolicyOutcome.NEEDS_APPROVAL, "LEGACY_HOLD", str(reason))

    def _parent_denial(self, workspace_id: str, definition: ActionDefinition) -> PolicyDecision | None:
        """Replying to a coding run is only allowed while delegating coding itself is not denied."""
        if definition.id not in self._CODING_INTERACTION_ACTIONS:
            return None
        parent = self.registry.get("coding.delegate")
        decision = self._policy_decision(workspace_id, parent, False) if parent else None
        return decision if decision is not None and decision.is_denied else None

    def get_coding_run_record(self, workspace_id: str, coding_execution_id: str) -> ActionExecution | None:
        """Public accessor: the coding.delegate record that owns a run, inside ``workspace_id`` only."""
        return self._find_coding_run_record(workspace_id, coding_execution_id)

    @staticmethod
    def _allowed_paths_from(proposal: Any) -> list[str]:
        out: list[str] = []
        for c in getattr(proposal, "constraints", None) or []:
            c_clean = str(c).strip()
            if c_clean.lower().startswith("allow_path:"):
                val = c_clean[len("allow_path:"):].strip()
                if val:
                    out.append(val)
        return out

    def _fail_by_policy(self, execution: ActionExecution, definition: ActionDefinition, decision: PolicyDecision) -> None:
        execution.status = ActionExecutionStatus.FAILED
        execution.error_message = decision.reason
        execution.completed_at = datetime.now(timezone.utc).isoformat()
        execution.metadata["policy_outcome"] = decision.outcome.value
        execution.metadata["policy_code"] = decision.code
        self.store.save_execution(execution)
        if self.activity_service:
            self.activity_service.log(
                workspace_id=execution.workspace_id,
                title=f"Action Blocked: {definition.name}",
                description=decision.reason,
                category=ActivityCategory.ACTION,
                status=ActivityStatus.FAILED,
                link_view="home",
                link_id=execution.id,
                metadata={"action_id": definition.id, "execution_id": execution.id,
                          "reason": decision.reason, "policy_code": decision.code},
            )

    def _find_coding_run_record(self, workspace_id: str, coding_execution_id: str | None) -> ActionExecution | None:
        """Finds the persisted coding.delegate record that owns a coding run, within this workspace only."""
        if not self.store or not hasattr(self.store, "list_executions"):
            return None
        records = self.store.list_executions(workspace_id, limit=500)
        coding = [r for r in records if r.action_id == "coding.delegate"]
        if not coding_execution_id:
            return coding[0] if coding else None  # newest first
        for rec in coding:
            out = rec.output_data or {}
            if rec.metadata.get("coding_execution_id") == coding_execution_id or out.get("execution_id") == coding_execution_id:
                return rec
        return None

    def _create_coding_mission(self, ws: Any, ws_id: str, inp: dict[str, Any], execution: Any, project: Path) -> str | None:
        """
        A delegated coding run is a mission: implementation + authorised test verification, with the evidence the
        quality gate must see (verified run, passing tests) recorded up front. Best effort: never blocks the run.
        """
        try:
            instruction = str(inp.get("instruction", "")).strip() or "Coding task"
            mission = ws.missions.create_mission(
                title=f"Coding: {instruction[:70]}", objective=instruction, workspace_id=ws_id,
                status="running",
                metadata={
                    "kind": "coding", "proposal_id": execution.metadata.get("proposal_id"),
                    "project_path": str(project), "required_evidence": ["coding_run_verified", "tests_passed"],
                    "action_execution_id": execution.id,
                },
                milestones=[
                    {"title": "Implementazione (agente di coding)", "description": instruction, "order_idx": 0},
                    {"title": "Verifica con test autorizzati", "description": "Esecuzione dei test approvata dall'utente", "order_idx": 1},
                ],
            )
            execution.metadata["mission_id"] = mission.id
            return mission.id
        except Exception as exc:
            logger.warning("Could not create coding mission: %s", exc)
            return None

    def _close_undispatched_coding_mission(self, ws: Any, ws_id: str, mission_id: str, exc: Exception) -> None:
        """Marks a mission created for a coding dispatch that never produced a run as failed, keeping the reason."""
        try:
            from aether.missions.models import ExecutionStatus as MExec, MilestoneStatus, MissionStatus
            store = ws.missions
            mission = store.get_mission(mission_id)
            if mission is None:
                return
            reason = f"Coding dispatch failed before any run started: {type(exc).__name__}: {exc}"
            meta = dict(mission.metadata or {})
            meta["dispatch_error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
            run_exec = store.create_execution(mission_id=mission_id, team_name=None, status=MExec.FAILED)
            store.update_execution(run_exec.id, status=MExec.FAILED, error_message=reason)
            store.update_mission(mission_id, status=MissionStatus.FAILED, active_execution_id=run_exec.id, metadata=meta)
            for ms in mission.milestones:
                # get_mission() overlays the active execution's own rows on the template rows: update both.
                store.update_milestone(ms.id, status=MilestoneStatus.SKIPPED)
                store.update_execution_milestone(run_exec.id, ms.id, status=MilestoneStatus.SKIPPED.value)
            try:
                from aether.personal.events import get_personal_event_hub
                get_personal_event_hub().publish(ws_id, "coding_run_update", {
                    "workspace_id": ws_id, "mission_id": mission_id, "run_id": None, "event": "dispatch_failed",
                    "status": "failed", "error": reason[:300]})
            except Exception:
                pass
        except Exception as close_exc:
            logger.warning("Could not close mission %s after dispatch failure: %s", mission_id, close_exc)

    def _assert_coding_run_owned(
        self, workspace_id: str, coding_execution_id: str | None, authority: ExecutionAuthority | None
    ) -> Any:
        """A coding run can only be addressed from its own workspace and under the proposal that started it."""
        if not coding_execution_id:
            raise UnauthorizedExecutionError("A coding execution_id is required for this interaction.")
        run = None
        try:
            run = self._coding_run_store(workspace_id).get_run(coding_execution_id)
        except Exception:
            run = None
        rec = self._find_coding_run_record(workspace_id, coding_execution_id)
        if run is None and rec is None:
            raise UnauthorizedExecutionError(
                f"Coding run '{coding_execution_id}' does not belong to workspace '{workspace_id}'."
            )
        owner = (run.task.proposal_id if run is not None else None) or ((rec.metadata.get("authority") or {}).get("proposal_id") if rec else None)
        if authority is None or not owner or owner != authority.proposal_id:
            raise UnauthorizedExecutionError(
                f"Authority is not bound to the proposal that started coding run '{coding_execution_id}'."
            )
        return rec or run

    def _coding_run_store(self, ws_id: str):
        """Durable coding-run store of this workspace (next to the workspace data, or the action store)."""
        from aether.coding.runs import CodingRunStore
        cache = self.__dict__.setdefault("_coding_run_stores", {})
        if ws_id not in cache:
            path = None
            canonical = ws_id
            try:
                ws = self._get_workspace(ws_id)
                path = getattr(ws, "coding_runs_db_path", None)
                if hasattr(ws, "canonical_id"):
                    canonical = ws.canonical_id(ws_id)
            except Exception:
                path = None
            if not path:
                path = Path(self.store.db_path).parent / "coding_runs.db"
            cache[ws_id] = CodingRunStore(path, canonical)
        return cache[ws_id]

    def _import_legacy_coding_run(self, orchestrator: Any, ws_id: str, exec_id: str | None) -> None:
        """
        Compatibility adapter for runs started before the durable run store existed (or whose provider bypassed
        it): rebuilds the run from the persisted ``coding.delegate`` action record and saves it in the store, so
        from then on it is recovered like any other run.
        """
        if not exec_id or orchestrator._find(exec_id) is not None:
            return
        rec = self._find_coding_run_record(ws_id, exec_id)
        if rec is None:
            return
        try:
            from aether.coding.models import CodingExecutionStatus, CodingResult, CodingTask, CodingTaskExecution
            out = rec.output_data or {}
            inp = rec.input_data or {}
            status_str = out.get("status") or ("completed" if rec.status.value == "succeeded" else "failed")
            status = CodingExecutionStatus(status_str) if status_str in CodingExecutionStatus._value2member_map_ else CodingExecutionStatus.FAILED
            task = CodingTask(
                instruction=inp.get("instruction") or out.get("summary") or "",
                project_path=inp.get("project_path") or (out.get("metadata") or {}).get("project_path") or "",
                context_files=list(inp.get("context_files") or []),
                provider_id=out.get("provider_id") or inp.get("provider_id") or "antigravity",
                workspace_id=ws_id, proposal_id=(rec.metadata.get("authority") or {}).get("proposal_id"),
            )
            run = CodingTaskExecution(
                id=out.get("execution_id") or exec_id, task=task, provider_id=task.provider_id, status=status,
                external_task_id=out.get("external_task_id"), started_at=rec.created_at, completed_at=rec.completed_at,
            )
            run.metadata["imported_from_action"] = rec.id
            if out.get("result"):
                run.result = CodingResult.from_dict(out["result"])
            orchestrator.register_execution(run)
            self._coding_run_store(ws_id).save_run(run)
        except Exception as exc:
            logger.warning("Could not import legacy coding run %s: %s", exec_id, exc)

    def _scoped_coding_execution_id(self, workspace_id: str, requested: str | None) -> str:
        """Resolves a coding run id strictly inside the caller's workspace; 'latest' means latest of THIS workspace."""
        store = self._coding_run_store(workspace_id)
        if requested:
            if store.get_run(requested) is not None:
                return requested
            rec = self._find_coding_run_record(workspace_id, requested)
            if rec is not None:
                return rec.metadata.get("coding_execution_id") or (rec.output_data or {}).get("execution_id") or requested
            raise ValueError(f"Coding run '{requested}' not found in workspace '{workspace_id}'.")
        runs = store.list_runs(limit=1)
        if runs:
            return runs[0].id
        rec = self._find_coding_run_record(workspace_id, None)
        if rec is not None:
            return rec.metadata.get("coding_execution_id") or (rec.output_data or {}).get("execution_id") or rec.id
        raise ValueError(f"No coding run found in workspace '{workspace_id}'.")

    def _workspace_roots(self, ws_id: str) -> list[Path]:
        """Directories a coding task may target without an explicit allow_path: the workspace's own roots."""
        roots: list[Path] = []
        try:
            ws = self._get_workspace(ws_id)
        except Exception:
            ws = None
        for attr in ("root", "project_path"):
            val = getattr(ws, attr, None) if ws is not None else None
            if val:
                roots.append(Path(val).resolve())
        if self.project_path:
            roots.append(Path(self.project_path).resolve())
        return roots

    @staticmethod
    def _assert_coding_path_allowed(p_dir: Path, allowed_paths: list[str], workspace_roots: list[Path] | None = None) -> None:
        """
        Positive filesystem perimeter for delegated coding. The target must lie inside a path the accepted proposal
        explicitly authorises, or inside the workspace's own root/project. Anything else is refused, and so are the
        user's home itself, its ancestors, system directories and the Aether installation (unless explicitly allowed).
        """
        def _inside(child: Path, parent: Path) -> bool:
            return child == parent or parent in child.parents

        from aether.core.system_paths import is_protected_system_path
        if is_protected_system_path(p_dir):
            raise ValueError(f"Cannot delegate coding task to system root directory: {p_dir}")
        home = Path.home().resolve()
        if p_dir == home or p_dir in home.parents:
            raise ValueError(f"Cannot delegate coding task to the home directory or one of its ancestors: {p_dir}")

        explicit = [Path(a).resolve() for a in allowed_paths if a]
        roots = list(workspace_roots or [])
        if not any(_inside(p_dir, r) for r in explicit + roots):
            raise UnauthorizedExecutionError(
                f"Project path '{p_dir}' is not inside an authorised path or the workspace; "
                f"the accepted proposal must name it (allow_path) or it must belong to the workspace."
            )
        aether_root = Path(__file__).resolve().parents[3]
        if (aether_root / "pyproject.toml").exists() and (_inside(p_dir, aether_root) or _inside(aether_root, p_dir)):
            if not any(_inside(p_dir, a) for a in explicit):
                raise ValueError(
                    "Delegating coding to the Aether installation itself requires an explicit allow_path in the accepted proposal."
                )

    def approve(self, execution_id: str, approver: str = "user") -> ActionExecution:
        """Approves a pending execution and runs it. Idempotent if already approved/completed."""
        with self._approval_lock:
            execution = self.store.get_execution(execution_id)
            if not execution:
                raise ValueError(f"Execution '{execution_id}' not found")

            # Idempotency: if already approved or running or completed, return existing execution
            if execution.status in (ActionExecutionStatus.APPROVED, ActionExecutionStatus.SUCCEEDED, ActionExecutionStatus.RUNNING):
                return execution

            if execution.status in (ActionExecutionStatus.REJECTED, ActionExecutionStatus.CANCELLED, ActionExecutionStatus.EXPIRED):
                raise ValueError(f"Cannot approve execution '{execution_id}': action was already declined / {execution.status.value}.")

            if execution.status == ActionExecutionStatus.FAILED:
                raise ValueError(f"Cannot approve execution '{execution_id}': action has already failed.")

            if execution.status not in (ActionExecutionStatus.WAITING_APPROVAL,):
                raise ValueError(f"Cannot approve execution in status '{execution.status.value}'")

            definition = self.registry.get(execution.action_id)
            if not definition:
                raise ValueError(f"Action '{execution.action_id}' not found")

            # Macro-pass 1.2: Revalidate persisted authority prior to dispatch
            # For non-read-only actions, authority metadata MUST be present — fail closed otherwise.
            is_read_only = definition.permission_level == ActionPermissionLevel.READ_ONLY
            auth_data = execution.metadata.get("authority")
            if not is_read_only:
                if not auth_data:
                    raise UnauthorizedExecutionError(
                        f"Cannot approve execution '{execution_id}': no persisted authority metadata. "
                        f"Non-read-only actions require validated execution authority."
                    )
                from aether.core.execution import ExecutionAuthority, ExecutionBoundary
                authority_obj = ExecutionAuthority.from_dict(auth_data)
                p_store = self._resolve_personal_store(execution.workspace_id)
                proposal_obj = ExecutionBoundary.validate_authority(
                    authority=authority_obj,
                    workspace_id=execution.workspace_id,
                    store=p_store,
                    action_or_boundary=execution.action_id,
                    input_data=execution.input_data,
                    step_id=authority_obj.step_id if authority_obj else None,
                    canonicalize=getattr(self.workspace, "canonical_id", None),
                )
                approved_paths = self._allowed_paths_from(proposal_obj)
                if approved_paths:
                    execution.metadata["allowed_paths"] = approved_paths

            # Policy is re-evaluated at approval time: a denial added while the action waited
            # (or any hard refusal) wins over the human click. Approval only satisfies NEEDS_APPROVAL.
            decision = self._policy_decision(execution.workspace_id, definition, False)
            if decision is not None and not decision.is_denied:
                decision = self._parent_denial(execution.workspace_id, definition) or decision
            if decision is not None and decision.is_denied:
                self._fail_by_policy(execution, definition, decision)
                return execution

            execution.transition_to(ActionExecutionStatus.APPROVED)
            execution.approved_by = approver
            if execution.action_id == "coding.delegate":
                from aether.personal.service import generate_executive_mandate
                raw_instr = execution.input_data.get("instruction", "")
                if raw_instr:
                    execution.input_data["instruction"] = generate_executive_mandate(raw_instr)
            self.store.save_execution(execution)

        return self._dispatch_and_run(definition, execution)

    def reject(self, execution_id: str, reason: str = "User declined") -> ActionExecution:
        """Rejects a pending execution. Idempotent if already rejected."""
        with self._approval_lock:
            execution = self.store.get_execution(execution_id)
            if not execution:
                raise ValueError(f"Execution '{execution_id}' not found")

            # Idempotency: if already rejected, return cleanly
            if execution.status == ActionExecutionStatus.REJECTED:
                return execution

            if execution.is_terminal():
                raise ValueError(f"Cannot decline execution '{execution_id}': action was already approved and is in terminal state '{execution.status.value}'.")

            if execution.status in (ActionExecutionStatus.APPROVED, ActionExecutionStatus.RUNNING):
                raise ValueError(f"Cannot decline execution '{execution_id}': action was already approved.")

            if execution.status not in (ActionExecutionStatus.WAITING_APPROVAL,):
                raise ValueError(f"Cannot reject execution in status '{execution.status.value}'")

            definition = self.registry.get(execution.action_id)
            action_name = definition.name if definition else execution.action_id

            execution.transition_to(ActionExecutionStatus.REJECTED)
            execution.rejection_reason = reason
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            self.store.save_execution(execution)

            if self.activity_service:
                self.activity_service.log(
                    workspace_id=execution.workspace_id,
                    title=f"Declined: {action_name}",
                    description=f"Action was declined ({reason}).",
                    category=ActivityCategory.ACTION,
                    status=ActivityStatus.REJECTED,
                    link_view="home",
                    link_id=execution.id,
                    metadata={"action_id": execution.action_id, "execution_id": execution.id},
                )

            return execution

    approve_execution = approve
    reject_execution = reject

    def _dispatch_and_run(
        self,
        definition: ActionDefinition,
        execution: ActionExecution,
    ) -> ActionExecution:
        """Dispatches action execution to handler or built-in connectors."""
        if execution.is_terminal():
            return execution

        if execution.status != ActionExecutionStatus.RUNNING:
            execution.transition_to(ActionExecutionStatus.RUNNING)
            self.store.save_execution(execution)

        # Atomic reservation in authority ledger BEFORE dispatching mutation
        if execution.metadata.get("authority"):
            auth_meta = execution.metadata["authority"]
            p_id = auth_meta.get("proposal_id")
            st_id = auth_meta.get("step_id") or execution.action_id
            p_store = self._resolve_personal_store(execution.workspace_id)
            if not p_store or not hasattr(p_store, "record_step_executed") or not p_id:
                execution.transition_to(ActionExecutionStatus.FAILED)
                execution.error_message = "Authority ledger recording failed: PersonalStore is not available."
                self.store.save_execution(execution)
                raise RuntimeError("Authority ledger recording failed: PersonalStore is not available.")
            try:
                from aether.core.execution import compute_args_digest
                p_store.record_step_executed(
                    proposal_id=p_id,
                    step_id=st_id,
                    action_id=execution.action_id,
                    args_digest=compute_args_digest(execution.input_data),
                )
            except Exception as ledger_err:
                execution.transition_to(ActionExecutionStatus.FAILED)
                execution.error_message = f"Authority ledger reservation failed: {ledger_err}"
                self.store.save_execution(execution)
                raise RuntimeError(f"Authority ledger reservation failed: {ledger_err}") from ledger_err

        try:
            handler = self.registry.get_handler(definition.id)
            if handler is not None:
                result = handler(execution.input_data, execution.workspace_id)
            else:
                result = self._execute_builtin_action(definition, execution)

            # Validate real success vs failure
            if isinstance(result, dict) and (result.get("success") is False or bool(result.get("error"))):
                err_msg = str(result.get("error") or "Action returned an unsuccessful result.")
                raise RuntimeError(err_msg)

            execution.transition_to(ActionExecutionStatus.SUCCEEDED)
            execution.output_data = result or {}
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            self.store.save_execution(execution)

            if self.activity_service:
                act_title = (
                    f"Auto-approved & Executed: {definition.name}"
                    if execution.metadata.get("auto_approved")
                    else f"Completed: {definition.name}"
                )
                act_desc = f"Successfully executed '{definition.name}'."
                act_status = ActivityStatus.COMPLETED
                if definition.id == "coding.delegate" and isinstance(result, dict):
                    if result.get("run_terminal") is False:
                        # Accepted, not done: the run is still going or waiting for the user.
                        act_title = f"Started: {definition.name}"
                        act_desc = (f"Coding run accepted (state: {result.get('status')}); it has not finished "
                                    f"and nothing is verified yet.")
                        act_status = ActivityStatus.IN_PROGRESS
                    elif result.get("verified") is False:
                        act_desc = f"Coding run ended without passing independent verification (state: {result.get('status')})."
                self.activity_service.log(
                    workspace_id=execution.workspace_id,
                    title=act_title,
                    description=act_desc,
                    category=ActivityCategory.ACTION,
                    status=act_status,
                    link_view="home",
                    link_id=execution.id,
                    metadata={"action_id": definition.id, "execution_id": execution.id, "provider": definition.provider},
                )

        except Exception as e:
            logger.exception(f"Action execution {execution.id} failed: {e}")
            execution.transition_to(ActionExecutionStatus.FAILED)
            # Mask potential secrets from error message
            safe_err = str(e)
            if execution.input_data and isinstance(execution.input_data, dict):
                for k, v in execution.input_data.items():
                    if isinstance(v, str) and len(v) >= 4:
                        if any(s in k.lower() for s in ("token", "key", "secret", "password", "auth", "credential", "bearer", "private")):
                            safe_err = safe_err.replace(v, "[REDACTED]")
            import re
            safe_err = re.sub(r'(?i)(token|key|password|secret|bearer)\s*[:=]\s*([^\s,;]+)', r'\1=[REDACTED]', safe_err)
            safe_err = re.sub(r'(?i)token\s+([a-zA-Z0-9_\-\.]+)', r'token [REDACTED]', safe_err)

            execution.error_message = safe_err
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            self.store.save_execution(execution)

            if self.activity_service:
                self.activity_service.log(
                    workspace_id=execution.workspace_id,
                    title=f"Failed: {definition.name}",
                    description=f"Error executing '{definition.name}': {safe_err}",
                    category=ActivityCategory.ACTION,
                    status=ActivityStatus.FAILED,
                    link_view="home",
                    link_id=execution.id,
                    metadata={"action_id": definition.id, "execution_id": execution.id, "error": safe_err},
                )

        return execution

    def _run_provider_connector(
        self,
        provider: str,
        workspace_id: str,
        action_id: str,
        input_data: dict[str, Any],
        get_connector_fn: Any,
    ) -> dict[str, Any]:
        """Dispatches an action to a connector with truthful status enforcement and operation auditing."""
        if not self.connection_service:
            raise RuntimeError(f"{provider.capitalize()} connection is not configured in this workspace.")
        conn = self.connection_service.get_connection(workspace_id, provider)
        if not conn or conn.status in (ConnectionStatus.NOT_CONFIGURED, ConnectionStatus.DISCONNECTED):
            raise RuntimeError(f"{provider.capitalize()} connection is not configured in this workspace.")
        if conn.status == ConnectionStatus.VERIFICATION_FAILED:
            raise RuntimeError(
                f"{provider.capitalize()} connection verification failed: {conn.last_verification_error or 'invalid credentials'}. Please update credentials."
            )

        connector = get_connector_fn()
        try:
            res = connector.execute(action_id, input_data)
            if hasattr(res, "success") and not res.success:
                raise RuntimeError(res.error or f"Connector operation '{action_id}' failed.")
            if hasattr(self.connection_service, "record_operation_success"):
                self.connection_service.record_operation_success(workspace_id, provider, action_id)
            return res.data if hasattr(res, "data") else (res if isinstance(res, dict) else {})
        except Exception as exc:
            err_str = str(exc).lower()
            is_auth = any(t in err_str for t in ("401", "403", "unauthorized", "bad credentials", "invalid token", "auth failed", "authentication failed"))
            if hasattr(self.connection_service, "record_operation_failure"):
                self.connection_service.record_operation_failure(workspace_id, provider, action_id, str(exc), is_auth_error=is_auth)
            raise

    def _execute_builtin_action(
        self,
        definition: ActionDefinition,
        execution: ActionExecution,
    ) -> dict[str, Any]:
        """Dispatches built-in actions to real connectors or local workspace handlers."""
        action_id = definition.id
        inp = execution.input_data
        ws_id = execution.workspace_id

        # 1. GitHub connector actions
        if action_id.startswith("github."):
            return self._run_provider_connector(
                "github", ws_id, action_id, inp, lambda: self.connection_service.get_github_connector(ws_id)
            )

        # 2. Email connector actions
        elif action_id.startswith("email."):
            return self._run_provider_connector(
                "email", ws_id, action_id, inp, lambda: self.connection_service.get_email_connector(ws_id)
            )

        # 3. Slack connector actions
        elif action_id.startswith("slack."):
            return self._run_provider_connector(
                "slack", ws_id, action_id, inp, lambda: self.connection_service.get_slack_connector(ws_id)
            )

        # 3b. Telegram connector actions
        elif action_id.startswith("telegram."):
            return self._run_provider_connector(
                "telegram", ws_id, action_id, inp, lambda: self.connection_service.get_telegram_connector(ws_id)
            )

        # 3c. Notion connector actions (Macro-pass P1.1)
        elif action_id.startswith("notion."):
            return self._run_provider_connector(
                "notion", ws_id, action_id, inp, lambda: self.connection_service.get_notion_connector(ws_id)
            )

        # 4. HTTP connector actions
        elif action_id.startswith("http."):
            if not self.connection_service:
                raise RuntimeError("HTTP connection service is not configured.")
            connector = self.connection_service.get_http_connector(ws_id)
            try:
                res = connector.execute(action_id, inp)
                if hasattr(res, "success") and not res.success:
                    raise RuntimeError(res.error or f"HTTP connector operation '{action_id}' failed.")
                if hasattr(self.connection_service, "record_operation_success"):
                    self.connection_service.record_operation_success(ws_id, "http", action_id)
                return res.data if hasattr(res, "data") else (res if isinstance(res, dict) else {})
            except Exception as exc:
                err_str = str(exc).lower()
                is_auth = any(t in err_str for t in ("401", "403", "unauthorized", "auth failed"))
                if hasattr(self.connection_service, "record_operation_failure"):
                    self.connection_service.record_operation_failure(ws_id, "http", action_id, str(exc), is_auth_error=is_auth)
                raise

        # 5. Calendar actions
        elif action_id == "calendar.create_event":
            if not self.connection_service:
                raise RuntimeError("Calendar connection is not configured in this workspace.")
            conn = self.connection_service.get_connection(ws_id, "calendar")
            if conn and conn.status == ConnectionStatus.DISCONNECTED:
                raise RuntimeError("Calendar connection is disconnected in this workspace.")
            connector = self.connection_service.get_calendar_connector(ws_id)
            res = connector.create_event(
                title=inp.get("title", "Untitled Event"),
                start_time=inp.get("start_time", datetime.now(timezone.utc).isoformat()),
                end_time=inp.get("end_time"),
                description=inp.get("description", ""),
                location=inp.get("location", ""),
            )
            if hasattr(self.connection_service, "record_operation_success"):
                self.connection_service.record_operation_success(ws_id, "calendar", action_id)
            return res

        elif action_id == "calendar.list_events":
            if not self.connection_service:
                return {"events": []}

            # If Google Calendar is configured with credentials, attempt Google Calendar query (including across all calendars)
            gconn = self.connection_service.get_connection(ws_id, "google_calendar")
            has_credentials = bool(gconn and (gconn.auth_metadata.get("access_token") or gconn.auth_metadata.get("refresh_token")))
            if gconn and gconn.status != ConnectionStatus.DISCONNECTED and has_credentials:
                try:
                    gconnector = self.connection_service.get_google_calendar_connector(ws_id)
                    cal_id = inp.get("calendar_id")
                    events = gconnector.list_events(
                        calendar_id=cal_id,
                        limit=int(inp.get("limit", 50)),
                        time_min=inp.get("time_min"),
                        time_max=inp.get("time_max"),
                        query=inp.get("query"),
                    )
                    if hasattr(self.connection_service, "record_operation_success"):
                        self.connection_service.record_operation_success(ws_id, "google_calendar", action_id)
                    return {"events": events, "provider": "google_calendar"}
                except Exception as g_err:
                    logger.warning("Google Calendar query encountered error: %s.", g_err)
                    if not gconn.auth_metadata.get("refresh_token"):
                        raise RuntimeError(f"L'autorizzazione di Google Calendar è scaduta: {gconn.last_verification_error or g_err}") from g_err

            if gconn and gconn.status == ConnectionStatus.VERIFICATION_FAILED and not has_credentials:
                raise RuntimeError(f"L'autorizzazione di Google Calendar è scaduta: {gconn.last_verification_error or 'Riconnetti il calendario.'}")

            conn = self.connection_service.get_connection(ws_id, "calendar")
            if conn and conn.status == ConnectionStatus.DISCONNECTED:
                raise RuntimeError("Calendar connection is disconnected in this workspace.")
            connector = self.connection_service.get_calendar_connector(ws_id)
            events = connector.list_events(limit=int(inp.get("limit", 50)))
            if hasattr(self.connection_service, "record_operation_success"):
                self.connection_service.record_operation_success(ws_id, "calendar", action_id)
            return {"events": events, "provider": "calendar"}

        # 5b. Google Calendar actions (Macro-pass P0.2)
        elif action_id.startswith("google_calendar."):
            if not self.connection_service:
                raise RuntimeError("Connection service not available.")
            conn = self.connection_service.get_connection(ws_id, "google_calendar")
            if not conn or conn.status == ConnectionStatus.NOT_CONFIGURED:
                raise RuntimeError("Google Calendar is not configured in this workspace.")
            if conn.status == ConnectionStatus.DISCONNECTED:
                raise RuntimeError("Google Calendar connection is disconnected in this workspace.")
            if conn.status == ConnectionStatus.VERIFICATION_FAILED and not conn.auth_metadata.get("refresh_token"):
                raise RuntimeError(f"Google Calendar authorization is invalid: {conn.last_verification_error}")

            connector = self.connection_service.get_google_calendar_connector(ws_id)
            try:
                if action_id == "google_calendar.create_event":
                    res = connector.create_event(
                        title=inp.get("title", "Untitled Event"),
                        start_time=inp.get("start_time", datetime.now(timezone.utc).isoformat()),
                        end_time=inp.get("end_time"),
                        description=inp.get("description", ""),
                        location=inp.get("location", ""),
                        calendar_id=inp.get("calendar_id"),
                    )
                elif action_id in ("google_calendar.list_events", "google_calendar.list_all_events"):
                    res = {
                        "events": connector.list_events(
                            calendar_id=inp.get("calendar_id"),
                            limit=int(inp.get("limit", 50)),
                            time_min=inp.get("time_min"),
                            time_max=inp.get("time_max"),
                            query=inp.get("query"),
                        )
                    }
                elif action_id == "google_calendar.get_event":
                    res = connector.get_event(event_id=inp.get("event_id", ""), calendar_id=inp.get("calendar_id"))
                elif action_id == "google_calendar.update_event":
                    res = connector.update_event(
                        event_id=inp.get("event_id", ""),
                        title=inp.get("title"),
                        start_time=inp.get("start_time"),
                        end_time=inp.get("end_time"),
                        description=inp.get("description"),
                        location=inp.get("location"),
                        calendar_id=inp.get("calendar_id"),
                    )
                elif action_id == "google_calendar.delete_event":
                    res = {"deleted": connector.delete_event(event_id=inp.get("event_id", ""), calendar_id=inp.get("calendar_id"))}
                elif action_id == "google_calendar.list_calendars":
                    res = {"calendars": connector.list_calendars()}
                else:
                    raise ValueError(f"Unknown Google Calendar action: {action_id}")

                if hasattr(self.connection_service, "record_operation_success"):
                    self.connection_service.record_operation_success(ws_id, "google_calendar", action_id)
                return res
            except Exception as exc:
                is_auth = "auth" in str(exc).lower() or "401" in str(exc) or "403" in str(exc)
                if hasattr(self.connection_service, "record_operation_failure"):
                    self.connection_service.record_operation_failure(ws_id, "google_calendar", action_id, str(exc), is_auth_error=is_auth)
                raise

        # 6. Local file actions
        elif action_id == "files.create_document":
            filename = inp.get("filename", "untitled.txt")
            content = inp.get("content", "")
            ws = self._get_workspace(ws_id)
            from aether.core.security import PathSandbox
            base_dir = self._user_files_base(ws)
            sandbox = PathSandbox(base_dir, auto_create=True)
            try:
                target_path = sandbox.resolve(filename)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path = None
                if target_path.is_file():
                    try:
                        previous = target_path.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        previous = None
                    if previous is not None and previous != content:
                        # Overwriting is never silent loss: the previous version is kept in a hidden history folder.
                        import datetime as _dt     # (a local `from datetime import datetime` would shadow the module-level name)
                        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                        history = base_dir / ".aether-versions"
                        history.mkdir(parents=True, exist_ok=True)
                        backup_path = history / f"{target_path.name}.{stamp}"
                        backup_path.write_text(previous, encoding="utf-8")
                target_path.write_text(content, encoding="utf-8")
                return {
                    "path": str(target_path),
                    "filename": filename,
                    "bytes": len(content.encode("utf-8")),
                    "status": "updated" if backup_path else "created",
                    **({"previous_version": str(backup_path)} if backup_path else {}),
                }
            except Exception as e:
                logger.error(f"Failed to write file {filename}: {e}")
                raise IOError(f"Could not create file '{filename}': {e}") from e

        elif action_id == "files.read_document":
            filename = inp.get("filename", "")
            ws = self._get_workspace(ws_id)
            from aether.core.security import PathSandbox
            base_dir = self._user_files_base(ws)
            sandbox = PathSandbox(base_dir, auto_create=True)
            try:
                target_path = sandbox.resolve(filename)
                if not (target_path.exists() and target_path.is_file()):
                    # Fallback check for files_dir if not in project root
                    if ws and hasattr(ws, "files_dir") and (ws.files_dir / filename).is_file():
                        target_path = ws.files_dir / filename
                    else:
                        return {"filename": filename, "content": "", "exists": False, "error": "File not found"}
                content = target_path.read_text(encoding="utf-8", errors="replace")
                return {"filename": filename, "path": str(target_path), "content": content, "exists": True}
            except Exception as e:
                return {"filename": filename, "path": "", "content": "", "exists": False, "error": str(e)}

        # 7. Web search action
        elif action_id == "web.search":
            query = (inp.get("query") or "").strip()
            if not query:
                raise ValueError("Web search query cannot be empty.")
            from aether.tools.web_search import DuckDuckGoSearchBackend
            backend = DuckDuckGoSearchBackend()
            try:
                results = backend.search(query=query, max_results=int(inp.get("max_results", 5)))
                return {
                    "query": query,
                    "results": [r.to_dict() for r in results],
                }
            except Exception as e:
                logger.error(f"Web search backend failed for query '{query}': {e}")
                raise RuntimeError(f"Web search failed: {e}") from e

        # 8. Automations actions
        elif action_id == "automations.create_draft":
            from aether.automation.builder import AutomationBuilder
            from aether.automation.models import AutomationDefinition
            prompt_text = inp.get("prompt", "")
            raw_auto = inp.get("automation")
            auto_def = AutomationDefinition.from_dict(raw_auto) if raw_auto else AutomationBuilder.build_from_natural_language(prompt_text)
            ws = self._get_workspace(ws_id)
            if not hasattr(ws, "automations") or not ws.automations:
                raise RuntimeError("Automations subsystem unavailable in workspace.")
            saved = ws.automations.save_automation(auto_def)
            return {"automation_id": saved.id, "name": saved.name, "status": "draft", "human_schedule": saved.human_schedule}

        elif action_id == "automations.activate":
            auto_id = inp.get("automation_id", "")
            ws = self._get_workspace(ws_id)
            if not hasattr(ws, "automations") or not ws.automations:
                raise RuntimeError("Automations subsystem unavailable in workspace.")
            activated = ws.automations.toggle_automation(auto_id, True)
            if activated:
                return {"automation_id": activated.id, "name": activated.name, "status": "active", "enabled": True}
            raise ValueError(f"Automation '{auto_id}' not found")

        # 9. Mission dry run action
        elif action_id == "missions.dry_run":
            from aether.missions.dry_run import MissionDryRunEngine
            from aether.missions.models import Milestone, Mission
            from aether.workspace.workspace import Workspace

            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None

            mid = inp.get("mission_id")
            mission = None
            if ws and mid and hasattr(ws, "missions"):
                mission = ws.missions.get_mission(mid)

            if not mission:
                title = inp.get("title", "Proposed Mission")
                obj = inp.get("objective", title)
                raw_milestones = inp.get("milestones", [])
                milestones = [Milestone.from_dict(m) if isinstance(m, dict) else m for m in raw_milestones]
                mission = Mission(
                    id=mid or f"msn-draft",
                    workspace_id=ws_id,
                    title=title,
                    objective=obj,
                    milestones=milestones,
                )

            report = MissionDryRunEngine.analyze_mission(mission, ws)
            return report.to_dict()

        # 10. Connection sync action
        elif action_id == "connections.sync":
            from aether.connections.sync import ConnectorSyncEngine
            from aether.workspace.workspace import Workspace

            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None

            if not ws:
                raise ValueError(f"Workspace '{ws_id}' not found for connection sync.")

            provider_req = inp.get("provider")
            options = inp.get("options") or {}

            if provider_req:
                res = ConnectorSyncEngine.sync_provider(ws, provider_req, options)
                return {
                    "synced": [res.to_dict()],
                    "total_items_synced": res.items_synced,
                    "provider": provider_req,
                    "status": res.status,
                }
            else:
                results = ConnectorSyncEngine.sync_all(ws, options)
                total = sum(r.items_synced for r in results)
                return {
                    "synced": [r.to_dict() for r in results],
                    "total_items_synced": total,
                    "status": "synced",
                }

        # 11. External agent delegation action
        elif action_id == "agents.delegate_external":
            import os
            from aether.agents.external import ExternalAgentAdapter, ExternalAgentConfig
            from aether.core.execution import Task

            agent_name = inp.get("agent_name", "external_worker")
            instruction = inp.get("instruction", "")
            protocol = str(inp.get("protocol", "http")).lower()
            endpoint_url = inp.get("endpoint_url")
            command = inp.get("command")
            timeout_seconds = float(inp.get("timeout_seconds", 60.0))
            auth_token = inp.get("auth_token")
            context_data = inp.get("context_data", {})

            # Try to resolve configured agent from team if exists
            target_adapter = None
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None

            if ws and hasattr(ws, "team") and ws.team:
                team_agent = ws.team._agents.get(agent_name)
                if isinstance(team_agent, ExternalAgentAdapter):
                    target_adapter = team_agent

            auth_obj = None
            if execution.metadata.get("authority"):
                from aether.core.execution import ExecutionAuthority
                auth_obj = ExecutionAuthority.from_dict(execution.metadata["authority"])

            if target_adapter is None:
                # Local commands must be pre-registered in workspace team configuration
                if command or protocol in ("cli", "command", "process"):
                    raise UnauthorizedExecutionError(
                        f"External agent '{agent_name}' with local command execution must be pre-registered in workspace team configuration."
                    )
                # Validate endpoint_url against SSRF
                if endpoint_url:
                    from aether.core.security import validate_public_url
                    validate_public_url(endpoint_url)

                if not endpoint_url and protocol != "mcp":
                    endpoint_url = os.environ.get("AETHER_EXTERNAL_AGENT_URL")

                cfg = ExternalAgentConfig(
                    name=agent_name,
                    role=inp.get("role", "external_worker"),
                    protocol=protocol,
                    endpoint_url=endpoint_url,
                    command=None,
                    timeout_seconds=timeout_seconds,
                    auth_token=auth_token,
                )
                target_adapter = ExternalAgentAdapter(config=cfg, workspace=self.workspace or ws)
            elif not getattr(target_adapter, "workspace", None) and (self.workspace or ws):
                target_adapter.workspace = self.workspace or ws

            task = Task(
                instruction=instruction,
                agent_name=agent_name,
                context_data=context_data,
                workspace_id=ws_id,
                authority=auth_obj,
            )
            res = target_adapter.execute(task, authority=auth_obj)
            return {
                "success": res.success,
                "status": str(res.status.value) if res.status else ("completed" if res.success else "failed"),
                "output": res.output,
                "error": res.error,
                "artifacts": res.artifacts,
                "deliverables": res.deliverables,
                "metadata": res.metadata,
            }

        # 11b. External autonomous coding agent orchestration
        elif action_id.startswith("coding."):
            from aether.coding.orchestrator import get_coding_orchestrator
            from aether.coding.models import CodingTask

            orchestrator = get_coding_orchestrator()
            run_store = self._coding_run_store(ws_id)
            orchestrator.bind_run_store(run_store)

            if action_id == "coding.list_runs":
                runs = run_store.list_runs(mission_id=inp.get("mission_id"), limit=int(inp.get("limit", 50)))
                return {"runs": [
                    {"id": r.id, "status": r.status.value, "provider_id": r.provider_id,
                     "model": (r.metadata or {}).get("model") or r.task.model, "mission_id": r.task.mission_id,
                     "proposal_id": r.task.proposal_id, "project_path": r.task.project_path,
                     "external_task_id": r.external_task_id, "started_at": r.started_at, "completed_at": r.completed_at,
                     "modified_files": (r.result.modified_files if r.result else []),
                     "remote_session_may_continue": bool((r.metadata or {}).get("remote_session_may_continue")),
                     } for r in runs]}

            elif action_id == "coding.run_tests":
                exec_id = self._scoped_coding_execution_id(ws_id, inp.get("execution_id"))
                self._import_legacy_coding_run(orchestrator, ws_id, exec_id)
                found = orchestrator._find(exec_id)
                if not found:
                    raise ValueError(f"Coding run '{exec_id}' not found.")
                provider, run = found
                if run.status.value in ("running", "queued"):
                    raise ValueError("Tests cannot run while the coding agent is still working on the project.")
                self._assert_coding_path_allowed(
                    Path(run.task.project_path).resolve(), execution.metadata.get("allowed_paths") or [], self._workspace_roots(ws_id)
                )
                from aether.coding.runs import run_authorised_tests
                outcome = run_authorised_tests(run, runner=inp.get("runner") or "auto",
                                               timeout_seconds=float(inp.get("timeout_seconds", 120.0)))
                run.result = provider.collect_results(run.id, raw_output=run.result.raw_output if run.result else None)
                provider._emit(run, "tests_run", exit_code=outcome["exit_code"], passed=outcome["passed"], runner=outcome["runner"])
                execution.metadata["coding_execution_id"] = run.id
                return {"success": True, "execution_id": run.id, "status": run.status.value,
                        "verification_passed": run.result.verification_passed, **outcome}

            elif action_id == "coding.release_project":
                exec_id = self._scoped_coding_execution_id(ws_id, inp.get("execution_id"))
                if not run_store.mark_released(exec_id, str(inp.get("reason") or "released by user")):
                    raise ValueError(f"Coding run '{exec_id}' not found.")
                execution.metadata["coding_execution_id"] = exec_id
                return {"success": True, "released": True, "execution_id": exec_id}

            if action_id == "coding.list_providers":
                ws = None
                try:
                    ws = self._get_workspace(ws_id)
                except Exception:
                    pass
                providers = orchestrator.list_providers(workspace=ws)
                pref_id = orchestrator.get_preferred_provider_id(workspace=ws)
                return {"providers": providers, "preferred_provider_id": pref_id}

            elif action_id == "coding.status":
                exec_id = self._scoped_coding_execution_id(ws_id, inp.get("execution_id"))
                self._import_legacy_coding_run(orchestrator, ws_id, exec_id)
                st = orchestrator.get_status(exec_id)
                return {
                    "status": st.status.value,
                    "provider_id": st.provider_id,
                    "external_task_id": st.external_task_id,
                    "execution_id": st.id,
                    "instruction": st.task.instruction,
                    "project_path": st.task.project_path,
                }

            elif action_id == "coding.results":
                exec_id = self._scoped_coding_execution_id(ws_id, inp.get("execution_id"))
                self._import_legacy_coding_run(orchestrator, ws_id, exec_id)
                results = orchestrator.collect_results(exec_id)
                return results.to_dict()

            elif action_id == "coding.delegate":
                ws = None
                try:
                    ws = self._get_workspace(ws_id)
                except Exception:
                    pass

                proj_path = inp.get("project_path")
                if not proj_path and ws and getattr(ws, "root", None):
                    proj_path = str(ws.root)
                if not proj_path and self.project_path:
                    proj_path = str(self.project_path)
                if not proj_path:
                    raise ValueError(
                        "project_path is required for coding delegation: Aether never falls back to the process working directory."
                    )

                p_dir = Path(proj_path).resolve()
                if not p_dir.exists() or not p_dir.is_dir():
                    raise ValueError(f"Project directory does not exist or is not a directory: {proj_path}")
                self._assert_coding_path_allowed(p_dir, execution.metadata.get("allowed_paths") or [], self._workspace_roots(ws_id))

                coding_mission_id = inp.get("mission_id") or execution.metadata.get("mission_id")
                created_mission_id = None
                if not coding_mission_id and ws is not None:
                    coding_mission_id = created_mission_id = self._create_coding_mission(ws, ws_id, inp, execution, p_dir)
                task = CodingTask(
                    instruction=inp.get("instruction", ""),
                    project_path=proj_path,
                    context_files=list(inp.get("context_files") or []),
                    context_data=dict(inp.get("context_data") or {}),
                    provider_id=inp.get("provider_id"),
                    model=inp.get("model"),
                    timeout_seconds=float(inp.get("timeout_seconds", 300.0)),
                    workspace_id=ws_id,
                    mission_id=coding_mission_id,
                    proposal_id=execution.metadata.get("proposal_id"),
                )

                try:
                    coding_exec = orchestrator.delegate_task(task, preferred_provider_id=inp.get("provider_id"), workspace=ws)
                except Exception as dispatch_exc:
                    # No run ever started (project busy, provider unavailable, ...): the mission we just created must
                    # not stay "running". The failure is recorded on it, then the original error keeps propagating.
                    if created_mission_id and ws is not None:
                        self._close_undispatched_coding_mission(ws, ws_id, created_mission_id, dispatch_exc)
                    raise
                # Persist the link between this action record and the coding run even if the run fails,
                # so later interaction/status calls can be authorised against the right proposal/workspace.
                execution.metadata["coding_execution_id"] = coding_exec.id
                execution.metadata["coding_provider_id"] = coding_exec.provider_id
                res_dict = coding_exec.result.to_dict() if coding_exec.result else {}
                waiting = coding_exec.status.value in ("waiting_for_interaction", "waiting_for_approval")

                run_state = coding_exec.status.value
                verified = bool(coding_exec.result and coding_exec.result.verification_passed is True and run_state == "completed")
                run_terminal = run_state in ("completed", "failed", "timed_out", "cancelled", "requires_rework")
                execution.metadata["coding_run_state"] = run_state
                return {
                    # "success" keeps its historical meaning for the action record: the request was accepted and the run
                    # did not fail. It does NOT say the work is done: use run_terminal / verified / deliverable_ready.
                    "success": True if waiting else (coding_exec.result.success if coding_exec.result else (run_state == "completed")),
                    "run_terminal": run_terminal,
                    "awaiting": ("interaction" if run_state == "waiting_for_interaction"
                                 else "approval" if run_state == "waiting_for_approval" else None),
                    "verified": verified,
                    "deliverable_ready": verified,
                    "status": coding_exec.status.value,
                    "provider_id": coding_exec.provider_id,
                    "execution_id": coding_exec.id,
                    "external_task_id": coding_exec.external_task_id,
                    "summary": coding_exec.result.summary if coding_exec.result else "",
                    "diff": coding_exec.result.diff if coding_exec.result else "",
                    "modified_files": coding_exec.result.modified_files if coding_exec.result else [],
                    "test_output": coding_exec.result.test_output if coding_exec.result else None,
                    "test_passed": coding_exec.result.test_passed if coding_exec.result else None,
                    "interaction_prompt": coding_exec.interaction_prompt,
                    "interaction_options": coding_exec.interaction_options,
                    "error": coding_exec.error,
                    "result": res_dict,
                }

            elif action_id in ("coding.send_message", "coding.interact"):
                exec_id = self._scoped_coding_execution_id(ws_id, inp.get("execution_id"))
                self._import_legacy_coding_run(orchestrator, ws_id, exec_id)
                msg_text = inp.get("message") or inp.get("decision") or ""
                coding_exec = orchestrator.send_message(exec_id, msg_text)
                res_dict = coding_exec.result.to_dict() if coding_exec.result else {}
                return {
                    # The reply was delivered; the action fails only if the run ended failed/timed out/cancelled.
                    "success": coding_exec.status.value not in ("failed", "timed_out", "cancelled"),
                    "status": coding_exec.status.value,
                    "provider_id": coding_exec.provider_id,
                    "execution_id": coding_exec.id,
                    "external_task_id": coding_exec.external_task_id,
                    "summary": coding_exec.result.summary if coding_exec.result else "",
                    "diff": coding_exec.result.diff if coding_exec.result else "",
                    "modified_files": coding_exec.result.modified_files if coding_exec.result else [],
                    "test_output": coding_exec.result.test_output if coding_exec.result else None,
                    "test_passed": coding_exec.result.test_passed if coding_exec.result else None,
                    "interaction_prompt": coding_exec.interaction_prompt,
                    "interaction_options": coding_exec.interaction_options,
                    "error": coding_exec.error,
                    "result": res_dict,
                }

        # 12. Knowledge Base actions
        elif action_id == "knowledge.search":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None

            team = getattr(ws, "default_team", None) or (ws.load_team() if ws else None)
            knowledge_store = getattr(team, "knowledge", None) if team else None
            if not knowledge_store and ws:
                from aether.knowledge.store import KnowledgeStore
                knowledge_store = KnowledgeStore(str(ws.knowledge_db_path))

            if not knowledge_store:
                return {"chunks": [], "count": 0}

            query = inp.get("query", "")
            limit = int(inp.get("limit", 5))
            scope = inp.get("scope", "workspace")
            project_id = inp.get("project_id")
            results = knowledge_store.search(query=query, limit=limit, scope=scope, project_id=project_id)
            return {
                "chunks": [c.to_dict() if hasattr(c, "to_dict") else {"content": c.content, "source": c.source} for c in results],
                "count": len(results),
            }

        elif action_id == "knowledge.ingest_url":
            from aether.workspace.workspace import Workspace
            from aether.knowledge.ingestion import DocumentIngester
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None

            team = getattr(ws, "default_team", None) or (ws.load_team() if ws else None)
            knowledge_store = getattr(team, "knowledge", None) if team else None
            if not knowledge_store and ws:
                from aether.knowledge.store import KnowledgeStore
                knowledge_store = KnowledgeStore(str(ws.knowledge_db_path))

            if not knowledge_store:
                raise ValueError("Knowledge store is not initialized in workspace.")

            url = inp.get("url", "")
            source_name = inp.get("source_name") or url
            scope = inp.get("scope", "workspace")
            project_id = inp.get("project_id")

            ingester = DocumentIngester(knowledge_store)
            chunks_added = ingester.ingest_url(url=url, source_name=source_name, scope=scope, project_id=project_id)
            return {
                "chunks_added": chunks_added,
                "source": source_name,
                "url": url,
            }

        elif action_id == "knowledge.ingest_file":
            from aether.workspace.workspace import Workspace
            from aether.knowledge.ingestion import DocumentIngester
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None

            team = getattr(ws, "default_team", None) or (ws.load_team() if ws else None)
            knowledge_store = getattr(team, "knowledge", None) if team else None
            if not knowledge_store and ws:
                from aether.knowledge.store import KnowledgeStore
                knowledge_store = KnowledgeStore(str(ws.knowledge_db_path))

            if not knowledge_store:
                raise ValueError("Knowledge store is not initialized in workspace.")

            file_path = inp.get("file_path", "")
            source_name = inp.get("source_name")
            scope = inp.get("scope", "workspace")
            project_id = inp.get("project_id")

            ingester = DocumentIngester(knowledge_store)
            chunks_added = ingester.ingest(file_path, source_name=source_name, scope=scope, project_id=project_id)
            return {
                "chunks_added": chunks_added,
                "source": source_name or file_path,
                "file_path": file_path,
            }

        elif action_id == "mission.list_playbooks":
            from aether.missions.playbooks import get_playbook_registry
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            mstore = getattr(ws, "missions", None) if ws else None
            registry = get_playbook_registry(store=mstore)
            cat = inp.get("category")
            playbooks = registry.list_playbooks(category=cat)
            return {
                "playbooks": [p.to_dict() for p in playbooks],
                "count": len(playbooks),
            }

        elif action_id == "mission.instantiate_playbook":
            from aether.missions.playbooks import get_playbook_registry
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            mstore = getattr(ws, "missions", None) if ws else None
            if not mstore:
                raise ValueError("Mission store is not available in current workspace.")
            registry = get_playbook_registry(store=mstore)
            pb_id = inp.get("playbook_id", "")
            mission = registry.instantiate(
                playbook_id=pb_id,
                store=mstore,
                workspace_id=ws_id,
                custom_objective=inp.get("custom_objective"),
                team_name=inp.get("team_name"),
                params=inp.get("params"),
            )
            return {
                "mission_id": mission.id,
                "title": mission.title,
                "milestones_count": len(mission.milestones),
                "objective": mission.objective,
                "team_name": mission.team_name,
            }

        elif action_id == "mission.export_timeline":
            from aether.missions.replay import ReplayCompiler
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            mstore = getattr(ws, "missions", None) if ws else None
            if not mstore:
                raise ValueError("Mission store is not available in current workspace.")
            compiler = ReplayCompiler(store=mstore)
            mission_id = inp.get("mission_id", "")
            execution_id = inp.get("execution_id")
            fmt = inp.get("format", "markdown")
            result = compiler.export_timeline(mission_id=mission_id, execution_id=execution_id, export_format=fmt)
            return {
                "timeline": result,
                "format": fmt,
                "mission_id": mission_id,
            }

        elif action_id == "learning.record_correction":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            learning_svc = getattr(ws, "learning", None) if ws else None
            if not learning_svc:
                raise ValueError("Learning service is not available in current workspace.")

            target_scope = inp.get("target_scope", "workspace")
            target_id = inp.get("target_identifier") or ("workspace" if target_scope == "workspace" else "default")
            problem = inp.get("problem", "")
            correction = inp.get("correction", "")
            rationale = inp.get("rationale", "")
            auto_verify = bool(inp.get("auto_verify", False))

            corr, lsn = learning_svc.record_correction(
                workspace_id=ws_id,
                target_scope=target_scope,
                target_identifier=target_id,
                problem=problem,
                correction=correction,
                rationale=rationale,
                auto_verify=auto_verify,
            )
            return {
                "correction_id": corr.id,
                "verification_status": corr.verification_status.value if hasattr(corr.verification_status, "value") else str(corr.verification_status),
                "lesson_id": lsn.id if lsn else None,
                "problem": corr.problem,
                "correction": corr.correction,
            }

        elif action_id == "learning.verify_correction":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            learning_svc = getattr(ws, "learning", None) if ws else None
            if not learning_svc:
                raise ValueError("Learning service is not available in current workspace.")

            corr_id = inp.get("correction_id", "")
            lesson = learning_svc.verify_correction(correction_id=corr_id, workspace_id=ws_id)
            return {
                "lesson_id": lesson.id,
                "title": lesson.title,
                "verification_status": lesson.verification_status.value if hasattr(lesson.verification_status, "value") else str(lesson.verification_status),
                "scope": lesson.scope.value if hasattr(lesson.scope, "value") else str(lesson.scope),
                "lesson_text": lesson.lesson_text,
            }

        elif action_id == "learning.list_lessons":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            learning_store = getattr(ws, "learning_store", None) if ws else None
            if not learning_store:
                raise ValueError("Learning store is not available in current workspace.")

            scope = inp.get("scope")
            status = inp.get("verification_status")
            limit = int(inp.get("limit", 50))
            lessons = learning_store.list_lessons(
                workspace_id=ws_id,
                scope=scope,
                verification_status=status,
                limit=limit,
            )
            return {
                "lessons": [l.to_dict() for l in lessons],
                "count": len(lessons),
            }

        elif action_id == "learning.get_insights":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            learning_svc = getattr(ws, "learning", None) if ws else None
            if not learning_svc:
                raise ValueError("Learning service is not available in current workspace.")

            insights = learning_svc.get_insights(workspace_id=ws_id)
            return insights

        elif action_id == "policy.get_policy":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            policy_svc = getattr(ws, "policy", None) if ws else None
            if not policy_svc:
                raise ValueError("Policy service is not available in current workspace.")
            p = policy_svc.get_policy(ws_id)
            return p.to_dict()

        elif action_id == "policy.update_policy":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            policy_svc = getattr(ws, "policy", None) if ws else None
            if not policy_svc:
                raise ValueError("Policy service is not available in current workspace.")
            p = policy_svc.update_policy(ws_id, inp)
            return {"policy": p.to_dict()}

        elif action_id == "routing.get_status":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            router = getattr(ws, "model_router", None) if ws else None
            if not router:
                from aether.routing.router import ModelRouter
                router = ModelRouter()
            return {
                "tiers": router.config.to_dict(),
            }

        elif action_id == "workflow.list":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            wf_store = getattr(ws, "workflows", None) if ws else None
            if not wf_store:
                raise ValueError("Workflow store is not available in current workspace.")
            wfs = wf_store.list_workflows(ws_id)
            return {
                "workflows": [w.to_dict() for w in wfs],
                "count": len(wfs),
            }

        elif action_id == "workflow.compile":
            from aether.workflows.compiler import WorkflowCompiler
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            wf_store = getattr(ws, "workflows", None) if ws else None
            if not wf_store:
                raise ValueError("Workflow store is not available in current workspace.")

            wf_id = inp.get("workflow_id", "")
            target_type = inp.get("target_type", "mission").lower()
            workflow = wf_store.get_workflow(wf_id, workspace_id=ws_id)
            if not workflow:
                raise ValueError(f"Workflow '{wf_id}' not found.")

            if target_type == "automation":
                auto_store = getattr(ws, "automations", None)
                if not auto_store:
                    raise ValueError("Automation store is not available.")
                res_obj = WorkflowCompiler.compile_to_automation(workflow, auto_store)
                wf_store.save_workflow(workflow)
                return {
                    "workflow_id": wf_id,
                    "compiled_id": res_obj.id,
                    "target_type": "automation",
                    "name": res_obj.name,
                }
            else:
                m_store = getattr(ws, "missions", None)
                if not m_store:
                    raise ValueError("Mission store is not available.")
                res_obj = WorkflowCompiler.compile_to_mission(workflow, m_store, params=inp.get("params"))
                wf_store.save_workflow(workflow)
                return {
                    "workflow_id": wf_id,
                    "compiled_id": res_obj.id,
                    "target_type": "mission",
                    "name": res_obj.title,
                }

        elif action_id == "workflow.run":
            from aether.workflows.compiler import WorkflowCompiler
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            wf_store = getattr(ws, "workflows", None) if ws else None
            m_store = getattr(ws, "missions", None) if ws else None
            if not wf_store or not m_store:
                raise ValueError("Workflow and Mission stores are required.")

            wf_id = inp.get("workflow_id", "")
            workflow = wf_store.get_workflow(wf_id, workspace_id=ws_id)
            if not workflow:
                raise ValueError(f"Workflow '{wf_id}' not found.")

            mission = WorkflowCompiler.compile_to_mission(workflow, m_store, params=inp.get("params"))
            wf_store.save_workflow(workflow)
            return {
                "mission_id": mission.id,
                "title": mission.title,
                "status": mission.status.value if hasattr(mission.status, "value") else str(mission.status),
                "milestones_count": len(mission.milestones),
            }

        elif action_id == "marketplace.list":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            eco_store = getattr(ws, "ecosystem", None) if ws else None
            if not eco_store:
                from aether.ecosystem.store import EcosystemStore
                eco_store = EcosystemStore(":memory:")

            pkgs = eco_store.list_packages(
                pkg_type=inp.get("type"),
                category=inp.get("category"),
                search=inp.get("search"),
                workspace_id=ws_id,
            )
            return {
                "packages": pkgs,
                "count": len(pkgs),
            }

        elif action_id == "marketplace.inspect":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            eco_store = getattr(ws, "ecosystem", None) if ws else None
            if not eco_store:
                raise ValueError("Ecosystem store is not available.")

            pkg_id = inp.get("package_id", "")
            pkg = eco_store.get_package(pkg_id)
            if not pkg:
                raise ValueError(f"Package '{pkg_id}' not found in marketplace catalog.")

            return {
                "package": pkg.to_dict(),
                "security_summary": pkg.security_summary.to_dict(),
            }

        elif action_id == "marketplace.install":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to install marketplace package.")
            eco_store = getattr(ws, "ecosystem", None)
            if not eco_store:
                raise ValueError("Ecosystem store is not available in workspace.")

            pkg_id = inp.get("package_id", "")
            installed = eco_store.install_package(pkg_id, ws)
            return {
                "package_id": installed.package_id,
                "installed": True,
                "version": installed.version,
                "install_path": installed.install_path or "",
            }

        elif action_id == "marketplace.uninstall":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to uninstall marketplace package.")
            eco_store = getattr(ws, "ecosystem", None)
            if not eco_store:
                raise ValueError("Ecosystem store is not available in workspace.")

            pkg_id = inp.get("package_id", "")
            success = eco_store.uninstall_package(pkg_id, ws)
            return {
                "package_id": pkg_id,
                "uninstalled": success,
            }

        elif action_id == "content.repurpose":
            from aether.workspace.workspace import Workspace
            from aether.content.models import RepurposeRequest, PlatformType, ContentTone
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to repurpose content.")
            content_store = getattr(ws, "content", None)
            content_engine = getattr(ws, "content_engine", None)
            if not content_store or not content_engine:
                raise ValueError("Content store or engine not available in workspace.")

            target_platforms_raw = inp.get("target_platforms") or ["linkedin", "twitter_thread", "newsletter", "video_script"]
            target_platforms = [PlatformType(p) for p in target_platforms_raw]
            tone_str = inp.get("tone", "thought_leadership")
            try:
                tone = ContentTone(tone_str)
            except ValueError:
                tone = ContentTone.THOUGHT_LEADERSHIP

            req = RepurposeRequest(
                source_text=inp.get("source_text", ""),
                title=inp.get("title") or "Repurposed Content",
                target_platforms=target_platforms,
                tone=tone,
                target_audience=inp.get("target_audience") or "Professionals & Developers",
                campaign_id=inp.get("campaign_id"),
            )
            result = content_engine.repurpose(req)
            content_store.save_content_item(result.item)
            for var in result.variants:
                content_store.save_variant(var)

            return result.to_dict()

        elif action_id == "content.create_campaign":
            from aether.workspace.workspace import Workspace
            from aether.content.models import Campaign
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to create campaign.")
            content_store = getattr(ws, "content", None)
            if not content_store:
                raise ValueError("Content store not available in workspace.")

            camp = Campaign(
                name=inp.get("name", "New Campaign"),
                description=inp.get("description", ""),
                target_audience=inp.get("target_audience", "General Audience"),
                objectives=inp.get("objectives", []),
                tags=inp.get("tags", []),
            )
            saved = content_store.create_campaign(camp)
            return {"campaign": saved.to_dict()}

        elif action_id == "content.list_campaigns":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to list campaigns.")
            content_store = getattr(ws, "content", None)
            if not content_store:
                return {"campaigns": []}

            status = inp.get("status")
            camps = content_store.list_campaigns(status=status)
            return {"campaigns": [c.to_dict() for c in camps]}

        elif action_id == "content.schedule_variant":
            from aether.workspace.workspace import Workspace
            from aether.content.models import ContentStatus
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to schedule variant.")
            content_store = getattr(ws, "content", None)
            if not content_store:
                raise ValueError("Content store not available in workspace.")

            variant_id = inp.get("variant_id", "")
            scheduled_at = inp.get("scheduled_at")
            updated = content_store.update_variant_status(
                variant_id=variant_id,
                status=ContentStatus.SCHEDULED,
                scheduled_at=scheduled_at,
            )
            if not updated:
                raise ValueError(f"Variant '{variant_id}' not found.")
            return {"variant": updated.to_dict()}

        elif action_id == "content.list_variants":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to list variants.")
            content_store = getattr(ws, "content", None)
            if not content_store:
                return {"variants": []}

            vars_list = content_store.list_variants(
                item_id=inp.get("item_id"),
                platform=inp.get("platform"),
                status=inp.get("status"),
            )
            return {"variants": [v.to_dict() for v in vars_list]}

        elif action_id == "client.create_profile":
            from aether.workspace.workspace import Workspace
            from aether.client.models import ClientProfile, BrandStyleGuide
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to create client profile.")
            client_store = getattr(ws, "client_store", None)
            if not client_store:
                raise ValueError("Client store not available in workspace.")

            brand_style = BrandStyleGuide(
                tone=inp.get("tone", "professional"),
                target_audience=inp.get("target_audience", "B2B Decision Makers"),
            )
            profile = ClientProfile(
                name=inp.get("name", "Client Org"),
                domain=inp.get("domain", ""),
                contact_email=inp.get("contact_email", ""),
                brand_style=brand_style,
                monthly_budget_tokens=inp.get("monthly_budget_tokens", 10_000_000),
            )
            saved = client_store.create_client(profile)
            return {"client": saved.to_dict()}

        elif action_id == "client.list_profiles":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to list clients.")
            client_store = getattr(ws, "client_store", None)
            if not client_store:
                return {"clients": []}

            clients = client_store.list_clients(status=inp.get("status"))
            return {"clients": [c.to_dict() for c in clients]}

        elif action_id == "client.create_review_link":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to create review link.")
            client_store = getattr(ws, "client_store", None)
            client_engine = getattr(ws, "client_engine", None)
            if not client_store or not client_engine:
                raise ValueError("Client store or engine not available in workspace.")

            rev = client_engine.create_review_link(
                client_id=inp.get("client_id", ""),
                deliverable_title=inp.get("deliverable_title", "Deliverable Batch"),
                deliverable_type=inp.get("deliverable_type", "content_batch"),
                deliverable_payload=inp.get("deliverable_payload", {}),
            )
            saved_rev = client_store.create_review_link(rev)
            return {"review": saved_rev.to_dict()}

        elif action_id == "client.submit_review":
            from aether.workspace.workspace import Workspace
            from aether.client.models import ReviewStatus
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to submit review decision.")
            client_store = getattr(ws, "client_store", None)
            if not client_store:
                raise ValueError("Client store not available in workspace.")

            token = inp.get("token", "")
            decision_str = inp.get("decision", "approved")
            status = ReviewStatus.APPROVED if decision_str == "approved" else ReviewStatus.REVISION_REQUESTED
            feedback = inp.get("feedback", "")
            updated = client_store.update_review_decision(token, status=status, feedback=feedback)
            if not updated:
                raise ValueError(f"Review link with token '{token}' not found.")
            return {"review": updated.to_dict()}

        elif action_id == "client.generate_report":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to generate client report.")
            client_store = getattr(ws, "client_store", None)
            client_engine = getattr(ws, "client_engine", None)
            content_store = getattr(ws, "content", None)
            if not client_store or not client_engine:
                raise ValueError("Client store or engine not available in workspace.")

            client_id = inp.get("client_id", "")
            client = client_store.get_client(client_id)
            if not client:
                raise ValueError(f"Client '{client_id}' not found.")

            report = client_engine.generate_client_executive_report(client, client_store, content_store)
            return {"report_markdown": report}

        elif action_id == "analytics.get_campaign_bi":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required for campaign business intelligence.")
            client_engine = getattr(ws, "client_engine", None)
            content_store = getattr(ws, "content", None)
            if not client_engine:
                raise ValueError("Client engine not available in workspace.")

            campaign_id = inp.get("campaign_id", "")
            bi = client_engine.generate_campaign_bi(campaign_id, content_store=content_store)
            return {"bi": bi.to_dict()}

        elif action_id == "benchmarking.run_suite":
            from aether.workspace.workspace import Workspace
            from aether.benchmarking.models import BenchmarkTargetType
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to run benchmark suite.")
            bm_store = getattr(ws, "benchmarking_store", None)
            bm_engine = getattr(ws, "benchmarking_engine", None)
            if not bm_store or not bm_engine:
                raise ValueError("Benchmarking store or engine not available in workspace.")

            target_id = inp.get("target_id") or inp.get("target_name") or "researcher"
            target_name = inp.get("target_name") or inp.get("target_id") or "researcher"
            target_type_str = inp.get("target_type", "agent")
            target_type = BenchmarkTargetType(target_type_str) if target_type_str in [t.value for t in BenchmarkTargetType] else BenchmarkTargetType.AGENT
            suite_name = inp.get("suite_name", "general_capability_v1")

            saved_run, alerts, proposals = bm_engine.evaluate_target(
                target_id=target_id,
                target_name=target_name,
                target_type=target_type,
                suite_name=suite_name,
                latency_ms=inp.get("latency_ms"),
                tokens_used=inp.get("tokens_used"),
                error_rate=inp.get("error_rate"),
                quality_score=inp.get("quality_score"),
                safety_compliance=inp.get("safety_compliance"),
                completion_rate=inp.get("completion_rate"),
            )

            return {
                "run": saved_run.to_dict(),
                "benchmark_run": saved_run.to_dict(),
                "alerts": [a.to_dict() for a in alerts],
                "proposals": [p.to_dict() for p in proposals],
                "proposal": proposals[0].to_dict() if proposals else None,
            }

        elif action_id == "benchmarking.get_leaderboard":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required for benchmark leaderboard.")
            bm_store = getattr(ws, "benchmarking_store", None)
            if not bm_store:
                return {"leaderboard": []}

            target_type = inp.get("target_type")
            limit = int(inp.get("limit", 20))
            runs = bm_store.list_runs(target_type=target_type, limit=limit)
            sorted_runs = sorted(runs, key=lambda r: r.overall_score, reverse=True)
            return {"leaderboard": [r.to_dict() for r in sorted_runs]}

        elif action_id == "benchmarking.list_proposals":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to list evolution proposals.")
            bm_store = getattr(ws, "benchmarking_store", None)
            if not bm_store:
                return {"proposals": []}

            props = bm_store.list_proposals(
                target_agent=inp.get("target_agent"),
                status=inp.get("status"),
            )
            return {"proposals": [p.to_dict() for p in props]}

        elif action_id == "benchmarking.apply_proposal":
            from aether.workspace.workspace import Workspace
            from aether.benchmarking.models import ProposalStatus
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to apply evolution proposal.")
            bm_store = getattr(ws, "benchmarking_store", None)
            bm_engine = getattr(ws, "benchmarking_engine", None)
            if not bm_store or not bm_engine:
                raise ValueError("Benchmarking store or engine not available in workspace.")

            proposal_id = inp.get("proposal_id", "")
            prop = bm_store.get_proposal(proposal_id)
            if not prop:
                raise ValueError(f"Proposal '{proposal_id}' not found.")

            applied = bm_engine.apply_evolution_proposal(prop, ws)
            updated = bm_store.update_proposal_status(proposal_id, ProposalStatus.APPLIED)
            return {
                "proposal": updated.to_dict() if updated else prop.to_dict(),
                "applied": applied,
            }

        elif action_id == "benchmarking.list_regression_alerts":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to list regression alerts.")
            bm_store = getattr(ws, "benchmarking_store", None)
            if not bm_store:
                return {"alerts": []}

            target_id = inp.get("target_id")
            unresolved = bool(inp.get("unresolved_only", False))
            alerts = bm_store.list_alerts(target_id=target_id, unresolved_only=unresolved)
            return {"alerts": [a.to_dict() for a in alerts]}

        elif action_id == "proactive.list_suggestions":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to list proactive suggestions.")
            pro_store = getattr(ws, "proactive_store", None)
            if not pro_store:
                return {"suggestions": []}

            suggestions = pro_store.list_suggestions(status=inp.get("status"), category=inp.get("category"))
            return {"suggestions": [s.to_dict() for s in suggestions]}

        elif action_id == "proactive.generate_suggestions":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to generate proactive suggestions.")
            pro_engine = getattr(ws, "proactive_engine", None)
            if not pro_engine:
                return {"suggestions": []}

            suggestions = pro_engine.scan_workspace_opportunities(ws)
            return {"suggestions": [s.to_dict() for s in suggestions]}

        elif action_id == "proactive.accept_suggestion":
            from aether.workspace.workspace import Workspace
            from aether.proactive.models import SuggestionStatus
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to accept suggestion.")
            pro_store = getattr(ws, "proactive_store", None)
            if not pro_store:
                raise ValueError("Proactive store not available in workspace.")

            sug_id = inp.get("suggestion_id", "")
            sug = pro_store.get_suggestion(sug_id)
            if not sug:
                raise ValueError(f"Suggestion '{sug_id}' not found.")

            executed_action = {}
            if sug.proposed_action_id:
                exec_res = self.execute(
                    action_id=sug.proposed_action_id,
                    workspace_id=ws_id,
                    input_data=sug.proposed_action_args,
                    auto_approve=True,
                )
                executed_action = exec_res.output_data

            updated = pro_store.update_suggestion_status(sug_id, SuggestionStatus.APPLIED)
            return {
                "suggestion": updated.to_dict() if updated else sug.to_dict(),
                "executed_action": executed_action,
            }

        elif action_id == "proactive.dismiss_suggestion":
            from aether.workspace.workspace import Workspace
            from aether.proactive.models import SuggestionStatus
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to dismiss suggestion.")
            pro_store = getattr(ws, "proactive_store", None)
            if not pro_store:
                raise ValueError("Proactive store not available in workspace.")

            sug_id = inp.get("suggestion_id", "")
            updated = pro_store.update_suggestion_status(sug_id, SuggestionStatus.DISMISSED)
            return {"suggestion": updated.to_dict() if updated else {}}

        elif action_id == "proactive.list_watchers":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to list ambient watchers.")
            pro_store = getattr(ws, "proactive_store", None)
            if not pro_store:
                return {"watchers": []}

            watchers = pro_store.list_watchers(status=inp.get("status"), watcher_type=inp.get("watcher_type"))
            return {"watchers": [w.to_dict() for w in watchers]}

        elif action_id == "proactive.create_watcher":
            from aether.workspace.workspace import Workspace
            from aether.proactive.models import Watcher, WatcherType
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to create ambient watcher.")
            pro_store = getattr(ws, "proactive_store", None)
            if not pro_store:
                raise ValueError("Proactive store not available in workspace.")

            watcher_type_str = inp.get("watcher_type", "file_change")
            watcher_type = WatcherType(watcher_type_str) if watcher_type_str in [t.value for t in WatcherType] else WatcherType.FILE_CHANGE

            watcher = Watcher(
                name=inp.get("name", "Ambient Watcher"),
                description=inp.get("description", ""),
                watcher_type=watcher_type,
                target=inp.get("target", ""),
                condition_expression=inp.get("condition_expression", "modified"),
                action_id=inp.get("action_id", ""),
                action_args=inp.get("action_args", {}),
                auto_trigger=bool(inp.get("auto_trigger", False)),
                interval_seconds=int(inp.get("interval_seconds", 60)),
            )
            saved = pro_store.save_watcher(watcher)
            return {"watcher": saved.to_dict()}

        elif action_id == "proactive.check_watchers":
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required to check ambient watchers.")
            pro_engine = getattr(ws, "proactive_engine", None)
            if not pro_engine:
                return {"results": []}

            results = pro_engine.check_all_watchers(workspace=ws)
            return {
                "results": [
                    {"watcher": w.to_dict(), "triggered": trig, "event": ev.to_dict()}
                    for w, trig, ev in results
                ]
            }

        # ---------------------------------------------------------------------
        # Notification Fabric Execution
        # ---------------------------------------------------------------------
        elif action_id.startswith("notifications."):
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required for notification fabric actions.")
            notif_svc = getattr(ws, "notifications", None)
            if not notif_svc:
                raise ValueError("Notification service not available on workspace.")

            if action_id == "notifications.send_briefing":
                briefing = notif_svc.dispatch_briefing(
                    workspace_id=ws_id,
                    title=inp.get("title", "Executive Update"),
                    summary=inp.get("summary", ""),
                    highlights=inp.get("highlights", []),
                    metrics=inp.get("metrics", {}),
                    action_links=inp.get("action_links", []),
                    channels=inp.get("channels"),
                )
                return {"briefing": briefing.to_dict()}

            elif action_id == "notifications.list_channels":
                channels = notif_svc.get_channels(ws_id)
                return {"channels": [c.to_dict() for c in channels]}

            elif action_id == "notifications.configure_channel":
                channel = notif_svc.configure_channel(
                    workspace_id=ws_id,
                    channel_type=inp.get("channel_type", "desktop"),
                    enabled=inp.get("enabled"),
                    name=inp.get("name"),
                    config=inp.get("config"),
                )
                return {"channel": channel.to_dict()}

            elif action_id == "notifications.test_channel":
                receipt = notif_svc.test_channel(
                    workspace_id=ws_id,
                    channel_type=inp.get("channel_type", "desktop"),
                )
                return {"receipt": receipt.to_dict()}

            elif action_id == "notifications.list_rules":
                rules = notif_svc.get_rules(ws_id)
                return {"rules": [r.to_dict() for r in rules]}

            elif action_id == "notifications.configure_rule":
                rule = notif_svc.configure_rule(
                    workspace_id=ws_id,
                    name=inp.get("name", "Custom Rule"),
                    event_types=inp.get("event_types"),
                    min_priority=inp.get("min_priority"),
                    channels=inp.get("channels"),
                    quiet_hours_enabled=inp.get("quiet_hours_enabled"),
                    quiet_hours_start=inp.get("quiet_hours_start"),
                    quiet_hours_end=inp.get("quiet_hours_end"),
                    rule_id=inp.get("rule_id"),
                )
                return {"rule": rule.to_dict()}

            elif action_id == "notifications.get_delivery_history":
                limit = int(inp.get("limit", 50))
                receipts = notif_svc.get_delivery_history(ws_id, limit=limit)
                return {"receipts": [r.to_dict() for r in receipts]}

        # ---------------------------------------------------------------------
        # Execution Fabric & Hardware Mesh Execution (Layer 17)
        # ---------------------------------------------------------------------
        elif action_id.startswith("fabric."):
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required for execution fabric actions.")
            fab_engine = getattr(ws, "fabric_engine", None)
            if not fab_engine:
                raise ValueError("Fabric engine not available on workspace.")

            if action_id == "fabric.list_nodes":
                nodes = fab_engine.list_nodes(ws_id)
                return {"nodes": [n.to_dict() for n in nodes]}

            elif action_id == "fabric.register_node":
                node = fab_engine.register_remote_node(
                    workspace_id=ws_id,
                    name=inp.get("name", "Remote Worker"),
                    role=inp.get("role", "worker"),
                    endpoint=inp.get("endpoint", "http://localhost:8000"),
                    capabilities=inp.get("capabilities"),
                    tags=inp.get("tags"),
                )
                return {"node": node.to_dict()}

            elif action_id == "fabric.route_workload":
                assignment = fab_engine.route_workload(
                    workspace_id=ws_id,
                    workload_name=inp.get("workload_name", "General Task"),
                    tier=inp.get("tier", "local_fast"),
                    min_cores=int(inp.get("min_cores", 1)),
                    min_vram_gb=float(inp.get("min_vram_gb", 0.0)),
                )
                return {"assignment": assignment.to_dict()}

            elif action_id == "fabric.get_telemetry":
                snapshot = fab_engine.get_telemetry_snapshot(ws_id)
                return {"telemetry": snapshot.to_dict()}

            elif action_id == "fabric.delete_node":
                deleted = fab_engine.delete_node(ws_id, inp.get("node_id", ""))
                return {"status": "ok" if deleted else "not_found", "node_id": inp.get("node_id")}

            elif action_id == "fabric.node_heartbeat":
                success = fab_engine.heartbeat_node(
                    ws_id,
                    inp.get("node_id", ""),
                    ping_ms=float(inp.get("ping_ms", 0.0)),
                )
                return {"status": "ok" if success else "failed", "node_id": inp.get("node_id")}

        elif action_id.startswith("autonomy."):
            from aether.workspace.workspace import Workspace
            try:
                ws = self._get_workspace(ws_id)
            except Exception:
                ws = None
            if not ws:
                raise ValueError("Active workspace required for operational autonomy actions.")
            orchestrator = getattr(ws, "autonomy_orchestrator", None)
            if not orchestrator:
                raise ValueError("Autonomy orchestrator not available on workspace.")

            if action_id == "autonomy.take_care_of_it":
                # Phase A Macro-pass 1.1: Autonomy enters the proposal architecture.
                # Does NOT execute plan_and_execute; stops at the proposal boundary.
                goal_prompt = inp.get("goal", "").strip() or "Autonomous operational loop"
                intent, context_pack, proposal, val_res = ws.personal.create_intent_and_proposal(
                    raw_input=goal_prompt,
                    workspace_id=ws_id,
                    source_surface="autonomy_action",
                )
                return {
                    "status": "blocked_pending_acceptance",
                    "proposal_id": proposal.id,
                    "proposal": proposal.to_dict(),
                    "validation": val_res.to_dict(),
                }

            elif action_id == "autonomy.list_goals":
                store = getattr(ws, "autonomy_store", None)
                goals = store.list_goals(ws_id, limit=int(inp.get("limit", 50))) if store else []
                return {"goals": [g.to_dict() for g in goals], "count": len(goals)}

            elif action_id == "autonomy.get_goal":
                store = getattr(ws, "autonomy_store", None)
                goal = store.get_goal(inp.get("goal_id", "")) if store else None
                if not goal:
                    raise ValueError(f"Autonomous goal '{inp.get('goal_id')}' not found.")
                return {"goal": goal.to_dict()}

        raise ValueError(
            f"Action '{action_id}' is not supported by built-in connectors and has no registered handler."
        )

