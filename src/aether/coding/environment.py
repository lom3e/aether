"""
Environment & Executable Discovery for External Coding Agents.
Provides robust PATH resolution on macOS, permission checking,
log sanitization (redacting tokens/secrets), and Node.js prerequisite verification.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
from typing import Any, Callable

from aether.core.process_control import new_process_group_kwargs, terminate_process_tree

logger = logging.getLogger(__name__)

STANDARD_MACOS_PATHS = [
    Path.home() / ".gemini" / "antigravity" / "bin",
    Path.home() / ".local" / "bin",
    Path("/opt/homebrew/bin"),
    Path("/opt/homebrew/sbin"),
    Path("/usr/local/bin"),
    Path("/Applications/Antigravity.app/Contents/Resources/bin"),
    Path.home() / ".cargo" / "bin",
]

# Sensitive token redaction regex patterns
SECRET_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9_\-]{20,})", re.IGNORECASE),
    re.compile(r"(Bearer\s+[a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
    re.compile(r"(token[\"':\s=]+)([a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
    re.compile(r"(key[\"':\s=]+)([a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
    re.compile(r"(password[\"':\s=]+)([^\s\"';&]{6,})", re.IGNORECASE),
]


def sanitize_log(text: str) -> str:
    """Redacts API keys, bearer tokens, passwords, and sensitive credentials from logs."""
    if not text:
        return ""
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub(r"[REDACTED]", sanitized)
    return sanitized


def get_augmented_env() -> dict[str, str]:
    """
    Returns os.environ with PATH augmented to include standard macOS CLI directories
    so that background processes (GUI, daemons) can find user-installed tools.
    """
    env = dict(os.environ)
    existing_path = env.get("PATH", "")
    existing_dirs = existing_path.split(os.pathsep) if existing_path else []

    extra_dirs = [
        str(p)
        for p in STANDARD_MACOS_PATHS
        if p.is_dir() and str(p) not in existing_dirs
    ]

    if extra_dirs:
        env["PATH"] = os.pathsep.join(extra_dirs + existing_dirs)

    return env


def find_executable(
    binary_names: str | list[str],
    custom_path: str | None = None,
    env_var: str | None = None,
) -> tuple[Path | None, str]:
    """
    Finds executable on the local host with strict permission verification.

    Returns:
        (Path, "ok") if found and executable.
        (Path, "permission_denied") if found but not executable.
        (None, "not_found") if not found.
    """
    names = [binary_names] if isinstance(binary_names, str) else list(binary_names)

    # 1. Custom explicit path if provided
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
        if p.is_file():
            if os.access(p, os.X_OK):
                return p, "ok"
            return p, "permission_denied"
        return None, "invalid_custom_path"

    # 2. Environment variable override
    if env_var:
        env_val = os.environ.get(env_var)
        if env_val:
            p = Path(env_val).expanduser().resolve()
            if p.is_file():
                if os.access(p, os.X_OK):
                    return p, "ok"
                return p, "permission_denied"
            return None, "invalid_env_path"

    # 3. Check standard search locations first (ensures user tools found even if PATH stripped)
    for name in names:
        for search_dir in STANDARD_MACOS_PATHS:
            cand = search_dir / name
            if cand.is_file():
                if os.access(cand, os.X_OK):
                    return cand, "ok"
                return cand, "permission_denied"

    # 4. Check system PATH via shutil.which
    aug_env = get_augmented_env()
    for name in names:
        which_res = shutil.which(name, path=aug_env.get("PATH"))
        if which_res:
            p = Path(which_res).resolve()
            if p.is_file():
                if os.access(p, os.X_OK):
                    return p, "ok"
                return p, "permission_denied"

    return None, "not_found"


def check_node_prerequisites() -> tuple[bool, str, dict[str, str]]:
    """
    Verifies that Node.js and npm are installed and meet version requirements (Node >= 18).
    Required by Claude Code and OpenAI Codex CLI.
    """
    aug_env = get_augmented_env()
    node_bin = shutil.which("node", path=aug_env.get("PATH"))
    npm_bin = shutil.which("npm", path=aug_env.get("PATH"))

    details: dict[str, str] = {}
    if not node_bin or not npm_bin:
        msg = "Node.js o npm non trovati. Installa Node.js (v18+) per utilizzare questo provider."
        return False, msg, details

    details["node_path"] = node_bin
    details["npm_path"] = npm_bin

    try:
        node_res = subprocess.run([node_bin, "--version"], capture_output=True, text=True, timeout=5.0, env=aug_env)
        details["node_version"] = node_res.stdout.strip()
    except Exception as e:
        return False, f"Impossibile determinare la versione di Node.js: {e}", details

    try:
        npm_res = subprocess.run([npm_bin, "--version"], capture_output=True, text=True, timeout=5.0, env=aug_env)
        details["npm_version"] = npm_res.stdout.strip()
    except Exception as e:
        return False, f"Impossibile determinare la versione di npm: {e}", details

    # Parse node version (e.g. v22.23.1)
    v_match = re.search(r"v?(\d+)", details.get("node_version", ""))
    if v_match:
        major = int(v_match.group(1))
        if major < 18:
            return False, f"Node.js versione {details['node_version']} obsoleta: richiesta v18 o successiva.", details

    return True, f"Node.js ({details.get('node_version')}) e npm ({details.get('npm_version')}) pronti.", details


def probe_cli_version(
    bin_path: str | Path,
    version_arg: str = "--version",
    timeout: float = 5.0,
) -> tuple[int, str]:
    """Runs binary with version flag safely, returning (returncode, version_output)."""
    p = Path(bin_path)
    if not p.is_file() or not os.access(p, os.X_OK):
        return -1, "File non trovato o permessi di esecuzione mancanti"

    aug_env = get_augmented_env()
    try:
        res = subprocess.run(
            [str(p), version_arg],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=aug_env,
        )
        out = (res.stdout or res.stderr).strip()
        return res.returncode, out
    except subprocess.TimeoutExpired:
        return -1, "Timeout durante la verifica della versione"
    except Exception as exc:
        return -1, str(exc)


def check_npm_global_writable() -> tuple[bool, str, Path | None]:
    """
    Checks if the npm global prefix directory is writable by the current user without sudo.
    Returns:
        (True, "Directory npm globale (...) scrivibile.", prefix_path)
        (False, Actionable error/guidance message, prefix_path)
    """
    aug_env = get_augmented_env()
    npm_bin = shutil.which("npm", path=aug_env.get("PATH"))
    if not npm_bin:
        return False, "npm non trovato nell'ambiente di esecuzione.", None

    try:
        res = subprocess.run(
            [npm_bin, "config", "get", "prefix"],
            capture_output=True,
            text=True,
            timeout=5.0,
            env=aug_env,
        )
        if res.returncode != 0:
            return False, f"Impossibile leggere il prefisso npm: {res.stderr.strip()}", None

        prefix_str = res.stdout.strip()
        prefix = Path(prefix_str).expanduser().resolve()

        # Check candidate locations for global installs
        candidates = [
            prefix,
            prefix / "lib" / "node_modules",
            prefix / "lib",
            prefix / "bin",
        ]
        is_writable = False
        for cand in candidates:
            if cand.exists() and os.access(cand, os.W_OK):
                is_writable = True
                break
            elif not cand.exists() and cand.parent.exists() and os.access(cand.parent, os.W_OK):
                is_writable = True
                break

        if is_writable:
            return True, f"Directory npm globale ({prefix}) scrivibile.", prefix

        msg = (
            f"La directory globale di npm ({prefix}) non è scrivibile dall'utente corrente (EACCES). "
            f"Per installare pacchetti globali senza privilegi di root, imposta un prefisso utente eseguendo: "
            f"'npm config set prefix ~/.local', oppure installa il pacchetto manualmente."
        )
        return False, msg, prefix
    except Exception as exc:
        return False, f"Errore durante la verifica dei permessi della directory npm: {exc}", None


def diagnose_npm_error(error_output: str) -> str:
    """Diagnoses common npm failure causes and provides actionable guidance."""
    text = (error_output or "").lower()
    if "eacces" in text or "permission denied" in text or "eperm" in text:
        return (
            "Permessi insufficienti durante l'installazione npm (EACCES / permission denied). "
            "Il prefisso globale di npm richiede permessi di amministratore. "
            "Esegui nel terminale: 'npm config set prefix ~/.local' per installare nella tua home directory, oppure installa manualmente."
        )
    if "enotfound" in text or "etimedout" in text or "fetch failed" in text or "network" in text:
        return (
            "Errore di connessione di rete o timeout verso il registro npm. "
            "Verifica la connessione a Internet, lo stato del proxy o il registro configurato."
        )
    if "ebadengine" in text or "unsupported engine" in text:
        return (
            "Versione di Node.js incompatibile con il pacchetto richiesto. "
            "Aggiorna Node.js alla versione 18 o superiore."
        )
    return error_output.strip()


def run_cancellable_process(
    cmd: list[str],
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 180.0,
    cancel_event: threading.Event | None = None,
    poll_interval: float = 0.1,
) -> tuple[int, str, str, bool]:
    """
    Executes a subprocess in an isolated process group (start_new_session=True) while cooperatively
    monitoring a cancellation flag.

    If cancel_event is set:
        - Signals the entire process group with SIGTERM.
        - Waits a grace period (1.5s), and escalates to SIGKILL if processes remain alive.
        - Returns (returncode, stdout, stderr, was_cancelled=True).

    If timeout expires:
        - Terminates the process group and raises subprocess.TimeoutExpired.

    Returns:
        (returncode, stdout, stderr, was_cancelled)
    """
    if cancel_event and cancel_event.is_set():
        return -signal.SIGTERM, "", "Operazione annullata prima dell'avvio del comando.", True

    aug_env = env if env is not None else get_augmented_env()
    cwd_str = str(cwd) if cwd else None

    proc = subprocess.Popen(
        cmd,
        cwd=cwd_str,
        env=aug_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **new_process_group_kwargs(),
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def _reader(pipe: Any, acc: list[str]) -> None:
        try:
            for line in iter(pipe.readline, ""):
                acc.append(line)
            pipe.close()
        except Exception:
            pass

    t_out = threading.Thread(target=_reader, args=(proc.stdout, stdout_lines), daemon=True)
    t_err = threading.Thread(target=_reader, args=(proc.stderr, stderr_lines), daemon=True)
    t_out.start()
    t_err.start()

    start_time = time.time()
    was_cancelled = False

    def _kill_group(force: bool) -> None:
        terminate_process_tree(proc, force=force)

    while proc.poll() is None:
        if cancel_event and cancel_event.is_set():
            was_cancelled = True
            logger.info("Cancellation detected for PID %s (PGID), sending SIGTERM...", proc.pid)
            _kill_group(False)
            try:
                proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                logger.warning("Process PID %s did not terminate with SIGTERM, escalating to SIGKILL...", proc.pid)
                _kill_group(True)
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    pass
            break

        if timeout and (time.time() - start_time) > timeout:
            logger.warning("Process PID %s exceeded timeout of %.1fs, terminating...", proc.pid, timeout)
            _kill_group(True)
            try:
                proc.wait(timeout=1.0)
            except Exception:
                pass
            t_out.join(timeout=1.0)
            t_err.join(timeout=1.0)
            out_str = "".join(stdout_lines)
            err_str = "".join(stderr_lines)
            raise subprocess.TimeoutExpired(cmd, timeout, output=out_str, stderr=err_str)

        time.sleep(poll_interval)

    t_out.join(timeout=1.0)
    t_err.join(timeout=1.0)

    out_str = "".join(stdout_lines)
    err_str = "".join(stderr_lines)
    rc = proc.returncode if proc.returncode is not None else (-signal.SIGTERM if was_cancelled else 0)

    return rc, out_str, err_str, was_cancelled
