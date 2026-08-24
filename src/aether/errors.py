"""
Aether unified error model.

This module defines the public exception hierarchy for the Aether framework.
"""

class AetherError(Exception):
    """Base class for all Aether exceptions."""
    pass

class PlanningError(AetherError):
    """Raised when the cognitive layer (Planner) fails to generate or evaluate a plan."""
    pass

class ExecutionError(AetherError):
    """Raised when the Execution Engine fails to execute a task or tool."""
    pass

class ProviderError(AetherError):
    """Raised when an AI Provider encounters an error."""
    pass

class RuntimeSafetyError(AetherError):
    """Raised when a Runtime Safety Policy constraint is violated (e.g. max cycles)."""
    pass

class DelegationError(ExecutionError):
    """Raised when an agent delegation fails."""
    pass

class AetherFatalError(AetherError):
    """Raised for unrecoverable framework errors."""
    pass


# ── Security & Filesystem Errors ───────────────────────────────────────────

class SecurityError(AetherError):
    """Base class for all security-related errors."""
    pass


class SecurityBoundaryViolation(SecurityError):
    """Raised when a path violates the sandbox boundary (e.g. traversal attempt, symlink escape)."""
    pass


class SensitivePathAccessDenied(SecurityError):
    """Raised when accessing a protected or sensitive file or directory (e.g. .env, .git, credentials, keys)."""
    pass


class FilesystemToolError(ExecutionError):
    """Base class for filesystem tool execution errors."""
    pass


class FileNotFoundToolError(FilesystemToolError):
    """Raised when a requested file does not exist in the sandbox."""
    pass


class DirectoryNotFoundToolError(FilesystemToolError):
    """Raised when a requested directory does not exist in the sandbox."""
    pass


# ── Skill Errors ────────────────────────────────────────────────────────────

class SkillError(AetherError):
    """Base class for all Skill-related errors."""
    pass


class SkillManifestNotFoundError(SkillError):
    """Raised when a skill.yaml manifest cannot be found in the skill source."""
    pass


class InvalidSkillManifestError(SkillError):
    """Raised when a skill.yaml manifest is malformed or fails validation."""
    pass


class InvalidSkillPackageError(SkillError):
    """Raised when a skill archive is corrupt, invalid, or has an unsupported format."""
    pass


class SkillPermissionDeniedError(SkillError):
    """Raised when a skill requests a permission that the active policy does not allow."""
    pass


class SkillToolBindingError(SkillError):
    """Raised when a skill's register() function fails to bind tools correctly."""
    pass
