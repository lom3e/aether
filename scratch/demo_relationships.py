"""
Aether v1.3.1 P1.2 Demo: Relationships and Delegation
"""
import os
import sys

from aether.team.config import AgentConfig, Relationship, TeamConfig
from aether.team.team import Team
from aether.knowledge.chunk import KnowledgeChunk
from aether.knowledge.store import KnowledgeStore

def main():
    print("=" * 60)
    print("Aether P1.2 Demo: Delegation & Agent Relationships")
    print("=" * 60)
    
    # Optional: check if ANTHROPIC_API_KEY or OPENAI_API_KEY is present
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")):
        print("\n[WARNING] Nessuna API key trovata (ANTHROPIC_API_KEY / OPENAI_API_KEY).")
        print("Imposta una variabile d'ambiente per eseguire la demo reale.")
        return

    # 1. Configurazione del Team con Relationships formali
    config = TeamConfig(
        agents=[
            AgentConfig(
                name="manager", 
                role="coordinator",
                system_prompt="""Sei il Project Manager. Il tuo compito è coordinare la ricerca.
Se hai bisogno di informazioni sui costi o sui progetti passati, delega sempre la ricerca al tuo 'researcher'.
Usa le informazioni che il researcher ti fornisce per rispondere in modo completo all'utente.
Se non sei in grado di usare il researcher, rispondi con un errore.
""",
                relationships=[
                    Relationship(type="delegates_to", target="researcher")
                ]
            ),
            AgentConfig(
                name="researcher", 
                role="researcher",
                system_prompt="""Sei l'Analista Ricercatore. 
Hai accesso alla Knowledge base aziendale tramite lo strumento search_knowledge.
Usa lo strumento per rispondere alle richieste che ti vengono delegate. 
Non inventare informazioni: se non trovi dati, dillo chiaramente.
""",
                relationships=[
                    Relationship(type="reports_to", target="manager")
                ]
            )
        ]
    )
    
    # 2. Creazione della Knowledge (simuliamo un DB esistente)
    print("\n[System] Inizializzazione KnowledgeStore...")
    store = KnowledgeStore(":memory:")
    store.add(KnowledgeChunk(
        content="Il budget totale per il progetto Phoenix nel Q4 è di 150.000 euro.",
        source="doc_q4_planning.md"
    ))
    store.add(KnowledgeChunk(
        content="Il team assegnato al progetto Phoenix è composto da: Alice, Bob, e Charlie.",
        source="team_allocation.md"
    ))
    
    # 3. Inizializzazione Team
    print("[System] Inizializzazione Team...")
    team = Team(config, knowledge_store=store)
    
    print("\n[System] Esecuzione Task: 'Qual è il budget del progetto Phoenix e chi ci lavora?'\n")
    print("-" * 60)
    
    # 4. Esecuzione task con l'output nell'ActivityFeed
    result = team.run("Qual è il budget del progetto Phoenix e chi ci lavora? Devo preparare il report.")
    
    print("-" * 60)
    print(f"\nRisultato Finale (Success: {result.success}):\n")
    print(result.output)
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
