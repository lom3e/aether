# Aether — Forensic Product Audit

Status: Active implementation baseline
Branch: development

This document is the source of truth for the current product-hardening cycle.

Important:
- Do not add unrelated features while this audit is being implemented.
- Local AI execution remains deferred.
- Functional truthfulness has priority over feature breadth.
- UX/UI improvements follow functional stabilization.

### A. Executive Summary

Aether ha una base tecnica ampia e molte capability backend reali, ma lo stato percepito dall’utente è oggi più maturo dello stato reale.

I problemi prioritari sono:

1. **Connections non truthful**: lo stato `CONNECTED` viene persistito senza verifica reale. Calendar è esplicitamente un calendario SQLite locale, ma la UI lo presenta come Google Calendar.
2. **Notifiche frammentate**: esistono backend dispatcher, SSE, App, Companion, Tauri e fallback AppleScript. Il click nativo non ha un handler completo e il target viene solo memorizzato, non consegnato direttamente all’app.
3. **Approval/Require Review non canonicalizzato**: notifiche diverse usano `home`, `automations`, `missions` o action execution con payload differenti. Alcuni errori frontend vengono ignorati.
4. **Email e integrazioni**: l’invio SMTP è reale, ma il setup e il “Test Connection” spesso validano solo il formato dei dati.
5. **UX troppo tecnica**: l’interfaccia espone ancora concetti architetturali come Workforce, Fabric, Teams, Agents, Memory e dettagli operativi che dovrebbero essere nascosti o progressivi.

Il build UI passa. Il worktree è rimasto pulito e non sono state apportate modifiche. Non è stato possibile eseguire un test manuale completo del desktop/macOS perché il runtime Python/test environment non è installato nella sessione corrente; le conclusioni runtime sono quindi basate su codice, test e percorsi end-to-end staticamente verificabili.

---

### B. Capability Audit

| Capability | Stato | Evidenza | Problemi | Priorità |
|---|---|---|---|---|
| Chat / Personal Assistant | ⚠️ Parzialmente funzionante | Pipeline in `personal/service.py`, SSE e runtime centralizzato | Stati intermedi dichiarati completed prima della fine dell’esecuzione; errori runtime possono essere mascherati da fallback testuali | P0 |
| Missions | ⚠️ Parzialmente funzionante | Runtime, mission graph, deliverables e approval API presenti | UI molto tecnica; deep-link da notifiche non porta sempre alla missione corretta; stati approval non uniformi | P1 |
| Action execution | ⚠️ Parzialmente funzionante | `ActionExecutor`, runtime e approval endpoints reali | “Action completed” viene aggiunto anche prima di verificare semanticamente il risultato; fallback “Done” troppo ottimistici | P0 |
| Approvals | ⚠️ Parzialmente funzionante | Endpoint approve/reject per missioni e action execution | Notification Center sceglie l’endpoint in base a `link_view`; errore non mostrato all’utente | P0 |
| Require Review / Review Needed | ❌ Rotta in alcuni percorsi | `NotificationCenter.tsx`, `Missions.tsx` | `link_view="home"` non contiene necessariamente il contesto da revisionare; il click può sembrare un no-op | P0 |
| Automations | ⚠️ Parzialmente funzionante | Scheduler avviato in startup, trigger cron/interval/file watcher | Il lifecycle esiste ma mancano feedback utente affidabili su ultimo run, errori, retry e stato effettivo | P1 |
| Filesystem watchers | ✅ Internamente funzionante | `automation/watchers.py`, snapshot filesystem reali | UX e gestione permessi desktop non esplicitate; primo scan non genera eventi, comportamento non documentato | P1 |
| HTTP/GitHub watchers | ⚠️ Parzialmente funzionante | Polling HTTP e GitHub reali | Stato dei token, errori e ultima verifica non esposti con sufficiente chiarezza | P1 |
| Deliverables | ⚠️ Parzialmente funzionante | `personal/context.py` raccoglie file da missioni, task e cartelle workspace | Possibili riferimenti a path inesistenti; UX non distingue chiaramente “creato”, “disponibile” e “verificato” | P1 |
| Companion | ⚠️ Parzialmente funzionante | Tauri companion, file drop, context probe, quick actions | È un secondo dashboard con stato e SSE propri; click notifiche mostra la main window ma non naviga sempre al target | P1 |
| Desktop context | 🔧 Internamente funzionante, UX incompleta | macOS usa `pbpaste` e `osascript`; Linux usa clipboard/xdotool | Richiede permessi OS; fallback silenziosi e risultato “Desktop” possono sembrare dati validi | P1 |
| Notification Center | ⚠️ Parzialmente funzionante | API persistenti, unread/read/dismiss, inline actions | Montato principalmente in Home; errori approve/reject ignorati; routing non uniforme | P0 |
| Marketplace / Workforce | 🔧 Funzionante internamente, UX incompleta | Store, agent/team/marketplace views presenti | Espone dettagli interni invece di capability orientate all’utente | P2 |
| Visual Workflows | ⚠️ Parzialmente funzionante | `WorkflowBuilder` e backend automation | Mancano prove end-to-end sufficienti che ogni configurazione UI venga eseguita realmente | P1 |
| Activity / audit trail | ⚠️ Parzialmente funzionante | Activity service e action history | Registra “Connected” e “Completed” anche quando la verifica o l’esecuzione reale non sono state completate | P0 |
| Local AI execution | ⚠️ Deferred | Runtime e fabric presenti ma non completamente disponibili | Area esplicitamente ammessa come deferred | Deferred |
| Browser/system actions | 🔧 Incompleta | Sono presenti subprocess/system probes e action adapters | Non emerge una superficie user-facing coerente per azioni browser/sistema; capability non sempre distinguibile da simulazione | P1 |
| External agents / MCP | 🔧 Internamente presente, UX incompleta | Adapter external agent e tool registry | Setup, stato, errori e confini di sicurezza non sono presentati come prodotto coerente | P1 |

