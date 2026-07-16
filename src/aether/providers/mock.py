from aether.providers.base import AIProvider


class MockProvider(AIProvider):
    """
    Deterministic provider for tests and local development.
    """

    def generate(self, prompt: str) -> str:
        return f"Mock response: {prompt}"
