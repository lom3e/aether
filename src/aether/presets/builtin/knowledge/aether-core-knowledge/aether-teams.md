# Team e Configurazione in Aether (Aether Teams)

[Status: Implemented] [Release: Alpha]

## Definizione di un Team (`team.yaml`)

Un **Team** rappresenta l'istanza eseguibile di una Workforce in un determinato workspace. I team risiedono nella directory `teams/` del workspace (es. `teams/default.yaml`, `teams/starter-workforce.yaml`).

### Schema del File `team.yaml`

```yaml
team:
  name: starter-workforce
  provider: ollama             # provider predefinito (ollama, openai, anthropic, gemini)
  model: qwen3.5:9b            # modello predefinito
  knowledge_path: ../knowledge/ # percorso opzionale della knowledge base

agents:
  - name: manager
    role: AI Workforce Coordinator
    instructions: >
      You coordinate the workforce. You receive tasks from the user, analyze requirements,
      delegate document research to researcher and writing to writer, then deliver the final answer.
    provider: ollama           # override provider per agente (opzionale)
    model: qwen3.5:9b          # override modello per agente (opzionale)
    skills: []                 # skill assegnate all'agente
    relationships:
      - delegates_to: researcher
      - delegates_to: writer

  - name: researcher
    role: Knowledge Research Analyst
    instructions: >
      You search the knowledge base using the search_knowledge tool and return structured findings.
    skills:
      - search_knowledge
```

---

## Risoluzione dell'Entry Agent

Quando il metodo `team.run(instruction)` viene invocato:
1. Il runtime cerca il primo agente che dichiara relazioni `delegates_to` (tipicamente il `manager`).
2. Se nessun agente ha deleghe, seleziona il primo agente elencato nel file YAML.
3. Il task viene inoltrato all'entry agent con un identificatore di sessione univoco per preservare il contesto di conversazione.