Riferimenti principali: [personal/service.py](</Users/matteo/Matteo/Lavoro/Progetti Personali/Aether/aether/src/aether/personal/service.py:1360>), [Missions.tsx](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/ui/src/Missions.tsx:350>), [NotificationCenter.tsx](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/ui/src/NotificationCenter.tsx:142>).

---

### C. Integrations Audit

| Integration | Stato | Autenticazione | Verifica reale | Azione end-to-end | Problemi / correzioni |
|---|---|---|---|---|---|
| Google Calendar | ❌ Rotta / misleading | Nessun OAuth Google | Sempre `True` | Funziona solo su SQLite locale | `CalendarConnector` salva in `calendar_events`; la UI lo presenta come Google Calendar. Serve OAuth reale oppure rinominare chiaramente “Aether Local Calendar” |
| GitHub | ⚠️ Parzialmente funzionante | PAT reale | Formato per default; live solo con `live_check` | Operazioni repo/issues/PR/file reali se token valido | UI non invia `live_check`; Connect può risultare riuscito con PAT non verificato |
| Email SMTP | ⚠️ Parzialmente funzionante | Username/password o app password | Formato per default; SMTP login solo se `live_check` | Invio SMTP reale | Setup incompleto: niente provider mode, TLS/SSL esplicito, sender, recipient test, app-password guidance, gestione update secrets |
| Slack bot | ⚠️ Parzialmente funzionante | Bot token o webhook | Formato per default; `auth.test` solo live | `chat.postMessage`/webhook reali | “Connected” non implica workspace/channel raggiungibile; manca selezione/verifica destinazione |
| Telegram | ⚠️ Parzialmente funzionante | Bot token reale | `getMe` solo se `live_check` | Bot API reale | Whitelist vuota autorizza tutti i chat ID: `is_chat_authorized()` ritorna `True`; rischio di sicurezza |
| Notion | 🟡 Mock/config shell | Token validato solo sintatticamente | Nessuna API Notion | Nessuna operazione Notion reale trovata | UI promette pagine/database read-write, ma non esiste un `NotionConnector` né un’azione API reale |
| HTTP | ⚠️ Parzialmente funzionante | Bearer/API key/Basic | Validazione principalmente configurativa | Request HTTP reale | Manca una verifica semantica dell’endpoint configurato; bisogna distinguere “URL valido” da “servizio accessibile” |
| OpenAPI | 🔧 Internamente funzionante, UX incompleta | Delegata a HTTP | Test prevalentemente mockati | Generator/tool execution reale se configurato | Non risulta esposta come setup completo nelle Connections; import spec, auth e test live devono essere user-facing |
| macOS desktop notifications | ⚠️ Parzialmente funzionante | Tauri notification permission o AppleScript | EventHub può dichiarare `SENT` senza prova native | Banner Tauri reale in alcuni percorsi | Click routing incompleto; fallback `osascript` non è Aether-owned e non garantisce icona/deep-link |
| Browser notifications | ⚠️ Parzialmente funzionante | Browser permission | Web Notification API | Banner browser reale | Icona impostata a `/logo.png`, file non trovato nel public asset set; click funziona solo nel fallback browser |
| Email notifications | ⚠️ Parzialmente funzionante | Dipende dalla connessione SMTP | Dipende dalla modalità di verifica | Dispatcher SMTP reale | Delivery receipt deve distinguere SMTP accepted da mailbox delivery |
| Webhook notifications | ✅ Internamente funzionante | URL + secret opzionale | HTTP request reale | POST reale | Necessari timeout/error state e UI per retry/ultima risposta |
| Filesystem | ✅ Internamente funzionante | Nessuna | Path sandbox e test presenti | File ingest/drop reale | UX desktop e permessi devono essere espliciti; evitare di presentare file path tecnici |
| Browser/system actions | 🔧 Incompleta | Non esiste un setup utente unico | Non verificabile come integration autonoma | Alcuni subprocess reali | Mancano confini chiari tra system probe, action adapter e vera automazione browser |
| External agents / MCP | 🔧 Internamente presente | Configurazione locale | Non uniforme | Adapter presenti | Stato, autorizzazioni, failure e capability devono essere mostrati senza esporre ToolRegistry/implementation details |
| Automations/watchers | ⚠️ Parzialmente funzionante | Dipende da ogni trigger | File/HTTP/GitHub polling reale | Scheduler viene avviato allo startup | Serve stato persistente e verificabile per enabled/running/last run/last error |

