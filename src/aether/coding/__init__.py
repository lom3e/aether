"""
Aether External Coding Agent Orchestration Package.
Coordinates Google Antigravity, Claude Code, and OpenAI Codex autonomous coding agents.
"""
from aether.coding.base import (
    BaseCodingAgentProvider,
    CodingAgentError,
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

__all__ = [
    "BaseCodingAgentProvider",
    "CodingAgentError",
    "CodingAgentUnavailableError",
    "CodingExecutionStatus",
    "CodingResult",
    "CodingTask",
    "CodingTaskExecution",
    "CodingAgentOrchestrator",
    "get_coding_orchestrator",
    "AntigravityCodingProvider",
    "ClaudeCodeCodingProvider",
    "CodexCodingProvider",
]
