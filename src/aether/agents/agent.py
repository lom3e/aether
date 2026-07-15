from aether.providers.base import AIProvider


class Agent:
    """
    Base Aether Agent.

    An agent represents a digital worker
    with identity, responsibilities and capabilities.
    """

    def __init__(
        self,
        name: str,
        role: str = "assistant",
        provider: AIProvider | None = None
    ):
        self.name = name
        self.role = role
        self.provider = provider

    def run(self, task: str) -> str:
        """
        Execute a task.
        """

        if not self.provider:
            return f"{self.name} has no AI provider configured."

        return self.provider.generate(task)