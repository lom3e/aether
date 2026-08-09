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
