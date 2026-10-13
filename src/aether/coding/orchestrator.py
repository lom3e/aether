"""
CodingAgentOrchestrator — Central Orchestrator for External Coding Agents.
Enforces the core product principle:
Aether coordinates, plans, and gathers verifiable evidence,
while external autonomous coding agents perform code modifications.
Never falls back to internal model code generation.
"""
from __future__ import annotations

import logging
from pathlib import Path
import threading
from typing import Any

from aether.coding.base import (
    BaseCodingAgentProvider,
    CodingAgentUnavailableError,
)
from aether.coding.models import (
    CodingExecutionStatus,
    CodingProviderStatus,
    CodingResult,
    CodingTask,
    CodingTaskExecution,
)
from aether.coding.providers.antigravity import AntigravityCodingProvider
from aether.coding.runs import ACTIVE_STATUSES, CodingRunStore, get_run_registry
from aether.coding.providers.claude_code import ClaudeCodeCodingProvider
from aether.coding.providers.codex import CodexCodingProvider

logger = logging.getLogger(__name__)


class CodingAgentOrchestrator:
    """
    Orchestrates delegation of software engineering tasks to autonomous coding agents.
    Maintains provider registry, checks readiness, coordinates execution sessions,
    and retrieves verifiable diffs and deliverables.
    """

    def __init__(self, providers: list[BaseCodingAgentProvider] | None = None) -> None:
        self._providers: dict[str, BaseCodingAgentProvider] = {}
        self._executions: dict[str, tuple[BaseCodingAgentProvider, CodingTaskExecution]] = {}
        self._preferred_provider_id: str | None = None
        self._project_guard = threading.Lock()
        self._reserved_projects: set[str] = set()

        if providers is not None:
            for p in providers:
                self.register_provider(p)
        else:
            self.register_provider(AntigravityCodingProvider())
            self.register_provider(ClaudeCodeCodingProvider())
            self.register_provider(CodexCodingProvider())

    def register_provider(self, provider: BaseCodingAgentProvider) -> None:
        """Registers a provider and attaches the durable run recorder to its lifecycle events."""
        self._providers[provider.id] = provider
        if hasattr(provider, "add_run_listener"):
            registry = get_run_registry()
            provider.add_run_listener(lambda ev, ex, data, _p=provider: registry.record(_p, ev, ex, data))

    def bind_run_store(self, store: CodingRunStore) -> CodingRunStore:
        """Makes a workspace's durable run store known (and recovers its unfinished runs once)."""
        registry = get_run_registry()
        known = registry.store_for(store.workspace_id)
        bound = registry.bind(store)
        if known is None:
            self.recover_runs(bound)
        return bound

    def recover_runs(self, store: CodingRunStore) -> list[str]:
        """
        After a restart: runs that were mid-flight can no longer be monitored, so they are failed with an
        explicit reason (their remote session is flagged as possibly alive); runs waiting for the user are
        re-attached, with their pre-run baseline, so the conversation can continue.
        """
        touched: list[str] = []
        for ex in store.list_runs(limit=500):
            if ex.status.value not in ACTIVE_STATUSES or ex.id in self._executions:
                continue
            provider = self._providers.get(ex.provider_id)
            if provider is None:
                continue
            if ex.status in (CodingExecutionStatus.WAITING_FOR_INTERACTION, CodingExecutionStatus.WAITING_FOR_APPROVAL):
                provider.restore_execution(ex, store.load_baseline(ex.id))
                self._executions[ex.id] = (provider, ex)
            else:
                ex.status = CodingExecutionStatus.FAILED
                ex.error = "The Aether server restarted while this run was in progress; its outcome could not be observed."
                ex.metadata["remote_session_may_continue"] = bool(ex.external_task_id)
                ex.metadata["interrupted_by_restart"] = True
                provider.restore_execution(ex, store.load_baseline(ex.id))
                provider._emit(ex, "run_interrupted_by_restart")
            touched.append(ex.id)
        return touched

    def _find(self, execution_id: str) -> tuple[BaseCodingAgentProvider, CodingTaskExecution] | None:
        """In-memory first, then the durable stores (this is what makes runs survive a restart)."""
        if execution_id in self._executions:
            return self._executions[execution_id]
        for store in get_run_registry().stores():
            ex = store.get_run(execution_id)
            if ex is None:
                continue
            provider = self._providers.get(ex.provider_id)
            if provider is None:
                return None
            provider.restore_execution(ex, store.load_baseline(ex.id))
            self._executions[ex.id] = (provider, ex)
            return provider, ex
        return None

    def get_provider(self, provider_id: str) -> BaseCodingAgentProvider | None:
        return self._providers.get(provider_id)

    def get_preferred_provider_id(self, workspace: Any = None) -> str:
        """
        Retrieves user's preferred provider ID.
        Checks workspace personal store first if available, then in-memory state.
        Defaults to 'antigravity' if available, or first registered provider.
        """
        if workspace and hasattr(workspace, "personal_store") and workspace.personal_store:
            try:
                saved = workspace.personal_store.get_setting("coding_preferred_provider")
                if saved and isinstance(saved, str) and saved in self._providers:
                    return saved
            except Exception as e:
                logger.debug("Failed reading coding_preferred_provider from personal store: %s", e)

        if self._preferred_provider_id and self._preferred_provider_id in self._providers:
            return self._preferred_provider_id

        if "antigravity" in self._providers:
            return "antigravity"
        return next(iter(self._providers.keys())) if self._providers else "antigravity"

    def set_preferred_provider_id(self, provider_id: str, workspace: Any = None) -> str:
        """
        Sets and persists user's preferred provider choice in the workspace personal store.
        """
        if provider_id not in self._providers:
            raise ValueError(f"Provider '{provider_id}' is not registered.")
        self._preferred_provider_id = provider_id
        if workspace and hasattr(workspace, "personal_store") and workspace.personal_store:
            try:
                workspace.personal_store.set_setting("coding_preferred_provider", provider_id)
            except Exception as e:
                logger.warning("Could not persist coding_preferred_provider in workspace: %s", e)
        return provider_id

    def list_providers_status(self, workspace: Any = None) -> list[CodingProviderStatus]:
        """
        Probes and returns full status for all providers distinguishing
        installed, authenticated, available, and missing prerequisites.
        """
        from aether.coding.setup import get_coding_setup_manager
        setup_mgr = get_coding_setup_manager()

        pref_id = self.get_preferred_provider_id(workspace)
        result: list[CodingProviderStatus] = []
        for pid, provider in self._providers.items():
            if hasattr(provider, "probe_status"):
                st = provider.probe_status(is_preferred=(pid == pref_id))
            else:
                ready, detail = provider.is_available()
                st = CodingProviderStatus(
                    id=pid,
                    name=provider.name,
                    description=provider.description,
                    installed=ready,
                    authenticated=ready,
                    available=ready,
                    is_preferred=(pid == pref_id),
                    diagnostic=detail,
                    missing_prerequisites=[] if ready else [detail],
                )
            active_op = setup_mgr.get_active_operation(pid)
            if active_op:
                st.active_setup_operation = active_op.to_dict()
            result.append(st)
        return result

    def start_install(self, provider_id: str, confirmed: bool = False) -> Any:
        """Starts background install operation with explicit consent gate."""
        provider = self.get_provider(provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' non registrato.")
        from aether.coding.setup import get_coding_setup_manager
        return get_coding_setup_manager().start_install(provider, confirmed=confirmed)

    def start_diagnose(self, provider_id: str) -> Any:
        """Starts asynchronous diagnostic verification for a provider."""
        provider = self.get_provider(provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' non registrato.")
        from aether.coding.setup import get_coding_setup_manager
        return get_coding_setup_manager().start_diagnose(provider)

    def start_authenticate(self, provider_id: str) -> Any:
        """Starts asynchronous authentication setup or check for a provider."""
        provider = self.get_provider(provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' non registrato.")
        from aether.coding.setup import get_coding_setup_manager
        return get_coding_setup_manager().start_authenticate(provider)

    def get_setup_operation(self, operation_id: str) -> Any:
        """Retrieves a setup operation by ID."""
        from aether.coding.setup import get_coding_setup_manager
        return get_coding_setup_manager().get_operation(operation_id)

    def cancel_setup_operation(self, operation_id: str) -> bool:
        """Cooperatively cancels an ongoing setup operation."""
        from aether.coding.setup import get_coding_setup_manager
        return get_coding_setup_manager().cancel_operation(operation_id)

    def list_providers(self, workspace: Any = None) -> list[dict[str, Any]]:
        """Lists all registered coding agent providers with current availability and diagnostics."""
        statuses = self.list_providers_status(workspace)
        return [s.to_dict() for s in statuses]

    def get_available_providers(self) -> list[BaseCodingAgentProvider]:
        """Returns all currently available coding agent providers."""
        available = []
        for provider in self._providers.values():
            ready, _ = provider.is_available()
            if ready:
                available.append(provider)
        return available

    def resolve_provider(
        self, preferred_id: str | None = None, workspace: Any = None
    ) -> tuple[BaseCodingAgentProvider, str]:
        """
        Resolves an available provider according to explicit request, persistent preference,
        or default priority order: Antigravity -> Claude Code -> Codex.
        Strict rule: Fails closed with a detailed diagnostic if requested or preferred provider
        is unauthenticated or unavailable. Never silently switches providers.
        """
        # 1. Explicit request for a specific provider
        if preferred_id:
            provider = self._providers.get(preferred_id)
            if not provider:
                raise CodingAgentUnavailableError(f"Coding agent provider '{preferred_id}' is not registered.")
            if hasattr(provider, "probe_status"):
                status = provider.probe_status()
                if not status.available:
                    prereqs = "\n".join(f"- {p}" for p in status.missing_prerequisites) if status.missing_prerequisites else ""
                    prereq_msg = f"\n\nPrerequisiti mancanti:\n{prereqs}" if prereqs else ""
                    raise CodingAgentUnavailableError(
                        f"Il coding agent richiesto '{provider.name}' ({preferred_id}) non è disponibile per l'esecuzione:\n"
                        f"{status.diagnostic}{prereq_msg}"
                    )
                return provider, status.diagnostic
            else:
                ready, detail = provider.is_available()
                if not ready:
                    raise CodingAgentUnavailableError(
                        f"Requested coding agent '{provider.name}' ({preferred_id}) is not available: {detail}"
                    )
                return provider, detail

        # 2. Check if user configured an explicit persistent preference
        configured_pref: str | None = None
        if workspace and hasattr(workspace, "personal_store") and workspace.personal_store:
            try:
                saved = workspace.personal_store.get_setting("coding_preferred_provider")
                if saved and isinstance(saved, str) and saved in self._providers:
                    configured_pref = saved
            except Exception:
                pass
        if not configured_pref and self._preferred_provider_id and self._preferred_provider_id in self._providers:
            configured_pref = self._preferred_provider_id

        if configured_pref and configured_pref in self._providers:
            provider = self._providers[configured_pref]
            if hasattr(provider, "probe_status"):
                status = provider.probe_status()
                if status.available:
                    return provider, status.diagnostic
                else:
                    # STRICT RULE: When user preference is set and unavailable, DO NOT SILENTLY SWITCH!
                    prereqs = "\n".join(f"- {p}" for p in status.missing_prerequisites) if status.missing_prerequisites else ""
                    prereq_msg = f"\n\nPrerequisiti mancanti:\n{prereqs}" if prereqs else ""
                    raise CodingAgentUnavailableError(
                        f"Il provider preferito '{provider.name}' ({configured_pref}) non è attualmente disponibile per l'esecuzione:\n"
                        f"{status.diagnostic}{prereq_msg}\n\n"
                        f"Aether non esegue un agente alternativo in silenzio. Per procedere, configura il prerequisito o seleziona esplicitamente un provider alternativo pronto."
                    )
            else:
                ready, detail = provider.is_available()
                if ready:
                    return provider, detail
                else:
                    raise CodingAgentUnavailableError(
                        f"Il provider preferito '{provider.name}' ({configured_pref}) non è disponibile: {detail}"
                    )

        # 3. Default priority order: Antigravity -> Claude Code -> Codex (when no explicit preference set)
        priority = ["antigravity", "claude_code", "codex"]
        diagnostics = []

        for pid in priority:
            provider = self._providers.get(pid)
            if provider:
                ready, detail = provider.is_available()
                if ready:
                    return provider, detail
                diagnostics.append(f"- **{provider.name}** (`{pid}`): {detail}")

        # Any other registered providers
        for pid, provider in self._providers.items():
            if pid not in priority:
                ready, detail = provider.is_available()
                if ready:
                    return provider, detail
                diagnostics.append(f"- **{provider.name}** (`{pid}`): {detail}")

        diag_report = "\n".join(diagnostics) if diagnostics else "Nessun provider registrato."
        raise CodingAgentUnavailableError(
            f"Nessun agente di coding autonomo è attualmente disponibile o autenticato:\n{diag_report}\n\n"
            f"Aether non scrive né modifica il codice direttamente con il modello interno per garantire l'integrità del codebase."
        )

    def get_latest_execution(self) -> CodingTaskExecution | None:
        """Returns the most recent coding task execution, if any."""
        if not self._executions:
            return None
        return list(self._executions.values())[-1][1]

    def register_execution(self, execution: CodingTaskExecution) -> None:
        """Registers or restores an execution session in the orchestrator and its provider."""
        provider = self.get_provider(execution.provider_id)
        if not provider:
            from aether.coding.providers.antigravity import AntigravityCodingProvider
            provider = AntigravityCodingProvider()
            self.register_provider(provider)
        if hasattr(provider, "_executions"):
            provider._executions[execution.id] = execution
        self._executions[execution.id] = (provider, execution)

    def delegate_task(
        self,
        task: CodingTask,
        preferred_provider_id: str | None = None,
        workspace: Any = None,
    ) -> CodingTaskExecution:
        """
        Delegates a development or coding task to an autonomous external coding agent.
        Enforces that Aether's internal model does not write code directly.
        """
        # Validate workspace directory safety
        if not task.project_path:
            raise ValueError("project_path must be provided for coding delegation.")

        p_dir = Path(task.project_path).resolve()
        if not p_dir.exists() or not p_dir.is_dir():
            raise ValueError(f"Project directory does not exist or is not a directory: {task.project_path}")

        forbidden_roots = {"/", "/System", "/usr", "/bin", "/sbin", "/etc", "/var", "/Library", "/private", "/private/var", "/tmp", "/private/tmp"}
        if str(p_dir) in forbidden_roots:
            raise ValueError(f"Cannot delegate coding task to protected system directory: {p_dir}")

        provider, _ = self.resolve_provider(preferred_provider_id or task.provider_id, workspace=workspace)
        task.provider_id = provider.id

        # One writer per project: refuse while a previous run may still be modifying it.
        key = str(p_dir)
        with self._project_guard:
            if key in self._reserved_projects:
                from aether.coding.runs import ProjectBusyError
                raise ProjectBusyError(key, "in-flight", "is being started by another request")
            get_run_registry().assert_project_free(key, self._providers)
            self._reserved_projects.add(key)
        try:
            logger.info("Delegating coding task '%s' to provider '%s'...", task.id, provider.name)
            execution = provider.start_task(task)
        finally:
            with self._project_guard:
                self._reserved_projects.discard(key)
        self._executions[execution.id] = (provider, execution)
        return execution

    def get_status(self, execution_id: str | None = None) -> CodingTaskExecution:
        """Queries status of an execution session."""
        target_id = execution_id
        if not target_id:
            latest = self.get_latest_execution()
            if latest:
                target_id = latest.id
            else:
                raise KeyError("No coding task executions found.")

        found = self._find(target_id)
        if found:
            provider, _ = found
            execution = provider.get_status(target_id)
            self._executions[target_id] = (provider, execution)
            return execution
        raise KeyError(f"Execution '{target_id}' not found.")

    def cancel_task(self, execution_id: str) -> bool:
        """Cancels an ongoing coding task."""
        found = self._find(execution_id)
        if found:
            return found[0].cancel_task(execution_id)
        return False

    def send_message(self, execution_id: str, message: str) -> CodingTaskExecution:
        """Routes a user decision, answer, or follow-up instruction to a coding task execution."""
        found = self._find(execution_id)
        if found:
            provider, _ = found
            if hasattr(provider, "send_message"):
                execution = provider.send_message(execution_id, message)
                self._executions[execution_id] = (provider, execution)
                return execution
            raise NotImplementedError(f"Provider '{provider.name}' does not support sending messages.")
        raise KeyError(f"Execution '{execution_id}' not found.")

    def collect_results(self, execution_id: str | None = None) -> CodingResult:
        """Collects verifiable git diff, modified files, and summary evidence."""
        target_id = execution_id
        if not target_id:
            latest = self.get_latest_execution()
            if latest:
                target_id = latest.id
            else:
                raise KeyError("No coding task executions found.")

        found = self._find(target_id)
        if found:
            return found[0].collect_results(target_id)
        raise KeyError(f"Execution '{target_id}' not found.")


# Global singleton instance for runtime and actions
_global_orchestrator: CodingAgentOrchestrator | None = None


def get_coding_orchestrator() -> CodingAgentOrchestrator:
    """Returns or creates the global CodingAgentOrchestrator singleton."""
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = CodingAgentOrchestrator()
    return _global_orchestrator
