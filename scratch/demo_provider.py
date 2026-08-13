"""
Aether v1.3.1 P1.3.1 Demo: Per-Agent Provider Resolution
"""
import sys

from aether.team.config import AgentConfig, TeamConfig
from aether.team.team import Team
from aether.providers.base import AIProvider
from aether.providers.capabilities import ProviderCapabilities
from aether.providers.types import ProviderConfig, ProviderResponse
from aether.core.execution import Message


class DemoMockProvider(AIProvider):
    """
    Mock deterministico che mostra chiaramente il proprio nome e modello
    per dimostrare la risoluzione indipendente.
    """
    def __init__(self, config: ProviderConfig | None = None, name: str = "mock"):
        super().__init__(config)
        self.name = name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def generate(
        self,
        messages: list[Message],
        tools=None,
        output_schema=None,
    ) -> ProviderResponse:
        model = self.config.model if self.config else "default"
        content = f"Risposta generata da Provider: '{self.name}' con Modello: '{model}'"
        return ProviderResponse(
            content=content,
            model=model,
            finish_reason="stop",
            message=Message(role="assistant", content=content)
        )


def main():
    print("=" * 60)
    print("Aether P1.3.1 Demo: Per-Agent Provider & Model Resolution")
    print("=" * 60)

    # 1. Configurazione YAML fittizia, equivalente a:
    # team:
    #   provider: "mock-team"
    #   model: "team-default-model"
    # agents:
    #   - name: manager
    #     provider: "mock-manager"
    #     model: "manager-model"
    #   - name: researcher
    #     provider: "mock-researcher"
    #     model: "researcher-model"
    #   - name: default_worker
    #     (eredita dal team)
    
    config = TeamConfig(
        default_provider="mock-team",
        default_model="team-default-model",
        agents=[
            AgentConfig(
                name="manager",
                role="coordinator",
                provider="mock-manager",
                model="manager-model"
            ),
            AgentConfig(
                name="researcher",
                role="researcher",
                provider="mock-researcher",
                model="researcher-model"
            ),
            AgentConfig(
                name="default_worker",
                role="worker"
            )
        ]
    )

    print("\n[System] Inizializzazione Team...")
    team = Team(config)

    from aether.providers.manager import ProviderManager
    # Per assicurarci che usi il nostro ProviderManager popolato:
    team._provider_manager = ProviderManager()
    
    def make_mock(name):
        return type(f"Mock{name}", (DemoMockProvider,), {
            "__init__": lambda self, config=None: DemoMockProvider.__init__(self, config, name=name)
        })
    team._provider_manager.register("mock-team", make_mock("mock-team"))
    team._provider_manager.register("mock-manager", make_mock("mock-manager"))
    team._provider_manager.register("mock-researcher", make_mock("mock-researcher"))
    
    # In una app vera il ProviderManager andrebbe in Dependency Injection, 
    # per la demo forziamo la risoluzione sui nostri mock.
    for agent_config in config.agents:
        agent = team.get_agent(agent_config.name)
        agent.provider = team._provider_for(agent_config)

    print("\n" + "-" * 60)
    for agent_name in ["manager", "researcher", "default_worker"]:
        agent = team.get_agent(agent_name)
        print(f"Agent: {agent_name.upper()}")
        
        # Simuliamo un'esecuzione manuale
        result = agent.provider.generate([])
        print(f"  -> {result.content}")
        print("-" * 60)

    print("\n✓ Demo completata con successo!\n" + "=" * 60)


if __name__ == "__main__":
    main()