Evidenze chiave:

- [connections/service.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/connections/service.py:32>)
- [connections/service.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/connections/service.py:250>)
- [connections/service.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/connections/service.py:318>)
- [routes.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/server/routes.py:6010>)
- [Connections.tsx](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/ui/src/Connections.tsx:310>)
- [email.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/connections/email.py:97>)
- [watchers.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/automation/watchers.py:1>)

---

### D. Truthfulness / Simulation Audit

1. **Calendar dichiarato connected senza account Google**

   `CalendarConnector.verify()` ritorna sempre `True`; `get_health()` ritorna sempre `CONNECTED`; la UI invia `auth_metadata: { type: "sqlite_built_in" }`.

   Il comportamento reale è un calendario locale SQLite, non Google Calendar.

2. **ConnectionService.connect() assegna sempre `CONNECTED`**

   [ConnectionService.connect()](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/connections/service.py:160>) salva direttamente `ConnectionStatus.CONNECTED` senza chiamare `verify()`.

3. **Il route `/connections` non verifica le credenziali**

   [routes.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/server/routes.py:6010>) salva il record dopo aver eventualmente unito i secret già presenti, ma la verifica è separata.

4. **“Test Connection” spesso significa solo format check**

   [Connections.tsx](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/ui/src/Connections.tsx:315>) non invia `live_check: true`.

   GitHub, Slack, Email e Telegram quindi possono risultare validi senza aver contattato il servizio.

5. **Notion è una configurazione finta dietro un’integrazione apparentemente reale**

   La verifica accetta token con formato plausibile, ma non esiste un client Notion né una chiamata all’API Notion.

6. **NotificationDispatcher dichiara `SENT` quando pubblica su EventHub**

   In [dispatcher.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/notifications/dispatcher.py:299>), se `event_hub` esiste ritorna immediatamente `DeliveryStatus.SENT`.

   Questo dimostra solo che l’evento è stato pubblicato internamente, non che:

   - il frontend lo abbia ricevuto;
   - Tauri abbia creato il banner;
   - macOS abbia mostrato la notifica;
   - l’icona sia corretta;
   - il click sia stato gestito.

7. **`test_channel()` è un test di dispatch, non un test desktop end-to-end**

   Pubblica un evento sull’EventHub e registra una receipt. Non verifica il comportamento dell’app macOS.

8. **Il target di notifica Tauri viene memorizzato, non associato al click**

   [main.rs](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src-tauri/src/main.rs:92>) salva `last_notification_target`, ma non registra un callback/evento di click della notifica.

9. **Il callback `onClick` frontend viene ignorato nel path Tauri**

   [desktop.ts](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/ui/src/desktop.ts:95>) usa `invoke('send_desktop_notification')` e ritorna. `options.onClick` viene usato solo dal Web Notification fallback.

10. **Due subscriber SSE possono generare la stessa notifica**

    `App.tsx` e `AmbientCompanion.tsx` ascoltano entrambi `/api/personal/events` e chiamano entrambi `notifyDesktop()`.

11. **Companion non naviga al target**

    Il callback del Companion chiama principalmente `showMainWindow()`, senza garantire la navigazione a `link_view/link_id`.

12. **Approval routing basato su `link_view` è fragile**

    In [NotificationCenter.tsx](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/ui/src/NotificationCenter.tsx:142>), tutto ciò che non ha `link_view === "missions"` viene inviato all’endpoint action execution. Questo non è sufficiente per notifiche con target Home, automation o deliverable.

13. **Gli errori inline approve/reject non vengono mostrati**

    Se `res.ok` è falso, non viene mostrato alcun feedback. Il click appare quindi come no-op.

14. **Personal service marca step come completed prima dell’esecuzione**

    Gli step `"Prepared action"` e `"Executing: ..."` vengono aggiunti con `status="completed"` prima di `runtime.execute()`.

15. **Fallback testuali possono mascherare risultati vuoti**

    Sono presenti messaggi come `"Done! I've successfully executed..."`, `"Task executed successfully"` e `"has been created"` quando il risultato runtime non contiene output sufficiente.

16. **Telegram autorizza tutti i chat se la whitelist è vuota**

    [telegram.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/connections/telegram.py:94>) ritorna `True` senza `allowed_chat_ids`.

17. **Secrets salvati in SQLite in `auth_metadata`**

    [store.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/connections/store.py:65>) persiste il JSON dei secret. Il masking avviene nella serializzazione API, non nella persistenza.

18. **Windows desktop path dichiara “queued” senza implementazione equivalente**

    Il dispatcher ritorna `SENT` con `"Windows notification queued"` senza una verifica analoga al path Tauri/macOS.

---

### E. Known Bugs

#### 1. macOS notification icon/click

**Root cause principale**

Esistono almeno tre percorsi:

