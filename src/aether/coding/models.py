"""
Models and Data Contracts for External Coding Agent Orchestration.
Supports Google Antigravity, Claude Code, and OpenAI Codex providers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class CodingExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_INTERACTION = "waiting_for_interaction"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    REQUIRES_REWORK = "requires_rework"


class InstallationState(StrEnum):
    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    OUTDATED = "outdated"
    INCOMPATIBLE_VERSION = "incompatible_version"
    BROKEN_INSTALLATION = "broken_installation"
    INVALID_PATH = "invalid_path"
    INSTALLING = "installing"
    UPDATING = "updating"
    INSTALLATION_FAILED = "installation_failed"
    UNKNOWN = "unknown"


class AuthenticationState(StrEnum):
    AUTHENTICATED = "authenticated"
    NOT_AUTHENTICATED = "not_authenticated"
    CREDENTIALS_DETECTED_UNVERIFIED = "credentials_detected_unverified"
    AUTHENTICATION_EXPIRED_OR_INVALID = "authentication_expired_or_invalid"
    INTERACTIVE_LOGIN_REQUIRED = "interactive_login_required"
    AUTHENTICATION_FAILED = "authentication_failed"
    UNKNOWN = "unknown"


class OperationalState(StrEnum):
    READY = "ready"
    BLOCKED_MISSING_INSTALLATION = "blocked_missing_installation"
    BLOCKED_MISSING_PREREQUISITES = "blocked_missing_prerequisites"
    BLOCKED_AUTHENTICATION = "blocked_authentication"
    BLOCKED_PERMISSIONS = "blocked_permissions"
    BLOCKED_NETWORK = "blocked_network"
    BLOCKED_CONFIGURATION = "blocked_configuration"
    BLOCKED_PROVIDER_ERROR = "blocked_provider_error"
    BUSY = "busy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class NextAction(StrEnum):
    INSTALL = "install"
    LOGIN = "login"
    VERIFY = "verify"
    UPDATE = "update"
    CONFIGURE = "configure"
    CHECK_PERMISSIONS = "check_permissions"
    RETRY = "retry"
    NONE = "none"


class SetupOperationType(StrEnum):
    INSTALL = "install"
    UPDATE = "update"
    AUTHENTICATE = "authenticate"
    DIAGNOSE = "diagnose"


class SetupOperationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SetupOperation:
    """Represents an observable lifecycle setup operation (install, update, authenticate, diagnose)."""
    id: str
    provider_id: str
    operation_type: str  # SetupOperationType
    status: str = SetupOperationStatus.PENDING
    progress: float = 0.0  # 0.0 - 100.0
    message: str = ""
    logs: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "operation_type": str(self.operation_type),
            "status": str(self.status),
            "progress": self.progress,
            "message": self.message,
            "logs": list(self.logs),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SetupOperation:
        return cls(
            id=str(data.get("id", "")),
            provider_id=str(data.get("provider_id", "")),
            operation_type=str(data.get("operation_type", SetupOperationType.DIAGNOSE)),
            status=str(data.get("status", SetupOperationStatus.PENDING)),
            progress=float(data.get("progress", 0.0)),
            message=str(data.get("message", "")),
            logs=list(data.get("logs") or []),
            started_at=str(data.get("started_at", "")),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
        )



@dataclass
class CodingTask:
    """Represents a development/coding task delegated to an external coding agent."""
    instruction: str
    project_path: str
    id: str = field(default_factory=lambda: f"ctask-{uuid.uuid4().hex[:10]}")
    context_files: list[str] = field(default_factory=list)
    context_data: dict[str, Any] = field(default_factory=dict)
    provider_id: str | None = None
    model: str | None = None
    timeout_seconds: float = 300.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Run identity: every result must be attributable to a workspace, a mission (when any) and a proposal.
    workspace_id: str | None = None
    mission_id: str | None = None
    proposal_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "mission_id": self.mission_id,
            "proposal_id": self.proposal_id,
            "id": self.id,
            "instruction": self.instruction,
            "project_path": self.project_path,
            "context_files": list(self.context_files),
            "context_data": dict(self.context_data),
            "provider_id": self.provider_id,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodingTask:
        return cls(
            workspace_id=data.get("workspace_id"),
            mission_id=data.get("mission_id"),
            proposal_id=data.get("proposal_id"),
            id=str(data.get("id") or f"ctask-{uuid.uuid4().hex[:10]}"),
            instruction=str(data.get("instruction", "")),
            project_path=str(data.get("project_path", "")),
            context_files=list(data.get("context_files") or []),
            context_data=dict(data.get("context_data") or {}),
            provider_id=data.get("provider_id"),
            model=data.get("model"),
            timeout_seconds=float(data.get("timeout_seconds", 300.0)),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class CodingResult:
    """Truthful outcome and verifiable evidence from an external coding agent execution."""
    success: bool
    status: CodingExecutionStatus
    provider_id: str
    external_task_id: str | None = None
    summary: str = ""
    diff: str = ""
    modified_files: list[str] = field(default_factory=list)
    test_output: str | None = None
    test_passed: bool | None = None
    error: str | None = None
    deliverables: list[dict[str, Any]] = field(default_factory=list)
    raw_output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    verification_passed: bool | None = None
    verification_details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status.value if isinstance(self.status, CodingExecutionStatus) else str(self.status),
            "provider_id": self.provider_id,
            "external_task_id": self.external_task_id,
            "summary": self.summary,
            "diff": self.diff,
            "modified_files": list(self.modified_files),
            "test_output": self.test_output,
            "test_passed": self.test_passed,
            "error": self.error,
            "deliverables": list(self.deliverables),
            "raw_output": self.raw_output,
            "metadata": dict(self.metadata),
            "verification_passed": self.verification_passed,
            "verification_details": dict(self.verification_details),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodingResult:
        st_raw = data.get("status", CodingExecutionStatus.COMPLETED)
        status = CodingExecutionStatus(st_raw) if st_raw in CodingExecutionStatus._value2member_map_ else CodingExecutionStatus.COMPLETED
        return cls(
            success=bool(data.get("success", False)),
            status=status,
            provider_id=str(data.get("provider_id", "unknown")),
            external_task_id=data.get("external_task_id"),
            summary=str(data.get("summary", "")),
            diff=str(data.get("diff", "")),
            modified_files=list(data.get("modified_files") or []),
            test_output=data.get("test_output"),
            test_passed=data.get("test_passed"),
            error=data.get("error"),
            deliverables=list(data.get("deliverables") or []),
            raw_output=data.get("raw_output"),
            metadata=dict(data.get("metadata") or {}),
            verification_passed=data.get("verification_passed"),
            verification_details=dict(data.get("verification_details") or {}),
        )


@dataclass
class CodingTaskExecution:
    """Execution session state for a delegated coding task."""
    id: str
    task: CodingTask
    provider_id: str
    status: CodingExecutionStatus = CodingExecutionStatus.QUEUED
    external_task_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    result: CodingResult | None = None
    error: str | None = None
    interaction_prompt: str | None = None
    interaction_options: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task.to_dict(),
            "provider_id": self.provider_id,
            "status": self.status.value if isinstance(self.status, CodingExecutionStatus) else str(self.status),
            "external_task_id": self.external_task_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result.to_dict() if self.result else None,
            "error": self.error,
            "interaction_prompt": self.interaction_prompt,
            "interaction_options": list(self.interaction_options),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodingTaskExecution:
        st_raw = data.get("status", CodingExecutionStatus.QUEUED)
        status = CodingExecutionStatus(st_raw) if st_raw in CodingExecutionStatus._value2member_map_ else CodingExecutionStatus.QUEUED
        task_dict = data.get("task") or {}
        task = CodingTask.from_dict(task_dict)
        res_dict = data.get("result")
        result = CodingResult.from_dict(res_dict) if res_dict else None
        return cls(
            id=str(data.get("id", "")),
            task=task,
            provider_id=str(data.get("provider_id", "")),
            status=status,
            external_task_id=data.get("external_task_id"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=result,
            error=data.get("error"),
            interaction_prompt=data.get("interaction_prompt"),
            interaction_options=list(data.get("interaction_options") or []),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class CodingProviderStatus:
    """Truthful readiness, installation, authentication, and diagnostic state for a coding agent."""
    id: str
    name: str
    description: str
    # 3-Dimensional States
    installation_state: str = InstallationState.UNKNOWN
    authentication_state: str = AuthenticationState.UNKNOWN
    operational_state: str = OperationalState.UNKNOWN
    auth_method: str | None = None
    # Boolean fields (derived & validated)
    installed: bool = False
    authenticated: bool = False
    available: bool = False
    is_preferred: bool = False
    binary_path: str | None = None
    version: str | None = None
    version_requirement: str | None = None
    diagnostic: str = ""
    missing_prerequisites: list[str] = field(default_factory=list)
    next_action: str = NextAction.NONE
    error_code: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    active_setup_operation: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        # Align boolean flags with 3D states if legacy or explicit values provided
        if self.installation_state == InstallationState.UNKNOWN and self.installed:
            self.installation_state = InstallationState.INSTALLED
        elif self.installation_state == InstallationState.INSTALLED:
            self.installed = True
        elif self.installation_state in (InstallationState.NOT_INSTALLED, InstallationState.BROKEN_INSTALLATION, InstallationState.INSTALLATION_FAILED):
            self.installed = False

        if self.authentication_state == AuthenticationState.UNKNOWN and self.authenticated:
            self.authentication_state = AuthenticationState.AUTHENTICATED
        elif self.authentication_state == AuthenticationState.AUTHENTICATED:
            self.authenticated = True
        else:
            self.authenticated = False

        # Compute truthful operational state if unknown
        if self.operational_state == OperationalState.UNKNOWN:
            if self.installation_state != InstallationState.INSTALLED:
                self.operational_state = OperationalState.BLOCKED_MISSING_INSTALLATION
            elif self.authentication_state != AuthenticationState.AUTHENTICATED:
                self.operational_state = OperationalState.BLOCKED_AUTHENTICATION
            elif self.missing_prerequisites:
                self.operational_state = OperationalState.BLOCKED_MISSING_PREREQUISITES
            else:
                self.operational_state = OperationalState.READY

        # Derive available strictly from actual verified conditions (Principle: Never hardcode True if requirements missing)
        self.available = (
            self.installation_state == InstallationState.INSTALLED
            and self.authentication_state == AuthenticationState.AUTHENTICATED
            and self.operational_state == OperationalState.READY
            and len(self.missing_prerequisites) == 0
        )

        # Derive next_action if not specified
        if self.next_action == NextAction.NONE:
            if self.installation_state in (InstallationState.NOT_INSTALLED, InstallationState.INSTALLATION_FAILED):
                self.next_action = NextAction.INSTALL
            elif self.installation_state == InstallationState.OUTDATED:
                self.next_action = NextAction.UPDATE
            elif self.authentication_state in (
                AuthenticationState.NOT_AUTHENTICATED,
                AuthenticationState.INTERACTIVE_LOGIN_REQUIRED,
                AuthenticationState.AUTHENTICATION_EXPIRED_OR_INVALID,
                AuthenticationState.CREDENTIALS_DETECTED_UNVERIFIED,
            ):
                self.next_action = NextAction.LOGIN
            elif self.operational_state == OperationalState.BLOCKED_PERMISSIONS:
                self.next_action = NextAction.CHECK_PERMISSIONS
            elif self.available:
                self.next_action = NextAction.NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "installation_state": str(self.installation_state),
            "authentication_state": str(self.authentication_state),
            "operational_state": str(self.operational_state),
            "auth_method": self.auth_method,
            "installed": self.installed,
            "authenticated": self.authenticated,
            "available": self.available,
            "is_preferred": self.is_preferred,
            "binary_path": self.binary_path,
            "version": self.version,
            "version_requirement": self.version_requirement,
            "diagnostic": self.diagnostic,
            "missing_prerequisites": list(self.missing_prerequisites),
            "next_action": str(self.next_action),
            "error_code": self.error_code,
            "capabilities": dict(self.capabilities),
            "active_setup_operation": self.active_setup_operation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodingProviderStatus:
        inst_st = str(data.get("installation_state") or (InstallationState.INSTALLED if data.get("installed") else InstallationState.NOT_INSTALLED))
        auth_st = str(data.get("authentication_state") or (AuthenticationState.AUTHENTICATED if data.get("authenticated") else AuthenticationState.NOT_AUTHENTICATED))
        op_st = str(data.get("operational_state") or (OperationalState.READY if data.get("available") else OperationalState.UNKNOWN))

        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            installation_state=inst_st,
            authentication_state=auth_st,
            operational_state=op_st,
            auth_method=data.get("auth_method"),
            installed=bool(data.get("installed", False)),
            authenticated=bool(data.get("authenticated", False)),
            available=bool(data.get("available", False)),
            is_preferred=bool(data.get("is_preferred", False)),
            binary_path=data.get("binary_path"),
            version=data.get("version"),
            version_requirement=data.get("version_requirement"),
            diagnostic=str(data.get("diagnostic", "")),
            missing_prerequisites=list(data.get("missing_prerequisites") or []),
            next_action=str(data.get("next_action") or NextAction.NONE),
            error_code=data.get("error_code"),
            capabilities=dict(data.get("capabilities") or {}),
            active_setup_operation=data.get("active_setup_operation"),
        )

