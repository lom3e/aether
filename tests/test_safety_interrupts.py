import time
import pytest
from aether.core.safety import RuntimeSafetyPolicy, Deadline

def test_safety_policy_pause_unpause():
    policy = RuntimeSafetyPolicy(deadline=Deadline.from_timeout(0.5))

    # Simulate execution time
    time.sleep(0.1)

    policy.pause()
    # Simulate human thinking for a long time
    time.sleep(0.5)

    policy.unpause()

    # We should still have time left, since 0.5s was paused
    policy.check_deadline()
    assert policy.deadline.remaining > 0

def test_safety_policy_without_pause_expires():
    policy = RuntimeSafetyPolicy(deadline=Deadline.from_timeout(0.5))

    time.sleep(0.6)

    with pytest.raises(Exception):
        policy.check_deadline()
