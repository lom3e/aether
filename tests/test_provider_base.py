"""Tests for AIProvider base fallbacks and backward compatibility."""

import pytest
from aether.providers.base import AIProvider
from aether.providers.types import Message, ProviderResponse

class CustomLegacyProvider(AIProvider):
    @property
    def capabilities(self):
        from aether.providers.capabilities import ProviderCapabilities
        return ProviderCapabilities()

    def generate(self, messages, tools=None, output_schema=None):
        return ProviderResponse(
            content="legacy sync response",
            model="legacy-model",
            finish_reason="stop",
        )

@pytest.mark.asyncio
async def test_base_agenerate_fallback():
    provider = CustomLegacyProvider()
    resp = await provider.agenerate([Message(role="user", content="hi")])
    assert resp.content == "legacy sync response"

def test_base_generate_stream_fallback():
    provider = CustomLegacyProvider()
    stream = list(provider.generate_stream([Message(role="user", content="hi")]))
    assert len(stream) == 1
    assert stream[0].text == "legacy sync response"
    assert stream[0].finish_reason == "stop"

@pytest.mark.asyncio
async def test_base_agenerate_stream_fallback():
    provider = CustomLegacyProvider()
    stream = []
    async for chunk in provider.agenerate_stream([Message(role="user", content="hi")]):
        stream.append(chunk)

    assert len(stream) == 1
    assert stream[0].text == "legacy sync response"
    assert stream[0].finish_reason == "stop"
