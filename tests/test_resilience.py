import pytest
from unittest.mock import MagicMock
import urllib.error
import time

from aether.providers.resilience import ResilientProvider
from aether.providers.base import AIProvider
from aether.providers.errors import TimeoutError
from aether.providers.types import ProviderResponse

class MockProvider(AIProvider):
    def __init__(self):
        self.mock = MagicMock()
        self.calls = 0

    @property
    def capabilities(self):
        return None

    def generate(self, messages, tools=None, output_schema=None):
        self.calls += 1
        return self.mock(messages, tools, output_schema)

def test_resilience_success_after_timeout():
    provider = MockProvider()

    # 1st call fails with timeout, 2nd call succeeds
    res_obj = ProviderResponse(content="success", model="test")
    provider.mock.side_effect = [TimeoutError("timeout"), res_obj]

    resilient = ResilientProvider(provider, max_retries=3, base_backoff=0.01)

    result = resilient.generate([{"role": "user", "content": "hi"}])
    assert result.content == "success"
    assert provider.calls == 2

import io

def test_resilience_429():
    provider = MockProvider()

    # HTTP 429
    exc = urllib.error.HTTPError(url="", code=429, msg="Too Many Requests", hdrs={}, fp=io.BytesIO(b""))

    res_obj = ProviderResponse(content="success", model="test")
    provider.mock.side_effect = [exc, res_obj]

    resilient = ResilientProvider(provider, max_retries=3, base_backoff=0.01)

    result = resilient.generate([{"role": "user", "content": "hi"}])
    assert result.content == "success"
    assert provider.calls == 2
    exc.close()

def test_resilience_fail_immediately_on_403():
    provider = MockProvider()

    # HTTP 403
    exc = urllib.error.HTTPError(url="", code=403, msg="Forbidden", hdrs={}, fp=io.BytesIO(b""))

    provider.mock.side_effect = exc

    resilient = ResilientProvider(provider, max_retries=3, base_backoff=0.01)

    with pytest.raises(urllib.error.HTTPError):
        resilient.generate([{"role": "user", "content": "hi"}])

    assert provider.calls == 1  # No retries
    exc.close()


def test_circuit_breaker_trips_and_recovers():
    from aether.providers.resilience import CircuitBreaker, CircuitBreakerOpenError, CircuitState

    provider = MockProvider()
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.2, provider_name="test_prov")
    resilient = ResilientProvider(provider, max_retries=1, base_backoff=0.001, circuit_breaker=cb)

    provider.mock.side_effect = TimeoutError("upstream timeout")

    # Call 1 fails
    with pytest.raises(TimeoutError):
        resilient.generate([{"role": "user", "content": "1"}])
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1

    # Call 2 fails -> trips circuit breaker to OPEN
    with pytest.raises(TimeoutError):
        resilient.generate([{"role": "user", "content": "2"}])
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 2

    # Call 3 is immediately rejected by circuit breaker without reaching provider!
    calls_before = provider.calls
    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        resilient.generate([{"role": "user", "content": "3"}])
    assert "Circuit breaker is OPEN" in str(exc_info.value)
    assert provider.calls == calls_before  # No upstream call made!

    # Wait for recovery timeout to transition to HALF_OPEN
    time.sleep(0.25)
    provider.mock.side_effect = None
    provider.mock.return_value = ProviderResponse(content="recovered", model="test")

    # Call 4 in HALF_OPEN succeeds -> resets circuit to CLOSED
    res = resilient.generate([{"role": "user", "content": "4"}])
    assert res.content == "recovered"
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
