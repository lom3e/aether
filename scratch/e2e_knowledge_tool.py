"""
E2E Test per P1.1: Knowledge as a Tool.
Verifica il flusso completo Agent -> search_knowledge -> KnowledgeStore -> Agent
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from aether.core.execution import Message, ToolCall
from aether.knowledge.chunk import KnowledgeChunk
from aether.knowledge.store import KnowledgeStore
from aether.providers.base import AIProvider
from aether.providers.capabilities import ProviderCapabilities
from aether.providers.types import ProviderConfig, ProviderResponse
from aether.team.config import AgentConfig, TeamConfig
from aether.team.team import Team


class KnowledgeSeekerProvider(AIProvider):
    """
    Mock provider that always calls search_knowledge on the first turn,
    then returns the tool result on the second turn.
    """
    
    def __init__(self, target_query: str) -> None:
        super().__init__()
        self.target_query = target_query

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True)

    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        
        # Count tool results to determine state
        has_tool_result = any(m.role == "tool" for m in messages)
        
        if not has_tool_result:
            # Turn 1: Request tool call
            msg = Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(
                        call_id="call_abc123",
                        tool_name="search_knowledge",
                        arguments={"query": self.target_query}
                    )
                ]
            )
            return ProviderResponse(
                content="",
                model="test-model",
                finish_reason="tool_calls",
                message=msg
            )
        else:
            # Turn 2: Read tool result and answer
            tool_msg = next(m for m in reversed(messages) if m.role == "tool")
            content = f"Ho letto dalla knowledge base: {tool_msg.content}"
            msg = Message(role="assistant", content=content)
            return ProviderResponse(
                content=content,
                model="test-model",
                finish_reason="stop",
                message=msg
            )


def run_e2e() -> None:
    print("Setting up Knowledge E2E test...")
    
    # 1. Crea KnowledgeStore e inserisci documenti
    store = KnowledgeStore(":memory:")
    store.add(KnowledgeChunk(
        content="Project Apollo requires a budget of $50,000 and focuses on lunar exploration.",
        source="budget.md",
        metadata={"category": "finance"}
    ))
    
    # 2. Crea Team
    config = TeamConfig(
        agents=[AgentConfig(name="researcher", role="researcher")]
    )
    
    # Provider custom che invoca esplicitamente il tool
    provider = KnowledgeSeekerProvider(target_query="Project Apollo budget")
    
    team = Team(config, provider=provider, knowledge_store=store)
    
    # 3. Verifica registrazione (un Agent abbia accesso a search_knowledge)
    agent = team.get_agent("researcher")
    assert "search_knowledge" in agent.tools, "Tool non registrato nell'agente"
    print("✓ Tool registrato con successo nell'agente")
    
    # 4. Esegui il task
    print("\nRunning task via Team...")
    result = team.run("What is the budget for Project Apollo?")
    
    # 5. Verifica che il risultato includa la stringa elaborata dal tool
    print("\n✓ Task completato")
    print(f"Result:\n{result.output}")
    print(f"Success: {result.success}")
    
    assert result.success is True
    assert "Project Apollo requires a budget of $50,000" in result.output, "Il risultato del tool non è arrivato al modello"
    assert "budget.md" in result.output, "La source non è stata restituita dal tool"
    
    print("\nE2E completato con successo!")


if __name__ == "__main__":
    run_e2e()