1. backend `NotificationDispatcher`;
2. EventHub → SSE → frontend;
3. Tauri IPC → `tauri_plugin_notification`.

Il fallback backend usa:

```python
osascript -e 'tell application "System Events" to display notification ...'
```

Questo crea una notifica attribuita a macOS/System Events, non a un’istanza Aether con bundle metadata completo. Non garantisce:

- icona Aether;
- app owner coerente;
- deep-link;
- focus della finestra Aether.

Il path Tauri è migliore per l’icona, ma [main.rs](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src-tauri/src/main.rs:92>) non registra l’evento di click della notifica. Il target viene scritto in memoria quando la notifica viene inviata e consumato soltanto su focus/reopen.

**Impatto**

- click che non porta ad Aether;
- apertura di Script Editor/Finder/file picker nei percorsi AppleScript legacy;
- notifiche senza icona corretta;
- status `SENT` anche se l’utente non ha ricevuto una UX utilizzabile.

**Fix richiesto**

Un solo native notification path per Tauri, con:

- app/bundle icon verificata;
- evento click nativo;
- payload deep-link persistente;
- focus della main window;
- routing a view + entity;
- fallback AppleScript disabilitato nell’app packaged;
- receipt assegnata solo dopo la consegna effettiva al native surface.

#### 2. `Require Review` no-op

**Root cause**

Il codice non ha un unico modello di review target.

- Le missioni usano `link_view="missions"`.
- Le approval action usano spesso `link_view="home"`.
- Le automation approval usano `link_view="automations"`.
- Il Notification Center assume che tutto ciò che non è mission sia una action execution.

Inoltre, `Home` non interpreta necessariamente `link_id` come approval da aprire e gli errori HTTP vengono solo loggati.

**Impatto**

La notifica può essere marcata come letta senza aprire la review corretta; il pulsante Approve/Reject può chiamare un endpoint sbagliato e non mostrare l’errore.

**Fix richiesto**

Definire un payload canonicalizzato:

```text
target_type: mission | action_execution | automation | deliverable
target_id
primary_action
secondary_action
deep_link
```

Un solo resolver frontend e un solo contratto backend per:

- open;
- approve;
- reject;
- expired;
- already completed;
- unauthorized;
- failed.

#### 3. Calendar fake Connected

**Root cause**

- `CalendarConnector` è locale.
- `verify()` ritorna sempre true.
- `get_calendar_connector()` crea automaticamente una connection.
- La UI usa il nome “Google Calendar / Sync”.
- Il toast è “Connected Calendar successfully”.

**Impatto**

L’utente crede di aver collegato il proprio Google Calendar quando nessun account Google è stato autorizzato.

**Fix richiesto**

Scegliere esplicitamente una delle due strade:

- implementare OAuth Google Calendar completo;
- oppure separare e rinominare il prodotto locale come `Aether Calendar`, senza claim Google/sync.

Per Google servono OAuth authorization code + PKCE, callback locale/browser, token refresh, scopes espliciti, `calendarList`/event verification, revoke e stato `Needs authorization`.

#### 4. Email configuration UX

**Root cause**

La UI espone un form SMTP minimale:

- username;
- password/app password;
- SMTP host;
- porta.

Manca:

- provider selection;
- TLS/SSL mode;
- sender address;
- test recipient;
- spiegazione Gmail app password/OAuth;
- differenza tra configurato e verificato;
- update secrets senza rendere obbligatorio reinserirli;
- errore strutturato per DNS, TLS, authentication e recipient rejection.

Il backend può fare login SMTP reale, ma solo se richiesto con `live_check`.

**Impatto**

L’utente non sa se Aether abbia:

- salvato la configurazione;
- verificato il server;
- autenticato l’account;
- inviato una mail reale.

---

### F. UX/UI Audit

#### Navigation e information architecture

Problemi:

- Troppe superfici di primo livello: Home, Missions, Workforce, Teams, Agents, Memory, Learning, Automations, Workflows, Skills, Content, Proactive, Fabric, Marketplace, Settings.
- Terminologia interna: `Workforce`, `Execution Fabric`, `Mesh Audit`, `Memory`, `Agent`, `Team`, `ToolRegistry`.
- Il prodotto appare come una piattaforma amministrativa invece che come un assistente operativo unico.

Direzione:

- Home come superficie outcome-oriented.
- Work/Missions come lavoro attivo.
- Connections come integrazioni.
- Automations come regole personali.
- Activity come cronologia.
- Settings come configurazione.
- Dettagli Workforce/Agent/Fabric solo progressivamente o in una sezione avanzata.

#### Connections

Problemi:

- Badge `Connected` non significa verificato.
- Calendar è confuso con Google.
- Le card mescolano account, capability, sync, action log e calendario.
- Secret update flow contraddittorio: il testo suggerisce di lasciare vuoto per mantenere il secret, ma alcuni campi sono `required`.
- Il feedback è spesso toast-only.
- Gli errori fetch vengono scritti in console senza stato UI.

Stato consigliato:

```text
Not configured
Configuration saved
Verification required
Verified
Expired / authentication failed
Last successful operation
```

