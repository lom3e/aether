"""
E2E Test per P1.2: Agent Relationships + Delegation
Verifica il flusso completo Manager -> Researcher -> Knowledge -> Manager
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
from aether.team.config import AgentConfig, Relationship, TeamConfig
from aether.team.team import Team
from aether.team.feed import ActivityFeed
from aether.coordination.events import EventEmitter


class E2EProvider(AIProvider):
    """
    Mock deterministico. 
    Se è il Manager: delega al Researcher, e quando riceve la risposta conclude.
    Se è il Researcher: usa search_knowledge, poi risponde al Manager.
    """
    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True)

    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        output_schema: Any | None = None,
    ) -> ProviderResponse:
        
        # Check system prompt / agent role to know who is calling
        system_msg = next((m for m in messages if m.role == "system"), None)
        is_manager = system_msg and "coordinator" in system_msg.content.lower()
        
        has_tool_result = any(m.role == "tool" for m in messages)
        
        if is_manager:
            if not has_tool_result:
                # Turn 1: Delegate to Researcher
                msg = Message(
                    role="assistant",
                    content="I need to ask the researcher.",
                    tool_calls=[
                        ToolCall(
                            call_id="call_mgr1",
                            tool_name="researcher",
                            arguments={"input_data": "Project Apollo budget"}
                        )
                    ]
                )
                return ProviderResponse(content="", model="mock", finish_reason="tool_calls", message=msg)
            else:
                # Turn 2: Got result from researcher
                tool_msg = next(m for m in reversed(messages) if m.role == "tool")
                content = f"Final Answer: {tool_msg.content}"
                msg = Message(role="assistant", content=content)
                return ProviderResponse(content=content, model="mock", finish_reason="stop", message=msg)
                
        else: # Researcher
            if not has_tool_result:
                # Turn 1: Search Knowledge
                msg = Message(
                    role="assistant",
                    content="Searching knowledge...",
                    tool_calls=[
                        ToolCall(
                            call_id="call_res1",
                            tool_name="search_knowledge",
                            arguments={"query": "Project Apollo budget"}
                        )
                    ]
                )
                return ProviderResponse(content="", model="mock", finish_reason="tool_calls", message=msg)
            else:
                # Turn 2: Return result to manager
                tool_msg = next(m for m in reversed(messages) if m.role == "tool")
                content = f"Found in docs: {tool_msg.content}"
                msg = Message(role="assistant", content=content)
                return ProviderResponse(content=content, model="mock", finish_reason="stop", message=msg)


def run_e2e() -> None:
    print("Setting up Relationships E2E test...\n")
    
    # 1. KnowledgeStore
    store = KnowledgeStore(":memory:")
    store.add(KnowledgeChunk(
        content="Project Apollo requires a budget of $50,000 and focuses on lunar exploration.",
        source="budget.md"
    ))
    
    # 2. Config con Relationships
    config = TeamConfig(
        agents=[
            AgentConfig(
                name="manager", 
                role="coordinator",
                relationships=[
                    Relationship(type="delegates_to", target="researcher")
                ]
            ),
            AgentConfig(
                name="researcher", 
                role="researcher",
                relationships=[
                    Relationship(type="reports_to", target="manager")
                ]
            )
        ]
    )
    
    provider = E2EProvider()
    team = Team(config, provider=provider, knowledge_store=store)
    
    print("\nStarting execution...")
    result = team.run("What is the budget for Project Apollo?")
    
    print(f"\nFinal Success: {result.success}")
    if not result.success:
        print(f"Error: {result.error}")
    print(f"Final Output: {result.output}")
    
    assert result.success is True
    assert "$50,000" in result.output, "Il budget non è arrivato alla risposta finale"
    print("✓ E2E completed successfully!")

if __name__ == "__main__":
    run_e2e()
