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