#### Notifications

Problemi:

- Notification Center non è realmente globale.
- App e Companion hanno comportamenti differenti.
- Toast, banner OS, inbox e approval card non condividono sempre lo stesso target.
- Non è evidente se una notifica sia informativa, richieda approvazione o sia fallita.
- Gli errori di azione possono non produrre alcun feedback.
- Manca una UI unica per delivery channel, stato e retry.

#### Approvals

Problemi:

- Il percorso di approvazione è distribuito tra Home, Missions, Notification Center e Companion.
- Il linguaggio “Approval”, “Require Review”, “Confirmation Required” non è uniforme.
- La schermata target non è deterministica.
- Un’azione già eseguita o scaduta non ha uno stato esplicito e comprensibile.

#### Missions

Problemi:

- Troppe informazioni tecniche nello stesso contesto: graph, replay, telemetry, trace, health, intelligence, workforce.
- Lo stato operativo non è sempre distinto dallo stato descrittivo.
- La UI dovrebbe mostrare prima obiettivo, avanzamento, blocco, output e prossima decisione.

#### Companion

Problemi:

- Sembra una seconda applicazione, non una superficie ambient.
- Quick actions come `Mesh Audit` espongono concetti interni.
- Ha polling, SSE e notification state separati dalla main app.
- File path e dettagli tecnici sono troppo visibili.
- Il click su una notifica mostra la main window ma non necessariamente il contesto corretto.

#### Automations

Problemi:

- Mancano indicatori affidabili di:
  - ultimo run;
  - prossimo run;
  - ultimo errore;
  - retry;
  - watcher attivo;
  - credenziale scaduta.
- Il sistema può apparire enabled anche quando il trigger non è verificabile.

#### Loading/error/empty states

Problemi ricorrenti:

- `console.error` senza messaggio UI.
- Risposte non-OK ignorate.
- Empty state che non distingue “nessun dato” da “backend non raggiungibile”.
- Success toast dopo salvataggio record, non dopo verifica reale.
- Loading state presenti ma non sempre accompagnati da cancellazione/retry.

#### Visual consistency

- Molti inline styles duplicati.
- Spacing, badge, modali e action buttons non completamente uniformi.
- Lingua mista tra stringhe hardcoded e i18n.
- Notification icon browser riferisce `/logo.png`, che non risulta presente negli asset pubblici verificati.
- Bundle UI oltre 1 MB non compresso; non è un blocker funzionale, ma indica che il prossimo pass UX dovrebbe includere consolidamento componenti e code splitting.

---

### G. Architecture / Code Health

#### 1. Notification pipeline duplicata

Pipeline attuali:

```text
NotificationService
  → Dispatcher
      → EventHub / osascript / Telegram / Email / Webhook
  → SSE
      → App
          → Tauri notification
      → Companion
          → Tauri notification
```

Questa architettura consente:

- doppie notifiche;
- receipts premature;
- target sovrascritti;
- comportamenti diversi tra main app e Companion;
- fallback non controllati.

Serve un solo `NotificationDeliveryCoordinator` e un solo `NotificationTargetResolver`.

#### 2. Connection state separato dalla connector health

Il record persistito ha uno status manuale. La salute del connector è calcolata separatamente. Non esistono in modo coerente:

- `last_verified_at`;
- `last_verification_error`;
- `last_successful_operation`;
- `credential_expiry`;
- `verification_method`.

#### 3. Secrets storage

I secret vengono memorizzati in JSON SQLite e mascherati principalmente nell’output API.

Per il prossimo livello serve almeno:

- cifratura a riposo;
- preferibilmente macOS Keychain per la build desktop;
- secret references invece di valori completi nei record;
- redaction uniforme nei log, activity e error payload;
- rotazione/revoca.

#### 4. Truthfulness nel runtime

Gli step e le notifiche di completamento sono generati in punti diversi dal risultato reale del runtime. Occorre un’unica macchina a stati:

```text
queued → running → waiting_approval → succeeded
                         ↘ rejected
                         ↘ failed
                         ↘ expired
```

Nessuna UI deve produrre `completed` o `success` prima della transizione reale.

#### 5. API e test con falsa copertura

I test verificano spesso:

- store locale;
- mock EventHub;
- `urllib.request.urlopen` patchato;
- token format;
- payload costruiti.

Questo non prova:

- OAuth;
- SMTP live;
- Slack live;
- GitHub API live;
- Tauri notification click;
- macOS bundle/icon;
- SSE → frontend → native notification;
- approval deep-link.

Riferimenti: [test_personal_agent_actions_connect.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/tests/test_personal_agent_actions_connect.py:1>), [test_macos_notification_ux_post_pass.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/tests/test_macos_notification_ux_post_pass.py:1>), [test_golden_paths_actions_connections.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/tests/test_golden_paths_actions_connections.py:1>).

#### 6. Scheduler lifecycle

Il scheduler viene avviato nello startup FastAPI e fermato nello shutdown:

[app.py](</Users/matteo/Matteo/Lavoro/Progetti%20Personali/Aether/aether/src/aether/server/app.py:145>).

