"""
Claude Code Autonomous Coding Agent Provider.
Dispatches coding tasks to Claude Code via the local `claude` CLI,
captures structured non-interactive outputs, and collects verifiable git evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
import uuid

from aether.coding.base import BaseCodingAgentProvider
from aether.coding.environment import (
    check_node_prerequisites,
    check_npm_global_writable,
    diagnose_npm_error,
    find_executable,
    get_augmented_env,
    run_cancellable_process,
    sanitize_log,
)
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


class ClaudeCodeCodingProvider(BaseCodingAgentProvider):
    """
    Provider orchestrating Claude Code as an autonomous coding agent.
    Interfaces directly with the local `claude` CLI.
    """

    ID = "claude_code"
    NAME = "Claude Code"
    DESCRIPTION = "Autonomous Claude Code CLI agent via local claude command"

    def __init__(self, binary_path: str | None = None) -> None:
        self._binary_path = binary_path
        self._executions: dict[str, CodingTaskExecution] = {}

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
        """Finds executable claude binary on the local system."""
        cand, status = find_executable(
            ["claude"],
            custom_path=self._binary_path,
            env_var="AETHER_CLAUDE_CODE_BIN",
        )
        if cand and status == "ok":
            return str(cand)
        return None

    @classmethod
    def declared_capabilities(cls) -> dict[str, Any]:
        """Truthful capabilities supported by the Claude Code CLI."""
        return {
            "autonomous_editing": True,
            "headless_cli": True,
            "json_output": True,
            "git_diff_evidence": True,
            "automated_testing": True,
            "cancellation": False,
            "multi_file": True,
        }

    def probe_status(self, is_preferred: bool = False) -> CodingProviderStatus:
        """
        Probes whether Claude Code is installed and authenticated.
        Distinguishes installation, authentication, availability, and missing prerequisites.
        """
        bin_raw = self.resolve_binary()
        bin_path = str(bin_raw) if bin_raw is not None else None

        if not bin_path:
            cand, status = find_executable(
                ["claude"],
                custom_path=self._binary_path,
                env_var="AETHER_CLAUDE_CODE_BIN",
            )
            if status == "permission_denied" and cand:
                return CodingProviderStatus(
                    id=self.id,
                    name=self.name,
                    description=self.description,
                    installation_state=InstallationState.INVALID_PATH,
                    authentication_state=AuthenticationState.UNKNOWN,
                    operational_state=OperationalState.BLOCKED_PERMISSIONS,
                    next_action=NextAction.RECOVER,
                    auth_method="oauth_terminal",
                    binary_path=str(cand),
                    is_preferred=is_preferred,
                    diagnostic=f"Claude Code trovato a {cand} ma non ha permessi di esecuzione.",
                    missing_prerequisites=[f"Assegna permessi di esecuzione: chmod +x {cand}"],
                    capabilities=self.declared_capabilities(),
                    error_code="permission_denied",
                )

            has_node, node_msg, _ = check_node_prerequisites()
            missing = (
                ["Installa Claude Code eseguendo 'npm install -g @anthropic-ai/claude-code' o collocando l'eseguibile in ~/.local/bin/claude."]
                if has_node
                else [node_msg, "Installa Node.js v18+ prima di installare Claude Code."]
            )
            op_st = OperationalState.BLOCKED_MISSING_INSTALLATION if has_node else OperationalState.BLOCKED_MISSING_PREREQUISITES
            return CodingProviderStatus(
                id=self.id,
                name=self.name,
                description=self.description,
                installation_state=InstallationState.NOT_INSTALLED,
                authentication_state=AuthenticationState.UNKNOWN,
                operational_state=op_st,
                next_action=NextAction.INSTALL,
                auth_method="oauth_terminal",
                is_preferred=is_preferred,
                diagnostic="Claude Code non trovato. Verificati i percorsi standard (~/.local/bin/claude, PATH).",
                missing_prerequisites=missing,
                capabilities=self.declared_capabilities(),
                error_code="not_found",
            )

        try:
            aug_env = get_augmented_env()
            res = subprocess.run(
                [bin_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5.0,
                env=aug_env,
            )
            if res.returncode != 0:
                return CodingProviderStatus(
                    id=self.id,
                    name=self.name,
                    description=self.description,
                    installation_state=InstallationState.BROKEN_INSTALLATION,
                    authentication_state=AuthenticationState.UNKNOWN,
                    operational_state=OperationalState.BLOCKED_PROVIDER_ERROR,
                    next_action=NextAction.RECOVER,
                    auth_method="oauth_terminal",
                    is_preferred=is_preferred,
                    binary_path=bin_path,
                    diagnostic=f"Claude Code presente a {bin_path} ma non responsivo (codice {res.returncode}): {res.stderr.strip()}",
                    missing_prerequisites=["Verifica che l'installazione di Claude Code sia integra."],
                    capabilities=self.declared_capabilities(),
                    error_code="binary_unresponsive",
                )

            ver_str = res.stdout.strip() or res.stderr.strip()

            # Probe real authentication state
            auth_res = subprocess.run(
                [bin_path, "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5.0,
                env=aug_env,
            )
            auth_out = (auth_res.stdout + " " + auth_res.stderr).strip()

            is_authenticated = False
            import re
            m = re.search(r"\{.*\}", auth_out, re.DOTALL)
            if m:
                try:
                    auth_json = json.loads(m.group(0))
                    if auth_json.get("loggedIn") is True:
                        is_authenticated = True
                    elif auth_json.get("loggedIn") is False or auth_json.get("authMethod") == "none":
                        is_authenticated = False
                except Exception:
                    pass

            if not is_authenticated and ("ready and authenticated" in auth_out or "logged in" in auth_out.lower()) and "not logged in" not in auth_out.lower():
                is_authenticated = True

            if is_authenticated:
                return CodingProviderStatus(
                    id=self.id,
                    name=self.name,
                    description=self.description,
                    installation_state=InstallationState.INSTALLED,
                    authentication_state=AuthenticationState.AUTHENTICATED,
                    operational_state=OperationalState.READY,
                    next_action=NextAction.NONE,
                    auth_method="oauth_terminal",
                    is_preferred=is_preferred,
                    binary_path=bin_path,
                    version=ver_str,
                    diagnostic=f"Claude Code pronto e autenticato a {bin_path} ({ver_str}).",
                    missing_prerequisites=[],
                    capabilities=self.declared_capabilities(),
                )

            return CodingProviderStatus(
                id=self.id,
                name=self.name,
                description=self.description,
                installation_state=InstallationState.INSTALLED,
                authentication_state=AuthenticationState.INTERACTIVE_LOGIN_REQUIRED,
                operational_state=OperationalState.BLOCKED_AUTHENTICATION,
                next_action=NextAction.LOGIN,
                auth_method="oauth_terminal",
                is_preferred=is_preferred,
                binary_path=bin_path,
                version=ver_str,
                diagnostic=f"Claude Code è installato a {bin_path} ({ver_str}) ma non autenticato (richiede il login interattivo nel terminale).",
                missing_prerequisites=[
                    "Esegui 'claude login' nel tuo terminale per autenticare la sessione."
                ],
                capabilities=self.declared_capabilities(),
                error_code="auth_required",
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
                auth_method="oauth_terminal",
                is_preferred=is_preferred,
                binary_path=bin_path,
                diagnostic=f"Errore durante l'esecuzione di Claude Code: {exc}",
                missing_prerequisites=["Controlla i permessi o la configurazione di Claude Code."],
                capabilities=self.declared_capabilities(),
                error_code="execution_failed",
            )

    def is_available(self) -> tuple[bool, str]:
        """Probes whether Claude Code is installed and authenticated."""
        st = self.probe_status()
        return st.available, st.diagnostic

    def get_installation_instructions(self) -> list[str]:
        return [
            "Prerequisito: Node.js (v18+) e npm devono essere installati nel sistema.",
            "Esegui nel tuo terminale: npm install -g @anthropic-ai/claude-code",
            "In alternativa, specifica il percorso dell'eseguibile tramite AETHER_CLAUDE_CODE_BIN.",
        ]

    def get_authentication_instructions(self) -> list[str]:
        return [
            "Claude Code richiede un'autenticazione interattiva tramite terminale e browser.",
            "Apri il terminale ed esegui il comando: claude login",
            "Segui le istruzioni a video per effettuare il login con il tuo account Anthropic.",
            "Al termine, torna in Aether e premi 'Verifica' per aggiornare lo stato.",
        ]

    def install(self, on_progress: Any = None, cancel_event: Any = None) -> tuple[bool, str]:
        if on_progress:
            on_progress(10.0, "Verifica dei prerequisiti di runtime (Node.js & npm)...")
        has_node, node_msg, _ = check_node_prerequisites()
        if not has_node:
            return False, f"Prerequisiti mancanti: {node_msg}"

        if on_progress:
            on_progress(20.0, "Verifica permessi directory di installazione npm...")
        is_writable, write_msg, _ = check_npm_global_writable()
        if not is_writable:
            return False, write_msg

        aug_env = get_augmented_env()
        npm_bin = shutil.which("npm", path=aug_env.get("PATH"))
        if not npm_bin:
            return False, "npm non trovato nell'ambiente di esecuzione."

        if on_progress:
            on_progress(30.0, "Installazione di @anthropic-ai/claude-code via npm...")

        try:
            rc, stdout, stderr, was_cancelled = run_cancellable_process(
                [npm_bin, "install", "-g", "@anthropic-ai/claude-code"],
                env=aug_env,
                timeout=180.0,
                cancel_event=cancel_event,
            )
            if was_cancelled:
                return False, "Installazione di Claude Code annullata dall'utente."

            if rc != 0:
                raw_err = (stderr.strip() or stdout.strip())[:400]
                diag_msg = diagnose_npm_error(raw_err)
                return False, f"npm install fallito (codice {rc}): {diag_msg}"

            if on_progress:
                on_progress(80.0, "Verifica dell'eseguibile installato...")

            cand, status = find_executable(["claude"], env_var="AETHER_CLAUDE_CODE_BIN")
            if not cand or status != "ok":
                return False, "Comando 'npm install' terminato ma l'eseguibile 'claude' non è stato trovato nei percorsi standard."

            if on_progress:
                on_progress(100.0, f"Claude Code installato con successo a {cand}.")
            return True, f"Claude Code installato a {cand}."
        except subprocess.TimeoutExpired:
            return False, "Installazione di Claude Code interrotta per timeout (superati 180s)."
        except Exception as exc:
            return False, f"Errore imprevisto durante l'installazione di Claude Code: {exc}"

    def authenticate(self, on_progress: Any = None, cancel_event: Any = None) -> tuple[bool, str]:
        if on_progress:
            on_progress(20.0, "Controllo stato sessione Claude Code...")
        st = self.probe_status()
        if st.authenticated:
            if on_progress:
                on_progress(100.0, "Claude Code è già autenticato.")
            return True, "Sessione Claude Code già attiva e autenticata."

        if on_progress:
            on_progress(50.0, "Predisposizione istruzioni per autenticazione interattiva...")
        return (
            False,
            "Claude Code richiede un'autenticazione OAuth interattiva da riga di comando. "
            "Apri il terminale ed esegui 'claude login', quindi premi 'Verifica' in Aether."
        )

    def update(self, on_progress: Any = None, cancel_event: Any = None) -> tuple[bool, str]:
        if on_progress:
            on_progress(15.0, "Verifica versione attuale di Claude Code...")
        aug_env = get_augmented_env()
        npm_bin = shutil.which("npm", path=aug_env.get("PATH"))
        if not npm_bin:
            return False, "npm non trovato nell'ambiente di esecuzione."

        if on_progress:
            on_progress(40.0, "Esecuzione npm update -g @anthropic-ai/claude-code...")
        try:
            rc, stdout, stderr, was_cancelled = run_cancellable_process(
                [npm_bin, "update", "-g", "@anthropic-ai/claude-code"],
                env=aug_env,
                timeout=180.0,
                cancel_event=cancel_event,
            )
            if was_cancelled:
                return False, "Aggiornamento annullato dall'utente."
            if rc != 0:
                raw_err = (stderr.strip() or stdout.strip())[:300]
                return False, f"Aggiornamento fallito: {diagnose_npm_error(raw_err)}"
            if on_progress:
                on_progress(100.0, "Claude Code aggiornato con successo.")
            return True, "Claude Code aggiornato con successo."
        except Exception as exc:
            return False, f"Errore durante l'aggiornamento: {exc}"

    def start_task(self, task: CodingTask) -> CodingTaskExecution:
        """Runs the task through the shared one-shot CLI runtime (registration, snapshot, evidence, events)."""
        return self._run_cli_once(
            task,
            label="Claude Code",
            build_cmd=lambda bin_path, prompt: [bin_path, "-p", prompt, "--output-format", "json"],
            parse_output=self._parse_cli_json,
        )

    @staticmethod
    def _parse_cli_json(stdout: str) -> str:
        """`claude -p --output-format json` wraps the final answer in {"result": ...}."""
        try:
            data = json.loads(stdout)
            if isinstance(data, dict) and isinstance(data.get("result"), str):
                return data["result"]
        except Exception:
            pass
        return stdout
