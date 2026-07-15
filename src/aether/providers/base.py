from abc import ABC, abstractmethod


class AIProvider(ABC):
    """
    Base interface for AI model providers.

    Providers are responsible for communicating
    with external AI models.
    """

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """
        Generate a response from an AI model.

        Args:
            prompt: User input

        Returns:
            Generated response
        """
        pass