La struttura è corretta internamente, ma servono:

- health endpoint;
- stato visibile in UI;
- run history affidabile;
- error persistence;
- gestione restart;
- verifica manuale di cron, file, HTTP e GitHub watcher.

#### 7. Security boundary Telegram

La whitelist vuota equivale ad accesso aperto. Deve essere una scelta esplicita, non il default.

#### 8. Static UI duplication

Il codice sorgente UI e gli asset compilati sotto `src/aether/server/static` sono entrambi presenti e sincronizzati via build. Questo crea rischio di:

- servire una build vecchia;
- verificare file sorgente ma eseguire asset obsoleti;
- dimenticare la sincronizzazione.

Serve una policy chiara di source-of-truth e una verifica CI che asset statici e sorgenti siano coerenti.

---

### H. Recommended Macro Passes

## Macro-pass P0.1 — Truthful Connection State

**Obiettivo**

Impedire qualsiasi stato `Connected`, `Success` o `Completed` senza prova reale.

**Problemi risolti**

- `ConnectionService.connect()` sempre connected.
- Test format-only presentati come connection test.
- Calendar fake connected.
- Activity log misleading.

**Aree principali**

- `src/aether/connections/service.py`
- `src/aether/connections/models.py`
- `src/aether/server/routes.py`
- `ui/src/Connections.tsx`
- `src/aether/connections/store.py`

**Dipendenze**

Nessuna, salvo definizione del nuovo connection state model.

**Rischi**

- Migrazione dei record esistenti.
- Possibile rottura di automazioni che assumono `status=connected`.

**Test**

- Connect senza credenziali: deve restare `needs_auth` o `disconnected`.
- Token sintatticamente valido ma servizio irraggiungibile: `verification_failed`.
- Operazione reale riuscita: aggiornamento di `last_successful_operation`.
- Secret vuoti durante update: preservare il secret esistente senza rendere il campo obbligatorio.

**Acceptance**

- Nessuna UI mostra `Connected` prima della verifica.
- Ogni connection mostra `Configured`, `Verified`, `Needs attention` o `Disconnected`.
- Activity log usa gli stessi stati.
- I messaggi distinguono formato, autenticazione e operazione reale.

**Verifica manuale**

Configurare ogni provider con credenziale invalida, correggerla, verificare, eseguire una read/write action e disconnettere.

---

## Macro-pass P0.2 — Calendar Boundary e OAuth Reale

**Obiettivo**

Eliminare l’ambiguità tra calendario locale Aether e Google Calendar.

**Problemi risolti**

- Fake Google Connected.
- OAuth assente.
- Verifica credenziali sempre positiva.
- Claim di sync non supportati.

**Aree principali**

- `src/aether/connections/service.py`
- `src/aether/connections/sync.py`
- `src/aether/server/routes.py`
- `ui/src/Connections.tsx`
- nuovo modulo Google OAuth/API
- connection store/token storage

**Dipendenze**

Macro-pass P0.1.

**Rischi**

- OAuth desktop callback.
- Token refresh.
- Scope e privacy.
- Differenza tra account locale e account Google.

**Test**

- OAuth cancel.
- OAuth invalid state.
- Token expired/refresh.
- Calendar list access.
- Event create/read/update/delete su calendario reale.
- Disconnect/revoke.

**Acceptance**

- Nessun “Google Calendar” senza OAuth concluso.
- Calendar locale, se mantenuto, è nominato esplicitamente `Aether Calendar`.
- `Connected` solo dopo una chiamata Google riuscita.
- Account e calendario selezionabili.
- Errori OAuth visibili e recuperabili.

**Verifica manuale**

Connect → browser Google login → grant → calendario selezionato → create event → verificarlo su Google Calendar → revoke → UI mostra disconnected.

---

## Macro-pass P0.3 — Canonical Notification Fabric

**Obiettivo**

Avere una sola pipeline notification → delivery → target → action.

**Problemi risolti**

- Doppie notifiche App/Companion.
- EventHub che dichiara SENT prematuramente.
- AppleScript legacy.
- Target non coerenti.
- Click senza routing.

**Aree principali**

- `src/aether/notifications/service.py`
- `src/aether/notifications/dispatcher.py`
- `ui/src/App.tsx`
- `ui/src/AmbientCompanion.tsx`
- `ui/src/desktop.ts`
- `src-tauri/src/main.rs`

**Dipendenze**

P0.1 per connection-aware notification channels.

**Rischi**

- Compatibilità con notifiche persistite esistenti.
- Differenze tra macOS, browser e Companion.

**Test**

- Una notifica produce una sola native delivery.
- Delivery receipt cambia in base al risultato reale.
- Dedupe deterministico.
- Target multipli contemporanei non si sovrascrivono.
- App chiusa/aperta/focalizzata.
- Permission denied.
- Fallback browser.

**Acceptance**

```text
notification
 → canonical target
 → one delivery owner
 → native banner
 → click
 → focus Aether
 → route view/entity
```

- AppleScript non viene usato nel packaged Tauri desktop.
- Icona Aether viene verificata sul banner.
- Nessun file picker, Script Editor o Finder.

