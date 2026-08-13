"""
Aether v1.3.1 P1.3.2 Demo: Persistent Conversation Memory
"""
import sys
import shutil
from pathlib import Path

from aether.team.config import AgentConfig, TeamConfig
from aether.team.team import Team
from aether.agents.identity import AgentStore
from aether.providers.mock import MockProvider
from aether.providers.types import ProviderResponse, ProviderConfig
from aether.core.execution import Message


class SmartMockProvider(MockProvider):
    """
    Mock deterministico che controlla la memoria: 
    se 'Apollo' è nel prompt, controlla i messaggi precedenti.
    Se trova il budget, risponde col budget, altrimenti dice 'Non lo so'.
    Se gli viene detto il budget, risponde 'Memorizzato'.
    """
    def generate(self, messages: list[Message], tools=None, output_schema=None) -> ProviderResponse:
        user_msg = messages[-1].content
        
        if "budget of" in user_msg:
            content = "✓ Memorizzato."
        elif "budget" in user_msg.lower():
            # Cerca nella history se ci è stato detto
            known_budget = None
            for m in messages:
                if "budget of €50,000" in m.content:
                    known_budget = "€50,000"
            
            if known_budget:
                content = f"Apollo's budget is {known_budget}."
            else:
                content = "I don't know the budget."
        else:
            content = "Hello."

        return ProviderResponse(
            content=content,
            model="smart-mock",
            finish_reason="stop",
            message=Message(role="assistant", content=content)
        )


def main():
    print("═══════════════════════════════════════════")
    print("Aether — Persistent Agent Memory Demo")
    print("═══════════════════════════════════════════\n")

    db_dir = Path("memory_demo_db")
    if db_dir.exists():
        shutil.rmtree(db_dir)
    db_dir.mkdir()

    identity_db = str(db_dir / "identities.db")
    conv_db = str(db_dir / "conversations.db")

    config = TeamConfig(
        agents=[
            AgentConfig(name="researcher", role="researcher")
        ]
    )

    # ---------------------------------------------------------
    # PROCESSO 1
    # ---------------------------------------------------------
    print("PROCESS 1\n")
    
    agent_store1 = AgentStore(identity_db)
    team1 = Team(config, provider=SmartMockProvider(), agent_store=agent_store1, conversation_db_path=conv_db)
    agent1 = team1.get_agent("researcher")
    
    agent_id1 = agent1.id
    print(f"Agent: {agent1.name}")
    print(f"Identity: {agent_id1}")
    
    user_msg_1 = "Apollo has a budget of €50,000."
    print(f"User: {user_msg_1}")
    
    # Eseguiamo il task su una sessione deterministica ("demo_session")
    # Nota: agent.run() userebbe task UUID casuale, noi forziamo la memoria simulando il context manager
    from aether.core.execution import AgentContext, Task
    ctx1 = AgentContext(agent_name=agent1.name, task=Task(id="demo_session", instruction="dummy"), messages=[])
    ctx1.messages.append(Message(role="user", content=user_msg_1))
    
    response1 = agent1.provider.generate(ctx1.messages)
    ctx1.messages.append(response1.message)
    print(f"Agent: {response1.content}")
    
    # Salviamo esplicitamente
    agent1.memory_manager.persist_context(ctx1)
    print("✓ Memory persisted\n")
    
    print("[Process terminated]\n")
    
    # Eliminiamo le istanze per simulare chiusura
    del agent1
    del team1
    del agent_store1

    # ---------------------------------------------------------
    # PROCESSO 2
    # ---------------------------------------------------------
    print("PROCESS 2\n")
    
    agent_store2 = AgentStore(identity_db)
    team2 = Team(config, provider=SmartMockProvider(), agent_store=agent_store2, conversation_db_path=conv_db)
    agent2 = team2.get_agent("researcher")
    
    print(f"Agent: {agent2.name}")
    print(f"Identity: {agent2.id}")
    
    if agent2.id == agent_id1:
        print("✓ Same identity restored")
    else:
        print("✗ IDENTITY MISMATCH!")
        sys.exit(1)
        
    ctx2 = AgentContext(agent_name=agent2.name, task=Task(id="demo_session", instruction="dummy"), messages=[])
    agent2.memory_manager.load_context(ctx2)
    
    if len(ctx2.messages) > 0:
        print("✓ Previous conversation restored\n")
    else:
        print("✗ MEMORY LOST!\n")
        sys.exit(1)
        
    user_msg_2 = "What is Apollo's budget?"
    print(f"User: {user_msg_2}")
    
    ctx2.messages.append(Message(role="user", content=user_msg_2))
    response2 = agent2.provider.generate(ctx2.messages)
    print(f"Agent: {response2.content}")
    
    if "€50,000" in response2.content:
        print("\n✓ PERSISTENCE VERIFIED")
    else:
        print("\n✗ PERSISTENCE FAILED")
        sys.exit(1)

    # Pulizia
    if db_dir.exists():
        shutil.rmtree(db_dir)

if __name__ == "__main__":
    main()
