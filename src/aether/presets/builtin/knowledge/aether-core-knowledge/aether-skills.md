# Sistema di Skill in Aether (Aether Skills)

[Status: Implemented] [Release: Alpha]

## Concetto di Skill

Una **Skill** in Aether è un pacchetto modulare di capacità eseguibili che estende i tool disponibili per un agente.

Le skill possono essere caricate da directory locali (`skills/<nome-skill>/`) o da archivi impacchettati (`.zip`, `.tar.gz`, `.aether-skill`).

---

## Struttura di una Skill

```
my-skill/
  skill.yaml        # Manifest descrittivo con metadati e permessi
  __init__.py       # Punto di ingresso con funzione register(registry, context)
  tools.py          # Implementazione dei tool Python
```

### Manifest `skill.yaml`

```yaml
id: web-search-skill
name: Web Search
version: 1.0.0
description: Abilita ricerche sul web tramite API sicure.
author: Aether Community
permissions:
  - id: network_access
    description: Accesso HTTP per interrogare motori di ricerca.
    required: true
dependencies:
  - name: python-requests
    version: ">=2.28.0"
```

---

## Policy sui Permessi (`SkillPermissionPolicy`)

Le skill possono richiedere permessi specifici (es. `network_access`, `filesystem_read`, `filesystem_write`). Aether supporta 3 livelli di policy di sicurezza:
1. `allow_all`: autorizza automaticamente tutti i permessi dichiarati (modalità default in sviluppo).
2. `prompt_user`: genera un'interruzione HITL (`RequireApproval`) per richiedere conferma all'utente prima dell'attivazione.
3. `deny`: blocca l'accesso alle risorse sensibili.
