from aether.agents.agent import Agent
from aether.providers.base import AIProvider


class DemoProvider(AIProvider):
    """
    Simple provider used for the first Aether demonstration.
    """

    def generate(self, prompt: str) -> str:
        return f"Aether received: {prompt}"


def main():
    provider = DemoProvider()

    agent = Agent(
        name="Aether Assistant",
        role="demo agent",
        provider=provider
    )

    response = agent.run(
        "Explain what you are"
    )

    print(response)


if __name__ == "__main__":
    main()