import os
from unittest import mock

import pytest

from aether.providers.errors import AuthenticationError
from aether.providers.types import ProviderConfig


def test_openai_provider_env_key():
    from aether.providers.openai_provider import OpenAIProvider, _HAS_OPENAI

    if not _HAS_OPENAI:
        pytest.skip("openai not installed")

    # 1. Explicit key
    provider = OpenAIProvider(ProviderConfig(api_key="explicit_key"))
    assert provider._client.api_key == "explicit_key"

    # 2. Env key
    with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "env_key"}, clear=True):
        provider = OpenAIProvider(ProviderConfig())
        assert provider._client.api_key == "env_key"

    # 3. Missing key
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(AuthenticationError, match="No API key provided"):
            OpenAIProvider(ProviderConfig())


def test_anthropic_provider_env_key():
    from aether.providers.anthropic_provider import AnthropicProvider, _HAS_ANTHROPIC

    if not _HAS_ANTHROPIC:
        pytest.skip("anthropic not installed")

    # 1. Explicit key
    provider = AnthropicProvider(ProviderConfig(api_key="explicit_key"))
    assert provider._client.api_key == "explicit_key"

    # 2. Env key
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env_key"}, clear=True):
        provider = AnthropicProvider(ProviderConfig())
        assert provider._client.api_key == "env_key"

    # 3. Missing key
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(AuthenticationError, match="No API key provided"):
            AnthropicProvider(ProviderConfig())


def test_gemini_provider_env_key():
    from aether.providers.gemini_provider import GeminiProvider, _HAS_GEMINI

    if not _HAS_GEMINI:
        pytest.skip("google-genai not installed")

    # 1. Explicit key
    provider = GeminiProvider(ProviderConfig(api_key="explicit_key"))
    assert provider._client.api_key == "explicit_key"

    # 2. Env key GEMINI_API_KEY
    with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "env_key"}, clear=True):
        provider = GeminiProvider(ProviderConfig())
        assert provider._client.api_key == "env_key"

    # 3. Env key GOOGLE_API_KEY
    with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "google_env_key"}, clear=True):
        provider = GeminiProvider(ProviderConfig())
        assert provider._client.api_key == "google_env_key"

    # 4. Missing key
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(AuthenticationError, match="No API key provided"):
            GeminiProvider(ProviderConfig())
