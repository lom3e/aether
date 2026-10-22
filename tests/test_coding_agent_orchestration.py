"""
Tests for External Coding Agent Orchestration (Macro 1 & Google Antigravity).
Validates:
- Common provider contracts and data models
- Provider discovery and live availability probing (Antigravity, Claude Code, Codex)
- Orchestrator priority resolution, provider selection, and diagnostics
- Strict fail-closed boundary: NEVER falling back to internal LLM code generation
- Action execution via ActionRegistry and ActionExecutor (coding.delegate, coding.status, coding.results, coding.list_providers)
- Personal Agent intent routing and conversational distinction
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from aether.actions.executor import ActionExecutor
from aether.actions.registry import ActionRegistry
from aether.actions.store import ActionStore
from aether.coding.base import (
    BaseCodingAgentProvider,
    CodingAgentUnavailableError,
)
from aether.coding.models import (
    CodingExecutionStatus,
    CodingResult,
    CodingTask,
    CodingTaskExecution,
)
from aether.coding.orchestrator import (
    CodingAgentOrchestrator,
    get_coding_orchestrator,
)
from aether.coding.providers.antigravity import AntigravityCodingProvider
from aether.coding.providers.claude_code import ClaudeCodeCodingProvider
from aether.coding.providers.codex import CodexCodingProvider
from aether.personal.models import IntentTier
from aether.personal.service import PersonalAgentService
from aether.personal.store import PersonalStore


# ---------------------------------------------------------------------------
# 1. Models & Serialization Tests
# ---------------------------------------------------------------------------

def test_coding_models_roundtrip():
    task = CodingTask(
        instruction="Implement OAuth token refresh loop",
        project_path="/tmp/project",
        context_files=["auth.py", "tokens.py"],
        context_data={"timeout": 30},
        provider_id="antigravity",
    )
    task_dict = task.to_dict()
    restored_task = CodingTask.from_dict(task_dict)
    assert restored_task.instruction == task.instruction
    assert restored_task.project_path == task.project_path
    assert restored_task.context_files == ["auth.py", "tokens.py"]
    assert restored_task.context_data == {"timeout": 30}
    assert restored_task.provider_id == "antigravity"

    res = CodingResult(
        success=True,
        status=CodingExecutionStatus.COMPLETED,
        provider_id="antigravity",
        external_task_id="conv-12345",
        summary="Modified 2 files successfully",
        diff="--- a/auth.py\n+++ b/auth.py\n@@ ...",
        modified_files=["auth.py", "tokens.py"],
    )
    res_dict = res.to_dict()
    restored_res = CodingResult.from_dict(res_dict)
    assert restored_res.success is True
    assert restored_res.status == CodingExecutionStatus.COMPLETED
    assert restored_res.provider_id == "antigravity"
    assert restored_res.modified_files == ["auth.py", "tokens.py"]
    assert "auth.py" in restored_res.diff

    execution = CodingTaskExecution(
        id="exec-001",
        task=task,
        provider_id="antigravity",
        status=CodingExecutionStatus.COMPLETED,
        result=res,
    )
    exec_dict = execution.to_dict()
    restored_exec = CodingTaskExecution.from_dict(exec_dict)
    assert restored_exec.id == "exec-001"
    assert restored_exec.status == CodingExecutionStatus.COMPLETED
    assert restored_exec.result is not None
    assert restored_exec.result.success is True


# ---------------------------------------------------------------------------
# 2. Live & Simulated Provider Availability Tests
# ---------------------------------------------------------------------------

def test_antigravity_live_availability():
    """Validates real live detection of Google Antigravity on host."""
    provider = AntigravityCodingProvider()
    ready, detail = provider.is_available()
    assert ready is True, f"Antigravity should be ready on host: {detail}"
    assert "agentapi" in detail
    assert provider.resolve_binary() is not None


def test_claude_code_live_availability():
    """Validates real live detection and truthful auth diagnosis of Claude Code CLI on host."""
    provider = ClaudeCodeCodingProvider()
    bin_path = provider.resolve_binary()
    assert bin_path is not None
    ready, detail = provider.is_available()
    # On host, Claude Code is installed at ~/.local/bin/claude but not logged in
    assert ready is False
    assert "non autenticato" in detail or "not authenticated" in detail

    # Validate structured probe_status
    status = provider.probe_status()
    assert status.id == "claude_code"
    assert status.installed is True
    assert status.authenticated is False
    assert status.available is False
    assert len(status.missing_prerequisites) > 0
    assert "claude login" in status.missing_prerequisites[0]


def test_claude_code_authenticated_mock():
    """Validates Claude Code availability when authenticated."""
    provider = ClaudeCodeCodingProvider()

    def fake_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return MagicMock(returncode=0, stdout="2.1.294 (Claude Code)\n", stderr="")
        if "status" in cmd:
            return MagicMock(returncode=0, stdout='{"loggedIn": true, "authMethod": "oauth"}\n', stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        ready, detail = provider.is_available()
        assert ready is True
        assert "pronto e autenticato" in detail or "ready and authenticated" in detail

        status = provider.probe_status()
        assert status.installed is True
        assert status.authenticated is True
        assert status.available is True
        assert len(status.missing_prerequisites) == 0



def test_codex_availability_and_session_probing():
    """Validates OpenAI Codex live diagnosis and session detection."""
    provider = CodexCodingProvider()
    # Hermetic: the developer machine may have the codex CLI installed; this test describes a machine without it.
    with patch.object(CodexCodingProvider, "resolve_binary", return_value=None):
        status = provider.probe_status()
    assert status.id == "codex"
    # CLI codex is not in PATH on host, but ~/.codex session is detected
    assert status.installed is False
    assert status.available is False
    assert len(status.missing_prerequisites) > 0
    assert "codex" in status.missing_prerequisites[0].lower()


def test_codex_availability_mocked_binary():
    """Validates OpenAI Codex availability when binary and session are present."""
    provider = CodexCodingProvider(api_key="sk-test-key")
    with patch.object(provider, "resolve_binary", return_value=Path("/usr/local/bin/codex")), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="codex version 0.8.0\n", stderr="")):
        ready, detail = provider.is_available()
        assert ready is True
        assert "pronto" in detail or "ready" in detail

        status = provider.probe_status()
        assert status.installed is True
        assert status.authenticated is True
        assert status.available is True
        assert len(status.missing_prerequisites) == 0



# ---------------------------------------------------------------------------
# 3. CodingAgentOrchestrator Logic Tests
# ---------------------------------------------------------------------------

def test_orchestrator_list_providers():
    orch = CodingAgentOrchestrator()
    providers = orch.list_providers()
    provider_ids = [p["id"] for p in providers]
    assert "antigravity" in provider_ids
    assert "claude_code" in provider_ids
    assert "codex" in provider_ids

    ag_prov = next(p for p in providers if p["id"] == "antigravity")
    assert ag_prov["available"] is True


def test_orchestrator_resolution_priority():
    """Default resolution prioritizes Antigravity if available."""
    orch = CodingAgentOrchestrator()
    provider, detail = orch.resolve_provider()
    assert provider.id == "antigravity"
    assert "agentapi" in detail


def test_orchestrator_preferred_provider():
    """Explicit provider preference is honored if available, or fails closed if unavailable."""
    orch = CodingAgentOrchestrator()

    # Antigravity is available
    ag_provider, _ = orch.resolve_provider(preferred_id="antigravity")
    assert ag_provider.id == "antigravity"

    # Claude Code is unauthenticated -> fails closed with informative error
    with pytest.raises(CodingAgentUnavailableError) as exc_claude:
        orch.resolve_provider(preferred_id="claude_code")
    assert "Claude Code" in str(exc_claude.value)
    assert "not authenticated" in str(exc_claude.value) or "login" in str(exc_claude.value)

    # Codex is unconfigured -> fails closed with informative error
    with pytest.raises(CodingAgentUnavailableError) as exc_codex:
        orch.resolve_provider(preferred_id="codex")
    assert "OpenAI Codex" in str(exc_codex.value)


def test_orchestrator_fail_closed_when_all_unavailable():
    """Strict Rule: If no provider is available, fail closed with diagnostics and NEVER write code directly."""
    mock_p1 = MagicMock(spec=BaseCodingAgentProvider)
    mock_p1.id = "p1"
    mock_p1.name = "Mock Agent 1"
    mock_p1.is_available.return_value = (False, "Binary missing")

    mock_p2 = MagicMock(spec=BaseCodingAgentProvider)
    mock_p2.id = "p2"
    mock_p2.name = "Mock Agent 2"
    mock_p2.is_available.return_value = (False, "Unauthorized")

    orch = CodingAgentOrchestrator(providers=[mock_p1, mock_p2])

    with pytest.raises(CodingAgentUnavailableError) as exc_info:
        orch.resolve_provider()

    err_msg = str(exc_info.value)
    assert "Mock Agent 1" in err_msg
    assert "Binary missing" in err_msg
    assert "Aether non scrive né modifica il codice direttamente" in err_msg


def test_orchestrator_delegate_and_collect(tmp_path):
    """Test task delegation and result collection with mock provider."""
    mock_provider = MagicMock(spec=BaseCodingAgentProvider)
    mock_provider.id = "mock_agent"
    mock_provider.name = "Mock Coding Agent"
    mock_provider.is_available.return_value = (True, "Ready")

    mock_exec = CodingTaskExecution(
        id="exec-123",
        task=CodingTask(instruction="Fix bug in parser", project_path=str(tmp_path)),
        provider_id="mock_agent",
        status=CodingExecutionStatus.COMPLETED,
        external_task_id="conv-mock-99",
        result=CodingResult(
            success=True,
            status=CodingExecutionStatus.COMPLETED,
            provider_id="mock_agent",
            summary="Fixed parser regex",
            diff="--- a/parser.py\n+++ b/parser.py",
            modified_files=["parser.py"],
        ),
    )
    mock_provider.start_task.return_value = mock_exec
    mock_provider.get_status.return_value = mock_exec
    mock_provider.collect_results.return_value = mock_exec.result

    orch = CodingAgentOrchestrator(providers=[mock_provider])
    task = CodingTask(instruction="Fix bug in parser", project_path=str(tmp_path))

    exec_res = orch.delegate_task(task)
    assert exec_res.id == "exec-123"
    assert exec_res.status == CodingExecutionStatus.COMPLETED
    assert exec_res.result is not None
    assert exec_res.result.summary == "Fixed parser regex"

    # Query status
    st = orch.get_status("exec-123")
    assert st.status == CodingExecutionStatus.COMPLETED

    # Collect results
    res = orch.collect_results("exec-123")
    assert res.modified_files == ["parser.py"]


# ---------------------------------------------------------------------------
# 4. ActionRegistry & ActionExecutor Integration Tests
# ---------------------------------------------------------------------------

def test_coding_actions_registered():
    registry = ActionRegistry()
    assert registry.get("coding.delegate") is not None
    assert registry.get("coding.status") is not None
    assert registry.get("coding.results") is not None
    assert registry.get("coding.list_providers") is not None

    coding_def = registry.get("coding.delegate")
    assert coding_def.requires_confirmation is True
    assert coding_def.tier.value == "act"


def test_action_executor_list_providers(tmp_path: Path):
    registry = ActionRegistry()
    store = ActionStore(str(tmp_path / "actions.db"))
    executor = ActionExecutor(registry=registry, store=store, project_path=str(tmp_path))

    exec_record = executor.execute(
        action_id="coding.list_providers",
        workspace_id="default",
        input_data={},
        auto_approve=True,
    )
    assert exec_record.status.value == "succeeded"
    providers = exec_record.output_data.get("providers", [])
    assert len(providers) >= 2
    ag = next(p for p in providers if p["id"] == "antigravity")
    assert ag["available"] is True


def test_action_executor_coding_delegate(tmp_path: Path):
    registry = ActionRegistry()
    store = ActionStore(str(tmp_path / "actions.db"))
    p_store = PersonalStore(str(tmp_path / "personal.db"))
    executor = ActionExecutor(registry=registry, store=store, personal_store=p_store, project_path=str(tmp_path))

    # Mock the orchestrator delegate call so we don't spawn external process in unit test
    mock_orch = MagicMock()
    mock_exec = CodingTaskExecution(
        id="exec-test",
        task=CodingTask(instruction="Add tests", project_path=str(tmp_path)),
        provider_id="antigravity",
        status=CodingExecutionStatus.COMPLETED,
        external_task_id="conv-live-001",
        result=CodingResult(
            success=True,
            status=CodingExecutionStatus.COMPLETED,
            provider_id="antigravity",
            summary="Unit tests created successfully",
            diff="--- /dev/null\n+++ b/test_new.py\n+def test_one(): pass",
            modified_files=["test_new.py"],
        ),
    )
    mock_orch.delegate_task.return_value = mock_exec

    with patch("aether.coding.orchestrator.get_coding_orchestrator", return_value=mock_orch), \
         patch("aether.core.execution.ExecutionBoundary.validate_authority", return_value=None):
        from aether.core.execution import ExecutionAuthority
        mock_auth = ExecutionAuthority(
            proposal_id="prop-test",
            proposal_version=1,
            workspace_id="default",
            granted_at="2026-10-09T00:00:00Z",
        )
        exec_record = executor.execute(
            action_id="coding.delegate",
            workspace_id="default",
            input_data={"instruction": "Add tests", "project_path": str(tmp_path)},
            auto_approve=True,
            authority=mock_auth,
        )

        # 1. Enforce safety gate: sensitive mutation requires explicit approval
        assert exec_record.status.value == "waiting_approval"

        # 2. Approve execution: dispatches and completes
        approved_record = executor.approve(exec_record.id, approver="user")

    assert approved_record.status.value == "succeeded"
    assert approved_record.output_data.get("provider_id") == "antigravity"
    assert approved_record.output_data.get("external_task_id") == "conv-live-001"
    assert approved_record.output_data.get("modified_files") == ["test_new.py"]
    assert "test_new.py" in approved_record.output_data.get("diff")


# ---------------------------------------------------------------------------
# 5. Personal Agent Intent Routing & Distinction Tests
# ---------------------------------------------------------------------------

def test_personal_service_intent_classification_coding(tmp_path: Path):
    store = PersonalStore(str(tmp_path / "personal.db"))
    service = PersonalAgentService(store=store)

    # 1. Implementation prompts -> coding.delegate (ACT tier)
    prompts_to_test = [
        "implementa la funzione di validazione token",
        "scrivi il codice per l'endpoint di ricerca",
        "crea codice per gestire i webhook di Stripe",
        "aggiungi test per il modulo OAuth",
        "fai il refactoring del parser json",
        "risolvi il bug nel controller di autenticazione",
        "delega ad Antigravity di creare il componente Navbar",
    ]

    for p in prompts_to_test:
        intent = service.classify_intent(p)
        assert intent.tier == IntentTier.ACT, f"Prompt '{p}' should be ACT tier"
        assert intent.action_id == "coding.delegate", f"Prompt '{p}' should route to coding.delegate"
        assert getattr(intent, "intent_type", None) == "coding"

    # 2. Explanations / read-only inquiries must NOT trigger coding.delegate
    expl_prompts = [
        "spiegami come funziona il codice in auth.py",
        "cosa fa il connettore Google Calendar?",
        "perché questo test fallisce?",
    ]
    for p in expl_prompts:
        intent = service.classify_intent(p)
        assert intent.action_id != "coding.delegate", f"Explanation prompt '{p}' must not trigger coding.delegate"

    # 3. Greetings & Casual conversation must remain clean
    conv_prompts = ["Ciao", "Grazie mille", "Buongiorno Aether"]
    for p in conv_prompts:
        intent = service.classify_intent(p)
        assert intent.tier == IntentTier.ANSWER
        assert getattr(intent, "intent_type", None) == "conversation"


def test_personal_service_process_prompt_coding_rendering(tmp_path: Path):
    """Verifies format of coding.delegate output when executed in PersonalService."""
    store = PersonalStore(str(tmp_path / "personal.db"))
    service = PersonalAgentService(store=store)

    # Mock runtime to simulate action execution result
    from aether.core.execution import ExecutionResult, ExecutionStatus
    mock_runtime_res = ExecutionResult(
        success=True,
        status=ExecutionStatus.COMPLETED,
        output="Done",
        metadata={
            "action_execution_id": "act-exec-123",
            "action_result": {
                "success": True,
                "status": "completed",
                "provider_id": "antigravity",
                "external_task_id": "conv-antigravity-999",
                "summary": "Implementato il middleware di autenticazione JWT.",
                "modified_files": ["src/auth/jwt.py", "tests/test_jwt.py"],
                "diff": "--- a/src/auth/jwt.py\n+++ b/src/auth/jwt.py\n+def verify_jwt(): pass",
            },
        },
    )

    with patch.object(service.runtime, "execute", return_value=mock_runtime_res):
        # Pass a mock authority so it proceeds directly to ACT execution without stopping at proposal
        from aether.core.execution import ExecutionAuthority
        mock_auth = ExecutionAuthority(
            proposal_id="prop-test",
            proposal_version=1,
            workspace_id="default",
            granted_at="2026-10-09T00:00:00Z",
        )

        resp = service.process_prompt(
            workspace_id="default",
            prompt="implementa il middleware di autenticazione JWT",
            authority=mock_auth,
        )

        assert "Delegated Coding Execution: `Google Antigravity`" in resp.content
        assert "conv-antigravity-999" in resp.content
        assert "src/auth/jwt.py" in resp.content
        assert "Diff Verificabile" in resp.content
        assert "verify_jwt" in resp.content


def test_orchestrator_path_safety(tmp_path: Path):
    """Enforces that delegating coding tasks to non-existent or system root directories fails closed."""
    orch = CodingAgentOrchestrator()

    # 1. Non-existent path
    task_nonexistent = CodingTask(instruction="Test", project_path="/nonexistent/path/xyz")
    with pytest.raises(ValueError) as exc1:
        orch.delegate_task(task_nonexistent)
    assert "does not exist" in str(exc1.value)

    # 2. System root path
    task_root = CodingTask(instruction="Test", project_path="/")
    with pytest.raises(ValueError) as exc2:
        orch.delegate_task(task_root)
    assert "protected system directory" in str(exc2.value)


def test_personal_service_coding_status_flow(tmp_path: Path):
    """Verifies that queries about coding task status route correctly to coding.status."""
    store = PersonalStore(str(tmp_path / "personal.db"))
    service = PersonalAgentService(store=store)

    intent = service.classify_intent("qual è lo stato del task di coding?")
    assert intent.tier == IntentTier.ANSWER
    assert intent.action_id == "coding.status"
    assert intent.intent_type == "coding_status"

    from aether.actions.models import ActionExecution, ActionExecutionStatus
    mock_record = ActionExecution(
        id="act-exec-status-1",
        action_id="coding.status",
        workspace_id="default",
        status=ActionExecutionStatus.SUCCEEDED,
        output_data={
            "status": "completed",
            "provider_id": "antigravity",
            "execution_id": "exec-status-123",
            "external_task_id": "conv-live-status-999",
            "instruction": "Implement OAuth refresh",
            "project_path": str(tmp_path),
        },
    )

    mock_executor = MagicMock()
    mock_executor.execute.return_value = mock_record
    service.action_executor = mock_executor

    resp = service.process_prompt(
        workspace_id="default",
        prompt="qual è lo stato del coding?",
    )
    assert "Stato Coding Agent: `Google Antigravity`" in resp.content
    assert "COMPLETED" in resp.content
    assert "conv-live-status-999" in resp.content


def test_persistent_settings_personal_store(tmp_path: Path):
    store = PersonalStore(str(tmp_path / "personal.db"))
    # Default is returned when not set
    assert store.get_setting("coding_preferred_provider", "antigravity") == "antigravity"
    # Set and persist
    store.set_setting("coding_preferred_provider", "claude_code")
    assert store.get_setting("coding_preferred_provider") == "claude_code"

    # Reopen database to verify durability
    store2 = PersonalStore(str(tmp_path / "personal.db"))
    assert store2.get_setting("coding_preferred_provider") == "claude_code"


def test_orchestrator_persistent_preferences(tmp_path: Path):
    store = PersonalStore(str(tmp_path / "personal.db"))
    mock_ws = MagicMock()
    mock_ws.personal_store = store

    orch = CodingAgentOrchestrator()
    # Default without setting
    assert orch.get_preferred_provider_id(mock_ws) == "antigravity"

    # Set preferred provider to codex
    orch.set_preferred_provider_id("codex", workspace=mock_ws)
    assert orch.get_preferred_provider_id(mock_ws) == "codex"
    assert store.get_setting("coding_preferred_provider") == "codex"

    # Invalid provider raises ValueError
    with pytest.raises(ValueError):
        orch.set_preferred_provider_id("unsupported_provider", workspace=mock_ws)


def test_orchestrator_fail_closed_preferred_unavailable(tmp_path: Path):
    """
    CRITICAL SAFETY GATE:
    When the preferred provider is unavailable (e.g. claude_code is unauthenticated,
    or codex is not installed), orchestrator MUST fail closed.
    It MUST NOT fall back silently to Antigravity, and MUST NOT fall back to LLM code generation.
    """
    store = PersonalStore(str(tmp_path / "personal.db"))
    store.set_setting("coding_preferred_provider", "claude_code")
    mock_ws = MagicMock()
    mock_ws.personal_store = store

    orch = CodingAgentOrchestrator()

    # Claude Code on host is unauthenticated
    with pytest.raises(CodingAgentUnavailableError) as exc_info:
        orch.resolve_provider(workspace=mock_ws)
    err_msg = str(exc_info.value)
    assert "claude_code" in err_msg or "Claude Code" in err_msg


def test_list_providers_status_diagnostics(tmp_path: Path):
    store = PersonalStore(str(tmp_path / "personal.db"))
    store.set_setting("coding_preferred_provider", "antigravity")
    mock_ws = MagicMock()
    mock_ws.personal_store = store

    orch = CodingAgentOrchestrator()
    with patch.object(CodexCodingProvider, "resolve_binary", return_value=None):  # hermetic: no codex CLI on this machine
        statuses = orch.list_providers_status(workspace=mock_ws)

    assert len(statuses) == 3
    p_map = {s.id: s for s in statuses}
    assert "antigravity" in p_map
    assert "claude_code" in p_map
    assert "codex" in p_map

    # Antigravity is preferred and available on host
    assert p_map["antigravity"].is_preferred is True
    assert p_map["antigravity"].installed is True
    assert p_map["antigravity"].available is True

    # Claude Code is installed but unauthenticated
    assert p_map["claude_code"].installed is True
    assert p_map["claude_code"].authenticated is False
    assert p_map["claude_code"].available is False
    assert len(p_map["claude_code"].missing_prerequisites) > 0

    # Codex has session but no binary
    assert p_map["codex"].installed is False
    assert p_map["codex"].available is False
    assert len(p_map["codex"].missing_prerequisites) > 0

