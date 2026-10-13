"""
Google Antigravity Coding Agent Provider.
Dispatches coding tasks to Google Antigravity via the local `agentapi` CLI,
monitors conversation metadata and transcripts, and collects verifiable git evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from typing import Any
import uuid

from aether.coding.base import BaseCodingAgentProvider
from aether.coding.environment import find_executable, get_augmented_env
from aether.coding.models import (
    AuthenticationState,
    CodingExecutionStatus,
    CodingProviderStatus,
    CodingResult,
    CodingTask,
    CodingTaskExecution,
    InstallationState,
    NextAction,
    OperationalState,
)

logger = logging.getLogger(__name__)


class AntigravityCodingProvider(BaseCodingAgentProvider):
    """
    Provider orchestrating Google Antigravity as an autonomous coding agent.
    Interfaces directly with the official local agentapi CLI.
    """

    ID = "antigravity"
    NAME = "Google Antigravity"
    DESCRIPTION = "Autonomous Google Antigravity coding agent via local agentapi CLI"

    def __init__(self, binary_path: str | None = None) -> None:
        self._binary_path = binary_path
        self._executions: dict[str, CodingTaskExecution] = {}
        self._finalization_prompted: set[str] = set()

    @property
    def id(self) -> str:
        return self.ID

    @property
    def name(self) -> str:
        return self.NAME

    @property
    def description(self) -> str:
        return self.DESCRIPTION

    def resolve_binary(self) -> str | None:
        """Finds executable agentapi binary on the local system."""
        cand, status = find_executable(
            ["agentapi", "agy", "language_server"],
            custom_path=self._binary_path,
            env_var="AETHER_ANTIGRAVITY_BIN",
        )
        if cand and status == "ok":
            return str(cand)
        return None

    @classmethod
    def declared_capabilities(cls) -> dict[str, Any]:
        """Truthful capabilities supported by the Antigravity agentapi runtime."""
        return {
            "autonomous_editing": True,
            "automated_testing": True,
            "git_diff_evidence": True,
            "transcripts": True,
            "live_status_polling": True,
            "cancellation": True,
            "multi_file": True,
            "interaction_routing": True,
            "session_resumption": True,
        }

    def probe_status(self, is_preferred: bool = False) -> CodingProviderStatus:
        """
        Probes local host for Google Antigravity binary, session, and execution readiness.
        Distinguishes installation, authentication, availability, and missing prerequisites.
        """
        cand, status = find_executable(
            ["agentapi", "agy", "language_server"],
            custom_path=self._binary_path,
            env_var="AETHER_ANTIGRAVITY_BIN",
        )
        if not cand:
            return CodingProviderStatus(
                id=self.id,
                name=self.name,
                description=self.description,
                installation_state=InstallationState.NOT_INSTALLED,
                authentication_state=AuthenticationState.UNKNOWN,
                operational_state=OperationalState.BLOCKED_MISSING_INSTALLATION,
                next_action=NextAction.INSTALL,
                auth_method="antigravity_session",
                is_preferred=is_preferred,
                diagnostic="Google Antigravity non trovato. Verificati i percorsi standard (~/.gemini/antigravity/bin/agentapi, PATH, /Applications/Antigravity.app).",
                missing_prerequisites=[
                    "Installa Google Antigravity o imposta la variabile AETHER_ANTIGRAVITY_BIN verso il binario agentapi o agy."
                ],
                capabilities=self.declared_capabilities(),
                error_code="not_found",
            )

        if status == "permission_denied":
            return CodingProviderStatus(
                id=self.id,
                name=self.name,
                description=self.description,
                installation_state=InstallationState.INVALID_PATH,
                authentication_state=AuthenticationState.UNKNOWN,
                operational_state=OperationalState.BLOCKED_PERMISSIONS,
                next_action=NextAction.RECOVER,
                auth_method="antigravity_session",
                binary_path=str(cand),
                is_preferred=is_preferred,
                diagnostic=f"Google Antigravity trovato a {cand} ma i permessi di esecuzione non sono concessi.",
                missing_prerequisites=[f"Assegna permessi di esecuzione: chmod +x {cand}"],
                capabilities=self.declared_capabilities(),
                error_code="permission_denied",
            )

        bin_path = str(cand)
        try:
            cmd = [bin_path, "--help"]
            if "language_server" in bin_path and not bin_path.endswith("agentapi"):
                cmd = [bin_path, "agentapi", "--help"]

            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
                env=get_augmented_env(),
            )
            is_responsive = (res.returncode == 0) or ("agentapi" in (res.stdout + res.stderr)) or ("agy" in (res.stdout + res.stderr))
            if not is_responsive:
                return CodingProviderStatus(
                    id=self.id,
                    name=self.name,
                    description=self.description,
                    installation_state=InstallationState.BROKEN_INSTALLATION,
                    authentication_state=AuthenticationState.UNKNOWN,
                    operational_state=OperationalState.BLOCKED_PROVIDER_ERROR,
                    next_action=NextAction.RECOVER,
                    auth_method="antigravity_session",
                    is_preferred=is_preferred,
                    binary_path=bin_path,
                    diagnostic=f"Google Antigravity presente a {bin_path} ma non responsivo (codice {res.returncode}): {res.stderr.strip()}",
                    missing_prerequisites=["Verifica che Antigravity sia in esecuzione o riavvia l'applicazione."],
                    capabilities=self.declared_capabilities(),
                    error_code="binary_unresponsive",
                )

            mode_desc = "agy CLI" if bin_path.endswith("agy") else "agentapi daemon"
            return CodingProviderStatus(
                id=self.id,
                name=self.name,
                description=self.description,
                installation_state=InstallationState.INSTALLED,
                authentication_state=AuthenticationState.AUTHENTICATED,
                operational_state=OperationalState.READY,
                next_action=NextAction.NONE,
                auth_method="antigravity_session",
                is_preferred=is_preferred,
                binary_path=bin_path,
                version=mode_desc,
                diagnostic=f"Google Antigravity pronto e autenticato via {mode_desc} ({bin_path}).",
                missing_prerequisites=[],
                capabilities=self.declared_capabilities(),
            )
        except Exception as exc:
            return CodingProviderStatus(
                id=self.id,
                name=self.name,
                description=self.description,
                installation_state=InstallationState.BROKEN_INSTALLATION,
                authentication_state=AuthenticationState.UNKNOWN,
                operational_state=OperationalState.BLOCKED_PROVIDER_ERROR,
                next_action=NextAction.RECOVER,
                auth_method="antigravity_session",
                is_preferred=is_preferred,
                binary_path=bin_path,
                diagnostic=f"Errore durante l'esecuzione del binario Google Antigravity: {exc}",
                missing_prerequisites=["Controlla i permessi di esecuzione e lo stato dell'applicazione Antigravity."],
                capabilities=self.declared_capabilities(),
                error_code="execution_failed",
            )

    def is_available(self) -> tuple[bool, str]:
        """Probes whether Google Antigravity agentapi is installed and responsive."""
        st = self.probe_status()
        return st.available, st.diagnostic

    def get_installation_instructions(self) -> list[str]:
        return [
            "Google Antigravity è parte dell'ambiente ufficiale di sviluppo Antigravity.",
            "Verifica che l'applicazione sia installata in /Applications/Antigravity.app.",
            "Assicurati che il binario 'agentapi' sia accessibile in ~/.gemini/antigravity/bin/agentapi.",
            "In alternativa, definisci la variabile d'ambiente AETHER_ANTIGRAVITY_BIN verso l'eseguibile.",
        ]

    def get_authentication_instructions(self) -> list[str]:
        return [
            "Apri l'applicazione Google Antigravity sul tuo computer.",
            "Verifica che la sessione sia attiva e collegata al tuo account autorizzato.",
            "Il demone locale agentapi si collegherà automaticamente alla sessione attiva.",
        ]

    def install(self, on_progress: Any = None, cancel_event: Any = None) -> tuple[bool, str]:
        if cancel_event and cancel_event.is_set():
            return False, "Operazione annullata dall'utente."
        if on_progress:
            on_progress(20.0, "Ricerca installazione Google Antigravity esistente...")
        bin_path = self.resolve_binary()
        if bin_path:
            if on_progress:
                on_progress(100.0, f"Google Antigravity trovato ed eseguibile a {bin_path}.")
            return True, f"Google Antigravity già presente a {bin_path}."

        if cancel_event and cancel_event.is_set():
            return False, "Operazione annullata dall'utente."

        if on_progress:
            on_progress(50.0, "Verifica presenza applicazione /Applications/Antigravity.app...")
        app_path = Path("/Applications/Antigravity.app")
        if app_path.exists():
            bin_cand = app_path / "Contents" / "Resources" / "bin" / "language_server"
            if bin_cand.exists() and os.access(bin_cand, os.X_OK):
                if on_progress:
                    on_progress(100.0, f"Individuato binario in {bin_cand}.")
                return True, f"Trovato binario Antigravity in {bin_cand}."

        return False, (
            "Google Antigravity richiede l'installazione dell'applicazione ufficiale desktop. "
            "Scarica Antigravity e assicurati che sia posizionato in /Applications/Antigravity.app o che agentapi sia in ~/.gemini/antigravity/bin."
        )

    def authenticate(self, on_progress: Any = None, cancel_event: Any = None) -> tuple[bool, str]:
        if cancel_event and cancel_event.is_set():
            return False, "Operazione annullata dall'utente."
        if on_progress:
            on_progress(30.0, "Controllo sessione locale Antigravity agentapi...")
        st = self.probe_status()
        if st.available:
            if on_progress:
                on_progress(100.0, "Sessione Google Antigravity verificata con successo.")
            return True, "Sessione Google Antigravity verificata e pronta."
        return False, "Google Antigravity non è attualmente attivo. Avvia l'applicazione Antigravity per abilitare la sessione."

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    POLL_INTERVAL = 1.5
    _DONE_STATES = frozenset({"", "DONE", "COMPLETED", "COMPLETE", "SUCCESS", "SUCCEEDED", "FINISHED", "IDLE"})
    _ERROR_STATES = frozenset({"ERROR", "FAILED", "FAILURE"})
    _INTERACTION_TOOLS = frozenset({"ask_question", "request_permission", "ask_user", "confirm_action"})
    _INTERACTION_ENTRY_TYPES = frozenset({"ASK_QUESTION"})
    # Seconds a trailing ERROR_MESSAGE must stay the last entry before it is treated as the end of the turn
    # (the agent may retry after a transient error).
    ERROR_SETTLE_SECONDS = 10.0
    _CONV_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{3,127}$")
    _UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
    _MANDATE_RE = re.compile(r"^MANDATO ESECUTIVO AUTORIZZATO DALL'OPERATORE:[^\n]*\n[^\n]*\n\n")
    _MESSAGEABLE_STATUSES = (
        CodingExecutionStatus.WAITING_FOR_INTERACTION,
        CodingExecutionStatus.WAITING_FOR_APPROVAL,
        CodingExecutionStatus.COMPLETED,
        CodingExecutionStatus.REQUIRES_REWORK,
    )

    @classmethod
    def _is_valid_conversation_id(cls, conv_id: str | None) -> bool:
        return bool(conv_id) and bool(cls._CONV_ID_RE.match(conv_id)) and ".." not in conv_id

    @staticmethod
    def _transcript_path(conv_id: str) -> Path:
        return Path.home() / ".gemini" / "antigravity" / "brain" / conv_id / ".system_generated" / "logs" / "transcript.jsonl"

    def start_task(self, task: CodingTask) -> CodingTaskExecution:
        """Dispatches a coding task to Google Antigravity and waits for the first turn to settle."""
        exec_id = f"exec-{uuid.uuid4().hex[:10]}"

        is_ready, reason = self.is_available()
        if not is_ready:
            return self._fail_early(task, exec_id, f"Google Antigravity unavailable: {reason}")
        if not task.project_path:
            return self._fail_early(task, exec_id, "Project path is required for coding delegation.")
        cwd_path = Path(task.project_path).resolve()
        if not cwd_path.exists() or not cwd_path.is_dir():
            return self._fail_early(
                task, exec_id, f"Target workspace directory does not exist or is not a directory: {task.project_path}"
            )
        bin_path = self.resolve_binary()
        if not bin_path:
            return self._fail_early(task, exec_id, "Google Antigravity binary could not be resolved.")

        prompt_text = self._build_agent_prompt(task)
        title = f"Aether: {task.instruction[:40]}"
        cmd = [bin_path]
        if "language_server" in bin_path and not bin_path.endswith("agentapi"):
            cmd.append("agentapi")
        cmd.extend(["new-conversation", f"--title={title}"])
        if task.model and task.model in ("flash_lite", "flash", "pro"):
            cmd.append(f"--model={task.model}")
        cmd.append(prompt_text)

        execution = CodingTaskExecution(
            id=exec_id,
            task=task,
            provider_id=self.id,
            status=CodingExecutionStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        execution.metadata = {
            "project_path": str(cwd_path),
            "active_seconds": 0.0,
            "remote_cancelled": False,
        }
        # Register BEFORE any dispatch/polling so status, messages, cancellation and
        # result collection can always find this run.
        self._register(execution)
        self._begin_run_evidence(execution, cwd_path)
        execution.metadata.update({"active_seconds": 0.0, "remote_cancelled": False})
        self._emit(execution, "run_started")

        task_timeout = float(task.timeout_seconds)
        t_start = time.time()
        stdout = ""
        try:
            logger.info("Executing Antigravity new-conversation for task %s...", task.id)
            res = subprocess.run(cmd, cwd=str(cwd_path), capture_output=True, text=True, timeout=task_timeout)
            stdout = (res.stdout or "").strip()
            stderr = (res.stderr or "").strip()

            if res.returncode != 0:
                self._set_terminal(
                    execution, CodingExecutionStatus.FAILED,
                    stderr or stdout or f"agentapi exited with status {res.returncode}", raw_output=stdout,
                )
                return execution

            conv_id = None
            try:
                out_json = json.loads(stdout)
                resp = out_json.get("response", {}) if isinstance(out_json, dict) else {}
                conv_id = (resp.get("newConversation") or {}).get("conversationId") or resp.get("conversationId")
            except Exception:
                pass
            if not conv_id:
                uuid_match = self._UUID_RE.search(stdout + " " + stderr)
                conv_id = uuid_match.group(0) if uuid_match else None

            if not self._is_valid_conversation_id(conv_id):
                execution.metadata["remote_status"] = "unknown_session_possibly_started"
                self._set_terminal(
                    execution, CodingExecutionStatus.FAILED,
                    "Antigravity did not return a valid conversation identifier: the run cannot be monitored or verified.",
                    raw_output=stdout,
                )
                return execution
            execution.external_task_id = conv_id
            self._emit(execution, "conversation_attached", conversation_id=conv_id)

            remaining = max(1.0, task_timeout - (time.time() - t_start))
            outcome = self._wait_for_conversation_completion(
                conv_id, cwd_path, timeout=remaining, baseline_line_count=0,
                cancel_event=self._cancel_events.get(exec_id), execution_id=exec_id,
            )
            self._apply_turn_outcome(execution, conv_id, outcome, stdout, time.time() - t_start)

        except subprocess.TimeoutExpired:
            self._add_active_time(execution, time.time() - t_start)
            self._set_terminal(
                execution, CodingExecutionStatus.TIMED_OUT,
                f"Antigravity execution timed out after {task.timeout_seconds}s", raw_output=stdout,
            )
        except Exception as exc:
            self._set_terminal(
                execution, CodingExecutionStatus.FAILED, f"Failed to execute Antigravity agentapi: {exc}", raw_output=stdout,
            )
        return execution

    def _apply_turn_outcome(
        self,
        execution: CodingTaskExecution,
        conv_id: str,
        outcome: tuple[bool, str, str, bool],
        raw_output: str,
        elapsed: float,
    ) -> None:
        """Translates a finished wait into exactly one distinguishable execution state."""
        turn_done, content, status, is_waiting = outcome
        self._add_active_time(execution, elapsed)
        timeout = execution.task.timeout_seconds

        if status == "CANCELLED" or execution.status == CodingExecutionStatus.CANCELLED:
            return  # cancel_task already recorded the terminal state and its honest remote status
        if is_waiting:
            execution.status = CodingExecutionStatus.WAITING_FOR_INTERACTION
            execution.interaction_prompt = content
            execution.interaction_options = ["Approva ed esegui modifiche", "Rifiuta ed annulla"]
            execution.error = None
            execution.result = CodingResult(
                success=False,
                status=CodingExecutionStatus.WAITING_FOR_INTERACTION,
                provider_id=self.id,
                external_task_id=conv_id,
                summary=content,
                raw_output=raw_output,
                metadata={
                    "project_path": execution.metadata.get("project_path"),
                    "execution_id": execution.id,
                    "interaction_reason": "waiting_for_approval",
                },
            )
            self._emit(execution, "interaction_requested", prompt=content)
        elif status == "TIMEOUT":
            self._set_terminal(
                execution, CodingExecutionStatus.TIMED_OUT,
                f"Antigravity conversation {conv_id} timed out after {timeout}s", raw_output=raw_output,
            )
        elif status == "ERROR":
            self._set_terminal(
                execution, CodingExecutionStatus.FAILED,
                content or f"Antigravity conversation {conv_id} failed with status ERROR.", raw_output=raw_output,
            )
        elif turn_done and status == "DONE":
            execution.status = CodingExecutionStatus.COMPLETED
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            execution.error = None
            execution.interaction_prompt = None
            execution.result = self.collect_results(execution.id, raw_output=raw_output)
            self._emit(execution, "run_completed", success=execution.result.success)
        else:
            self._set_terminal(
                execution, CodingExecutionStatus.FAILED,
                f"Antigravity conversation {conv_id} ended in an undetermined state ({status or 'unknown'}).",
                raw_output=raw_output,
            )

    @classmethod
    def _check_if_waiting_for_interaction(cls, content: str, last_entry: dict[str, Any]) -> tuple[bool, str]:
        """
        Detects whether the agent turn has paused to request explicit user approval or an answer.
        Structured tool calls are authoritative; the textual heuristics are deliberately narrow and
        are vetoed by completion markers so a finished summary is not mistaken for a pending request.
        """
        if last_entry.get("type") in cls._INTERACTION_ENTRY_TYPES and str(last_entry.get("status", "")).upper() in ("", "DONE", "RUNNING"):
            return True, "Agent asked a question and is waiting for the answer."
        for tc in last_entry.get("tool_calls", []) or []:
            name = tc.get("name") or (tc.get("function") or {}).get("name") or ""
            if name in cls._INTERACTION_TOOLS:
                return True, f"Agent requested interaction via {name}"

        c_lower = (content or "").lower().strip()
        if not c_lower:
            return False, ""

        waiting_phrases = [
            "in attesa della tua esplicita approvazione", "in attesa della tua approvazione",
            "in attesa di approvazione", "in attesa della tua conferma", "in attesa di conferma",
            "in attesa del tuo via libera", "in attesa della tua autorizzazione",
            "waiting for your approval", "waiting for explicit approval",
            "awaiting your approval", "awaiting explicit approval", "awaiting approval",
        ]
        if any(p in c_lower for p in waiting_phrases):
            return True, "Agent formulated proposal and is waiting for explicit user approval."

        completion_markers = (
            "completato", "concluso", "ho applicato", "ho implementato", "modifiche applicate",
            "test passano", "tutti i test", "completed", "implemented", "done.", "tests pass",
        )
        plan_phrases = ("proposta di esecuzione", "piano di esecuzione")
        decision_words = ("conferma", "approvazione", "approvi", "approve", "confirm")
        if (
            any(p in c_lower for p in plan_phrases)
            and any(w in c_lower for w in decision_words)
            and not any(m in c_lower for m in completion_markers)
        ):
            return True, "Agent formulated an execution plan and is waiting for explicit user approval."

        if c_lower.endswith("?") and any(
            w in c_lower[-150:] for w in ["vuoi procedere", "confermi", "approvi", "do you want to proceed", "should i proceed", "shall i proceed"]
        ):
            return True, "Agent is asking for user decision before proceeding."

        return False, ""

    def _wait_for_conversation_completion(
        self,
        conv_id: str,
        p_dir: Path,
        timeout: float = 120.0,
        poll_interval: float | None = None,
        baseline_line_count: int = 0,
        cancel_event: threading.Event | None = None,
        execution_id: str | None = None,
    ) -> tuple[bool, str, str, bool]:
        """
        Polls the conversation transcript until the current turn settles.

        Only entries after ``baseline_line_count`` belong to this turn, and only once a USER_INPUT entry opened it.
        A turn is complete only when its
        last entry is a model PLANNER_RESPONSE with no tool calls and a terminal-success status; entries
        reporting an in-progress status keep the wait open.
        Returns (turn_completed, last_content, status, waiting_for_interaction) where status is one of
        DONE, ERROR, TIMEOUT, CANCELLED.
        """
        poll_interval = self.POLL_INTERVAL if poll_interval is None else poll_interval
        start_time = time.time()
        transcript_file = self._transcript_path(conv_id)
        logger.info("Waiting for Antigravity conversation %s completion (baseline_lines=%d)...", conv_id, baseline_line_count)

        file_appeared = False
        last_change_time = time.time()
        last_lines_count = baseline_line_count

        while (time.time() - start_time) < timeout:
            if cancel_event is not None and cancel_event.is_set():
                return False, "", "CANCELLED", False

            if transcript_file.exists():
                file_appeared = True
                try:
                    with open(transcript_file, "r", encoding="utf-8") as f:
                        lines = [l.strip() for l in f if l.strip()]
                    if len(lines) != last_lines_count:
                        last_lines_count = len(lines)
                        last_change_time = time.time()

                    if len(lines) > baseline_line_count:
                        new_entries: list[dict[str, Any]] = []
                        for raw in lines[baseline_line_count:]:
                            try:
                                parsed = json.loads(raw)
                                if isinstance(parsed, dict):
                                    new_entries.append(parsed)
                            except Exception:
                                continue
                        # A turn exists only once the transcript shows the user message that opened it:
                        # entries from a previous turn can never satisfy this wait.
                        turn_started = any(e.get("type") == "USER_INPUT" for e in new_entries)
                        if new_entries and turn_started:
                            last_entry = new_entries[-1]
                            t_type = last_entry.get("type")
                            t_source = last_entry.get("source")
                            tool_calls = last_entry.get("tool_calls", [])
                            content = last_entry.get("content", "") or ""
                            state = str(last_entry.get("status", "") or "").upper()

                            # A permission/answer request issued as a tool call is a pause, not completion.
                            waiting_tc, reason = self._check_if_waiting_for_interaction("", last_entry)
                            if waiting_tc:
                                return True, content or reason, "WAITING", True

                            if (
                                t_type == "ERROR_MESSAGE"
                                and t_source == "SYSTEM"
                                and (time.time() - last_change_time) >= self.ERROR_SETTLE_SECONDS
                            ):
                                return False, content or str(last_entry.get("error", "")), "ERROR", False

                            if t_type == "PLANNER_RESPONSE" and t_source == "MODEL" and not tool_calls:
                                if state in self._ERROR_STATES:
                                    logger.warning("Antigravity conversation %s turn failed with %s status.", conv_id, state)
                                    return False, content, "ERROR", False
                                is_waiting, _ = self._check_if_waiting_for_interaction(content, last_entry)
                                if is_waiting:
                                    return True, content, "WAITING", True
                                if state in self._DONE_STATES:
                                    return True, content, "DONE", False
                                # in-progress status: the turn is not over, keep polling

                            self._maybe_request_finalization(
                                conv_id, p_dir, execution_id, new_entries, last_entry,
                                idle_seconds=time.time() - last_change_time,
                                budget=timeout - (time.time() - start_time),
                            )
                except Exception as exc:
                    logger.debug("Error checking transcript for %s: %s", conv_id, exc)
            else:
                if not file_appeared and (time.time() - start_time) > min(30.0, timeout):
                    logger.warning("Transcript file for conversation %s did not appear within timeout.", conv_id)
                    return False, "", "TIMEOUT", False

            if cancel_event is not None:
                if cancel_event.wait(poll_interval):
                    return False, "", "CANCELLED", False
            else:
                time.sleep(poll_interval)

        logger.warning("Wait for Antigravity conversation %s timed out after %.1fs", conv_id, timeout)
        return False, "", "TIMEOUT", False

    def _maybe_request_finalization(
        self,
        conv_id: str,
        p_dir: Path,
        execution_id: str | None,
        new_entries: list[dict[str, Any]],
        last_entry: dict[str, Any],
        idle_seconds: float,
        budget: float,
    ) -> None:
        """
        Sends at most ONE automatic 'verify and summarise' nudge per execution, and never while the
        agent may be waiting on a permission/answer.
        """
        if idle_seconds <= 15.0 or len(new_entries) < 2 or last_entry.get("type") != "GENERIC":
            return
        key = execution_id or conv_id
        if key in self._finalization_prompted:
            return
        if any(self._check_if_waiting_for_interaction(e.get("content", "") or "", e)[0] for e in new_entries[-5:]):
            return
        if execution_id:
            ex = self._executions.get(execution_id)
            if ex is not None and ex.status != CodingExecutionStatus.RUNNING:
                return
        self._finalization_prompted.add(key)
        bin_path = self.resolve_binary()
        if not bin_path:
            return
        cmd = [bin_path]
        if "language_server" in bin_path and not bin_path.endswith("agentapi"):
            cmd.append("agentapi")
        cmd.extend(["send-message", "--title=Aether Verification", conv_id,
                    "Verifica il completamento dei requisiti e fornisci il riepilogo finale."])
        try:
            subprocess.run(cmd, cwd=str(p_dir), capture_output=True, text=True, timeout=min(10.0, max(1.0, budget)))
        except Exception as exc:
            logger.debug("Automatic finalization request failed for %s: %s", conv_id, exc)

    def send_message(self, execution_id: str, message: str) -> CodingTaskExecution:
        """
        Routes a user decision/answer to the conversation and waits for the next turn.
        Allowed only while the run is waiting for the user (or finished and being refined); never while a
        turn is already in progress, and never concurrently with another message.
        """
        exec_item = self._executions.get(execution_id)
        if not exec_item:
            raise KeyError(f"Execution '{execution_id}' not found.")
        if exec_item.status == CodingExecutionStatus.RUNNING:
            raise ValueError(f"Execution '{execution_id}' is running a turn; wait for it to settle before sending a message.")
        if exec_item.status not in self._MESSAGEABLE_STATUSES:
            raise ValueError(
                f"Execution '{execution_id}' is in status '{exec_item.status.value}' and cannot receive messages."
            )
        conv_id = exec_item.external_task_id
        if not self._is_valid_conversation_id(conv_id):
            raise ValueError(f"Execution '{execution_id}' has no valid Antigravity conversation ID.")
        bin_path = self.resolve_binary()
        if not bin_path:
            raise RuntimeError("Antigravity binary not found for routing message.")

        lock = self._msg_locks.setdefault(execution_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise ValueError(f"Execution '{execution_id}' is already processing a message.")
        try:
            task_timeout = float(exec_item.task.timeout_seconds)
            used = float(exec_item.metadata.get("active_seconds", 0.0))
            if used >= task_timeout:
                self._set_terminal(
                    exec_item, CodingExecutionStatus.TIMED_OUT,
                    f"Total active time budget of {task_timeout:.0f}s exhausted before the message was sent.",
                )
                return exec_item

            transcript_file = self._transcript_path(conv_id)
            baseline_lines = 0
            if transcript_file.exists():
                try:
                    with open(transcript_file, "r", encoding="utf-8") as f:
                        baseline_lines = sum(1 for line in f if line.strip())
                except Exception:
                    pass

            cmd = [bin_path]
            if "language_server" in bin_path and not bin_path.endswith("agentapi"):
                cmd.append("agentapi")
            cmd.extend(["send-message", f"--title=Aether Decision: {exec_item.task.id}", conv_id, message])
            cwd_path = Path(exec_item.task.project_path).resolve() if exec_item.task.project_path else Path.cwd().resolve()

            t_start = time.time()
            exec_item.status = CodingExecutionStatus.RUNNING
            exec_item.interaction_prompt = None
            self._emit(exec_item, "message_sent", message_chars=len(message))
            try:
                send_res = subprocess.run(
                    cmd, cwd=str(cwd_path), capture_output=True, text=True,
                    timeout=min(30.0, max(1.0, task_timeout - used)),
                )
            except subprocess.TimeoutExpired:
                self._add_active_time(exec_item, time.time() - t_start)
                self._set_terminal(
                    exec_item, CodingExecutionStatus.FAILED,
                    "Delivery of the decision to Antigravity timed out; delivery state is unknown.",
                )
                return exec_item

            if send_res.returncode != 0:
                err = send_res.stderr or send_res.stdout or f"agentapi send-message exited with code {send_res.returncode}"
                self._add_active_time(exec_item, time.time() - t_start)
                self._set_terminal(
                    exec_item, CodingExecutionStatus.FAILED,
                    f"Failed to deliver decision to Antigravity: {err}", raw_output=send_res.stdout,
                )
                return exec_item

            remaining = max(1.0, task_timeout - used - (time.time() - t_start))
            outcome = self._wait_for_conversation_completion(
                conv_id, cwd_path, timeout=remaining, baseline_line_count=baseline_lines,
                cancel_event=self._cancel_events.get(execution_id), execution_id=execution_id,
            )
            self._apply_turn_outcome(exec_item, conv_id, outcome, send_res.stdout or "", time.time() - t_start)
            return exec_item
        finally:
            lock.release()

    def _agent_summary(self, execution: CodingTaskExecution, raw_output: str | None) -> str:
        """The last thing the agent said in its transcript (never a canned message)."""
        conv = execution.external_task_id
        if not self._is_valid_conversation_id(conv):
            return ""
        tf = self._transcript_path(conv)
        if not tf.exists():
            return ""
        try:
            with open(tf, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            for line in reversed(lines):
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if entry.get("type") == "PLANNER_RESPONSE" and isinstance(entry.get("content"), str) and entry["content"].strip():
                    return entry["content"].strip()
        except Exception as err:
            logger.debug("Failed reading transcript: %s", err)
        return ""

    REMOTE_QUIET_SECONDS = 90.0

    def remote_activity_state(self, execution: CodingTaskExecution) -> str:
        """
        'idle' only when the transcript has been quiet and its last entry is a finished model turn;
        'active' when it changed recently; 'unknown' when there is nothing to observe.
        agentapi has no status/cancel verb, so this is the only positive evidence available.
        """
        conv = execution.external_task_id
        if not self._is_valid_conversation_id(conv):
            return "unknown"
        tf = self._transcript_path(conv)
        if not tf.exists():
            return "unknown"
        try:
            age = time.time() - tf.stat().st_mtime
            with open(tf, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            last = json.loads(lines[-1]) if lines else {}
        except Exception:
            return "unknown"
        if age < self.REMOTE_QUIET_SECONDS:
            return "active"
        finished = last.get("type") == "PLANNER_RESPONSE" and not last.get("tool_calls") and str(last.get("status", "")).upper() in self._DONE_STATES
        return "idle" if finished else "unknown"
