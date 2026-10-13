"""
Observable Lifecycle Setup Manager for External Coding Agents.
Manages asynchronous installation, authentication, diagnostics, and recovery operations.
Enforces explicit user consent before system modifications, prerequisite verification,
sanitized streaming logs, and post-installation validation.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import threading
from typing import Any, Callable
import uuid

from aether.coding.base import BaseCodingAgentProvider
from aether.coding.environment import sanitize_log
from aether.coding.models import (
    CodingProviderStatus,
    InstallationState,
    OperationalState,
    SetupOperation,
    SetupOperationStatus,
    SetupOperationType,
)

logger = logging.getLogger(__name__)


class CodingSetupManager:
    """Coordinates lifecycle setup operations for external coding agents."""

    def __init__(self, max_workers: int = 4) -> None:
        self._operations: dict[str, SetupOperation] = {}
        self._cancel_flags: dict[str, threading.Event] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="coding-setup")
        self._lock = threading.Lock()

    def get_operation(self, operation_id: str) -> SetupOperation | None:
        """Retrieves setup operation by ID."""
        with self._lock:
            return self._operations.get(operation_id)

    def list_operations(self, provider_id: str | None = None) -> list[SetupOperation]:
        """Lists operations optionally filtered by provider."""
        with self._lock:
            ops = list(self._operations.values())
        if provider_id:
            ops = [o for o in ops if o.provider_id == provider_id]
        return sorted(ops, key=lambda o: o.started_at, reverse=True)

    def cancel_operation(self, operation_id: str) -> bool:
        """Requests cooperative cancellation of a running operation."""
        with self._lock:
            op = self._operations.get(operation_id)
            flag = self._cancel_flags.get(operation_id)
            if not op or not flag or op.status != SetupOperationStatus.RUNNING:
                return False
            flag.set()
            op.status = SetupOperationStatus.CANCELLED
            op.message = "Operazione annullata dall'utente."
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.logs.append("[SETUP] Annullamento richiesto dall'utente.")
            return True

    def get_active_operation(self, provider_id: str) -> SetupOperation | None:
        """Returns the currently active (running or pending) operation for a provider, if any."""
        with self._lock:
            for op in reversed(list(self._operations.values())):
                if op.provider_id == provider_id and op.status in (SetupOperationStatus.PENDING, SetupOperationStatus.RUNNING):
                    return op
        return None

    def start_install(
        self,
        provider: BaseCodingAgentProvider,
        confirmed: bool = False,
    ) -> SetupOperation:
        """
        Initiates an installation operation with explicit confirmation requirement.
        Enforces non-blocking execution and post-install verification.
        """
        if not confirmed:
            raise ValueError(
                f"L'installazione del provider '{provider.name}' richiede una conferma esplicita dell'utente prima di apportare modifiche al sistema."
            )

        active = self.get_active_operation(provider.id)
        if active:
            raise RuntimeError(
                f"Un'operazione ({active.operation_type}) è già in corso per {provider.name} (id: {active.id})."
            )

        op_id = f"op-inst-{uuid.uuid4().hex[:8]}"
        op = SetupOperation(
            id=op_id,
            provider_id=provider.id,
            operation_type=SetupOperationType.INSTALL,
            status=SetupOperationStatus.RUNNING,
            progress=5.0,
            message=f"Avvio installazione di {provider.name}...",
            logs=[f"[SETUP] Avvio installazione per {provider.name} ({provider.id})"],
        )

        cancel_event = threading.Event()
        with self._lock:
            self._operations[op_id] = op
            self._cancel_flags[op_id] = cancel_event

        self._executor.submit(self._run_install_task, op_id, provider, cancel_event)
        return op

    def _run_install_task(
        self,
        operation_id: str,
        provider: BaseCodingAgentProvider,
        cancel_event: threading.Event,
    ) -> None:
        """Background worker thread for executing installation."""
        op = self._operations[operation_id]

        def on_progress(pct: float, msg: str) -> None:
            if cancel_event.is_set():
                return
            with self._lock:
                op.progress = min(95.0, max(5.0, pct))
                op.message = msg
                op.logs.append(sanitize_log(f"[{pct:.0f}%] {msg}"))

        try:
            if cancel_event.is_set():
                return

            on_progress(10.0, f"Controllo prerequisiti per {provider.name}...")

            # Run provider install logic
            success, message = provider.install(on_progress=on_progress, cancel_event=cancel_event)

            if cancel_event.is_set():
                return

            if not success:
                with self._lock:
                    op.status = SetupOperationStatus.FAILED
                    op.progress = 100.0
                    op.error = message
                    op.message = f"Installazione fallita: {message}"
                    op.completed_at = datetime.now(timezone.utc).isoformat()
                    op.logs.append(f"[ERRORE] {message}")
                return

            # Post-installation verification probe (Principle: Never declare Installed until post-check confirms)
            on_progress(90.0, "Verifica post-installazione dell'eseguibile e delle capacità...")
            post_status = provider.probe_status()

            if post_status.installation_state != InstallationState.INSTALLED:
                with self._lock:
                    op.status = SetupOperationStatus.FAILED
                    op.progress = 100.0
                    op.error = f"Verifica post-installazione non riuscita: {post_status.diagnostic}"
                    op.message = "Installazione completata ma il binario non risulta funzionante o verificato."
                    op.completed_at = datetime.now(timezone.utc).isoformat()
                    op.logs.append(f"[ERRORE] {op.error}")
                return

            with self._lock:
                op.status = SetupOperationStatus.SUCCEEDED
                op.progress = 100.0
                op.message = f"Installazione di {provider.name} completata e verificata con successo."
                op.completed_at = datetime.now(timezone.utc).isoformat()
                op.logs.append("[SUCCESSO] Provider installato e verificato nel sistema.")

        except Exception as exc:
            logger.exception("Unexpected error during installation of %s", provider.id)
            with self._lock:
                op.status = SetupOperationStatus.FAILED
                op.progress = 100.0
                op.error = str(exc)
                op.message = f"Errore imprevisto durante l'installazione: {exc}"
                op.completed_at = datetime.now(timezone.utc).isoformat()
                op.logs.append(f"[ECCEZIONE] {exc}")

    def start_diagnose(self, provider: BaseCodingAgentProvider) -> SetupOperation:
        """Runs a live diagnostic probe for a provider asynchronously."""
        op_id = f"op-diag-{uuid.uuid4().hex[:8]}"
        op = SetupOperation(
            id=op_id,
            provider_id=provider.id,
            operation_type=SetupOperationType.DIAGNOSE,
            status=SetupOperationStatus.RUNNING,
            progress=20.0,
            message=f"Verifica diagnostica in corso per {provider.name}...",
            logs=[f"[DIAGNOSTICA] Controllo eseguibile, permessi e autenticazione per {provider.name}"],
        )

        with self._lock:
            self._operations[op_id] = op

        def _worker():
            try:
                st = provider.probe_status()
                with self._lock:
                    op.status = SetupOperationStatus.SUCCEEDED
                    op.progress = 100.0
                    op.message = st.diagnostic
                    op.completed_at = datetime.now(timezone.utc).isoformat()
                    op.logs.append(f"[RISULTATO] Stato: {st.operational_state.upper()} ({st.diagnostic})")
            except Exception as e:
                with self._lock:
                    op.status = SetupOperationStatus.FAILED
                    op.progress = 100.0
                    op.error = str(e)
                    op.message = f"Diagnostica fallita: {e}"
                    op.completed_at = datetime.now(timezone.utc).isoformat()

        self._executor.submit(_worker)
        return op

    def start_authenticate(
        self,
        provider: BaseCodingAgentProvider,
    ) -> SetupOperation:
        """Initiates an authentication check or setup operation asynchronously."""
        active = self.get_active_operation(provider.id)
        if active:
            raise RuntimeError(
                f"Un'operazione ({active.operation_type}) è già in corso per {provider.name} (id: {active.id})."
            )

        op_id = f"op-auth-{uuid.uuid4().hex[:8]}"
        op = SetupOperation(
            id=op_id,
            provider_id=provider.id,
            operation_type=SetupOperationType.AUTHENTICATE,
            status=SetupOperationStatus.RUNNING,
            progress=15.0,
            message=f"Avvio autenticazione per {provider.name}...",
            logs=[f"[AUTH] Inizio procedura autenticazione per {provider.name}"],
        )

        cancel_event = threading.Event()
        with self._lock:
            self._operations[op_id] = op
            self._cancel_flags[op_id] = cancel_event

        def _worker():
            def on_progress(pct: float, msg: str) -> None:
                if cancel_event.is_set():
                    return
                with self._lock:
                    op.progress = min(90.0, max(10.0, pct))
                    op.message = msg
                    op.logs.append(sanitize_log(f"[{pct:.0f}%] {msg}"))

            try:
                success, msg = provider.authenticate(on_progress=on_progress, cancel_event=cancel_event)
                if cancel_event.is_set():
                    return

                # Probe status post-auth
                st = provider.probe_status()
                with self._lock:
                    if success or st.authenticated:
                        op.status = SetupOperationStatus.SUCCEEDED
                        op.progress = 100.0
                        op.message = msg or st.diagnostic
                        op.completed_at = datetime.now(timezone.utc).isoformat()
                        op.logs.append(f"[AUTH SUCCESSO] {op.message}")
                    else:
                        op.status = SetupOperationStatus.FAILED
                        op.progress = 100.0
                        op.error = msg
                        op.message = f"Autenticazione non riuscita o richiede passaggi manuali: {msg}"
                        op.completed_at = datetime.now(timezone.utc).isoformat()
                        op.logs.append(f"[AUTH INCOMPLETA] {msg}")
            except Exception as e:
                with self._lock:
                    op.status = SetupOperationStatus.FAILED
                    op.progress = 100.0
                    op.error = str(e)
                    op.message = f"Errore durante l'autenticazione: {e}"
                    op.completed_at = datetime.now(timezone.utc).isoformat()
                    op.logs.append(f"[ERRORE] {e}")

        self._executor.submit(_worker)
        return op

    def start_update(
        self,
        provider: BaseCodingAgentProvider,
        confirmed: bool = False,
    ) -> SetupOperation:
        """Initiates an update operation with explicit confirmation requirement."""
        if not confirmed:
            raise ValueError(
                f"L'aggiornamento del provider '{provider.name}' richiede una conferma esplicita dell'utente."
            )

        active = self.get_active_operation(provider.id)
        if active:
            raise RuntimeError(
                f"Un'operazione ({active.operation_type}) è già in corso per {provider.name} (id: {active.id})."
            )

        op_id = f"op-upd-{uuid.uuid4().hex[:8]}"
        op = SetupOperation(
            id=op_id,
            provider_id=provider.id,
            operation_type=SetupOperationType.UPDATE,
            status=SetupOperationStatus.RUNNING,
            progress=10.0,
            message=f"Avvio aggiornamento di {provider.name}...",
            logs=[f"[UPDATE] Inizio aggiornamento per {provider.name}"],
        )

        cancel_event = threading.Event()
        with self._lock:
            self._operations[op_id] = op
            self._cancel_flags[op_id] = cancel_event

        def _worker():
            def on_progress(pct: float, msg: str) -> None:
                if cancel_event.is_set():
                    return
                with self._lock:
                    op.progress = min(90.0, max(10.0, pct))
                    op.message = msg
                    op.logs.append(sanitize_log(f"[{pct:.0f}%] {msg}"))

            try:
                success, msg = provider.update(on_progress=on_progress, cancel_event=cancel_event)
                if cancel_event.is_set():
                    return

                st = provider.probe_status()
                with self._lock:
                    if success:
                        op.status = SetupOperationStatus.SUCCEEDED
                        op.progress = 100.0
                        op.message = msg or f"Aggiornamento completato ({st.version or 'ok'})."
                        op.completed_at = datetime.now(timezone.utc).isoformat()
                        op.logs.append(f"[UPDATE SUCCESSO] {op.message}")
                    else:
                        op.status = SetupOperationStatus.FAILED
                        op.progress = 100.0
                        op.error = msg
                        op.message = f"Aggiornamento fallito: {msg}"
                        op.completed_at = datetime.now(timezone.utc).isoformat()
                        op.logs.append(f"[UPDATE FALLITO] {msg}")
            except Exception as e:
                with self._lock:
                    op.status = SetupOperationStatus.FAILED
                    op.progress = 100.0
                    op.error = str(e)
                    op.message = f"Errore durante l'aggiornamento: {e}"
                    op.completed_at = datetime.now(timezone.utc).isoformat()
                    op.logs.append(f"[ERRORE] {e}")

        self._executor.submit(_worker)
        return op


# Global singleton
_GLOBAL_SETUP_MANAGER: CodingSetupManager | None = None


def get_coding_setup_manager() -> CodingSetupManager:
    """Returns the singleton CodingSetupManager instance."""
    global _GLOBAL_SETUP_MANAGER
    if _GLOBAL_SETUP_MANAGER is None:
        _GLOBAL_SETUP_MANAGER = CodingSetupManager()
    return _GLOBAL_SETUP_MANAGER
