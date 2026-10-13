"""
Known defect, documented as a strict xfail (it turns into a failure the day it is fixed, so the marker must then go):
constructing an ``OllamaProvider`` probes the local server (``GET /api/tags``) and may choose an installed model. A
provider object must be creatable without any I/O (resolution of a configured provider contacts nothing).

The probe is refused by the network guard, so no real server is contacted.
"""
from __future__ import annotations

import pytest

from aether.providers.ollama import OllamaProvider
from aether.providers.types import ProviderConfig


@pytest.mark.xfail(
    strict=True,
    reason="OllamaProvider.__init__ probes /api/tags (and may select an installed model implicitly): open finding",
)
@pytest.mark.network_block_expected  # the refused probe is the very thing observed here
def test_constructing_an_ollama_provider_does_not_contact_the_server(network_attempts):
    OllamaProvider(ProviderConfig(model="explicit-model"))
    assert network_attempts == [], f"constructor opened connections: {network_attempts}"
