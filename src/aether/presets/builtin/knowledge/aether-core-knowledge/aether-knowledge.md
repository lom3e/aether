# Knowledge Base & Retrieval in Aether (Aether Knowledge)

[Status: Implemented] [Release: Alpha]

## Architettura della Knowledge Base

La Knowledge Base di Aether (`KnowledgeStore`) è un archivio documentale locale basato su **SQLite** progettato per essere leggero, affidabile e privo di dipendenze pesanti.

---

## Separazione Netta: System Knowledge vs Workspace Knowledge

Per evitare contaminazioni tra i documenti aziendali privati dell'utente e la documentazione del sistema, Aether distingue due ambiti di conoscenza:

1. **System Knowledge (`scope: system`)**:
   - Contiene i knowledge pack ufficiali preinstallati di Aether (es. `aether-core-knowledge`).
   - È in sola lettura per la UI ordinaria.
   - Fornisce a tutti gli agenti (in particolare a `researcher` e `manager`) la comprensione esatta delle capacità e dei componenti della piattaforma.

2. **Workspace Knowledge (`scope: workspace`)**:
   - Contiene i documenti, file PDF, file Markdown, file TXT e CSV caricati dall'utente per i propri task aziendali.
   - È completamente controllata dall'utente (può aggiungere, aggiornare o cancellare file in qualsiasi momento).

---

## Ingestione e Chunking dei Documenti (`DocumentIngester`)

1. **Formati Supportati**: `.txt`, `.md`, `.markdown`, `.pdf`, `.csv`, `.py`, `.yaml`, `.json`.
2. **Chunking**:
   - I documenti vengono suddivisi in finestre sovrapposte (default: 800 caratteri con 100 caratteri di overlap).
   - Il parser privilegia i confini naturali di paragrafo (`\n\n`) o fine frase (`. `, `! `, `? `).
3. **Persistenza**:
   - I frammenti vengono salvati nella tabella `knowledge_chunks` con metadati, indice del chunk, hash di deduplicazione e scope.

---

## Tool `search_knowledge`

Gli agenti dotati della skill o del tool `search_knowledge` possono interrogare la knowledge base con query in linguaggio naturale.

Il tool restituisce i frammenti più pertinenti indicando esplicitamente la provenienza:
- `[System Knowledge] what-is-aether.md`
- `[Workspace Document] report_finanziario_2026.pdf`
