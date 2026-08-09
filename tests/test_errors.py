from aether.errors import (
    AetherError,
    PlanningError,
    ExecutionError,
    ProviderError,
    RuntimeSafetyError,
    DelegationError,
    AetherFatalError,
)
from aether.providers.errors import ProviderError as OldProviderError
from aether.core.safety import RuntimeSafetyError as OldRuntimeSafetyError
from aether.core.delegation import DelegationError as OldDelegationError

def test_error_hierarchy():
    # Base inheritance
    assert issubclass(PlanningError, AetherError)
    assert issubclass(ExecutionError, AetherError)
    assert issubclass(ProviderError, AetherError)
    assert issubclass(RuntimeSafetyError, AetherError)
    assert issubclass(DelegationError, ExecutionError)
    assert issubclass(AetherFatalError, AetherError)

def test_backward_compatibility():
    # Legacy aliases/subclasses should be instance of the unified ones
    try:
        raise OldProviderError("test", provider="mock")
    except ProviderError:
        pass  # Expected
        
    try:
        raise OldRuntimeSafetyError("test")
    except RuntimeSafetyError:
        pass  # Expected
        
    try:
        raise OldDelegationError("test")
    except DelegationError:
        pass  # Expected
