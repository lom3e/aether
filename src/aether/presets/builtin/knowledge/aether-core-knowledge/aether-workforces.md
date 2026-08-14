# AI Workforces in Aether

[Status: Implemented] [Release: Alpha]

## Concetto di Workforce

Una **Workforce** (forza lavoro di agenti AI) è una rete organizzata di agenti autonomi specializzati che collaborano per raggiungere obiettivi complessi.

A differenza di un singolo modello che tenta di svolgere ogni mansione:
- Ogni agente ha un ambito di competenza limitato e focalizzato.
- La cooperazione avviene tramite **deleghe topologiche dichiarate**.
- La conoscenza viene condivisa tramite la **KnowledgeBase** centralizzata del team.

---

## Topologia di Collaborazione e Delega

In Aether, le relazioni tra agenti sono definite a livello di configurazione:

```yaml
agents:
  - name: manager
    role: AI Workforce Coordinator
    relationships:
      - delegates_to: researcher
      - delegates_to: writer

  - name: researcher
    role: Knowledge Research Analyst
    skills:
      - search_knowledge

  - name: writer
    role: Content Specialist
```

### Come Funziona la Delega:
1. Quando `manager` dichiara `delegates_to: researcher`, il runtime Aether crea un `AgentTool` associato a `researcher` e lo registra nel `ToolRegistry` del manager con il nome `delegate_to_researcher`.
2. Il manager, analizzando una richiesta complessa dell'utente, riconosce di dover effettuare una ricerca documentale ed emette una `tool_call` verso `delegate_to_researcher` passando il sotto-task.
3. Il `Coordinator` esegue il sub-task tramite l'agente `researcher` in modo isolato.
4. L'output restituito da `researcher` viene consegnato al manager come risultato del tool.
5. Il manager può quindi delegare al `writer` per formattare la risposta finale o rispondere direttamente all'utente.

---

## Starter Pack Ufficiali Disponibili

1. **Aether Starter Workforce**:
   - `manager`: coordinamento ed elaborazione richieste.
   - `researcher`: ricerca approfondita nei documenti della knowledge base.
   - `writer`: redazione e formattazione dei deliverable.

2. **Aether Research Workforce**:
   - `research-manager`: pianificazione delle indagini.
   - `researcher`: estrazione fatti grezzi ed evidenze.
   - `analyst`: analisi comparativa e sintesi critica.
