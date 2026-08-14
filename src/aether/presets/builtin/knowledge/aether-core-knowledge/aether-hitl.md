# Human-in-the-Loop (HITL) in Aether

[Status: Implemented] [Release: Alpha]

## Sicurezza e Controllo Umano

Aether include un sottosistema nativo di Human-in-the-Loop per garantire che nessuna azione critica venga eseguita senza autorizzazione esplicita.

---

## Primitive di Interruzione

1. **`RequireApproval`**:
   - Richiede una conferma binaria (Sì/No, Approve/Decline).
   - Utilizzata per operazioni protette (es. esecuzione codice, eliminazione dati, acquisti, modifiche di configurazione).

2. **`RequireInput`**:
   - Richiede una stringa di testo o un input esplicito dall'operatore.
   - Utilizzata quando l'agente ha bisogno di chiarimenti sui requisiti o di parametri mancanti.

---

## Meccanismo di Sospensione e Ripresa

1. Quando un tool solleva un'eccezione `AgentInterrupt` (come `RequireApproval`):
   - L'agente salva lo stato della sessione ReAct (`_react_sessions[session_id]`).
   - Il runtime sospende l'esecuzione senza fallire il task.
   - Un evento WebSocket di tipo `interrupt` viene inviato al browser.
2. L'interfaccia utente mostra una scheda interattiva con il messaggio e i pulsanti di azione.
3. Quando l'utente risponde (`yes` / `no` o testo), il WebSocket inoltra la risposta a `team.resume(session_id, response)`.
4. L'agente riprende l'esecuzione esattamente dal punto in cui era stato sospeso, iniettando la risposta umana come risultato del tool senza rieseguire l'azione due volte.
