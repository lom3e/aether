"""
OpenAI Codex Autonomous Coding Agent Provider Contract.
Provides full provider implementation for OpenAI Codex: CLI binary detection,
user session inspection (~/.codex/auth.json, OPENAI_API_KEY), execution dispatch,
and verifiable evidence collection.
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


class CodexCodingProvider(BaseCodingAgentProvider):
    """
    Provider orchestrating OpenAI Codex as an autonomous coding agent.
    Probes CLI binary, user session (~/.codex/auth.json), and environment.
    """

    ID = "codex"
    NAME = "OpenAI Codex"
    DESCRIPTION = "Autonomous OpenAI Codex CLI agent interface"

    def __init__(self, api_key: str | None = None, binary_path: str | None = None) -> None:
        self._api_key = api_key
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
        """Finds executable codex binary on the local system."""
        cand, status = find_executable(
            ["codex"],
            custom_path=self._binary_path,
            env_var="AETHER_CODEX_BIN",
        )
        if cand and status == "ok":
            return str(cand)
        return None

    def _check_user_session(self) -> tuple[bool, str]:
        """
        Inspects authenticated user session without requiring raw API keys.
        Checks explicit api_key, OPENAI_API_KEY, and ~/.codex/auth.json profile.
        """
        if self._api_key:
            return True, "API Key configurata esplicitamente"

        env_key = os.environ.get("OPENAI_API_KEY")
        if env_key:
            return True, "OPENAI_API_KEY trovata nell'ambiente"

        codex_auth = Path.home() / ".codex" / "auth.json"
        if codex_auth.exists():
            try:
                with open(codex_auth, "r", encoding="utf-8") as f:
                    auth_data = json.load(f)
                mode = auth_data.get("auth_mode", "unknown")
                has_tokens = bool(auth_data.get("tokens"))
                has_key = bool(auth_data.get("OPENAI_API_KEY"))
                if has_tokens or has_key or mode == "chatgpt":
                    return True, f"Sessione utente autenticata (~/.codex/auth.json, modalità: {mode})"
            except Exception as e:
                logger.debug("Failed reading ~/.codex/auth.json: %s", e)

        return False, "Nessuna sessione autenticata o OPENAI_API_KEY trovata"

    @classmethod
    def declared_capabilities(cls) -> dict[str, Any]:
        """Truthful capabilities supported by OpenAI Codex."""
        return {
            "autonomous_editing": True,
            "automated_testing": True,
            "git_diff_evidence": True,
            "cli_integration": True,
            "cancellation": True,
            "multi_file": True,
        }

    def probe_status(self, is_preferred: bool = False) -> CodingProviderStatus:
        """
        Probes whether OpenAI Codex CLI and authentication are available.
        Distinguishes installation, authentication, availability, and missing prerequisites.
        """
        bin_raw = self.resolve_binary()
        bin_path = str(bin_raw) if bin_raw is not None else None
        has_session, session_detail = self._check_user_session()

        auth_method = "chatgpt_session" if "auth.json" in session_detail else ("api_key" if has_session else None)

        if not bin_path:
            cand, status = find_executable(
                ["codex"],
                custom_path=self._binary_path,
                env_var="AETHER_CODEX_BIN",
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
                    auth_method=auth_method,
                    binary_path=str(cand),
                    is_preferred=is_preferred,
                    diagnostic=f"Codex CLI trovato a {cand} ma non ha permessi di esecuzione.",
                    missing_prerequisites=[f"Assegna permessi di esecuzione: chmod +x {cand}"],
                    capabilities=self.declared_capabilities(),
                    error_code="permission_denied",
                )

            has_node, node_msg, _ = check_node_prerequisites()
            if has_session:
                diag = f"Sessione Codex rilevata ({session_detail}), ma il CLI 'codex' non è installato nel PATH."
                prereqs = (
                    ["Installa il CLI 'codex' nel PATH (es. 'npm install -g @openai/codex') per completare l'abilitazione."]
                    if has_node
                    else [node_msg, "Installa Node.js prima di installare il CLI 'codex'."]
                )
                auth_state = AuthenticationState.CREDENTIALS_DETECTED_UNVERIFIED
            else:
                diag = "OpenAI Codex CLI ('codex') non trovato e nessuna credenziale/sessione configurata."
                prereqs = (
                    [
                        "Installa il CLI 'codex' nel PATH (es. 'npm install -g @openai/codex').",
                        "Configura la sessione (accedi con 'codex login' o imposta OPENAI_API_KEY).",
                    ]
                    if has_node
                    else [node_msg, "Installa Node.js prima di installare il CLI 'codex'."]
                )
                auth_state = AuthenticationState.NOT_AUTHENTICATED

            op_st = OperationalState.BLOCKED_MISSING_INSTALLATION if has_node else OperationalState.BLOCKED_MISSING_PREREQUISITES

            return CodingProviderStatus(
                id=self.id,
                name=self.name,
                description=self.description,
                installation_state=InstallationState.NOT_INSTALLED,
                authentication_state=auth_state,
                operational_state=op_st,
                next_action=NextAction.INSTALL,
                auth_method=auth_method,
                is_preferred=is_preferred,
                diagnostic=diag,
                missing_prerequisites=prereqs,
                capabilities=self.declared_capabilities(),
                error_code="not_found",
            )
        aug_env = get_augmented_env()
        try:
            res = subprocess.run(
                [bin_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5.0,
                env=aug_env,
            )
            ver_str = res.stdout.strip() or res.stderr.strip()
            if res.returncode != 0:
                return CodingProviderStatus(
                    id=self.id,
                    name=self.name,
                    description=self.description,
                    installation_state=InstallationState.BROKEN_INSTALLATION,
                    authentication_state=AuthenticationState.UNKNOWN,
                    operational_state=OperationalState.BLOCKED_PROVIDER_ERROR,
                    next_action=NextAction.RECOVER,
                    auth_method=auth_method,
                    is_preferred=is_preferred,
                    binary_path=bin_path,
                    diagnostic=f"Codex CLI trovato a {bin_path} ma non responsivo (codice {res.returncode}): {ver_str}",
                    missing_prerequisites=["Verifica che l'installazione del CLI 'codex' sia integra."],
                    capabilities=self.declared_capabilities(),
                    error_code="binary_unresponsive",
                )

            # Check CLI-level auth if supported
            cli_auth = False
            try:
                auth_res = subprocess.run([bin_path, "auth", "status"], capture_output=True, text=True, timeout=5.0, env=aug_env)
                if auth_res.returncode == 0 and "logged in" in auth_res.stdout.lower() and "not logged in" not in auth_res.stdout.lower():
                    cli_auth = True
            except Exception:
                pass

            is_auth = has_session or cli_auth
            if is_auth:
                return CodingProviderStatus(
                    id=self.id,
                    name=self.name,
                    description=self.description,
                    installation_state=InstallationState.INSTALLED,
                    authentication_state=AuthenticationState.AUTHENTICATED,
                    operational_state=OperationalState.READY,
                    next_action=NextAction.NONE,
                    auth_method=auth_method,
                    is_preferred=is_preferred,
                    binary_path=bin_path,
                    version=ver_str,
                    diagnostic=f"OpenAI Codex CLI pronto e autenticato a {bin_path} ({ver_str}).",
                    missing_prerequisites=[],
                    capabilities=self.declared_capabilities(),
                )

            return CodingProviderStatus(
                id=self.id,
                name=self.name,
                description=self.description,
                installation_state=InstallationState.INSTALLED,
                authentication_state=AuthenticationState.NOT_AUTHENTICATED,
                operational_state=OperationalState.BLOCKED_AUTHENTICATION,
                next_action=NextAction.LOGIN,
                auth_method=auth_method,
                is_preferred=is_preferred,
                binary_path=bin_path,
                version=ver_str,
                diagnostic=f"OpenAI Codex CLI installato a {bin_path} ({ver_str}) ma non autenticato.",
                missing_prerequisites=["Esegui 'codex login' nel terminale o imposta OPENAI_API_KEY."],
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
                auth_method=auth_method,
                is_preferred=is_preferred,
                binary_path=bin_path,
                diagnostic=f"Errore durante l'esecuzione di Codex: {exc}",
                missing_prerequisites=["Controlla i permessi o la configurazione del CLI Codex."],
                capabilities=self.declared_capabilities(),
                error_code="execution_failed",
            )

    def is_available(self) -> tuple[bool, str]:
        """Probes whether OpenAI Codex is installed and authenticated."""
        st = self.probe_status()
        return st.available, st.diagnostic

    def get_installation_instructions(self) -> list[str]:
        return [
            "Prerequisito: Node.js (v18+) e npm devono essere installati nel sistema.",
            "Esegui nel tuo terminale: npm install -g @openai/codex",
            "In alternativa, specifica il percorso dell'eseguibile tramite AETHER_CODEX_BIN.",
        ]

    def get_authentication_instructions(self) -> list[str]:
        return [
            "OpenAI Codex supporta l'autenticazione tramite sessione o chiave API.",
            "Metodo 1: Esegui 'codex login' nel tuo terminale per autenticare la sessione del tuo account.",
            "Metodo 2: Esporta OPENAI_API_KEY nel tuo ambiente shell.",
        ]

    def install(self, on_progress: Any = None, cancel_event: Any = None) -> tuple[bool, str]:
        if on_progress:
            on_progress(10.0, "Verifica prerequisiti di sistema (Node.js & npm)...")
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
            on_progress(30.0, "Installazione di @openai/codex via npm...")

        try:
            rc, stdout, stderr, was_cancelled = run_cancellable_process(
                [npm_bin, "install", "-g", "@openai/codex"],
                env=aug_env,
                timeout=180.0,
                cancel_event=cancel_event,
            )
            if was_cancelled:
                return False, "Installazione di OpenAI Codex annullata dall'utente."

            if rc != 0:
                raw_err = (stderr.strip() or stdout.strip())[:400]
                diag_msg = diagnose_npm_error(raw_err)
                return False, f"npm install fallito (codice {rc}): {diag_msg}"

            if on_progress:
                on_progress(80.0, "Verifica dell'eseguibile installato...")

            cand, status = find_executable(["codex"], env_var="AETHER_CODEX_BIN")
            if not cand or status != "ok":
                return False, "Comando 'npm install' terminato ma l'eseguibile 'codex' non è stato trovato nei percorsi standard."

            if on_progress:
                on_progress(100.0, f"OpenAI Codex CLI installato con successo a {cand}.")
            return True, f"OpenAI Codex CLI installato a {cand}."
        except subprocess.TimeoutExpired:
            return False, "Installazione di OpenAI Codex interrotta per timeout (superati 180s)."
        except Exception as exc:
            return False, f"Errore imprevisto durante l'installazione di Codex: {exc}"

    def authenticate(self, on_progress: Any = None, cancel_event: Any = None) -> tuple[bool, str]:
        if on_progress:
            on_progress(20.0, "Controllo sessione e credenziali OpenAI Codex...")
        has_session, session_detail = self._check_user_session()
        if has_session:
            if on_progress:
                on_progress(100.0, f"Credenziali verificate: {session_detail}")
            return True, f"Sessione o chiave API presente: {session_detail}"

        return (
            False,
            "Nessuna sessione trovata. Esegui 'codex login' nel terminale o esporta la variabile OPENAI_API_KEY."
        )

    def update(self, on_progress: Any = None, cancel_event: Any = None) -> tuple[bool, str]:
        if on_progress:
            on_progress(15.0, "Verifica versione attuale di OpenAI Codex...")
        aug_env = get_augmented_env()
        npm_bin = shutil.which("npm", path=aug_env.get("PATH"))
        if not npm_bin:
            return False, "npm non trovato nell'ambiente di esecuzione."

        if on_progress:
            on_progress(40.0, "Esecuzione npm update -g @openai/codex...")
        try:
            rc, stdout, stderr, was_cancelled = run_cancellable_process(
                [npm_bin, "update", "-g", "@openai/codex"],
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
                on_progress(100.0, "OpenAI Codex aggiornato con successo.")
            return True, "OpenAI Codex aggiornato con successo."
        except Exception as exc:
            return False, f"Errore durante l'aggiornamento: {exc}"

    def start_task(self, task: CodingTask) -> CodingTaskExecution:
        """Runs the task through the shared one-shot CLI runtime (registration, snapshot, evidence, events)."""
        return self._run_cli_once(
            task,
            label="OpenAI Codex",
            build_cmd=lambda bin_path, prompt: [bin_path, "-p", prompt],
        )
