import pytest
import time
from aether.core.safety import RuntimeSafetyPolicy, RuntimeSafetyError, Deadline

def test_runtime_safety_max_cycles():
    policy = RuntimeSafetyPolicy(max_cognitive_cycles=2)
    policy.before_cycle()
    policy.after_cycle()
    policy.before_cycle()
    policy.after_cycle()

    with pytest.raises(RuntimeSafetyError, match="Maximum cognitive cycles"):
        policy.before_cycle()

def test_runtime_safety_max_replans():
    policy = RuntimeSafetyPolicy(max_replans=1)
    policy.before_replan()

    with pytest.raises(RuntimeSafetyError, match="Maximum replan attempts"):
        policy.before_replan()

def test_runtime_safety_reset_replans():
    policy = RuntimeSafetyPolicy(max_replans=1)
    policy.before_replan()
    policy.reset_replans()
    # Should not raise
    policy.before_replan()

def test_runtime_safety_deadline():
    # Deadline in the past
    deadline = Deadline(timestamp=time.time() - 10)
    policy = RuntimeSafetyPolicy(deadline=deadline)

    with pytest.raises(RuntimeSafetyError, match="Absolute deadline exceeded"):
        policy.check_deadline()

    with pytest.raises(RuntimeSafetyError, match="Absolute deadline exceeded"):
        policy.before_cycle()
