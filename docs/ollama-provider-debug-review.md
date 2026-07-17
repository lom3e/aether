# Ollama Provider Debug Review — Milestone v0.9.0

## 1. Analisi Causa Probabile

La causa principale del timeout è il tempo richiesto per l'inizializzazione e il caricamento (loading) del modello locale in memoria da parte di Ollama.

*   **Dimensione del Modello**: Il modello `qwen3:14b` ha una dimensione su disco di circa **9.27 GB** (14.8B parametri, quantizzazione Q4_K_M).
*   **Caricamento in RAM/VRAM**: Al primo avvio della chiamata, o se il modello è stato scaricato dalla memoria per inattività, Ollama deve leggere 9.27 GB dal disco ed allocarli nella VRAM della GPU o nella RAM di sistema. Questa operazione richiede tipicamente tra i **35 e i 90 secondi** a seconda dell'hardware (SSD vs HDD, throughput della VRAM).
*   **Timeout di Default**: Il timeout configurato di default in `ProviderConfig` è di **30.0 secondi**.
*   **Esito**: Poiché il tempo di caricamento del modello supera i 30 secondi, il client standard `urllib` solleva un timeout di socket prima che Ollama possa iniziare a generare i primi token di risposta.

---

## 2. Verifica Compatibilità Ollama API

La struttura del payload inviato da `OllamaProvider._build_payload` è conforme alle specifiche dell'API `/api/chat` di Ollama:

*   **Messaggi**: La lista viene passata correttamente come array di oggetti con chiavi `role` e `content`.
*   **Stream**: Il parametro `"stream": False` è configurato correttamente.
*   **Opzioni**: Parametri opzionali come `temperature` e `num_predict` (mappato da `max_tokens`) vengono passati correttamente all'interno dell'oggetto `"options"`.
*   **Propagazione Errore**: La gestione delle eccezioni cattura correttamente il `TimeoutError` e lo mappa su `ProviderTimeoutError`, producendo il messaggio coerente `[ollama] Request to http://localhost:11434/api/chat timed out after 30.0s` all'interno dell'errore dell'Agent.

---

## 3. Modifiche Consigliate

Per risolvere il problema senza introdurre over-engineering, si propongono due interventi mirati:

1.  **Innalzamento del default timeout in `OllamaProvider`**:
    Se il timeout di `ProviderConfig` non viene configurato esplicitamente (rimanendo al valore di default di 30.0 secondi), l'inizializzazione di `OllamaProvider` innalzerà automaticamente il valore di timeout a **120.0 secondi**. Questo valore è sufficiente a coprire il cold start di modelli locali di medie/grandi dimensioni (fino a 30B parametri).
2.  **Configurazione esplicita nel test**:
    Impostare esplicitamente un timeout a `120.0` nel file di test `test_ollama_agent.py` come buona pratica documentale.

---

## 4. File Coinvolti

*   `src/aether/providers/ollama.py`: Modifica al costruttore `__init__` per impostare il timeout di default per Ollama a `120.0` se configurato a `30.0`.
*   `test_ollama_agent.py`: Aggiunta del campo `timeout=120.0` in `ProviderConfig`.

---

## 5. Piano Commit

```text
refactor(providers): raise default timeout to 120s in OllamaProvider

- If the user uses the default 30s timeout, automatically scale it to 120s
  to handle cold start model loading times for local Ollama instances.
```

```text
test(ollama): set explicit timeout in E2E agent test

- Update test_ollama_agent.py to configure an explicit 120.0s timeout.
```