**Verifica manuale**

Mission approval, action approval, deliverable ready e automation failure, con app in foreground, background e chiusa.

---

## Macro-pass P0.4 — Approvals e Require Review

**Obiettivo**

Rendere ogni review apribile, approvabile e rifiutabile con un contratto unico.

**Problemi risolti**

- Require Review no-op.
- Endpoint scelto dal `link_view`.
- Errori silenziosi.
- Target Home non specifico.

**Aree principali**

- `ui/src/NotificationCenter.tsx`
- `ui/src/Home.tsx`
- `ui/src/Missions.tsx`
- `src/aether/notifications/models.py`
- `src/aether/personal/service.py`
- action/mission approval routes

**Dipendenze**

P0.3.

**Rischi**

- Compatibilità con notification payload storici.
- Idempotenza approve/reject.

**Test**

- Mission approval.
- Action execution approval.
- Automation approval.
- Already approved.
- Already rejected.
- Expired.
- Unauthorized.
- Backend 500.
- Retry frontend.

**Acceptance**

- Ogni approval ha `target_type`, `target_id`, `open_target`, `approve_action`, `reject_action`.
- Il click apre la schermata e l’elemento esatto.
- Ogni errore produce feedback utente.
- La notifica cambia stato dopo l’azione.

**Verifica manuale**

Creare un’azione che richiede review da Chat, Home, Companion e notifica macOS.

---

## Macro-pass P1.1 — Integration Hardening

**Obiettivo**

Completare le integrazioni già dichiarate esistenti.

**Problemi risolti**

- Format-only verification.
- Notion finta.
- Email setup incompleto.
- Slack/GitHub/Telegram senza live health.
- Telegram whitelist aperta.

**Aree principali**

- `src/aether/connections/github.py`
- `email.py`
- `slack.py`
- `telegram.py`
- `http.py`
- nuovo `notion.py` oppure rimozione del provider dalla UI
- `ui/src/Connections.tsx`

**Dipendenze**

P0.1.

**Rischi**

- Rate limit.
- Secret rotation.
- Provider policy differences.

**Test**

Per ogni provider:

- invalid credentials;
- valid credentials;
- live verify;
- primary read;
- primary write;
- timeout;
- revoked token;
- masked secrets;
- disconnect.

**Acceptance**

- Notion o è reale o non è presentata come integration disponibile.
- Email include provider, TLS mode, sender e test recipient.
- Telegram richiede whitelist esplicita per accesso companion.
- Ogni provider espone ultimo check, ultimo errore e ultima operazione reale.

---

## Macro-pass P1.2 — Runtime State e Action Safety

**Obiettivo**

Allineare status, output, activity e notifiche al risultato reale del runtime.

**Problemi risolti**

- Step completed prematuri.
- Success fallback.
- Action completion non verificata.
- Auto-approve non sufficientemente evidente.

**Aree principali**

- `src/aether/personal/service.py`
- `src/aether/actions/executor.py`
- `src/aether/actions/models.py`
- mission runtime
- activity service
- notification service

**Dipendenze**

P0.4.

**Rischi**

- Migrazione dei run storici.
- Stati intermedi più numerosi nella UI.

**Test**

- runtime success;
- runtime failure;
- timeout;
- partial failure;
- approval wait;
- retry;
- idempotenza;
- external agent failure;
- auto-approve policy.

**Acceptance**

- Nessun “success” con runtime failure.
- Un’azione notificata come completed ha prova persistita dell’operazione.
- I fallback testuali non possono trasformare un errore in successo.
- Auto-approve è limitato ad azioni safe e mostrato coerentemente.

---

## Macro-pass P1.3 — Automation e Watcher Reliability

**Obiettivo**

Rendere verificabile il comportamento reale di scheduler, cron, filesystem, HTTP e GitHub watcher.

**Problemi risolti**

- Stato enabled non equivalente a running.
- Errori persi nei log.
- Mancanza di run history affidabile.
- Watcher non osservabili dalla UI.

**Aree principali**

- `src/aether/automation/scheduler.py`
- `src/aether/automation/watchers.py`
- `src/aether/automation/engine.py`
- `src/aether/server/app.py`
- `ui/src/Automations.tsx`

**Dipendenze**

P1.2.

**Rischi**

- Scheduling duplicato dopo restart.
- Trigger ripetuti.
- Race tra watcher e manual run.

**Test**

- scheduler startup/shutdown;
- restart recovery;
- cron;
- interval;
- filesystem create/modify;
- HTTP content change;
- GitHub commit change;
- concurrency limit;
- duplicate suppression;
- failure retry.

**Acceptance**

La UI deve mostrare:

- active/paused;
- scheduler healthy/unhealthy;
- last run;
- next run;
- last result;
- last error;
- trigger source.

---

## Macro-pass P2.1 — Unified Product UX

**Obiettivo**

Ridurre la complessità percepita senza eliminare capability.

**Problemi risolti**

- IA frammentata.
- Terminologia tecnica.
- Second dashboard Companion.
- Feedback incoerente.

**Aree principali**

- `ui/src/App.tsx`
- `ui/src/Sidebar.tsx`
- `ui/src/Home.tsx`
- `ui/src/Missions.tsx`
- `ui/src/AmbientCompanion.tsx`
- componenti shared UI/i18n

**Dipendenze**

P0 e P1 completati.

**Rischi**

- Regressioni di routing.
- Perdita di accesso alle funzioni avanzate.

**Test**

- navigation matrix;
- keyboard shortcuts;
- responsive desktop/companion;
- loading/error/empty/success states;
- localization consistency.

**Acceptance**

- L’utente vede obiettivi, lavori, connessioni e decisioni.
- I concetti interni sono nascosti o relegati a “Advanced”.
- Companion è una superficie ambient, non una seconda console.
- Notification Center e approval inbox sono globali.

---

## Macro-pass P2.2 — Connections UX Premium

**Obiettivo**

Rendere setup, verifica e stato delle integrazioni comprensibili.

**Problemi risolti**

- Email confusa.
- Status ambiguo.
- Secret update poco chiaro.
- Form provider-specifici incompleti.

**Aree principali**

- `ui/src/Connections.tsx`
- shared form/validation components
- connection status API

**Acceptance**

Ogni card mostra:

- cosa permette;
- cosa serve;
- cosa è stato verificato;
- quando;
- ultimo errore;
- azione primaria;
- disconnect/revoke.

---

## Macro-pass P2.3 — Missions, Deliverables e Reviews

**Obiettivo**

Portare l’esperienza da telemetry/admin console a outcome operativo.

**Problemi risolti**

- Eccessiva densità tecnica.
- Deliverable poco distinguibili.
- Review non centrali.

**Acceptance**

Ogni missione mostra prima:

1. obiettivo;
2. stato reale;
3. blocco o richiesta utente;
4. output;
5. prossima azione.

Trace, graph e telemetry diventano dettagli espandibili.

---

## Macro-pass P3.1 — Consolidamento architetturale

**Obiettivo**

Rimuovere duplicazioni solo dopo aver stabilizzato i contratti.

**Problemi risolti**

- Notification path paralleli.
- Connection state duplicato.
- SSE App/Companion separati.
- Static build ambiguity.
- Activity status non canonici.

**Aree principali**

- notification coordinator;
- connection health model;
- canonical target resolver;
- event contracts;
- static asset build pipeline.

**Acceptance**

- Un solo owner per ogni delivery.
- Un solo modello di connection health.
- Un solo contratto per approval/deep-link.
- CI verifica che static build sia aggiornato.

---

## Macro-pass P3.2 — Test e packaging release-grade

**Obiettivo**

Aggiungere la prova reale mancante.

**Test necessari**

- backend unit/integration;
- provider contract tests;
- Tauri/macOS packaged smoke test;
- notification icon/click;
- OAuth;
- SMTP live test environment;
- SSE-to-native delivery;
- Companion/main synchronization;
- clean build/install/uninstall;
- no stale static assets.

---

### I. Definition of Done

Aether può essere dichiarato pronto al prossimo livello solo quando:

- [ ] Nessuna connection mostra `Connected` senza verifica reale.
- [ ] Calendar distingue chiaramente Aether local calendar e Google Calendar.
- [ ] Google Calendar OAuth funziona end-to-end, incluso refresh/revoke.
- [ ] Email verifica realmente SMTP login e mostra errori utili.
- [ ] GitHub, Slack, Telegram e HTTP distinguono format validation da live verification.
- [ ] Notion è reale oppure rimossa dalla superficie user-facing.
- [ ] Telegram richiede autorizzazione esplicita dei chat ID.
- [ ] Secrets non sono conservati in chiaro nel normale SQLite store.
- [ ] Ogni action ha stato reale `queued/running/waiting/succeeded/failed/rejected`.
- [ ] Nessun fallback testuale trasforma failure in success.
- [ ] Una notifica genera una sola delivery desktop.
- [ ] La notifica macOS mostra icona Aether.
- [ ] Click notifica apre/focalizza Aether.
- [ ] Click notifica porta alla missione, approval, automation o deliverable corretto.
- [ ] Non viene mai aperto Script Editor, Finder o file picker.
- [ ] `Require Review` funziona da Home, Mission, Companion e notifica nativa.
- [ ] Approve/Reject mostrano sempre successo o errore.
- [ ] Notification Center è disponibile globalmente.
- [ ] Companion e main app condividono stato e routing.
- [ ] Scheduler e watcher mostrano stato reale, ultimo run e ultimo errore.
- [ ] Loading, empty, error e success states sono coerenti.
- [ ] L’interfaccia non espone dettagli interni quando non necessari.
- [ ] Le capability avanzate restano disponibili in modalità advanced.
- [ ] Test backend, UI, Tauri e manuali coprono i percorsi reali, non soltanto mock e store locali.
- [ ] Build UI e asset statici sono coerenti.
- [ ] Build desktop macOS installata e testata su una macchina reale.
- [ ] Il repository resta pulito dopo build e packaging.