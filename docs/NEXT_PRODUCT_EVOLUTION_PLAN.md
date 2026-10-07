# AETHER — MASTER PRODUCT, CONNECTOR, COMPANION & UI REWORK PLAN
**Versione Documento:** 2.3.0-MASTER (Definitive Architectural Blueprint)
**Data di Rilascio:** Ottobre 2026
**Stato:** Architectural Blueprint & Implementation Plan (Source of Truth Definitiva)
**Visione Fondamentale:** Trasformare Aether in un **Personal AI Workforce Operating System / Personal AI Office**, accessibile e naturale per chiunque ("regola del nonnino"), fondato sull'autonomia guidata, sul rispetto della privacy, sulla robustezza deterministica del runtime e su un'architettura di autenticazione realistica e prudente per un progetto desktop open-source.

---

## IL PRINCIPIO FONDAMENTALE DI AETHER

> **Connected Apps e Connettori sono solo uno strato abilitante di Aether, non il prodotto.**

La visione definitiva di Aether è:
> **Personal AI Workforce Operating System / Personal AI Office.**

L'utente non deve normalmente pensare:
- a quale agente specifico affidare il lavoro;
- a quale connettore esterno connettersi manualmente;
- a quale tool o API effettuare la chiamata;
- a quale workflow tecnico avviare.

L'esperienza d'uso naturale e fondamentale è poter dire:
> **“Aether, pensaci tu.”**

Aether decide autonomamente, entro precisi limiti di sicurezza, contesto e autorizzazione preventiva:
1. **Quale contesto recuperare** dalla memoria locale, dai file di progetto e dalla storia operativa;
2. **Quali workspace, repository o documenti** includere nel perimetro del compito;
3. **Quali connettori e servizi esterni** interrogare per raccogliere informazioni fresche o sincronizzate;
4. **Quali capacità (capabilities)** sono strettamente necessarie per il compito;
5. **Quali figure e agenti specializzati assemblare dinamicamente** per portare a termine la missione;
6. **Quali passaggi eseguire in autonomia protetta** e quali invece richiedono l'autorizzazione dell'utente;
7. **Come verificare rigorosamente il risultato** prima di considerarlo completato e notificarlo.

---

## INDICE GENERALE

1. [Il Modello Concettuale: Memory, Connectors, Workforce, Missions, Companion, Security](#1-il-modello-concettuale-di-aether)
2. [Context & Capability Router](#2-context--capability-router)
3. [Dynamic Workforce Assembly](#3-dynamic-workforce-assembly)
4. [Golden Path: Connector → Workforce → Mission](#4-golden-path-connector--workforce--mission)
5. [Architettura del Companion Ambientale (Superficie, non Second UI)](#5-architettura-del-companion-ambientale)
6. [Provider Auth Architecture — Public Client vs Confidential Client](#6-provider-auth-architecture--public-client-vs-confidential-client)
7. [Provider & Auth Registration Layer](#7-provider--auth-registration-layer)
8. [Risk-Based Permission Model & Execution Boundary](#8-risk-based-permission-model--execution-boundary)
9. [Connector Ecosystem & Validation Set Iniziale](#9-connector-ecosystem--validation-set-iniziale)
10. [Il Ruolo di MCP (Model Context Protocol)](#10-il-ruolo-di-mcp-model-context-protocol)
11. [Cloud Model Fallback & Policy di Trasparenza](#11-cloud-model-fallback--policy-di-trasparenza)
12. [Aether Design System & Form System](#12-aether-design-system--form-system)
13. [UI/UX Overhaul & Servizi Collegati](#13-uiux-overhaul--servizi-collegati)
14. [Strategia di Localizzazione & Glossario Italiano](#14-strategia-di-localizzazione--glossario-italiano)
15. [Benchmark & Ricerca Ufficiale sui Provider (ChatGPT, Claude, Gemini)](#15-benchmark--ricerca-ufficiale-sui-provider)
16. [Roadmap di Implementazione Sequenziata (Fase 0 - Fase 8)](#16-roadmap-di-implementazione-sequenziata-fase-0---fase-8)
17. [Strategia di Testing & Verifica](#17-strategia-di-testing--verifica)
18. [Rischi, Dipendenze & Limitazioni Tecniche](#18-rischi-dipendenze--limitazioni-tecniche)
19. [Nuova Definition of Done Globale](#19-nuova-definition-of-done-globale)
20. [Cosa NON Fare o Rinviare a Fasi Successive](#20-cosa-non-fare-o-rinviare-a-fasi-successive)
21. [Executive Summary (Sintesi Direzionale)](#21-executive-summary-sintesi-direzionale)

---

## 1. IL MODELLO CONCETTUALE DI AETHER

Aether opera come un organismo coeso suddiviso in sei pilastri architetturali:

```
+---------------------------------------------------------------------------------+
|                             AETHER PERSONAL RUNTIME                             |
+---------------------------------------------------------------------------------+
|  1. MEMORY            -> Contesto persistente, conoscenza pregressa, preferenze |
|  2. CONNECTORS        -> Sensi e mani di Aether: accesso sicuro al mondo esterno |
|  3. WORKFORCE         -> Collaboratori specializzati assemblati su richiesta    |
|  4. MISSIONS          -> Lavoro strutturato, obiettivi a medio termine, verifiche|
|  5. COMPANION         -> Interfaccia ambientale micro-HUD veloce e invisibile   |
|  6. EXECUTION BOUNDARY-> Sicurezza deterministica, isolamento e autorizzazioni   |
+---------------------------------------------------------------------------------+
```

### I Connettori come Sensi e Mani di Aether
Un connettore in Aether **non è** una semplice voce isolata nella schermata impostazioni. È una sorgente vivente di:
- **Context:** Dati freschi recuperabili per arricchire il prompt (es. ultime discussioni, impegni di calendario, stato dei ticket).
- **Capabilities:** Abilità formali esposte agli agenti (es. `SEARCH`, `READ`, `WRITE`, `SYNC`, `WATCH`).
- **Actions:** Singole operazioni eseguibili secondo contratti tipizzati (es. `create_issue`, `send_draft_email`, `reschedule_event`).
- **Events:** Segnali asincroni in ingresso (es. ricezione email da contatto prioritario, commit su branch protetto).
- **Resources:** File, documenti, allegati o schemi a cui gli agenti possono fare riferimento strutturato.

#### Esempio: Modello delle Capability del Connettore GitHub
```text
GitHub Connector
├── Context: Repository metadata, collaboratori, permessi, label attive
├── Capability SEARCH: Cerca repository, codice, issue aperte, pull request
├── Capability READ: Leggi issue specifica, diff PR, file sorgente, workflow run
├── Capability WRITE (High Risk): Crea branch, apri commit, invia PR, merge PR
├── Capability WATCH: Monitora webhook di commenti o review assegnate
└── Resources: Archivio codice, asset di release, changelog
```

---

## 2. CONTEXT & CAPABILITY ROUTER

Il **Context & Capability Router** è una componente centrale del Personal Runtime, situata a monte dell'orchestrazione degli agenti. Non è un plugin dei connettori, ma il motore decisionale che interpreta l'intento dell'utente e prepara il terreno operativo.

```
                                  Prompt Utente
                                        |
                                        v
                    +---------------------------------------+
                    |      CONTEXT & CAPABILITY ROUTER      |
                    +---------------------------------------+
                    | 1. Interpretazione dell'Intento       |
                    | 2. Identificazione Informazioni Utili |
                    | 3. Recupero Contesto Locale (Memory)  |
                    | 4. Risoluzione Connettori & Capab.    |
                    | 5. Applicazione Least Privilege       |
                    | 6. Generazione del Context Pack       |
                    +---------------------------------------+
                                        |
                                        v
                                  Context Pack
                                        |
                                        +----------------------------------+
                                        |                                  |
                                        v                                  v
                               [Personal Assistant]           [Dynamic Workforce]
                               (Risposta Rapida)              (Missione Complessa)
```

### Responsabilità Fondamentali:
1. **Interpretare l'intento naturale:** Comprendere cosa serve realmente all'utente, senza richiedere parole chiave rigide o sintassi da terminale.
2. **Determinare le informazioni mancanti:** Identificare quali dati servono per rispondere o agire (es. disponibilità oraria, stato del progetto, email ricevute).
3. **Recuperare il contesto già disponibile:** Attingere alla memoria locale, ai documenti indicizzati e ai file di configurazione senza chiamare la rete se non necessario.
4. **Risolvere i connettori appropriati:** Selezionare quali connettori collegati possono soddisfare il bisogno informativo o operativo.
5. **Applicare il principio del Least Privilege:** Includere nel contesto e nei permessi della richiesta **esclusivamente** le capability strettamente indispensabili (se l'utente chiede una verifica, il router non concede permessi di scrittura).
6. **Costruire il Context Pack:** Assemblare un payload unificato, compatto e strutturato contenente tutti i dati rilevanti per la sessione o la missione.

### Esempi di Funzionamento:

#### Esempio 1: Richiesta Rapida Informativa
```text
“Aether, controlla le mail di Luca e verifica se domani sono libero.”

Intent:
  ├── Verifica richieste di Luca via email
  └── Verifica disponibilità oraria per la giornata di domani
Context Resolution:
  ├── Memory: Risolve l'identità di "Luca" (indirizzo email noto nei contatti)
  ├── Gmail: Capability SEARCH e READ (query: from:luca@... negli ultimi 3 giorni)
  └── Google Calendar: Capability SEARCH e READ (intervallo: domani dalle 08:00 alle 20:00)
Capability Router:
  └── Concede accesso in sola lettura (READ) ai soli record filtrati
Context Pack:
  └── [Email estratte di Luca] + [Eventi esistenti sul calendario di domani]
Esecuzione:
  └── Personal Agent elabora i dati e formula la risposta sintetica nell'HUD:
      "Luca ti ha chiesto un incontro di 30 min per il progetto Alpha. Domani sei libero dalle 10:00 alle 12:30 e dopo le 16:00."
```

#### Esempio 2: Incarico Strutturato di Progetto
```text
“Controlla le issue GitHub del cliente Alfa e prepara le modifiche necessarie.”

Intent:
  └── Risolvere problemi pendenti del repository cliente con implementazione codice
Context Resolution:
  ├── Memory: Associazione "Cliente Alfa" -> Repository `org-alfa/portal-app`
  ├── Connettore GitHub: Capability SEARCH e READ (issue aperte con label "bug" o "high")
  ├── Workspace Locale: Codice sorgente clonato e documentazione di progetto
  └── Mission History: Traccia delle modifiche completate nelle missioni precedenti
Capability Router:
  └── Concede capability GitHub READ, Workspace READ/WRITE, GitHub WRITE (con approvazione)
Context Pack:
  └── Context pack completo generato per il pianificatore
Dynamic Workforce Assembly:
  └── Assembra: Planner -> Developer -> Tester -> Reviewer
Esecuzione:
  └── Avvio Missione con proposta d'azione sottoposta a verifica.
```

---

## 3. DYNAMIC WORKFORCE ASSEMBLY

La Workforce di Aether **non è un insieme fisso o immutabile di agenti hardcodati**. Aether modella la squadra di collaboratori dinamicamente in base alle capability richieste dalla missione:

```
                          Missione o Incarico
                                   |
                                   v
                         Required Capabilities
                                   |
                                   v
                      DYNAMIC WORKFORCE ASSEMBLY
                                   |
                +------------------+------------------+
                |                  |                  |
                v                  v                  v
           Ruoli Agenti          Skills        Tools / Connectors
                |                  |                  |
                +------------------+------------------+
                                   |
                                   v
                         Esecuzione Coordinata
```

### Composizione Basata su Ruoli e Competenze
Gli agenti vengono istanziati come entità leggere e focalizzate. Ciascun agente riceve:
- Un **Ruolo Funzionale** (es. Architetto, Sviluppatore, Revisore, Copywriter, Assistente Amministrativo);
- Le **Skills necessarie** (istruzioni operative e logiche di dominio);
- Il **Set di Tools e Connettori minimo indispensabile** assegnato dal Capability Router.

### Esempi di Squadre Assemblate Dinamicamente:

| Dominio | Squadra Assemblata Dinamicamente | Ruoli e Connettori Assegnati |
|---|---|---|
| **Sviluppo Software (Coding)** | • **Architect:** Analisi requisiti e architettura<br>• **Planner:** Scomposizione in step tecnici<br>• **Developer:** Scrittura codice locale e modifiche<br>• **Tester:** Esecuzione test unitari e regressioni<br>• **Reviewer:** Code review e preparazione PR | Connettori: GitHub (READ/WRITE), Workspace Filesystem, Local Terminal |
| **Marketing & Comunicazione** | • **Researcher:** Analisi trend e competitor<br>• **Strategist:** Definizione piano editoriale e hook<br>• **Writer:** Redazione testi (LinkedIn, X, Newsletter)<br>• **Designer:** Linee guida visive e formattazione<br>• **Reviewer:** Verifica tono di voce e approvazione | Connettori: Notion, Slack, Google Drive, Web Search, MCP Fetch |
| **Assistenza Esecutiva / Ufficio** | • **Organizer:** Prioritizzazione impegni giornalieri<br>• **Email Assistant:** Scansione e bozze risposte<br>• **Calendar Assistant:** Risoluzione conflitti riunioni<br>• **Document Assistant:** Sintesi verbali e allegati | Connettori: Google Calendar, Gmail, Outlook, OneDrive, Telegram |

---

## 4. GOLDEN PATH: CONNECTOR → WORKFORCE → MISSION

Il flusso vitale ideale di Aether illustra come l'interazione umana minima si traduca in lavoro ad alta precisione:

```
[ UTENTE ]
   |
   | "Aether, prenditi cura del problema del cliente Alfa."
   v
[ CONTEXT & CAPABILITY ROUTER ]
   |
   | Risolve identità cliente, repo `org-alfa/app`, cartella Drive e thread recenti
   v
[ CONTEXT PACK CREATION ]
   |
   | Raccoglie: Issue GitHub #42, Documento requisiti Drive, Ultima email cliente
   v
[ MISSION PROPOSAL ]
   |
   | Sintetizza: "Risoluzione bug di caricamento dati cliente Alfa (Issue #42)"
   v
[ DYNAMIC WORKFORCE ASSEMBLY ]
   |
   | Assembra: Planner -> Developer -> Tester -> Reviewer
   v
[ USER APPROVAL (Se richiesta dal Risk Model) ]
   |
   | L'utente visualizza nell'HUD o nel Desktop: "Avvio missione con accesso a GitHub Alfa?" [Approva]
   v
[ MISSION EXECUTION ]
   |
   | Developer modifica file locale -> Tester esegue i test -> Reviewer valida
   v
[ CONNECTOR ACTIONS (HIGH RISK) ]
   |
   | Apertura PR su GitHub -> Richiesta di approvazione prima del merge
   v
[ VERIFICATION & DELIVERABLE ]
   |
   | Verifica esito CI/CD -> Generazione Deliverable: Report modifiche e PR pronta
   v
[ COMPANION NOTIFICATION ]
   |
   | HUD Companion mostra: "Problema cliente Alfa risolto. PR #15 aperta e test superati."
```

---

## 5. ARCHITETTURA DEL COMPANION AMBIENTALE

### 5.1 Principio Fondamentale: Il Companion è una Superficie, NON una Seconda UI
> **Regola Architetturale:** *Il Companion è una superficie di interazione del Personal Runtime, non un secondo frontend completo che duplica la logica dell'app.*

Aether possiede un unico cervello, un'unica memoria e un unico motore di esecuzione condivisi da tutte le superfici:
```
+---------------------------------------------------------------------------------+
|                         AETHER UNIFIED PERSONAL RUNTIME                         |
|  (Memory • Context Router • Dynamic Workforce • Connectors • Execution Boundary)|
+---------------------------------------------------------------------------------+
         |                    |                    |                   |
         v                    v                    v                   v
   [ Web Desktop UI ]  [ Ambient Companion ]   [ Telegram Bridge ]  [ Future Voice ]
```

### 5.2 Comportamento e Ciclo di Vita del Companion
Il Companion **non è** una finestra chat sempre aperta sullo schermo, né un duplicato compresso del desktop. È un **HUD invisibile e fulmineo**:
- **Stato Normale:** Invisibile, risiede nella barra di sistema con consumo minimo di risorse.
- **Invocazione:** Richiamato istantaneamente con scorciatoia globale di sistema (`Command+Shift+Space` su Mac, `Ctrl+Shift+Space` su Windows/Linux).
- **Interazione:** Un micro-HUD elegante (stile Spotlight/Raycast) orientato al comando rapido vocale o testuale.
- **Risposta:** Breve overlay sintetico con informazioni essenziali e azioni immediate.
- **Approvazione:** Schede compatte per approvare o rifiutare azioni con un solo tocco.
- **Compiti Complessi:** Quando l'utente chiede compiti lunghi (es. *"Crea una missione per riscrivere questo modulo"*), il Companion lancia la missione nel runtime e si richiude, lasciando che il lavoro prosegua in background. L'utente può aprire il Desktop completo solo se desidera ispezionare il canvas dettagliato.

### 5.3 Comprensione dello Schermo (Screen Understanding) & Assistenza Visiva
- **Esclusivamente On-Demand:** Nessuna scansione continua o registrazione occulta in background. La cattura avviene unicamente su comando esplicito dell'utente (icona mirino o comando vocale *"Guarda cosa c'è a schermo"*).
- **Provider Agnostico (Vision-Capable):** L'acquisizione del fotogramma viene elaborata dal router di inferenza tramite un **Vision-capable provider** configurato (locale o cloud), senza vincolare il codice a specifici modelli commerciali o versioni transitorie.
- **Assistenza Visiva Non Invasiva:** L'HUD del Companion può proiettare sulla propria superficie trasparente sovrapposta annotazioni visive (evidenziazione di aree, frecce di guida, spiegazioni del testo) senza interferire direttamente con il controllo fisico del cursore dell'utente.
- **Privacy e Mascheramento:** Rilevamento preventivo di campi sensibili (password, numeri finanziari) con oscuramento prima dell'invio al provider di intelligenza visiva.

### 5.4 Risoluzione della Scorciatoia Globale su macOS
- Risoluzione dei conflitti storici di `Option+Space` sostituendo il default con `Command+Shift+Space`.
- Integrazione delle dichiarazioni di capability native in Tauri v2 (`capabilities/default.json`).
- Controllo programmatico all'avvio dei permessi di Accessibilità macOS (`AXIsProcessTrustedWithOptions`) con notifica amichevole e apertura automatica delle Impostazioni di Sistema in caso di permesso mancante.
- Auto-dismiss immediato su evento di `blur` / perdita di fuoco della finestra dell'HUD.

---

## 6. PROVIDER AUTH ARCHITECTURE — PUBLIC CLIENT VS CONFIDENTIAL CLIENT

Questa sezione formalizza una **decisione architetturale ufficiale e vincolante** di Aether: come conciliare la natura open-source e desktop locale dell'applicazione con i modelli di sicurezza OAuth imposti dai grandi provider.

### 6.1 Il Principio Fondamentale
> **Regola Architetturale Fondamentale:**
> *Aether must never embed or depend on the confidentiality of a provider client secret inside the open-source desktop application.*

Un client desktop distribuito pubblicamente (open-source binario o repository) opera per definizione nell'ambiente dell'utente e non può mantenere confidenziale un segreto. I provider revocano o rifiutano le applicazioni che espongono segreti confidenziali nei client nativi.

Pertanto, l'architettura distingue rigorosamente:

```
+------------------------------------------------------------------------------------+
|                               MODELLI DI CLIENT OAUTH                              |
+------------------------------------------------------------------------------------+
|  A. PUBLIC CLIENT (Ideale per Desktop / Open-Source)                               |
|     • Non fa affidamento sulla segretezza del client_secret                        |
|     • OAuth 2.0 Authorization Code con PKCE (RFC 7636)                             |
|     • Device Authorization Flow (RFC 8628) quando appropriato e documentato        |
|     • La sicurezza poggia su code_verifier, code_challenge dinamico e state        |
|------------------------------------------------------------------------------------|
|  B. CONFIDENTIAL CLIENT (Richiede un Backend Broker Controllato)                   |
|     • Il client_secret risiede esclusivamente lato server nel cloud                |
|     • Richiede un Aether Auth Broker controllato dall'infrastruttura ufficiale     |
|     • La desktop app locale parla con il broker per lo scambio token / refresh     |
|     • La desktop app NON conosce né memorizza mai i segreti del provider          |
+------------------------------------------------------------------------------------+
```

### 6.2 Matrice Ufficiale dei Provider

La seguente tabella stabilisce la strategia di autenticazione tecnicamente valida per ciascun provider, senza mai inventare supporto PKCE o Device Flow non documentato:

| Provider | Strategia di Autenticazione | Desktop Diretto? | Broker Necessario? | Note Architetturali |
|---|---|:---:|:---:|---|
| **Google** | Authorization Code + PKCE | **Sì** | Opzionale | Modello ufficiale Google per "Native / Installed App" (loopback redirect su porta effimera). Il client desktop opera come public client; eventuali identificatori distribuiti non sono trattati come segreti confidenziali. La sicurezza del flusso poggia rigorosamente su PKCE (`code_verifier` / `code_challenge`), `state` e corretta validazione del loopback redirect, non sulla segretezza di un `client_secret`. |
| **GitHub** | GitHub App / OAuth App (PKCE o Device Flow) | **Sì** (a seconda del flow scelto) | Opzionale | Distinguere chiaramente tra **GitHub App** (raccomandata per granularità dei permessi, accesso selettivo ai repository e token temporanei) e **GitHub OAuth App** tradizionale. Preferire il flusso browser + PKCE quando appropriato; utilizzare il Device Authorization Flow solo quando specificamente giustificato da vincoli di redirect/headless (non usarlo per pigrizia semplicemente perché "desktop"). |
| **Slack** | OAuth v2 | **No** (per confidential app Aether) | **Sì** | Le Slack App standard richiedono un `client_secret` lato server per lo scambio del codice. Vietato distribuire il secret nel binario desktop; richiede Aether Auth Broker nel deployment hosted o configurazione developer BYOA nel deployment locale standalone. |
| **Notion** | OAuth 2.0 | A seconda del modello | **Probabile** | L'endpoint `/v1/oauth/token` di Notion richiede autenticazione con `client_secret` confidenziale lato server. Richiede Auth Broker cloud oppure token interno per integrazioni workspace (Internal Integration Token) in locale. |
| **Telegram** | Bot Token / Webhook Setup | **Sì** | **No** | Non è OAuth. Setup guidato tramite `@BotFather`: token inserito dall'utente e salvato cifrato nel SecretStore locale. |
| **Model Context Protocol (MCP)** | Autenticazione specifica del server MCP | Dipende | Dipende | L'autenticazione appartiene al server/provider MCP specifico (STDIO locale o Bearer remoto). |
| **Generic REST / OpenAPI** | API Key / Bearer / OAuth custom | Dipende | Dipende | Autenticazione dichiarata dallo schema dell'endpoint. Mai fabbricare connettività fittizia. |

### 6.3 I Due Modelli di Distribuzione (Deployment Models)

#### Modello 1: Aether Open Source / Local (Desktop Locale Standalone)
L'utente esegue Aether sul proprio computer senza dipendere da servizi cloud centralizzati:
- **Zero Segreti Confidenziali Embedded:** Nessun provider `client_secret` confidenziale viene incorporato nel pacchetto open-source o compilato nel binario Tauri.
- **Public-Client OAuth Nativo:** Per provider come Google e GitHub, l'app usa direttamente flussi con PKCE o Device Flow, parlando direttamente con gli endpoint del provider via browser di sistema.
- **Developer Configuration / Setup Guidato (BYOA):** Per provider che impongono un confidential client (es. Slack, Notion) in assenza di un broker ufficiale, Aether richiede che l'utente inserisca le proprie credenziali sviluppatore all'interno della sezione dedicata.
- **Nessuna Falsa Connessione:** Vietato simulare un "One-Click" se l'architettura tecnica del provider non lo rende possibile in locale.

#### Modello 2: Aether Hosted / Cloud (Con Aether Auth Broker)
Quando l'utente utilizza la distribuzione ufficiale supportata dall'infrastruttura di Aether:
- L'infrastruttura include un **Aether Auth Broker** sicuro e conforme.
- Il broker custodisce i `client_secret` registrati ufficialmente per Aether, gestisce gli endpoint di callback pubblici e coordina lo scambio protetto dei token di autorizzazione.
- L'applicazione desktop locale dialoga con l'Auth Broker tramite canali cifrati con token di sessione autenticato.
- La desktop app riceve solo i token utente finali da memorizzare nel `SecretStore` locale AES-GCM, senza mai entrare in contatto con i segreti applicativi del provider.

### 6.4 Il Concetto di "One-Click Connection" Correttamente Definito
Nel contesto di Aether:
> **"One-Click Connection" significa una UX chiara, intuitiva e guidata per l'utente, non l'assenza di un backend di intermediazione.**

- **Google:** `Connetti` → apre il browser di sistema su Google OAuth (Authorization Code + PKCE per Native Apps) → consenso utente → callback locale su porta effimera loopback → probe reale → connettore collegato.
- **GitHub:** `Connetti` → apre il flusso ufficiale GitHub (browser + PKCE o Device Flow a seconda del modello App/OAuth scelto) → autorizzazione utente → probe reale → connettore collegato.
- **Slack:** `Connetti` → apre il flusso tramite Aether Auth Broker (oppure, nel modello open-source puro, setup guidato della propria Slack App).
- **Telegram:** `Configura` → setup guidato semplice e amichevole, poiché Telegram impiega token bot e non OAuth.
- **Provider senza registrazione Aether o Broker:** Mostra esplicitamente lo stato `Configurazione Iniziale Richiesta` (`SETUP_REQUIRED`), mai un falso badge `Collegato`.

### 6.5 Integrazione con il Connector State Model

Gli stati del connettore riflettono fedelmente l'infrastruttura di autenticazione:

> **Il Modello Veritiero di `CONNECTED`:**
> `CONNECTED` ≠ "OAuth completato"
> `CONNECTED` deve significare rigorosamente che:
> 1. L'autorizzazione utente è stata completata con successo;
> 2. La credenziale o token è stata acquisita;
> 3. Il token è archiviato cifrato in modo sicuro nel SecretStore locale;
> 4. Un **probe reale** contro l'endpoint del provider ha avuto esito positivo (health check attivo con risposta valida);
> 5. Le capability dichiarate sono realmente utilizzabili ed esecutive.

| Stato Backend | Badge Interfaccia | Descrizione Reale | Azione Disponibile |
|---|---|---|---|
| `NOT_CONFIGURED` | Grigio: *Non collegato* | Il servizio non è configurato e non è attiva alcuna sessione. | **[Collega con 1 Clic]** |
| `SETUP_REQUIRED` | Giallo: *Configurazione richiesta* | Mancano prerequisiti strutturali (es. broker non disponibile o credenziali developer richieste). Non è un workaround temporaneo ma uno stato reale. | **[Configura]** |
| `CONNECTING` | Blu: *Autorizzazione in corso...* | È stata aperta la pagina del browser per l'autorizzazione dell'utente. | Spinner + **[Annulla]** |
| `CONNECTED` | Verde: *Collegato e attivo* | Token presente nel SecretStore e probe reale di salute superato con successo. | **[Gestisci]** o **[Disconnetti]** |
| `EXPIRED` | Arancione: *Accesso scaduto* | Il refresh token è revocato o scaduto. Richiede nuova autorizzazione. | **[Riconnetti]** |
| `ERROR` | Rosso: *Errore di connessione* | Chiamata API fallita, errore di rete o parametri respinti dal provider. | **[Risolvi Problema]** |

### 6.6 Regole Architetturali Vincolanti
1. **Regola sui Segreti:**
   > *Aether must never embed or depend on the confidentiality of a provider client secret inside the open-source desktop application.*
2. **Regola sulla Verità dello Stato:**
   > *Aether must never claim a provider is CONNECTED until a real provider authorization, secure token storage, and health probe verification flow have succeeded.*

---

## 7. PROVIDER & AUTH REGISTRATION LAYER

Il **Provider & Auth Registration Layer** governa la separazione strutturale tra gestione delle credenziali di registrazione e sessioni utente:

```
+---------------------------------------------------------------------------------+
|                     PROVIDER & AUTH REGISTRATION LAYER                          |
+---------------------------------------------------------------------------------+
|  1. PUBLIC CLIENT FLOWS        | Gestione autonoma dei protocolli PKCE e        |
|     (Nativi per Desktop)       | Device Flow senza intermediari (Google, GitHub)|
|--------------------------------+------------------------------------------------|
|  2. BROKER CLIENT FLOWS        | Integrazione trasparente con Aether Auth Broker|
|     (Per Confidential Apps)    | per servizi che esigono client_secret server.  |
|--------------------------------+------------------------------------------------|
|  3. DEVELOPER BYOA MODE        | Modalità "Bring Your Own App" per ambienti     |
|     (Self-hosted / Avanzati)   | completamente disconnessi o tenant dedicati.   |
|--------------------------------+------------------------------------------------|
|  4. USER SESSION STORAGE       | Cifratura token utente finale in SecretStore   |
|     (Locale AES-GCM-256)       | con secure local secret storage (OS-backed     |
|                                | secure storage dove disponibile; protezione    |
|                                | hardware dove supportata dalla piattaforma).   |
+---------------------------------------------------------------------------------+
```

---

## 8. RISK-BASED PERMISSION MODEL & EXECUTION BOUNDARY

### 8.1 Superamento del Modello Semplificato (Read vs Write)
La distinzione elementare *READ = sempre sicuro / WRITE = insicuro* è insufficiente nei contesti reali: leggere una cartella di posta riservata contenente dati legali o finanziari può avere un impatto sulla privacy molto più critico rispetto alla scrittura di una nota bozza locale.

Aether adotta un **Modello di Rischio Multidimensionale** integrato in `ExecutionAuthority`:

$$\text{Rischio} = f(\text{Azione}, \text{Sensibilità Dati}, \text{Destinazione}, \text{Reversibilità}, \text{Ruolo Agente}, \text{Contesto})$$

### 8.2 I Tre Livelli di Rischio e le Policy di Azione

```
+---------------------------------------------------------------------------------+
|  LIVELLO DI RISCHIO   | ESEMPI DI OPERAZIONI            | POLICY DI DEFAULT     |
+-----------------------+---------------------------------+-----------------------+
|  BASSO (Low Risk)     | • Lettura calendario personale  | ALLOW                 |
|                       | • Ricerca issue pubbliche       | (Esecuzione autonoma, |
|                       | • Creazione bozza locale        | tracciata in audit)   |
|-----------------------+---------------------------------+-----------------------+
|  MEDIO (Medium Risk)  | • Lettura repository privato    | ASK (prima volta)     |
|                       | • Creazione ticket / issue      | oppure ALLOW se       |
|                       | • Spostamento evento calendario | approvato nel piano   |
|-----------------------+---------------------------------+-----------------------+
|  ALTO (High Risk)     | • Lettura email riservate / fin | ASK                   |
|                       | • Invio email all'esterno       | (Approvazione esplic. |
|                       | • Cancellazione eventi / dati   | obbligatoria per ogni |
|                       | • Merge PR / Commit su main     | singola mutazione)    |
+---------------------------------------------------------------------------------+
```

### Le Tre Risposte dell'Execution Authority:
- **`ALLOW`:** L'azione viene eseguita silenziosamente nel runtime, registrata nell'Audit Log.
- **`ASK`:** L'azione viene sospesa; Aether genera una scheda di autorizzazione contestuale nell'HUD del Companion o nel Desktop, mostrando destinatario, payload e impatto.
- **`DENY`:** L'azione viene bloccata preventivamente (es. violazione policy SSRF, accesso a percorso di sistema non autorizzato, scope non presente nel token).

---

## 9. CONNECTOR ECOSYSTEM & VALIDATION SET INIZIALE

### 9.1 Regola di Sviluppo: Eccellenza Prima dell'Espansione
> **Regola Architetturale:** *Non implementare decine di connettori contemporaneamente. È tassativo perfezionare prima l'architettura su un piccolo set rappresentativo che copra tutte le combinazioni di autenticazione, permessi e flussi operativi.*

### 9.2 Validation Set Iniziale — 7 Connettori Core + MCP (8 Componenti Chiave)
Questo set di connettori dimostra la completezza dell'architettura prima di estendere il catalogo a servizi secondari:

1. **Google Calendar (Google Workspace):** Dimostra OAuth 2.0 Authorization Code + PKCE nativo per Desktop Public Client, refresh offline automatico, capability `SEARCH`, `READ`, `WRITE`, `SYNC`.
2. **Gmail (Google Workspace):** Dimostra gestione di dati ad alta sensibilità, capability `READ` protetta, invio bozze con `ASK` obbligatorio prima dell'invio.
3. **Google Drive (Archiviazione Cloud):** Dimostra scansione documentale, recupero contesto per RAG e rispetto delle quote via PKCE.
4. **GitHub (Sviluppo & Codice):** Dimostra GitHub App o OAuth con browser PKCE / Device Flow nativo per Public Client, permessi repository selettivi, gestione branch/PR e interazione complessa con la Workforce di sviluppo.
5. **Slack (Comunicazione Team):** Dimostra il modello Confidential Client supportato da Auth Broker (o developer credentials BYOA in modalità self-hosted), invio aggiornamenti su canali dedicati, notifiche asincrone.
6. **Telegram (Messaggistica Personale & Bridge):** Dimostra setup guidato basato su token bot protetto, messaggi bidirezionali e interazione remota.
7. **Notion (Produttività & Note):** Dimostra token interni workspace o OAuth con broker, mappatura database e aggiornamento pagine di progetto.
8. **Model Context Protocol (MCP Host):** Dimostra l'interoperabilità con tool standard aperti locali e remoti.

---

## 10. IL RUOLO DI MCP (MODEL CONTEXT PROTOCOL)

### 10.1 MCP come Open Interoperability Layer, NON Sostituto dei Connettori Nativi
L'architettura distingue chiaramente quando impiegare un connettore nativo e quando affidarsi al protocollo MCP:

```
                      NECESSITÀ DI INTEGRAZIONE ESTERNA
                                      |
              +-----------------------+-----------------------+
              |                                               |
              v                                               v
     CONNETTORE NATIVO                                 CONNETTORE MCP
  (Preferito per servizi core)                   (Per estendibilità aperta)
              |                                               |
  • API ufficiale matura e stabile               • Ecosistema open source esterno
  • Autenticazione OAuth ufficiale               • Tool specialistici di terze parti
  • Controllo granulare sulla UX                 • Database aziendali personalizzati
  • Supporto per webhook nativi e SYNC           • Tool locali a riga di comando (CLI)
  • Sicurezza e audit deterministici             • Risorse e prompt remoti condivisi
```

### 10.2 Linee Guida per l'Adozione MCP in Aether:
1. **Connettori Nativi per i Servizi Quotidiani:** Google, GitHub, Slack e Telegram beneficiano di connettori nativi scritti per offrire la massima fluidità e sicurezza senza richiedere l'avvio di processi MCP ausiliari.
2. **Aether come MCP Host Aperto:** Aether implementa il ruolo di Host MCP conforme alla specifica aperta standard.
3. **Specifiche Aggiornate al Momento dell'Implementazione:** L'implementazione del client MCP seguirà le specifiche correnti al momento dello sviluppo (incluso il supporto per i trasporti standard come STDIO per tool locali e stream HTTP/SSE per endpoint remoti), senza vincolare preventivamente il runtime a singole librerie transitorie o schemi deprecati.

---

## 11. CLOUD MODEL FALLBACK & POLICY DI TRASPARENZA

### 11.1 Risoluzione del Problema Riscontrato nei Test ("Method Not Allowed")
Quando un provider locale (come Ollama) è spento o non raggiungibile, Aether non deve mai generare errori tecnici oscuri (come HTTP 405 o eccezioni non gestite) né bloccarsi.

### 11.2 Regola di Trasparenza sui Fallback Cloud
> **Regola di Privacy e Costi:** *Aether NON deve MAI cambiare provider o spostare una richiesta su modelli cloud silenziosamente o in modo invisibile all'utente, specialmente se ciò altera la confidenzialità dei dati, la residenza delle informazioni o genera costi a consumo.*

```text
                  Richiesta di Elaborazione (es. Social Repurpose)
                                        |
                                        v
                            Verifica Provider Locale
                                        |
                    +-------------------+-------------------+
                    |                                       |
                    v (Disponibile)                         v (Non Raggiungibile)
            Esecuzione Locale                       Rilevamento Stato
                                                            |
                                                            v
                                            +-------------------------------+
                                            |   MODALE / DIALOG INFORMATIVO  |
                                            |   "Il motore locale è spento" |
                                            +-------------------------------+
                                                            |
                                        +-------------------+-------------------+
                                        |                                       |
                                        v                                       v
                           [ Usa Modello Cloud ]                       [ Avvia Motore Locale ]
                           (Mostra costi/privacy e                     (Guida o tentativo di
                            richiede conferma utente)                   avvio del servizio)
```

1. **Se il motore locale è attivo:** L'elaborazione procede normalmente in locale.
2. **Se il motore locale non è attivo ma esiste un provider cloud configurato e verificato:** Aether informa l'utente con linguaggio naturale:
   *"Il motore di intelligenza locale non è attualmente attivo. Desideri utilizzare il modello cloud configurato per completare questa operazione?"*
3. **Se nessun provider cloud è configurato o utilizzabile:** Aether mostra esplicitamente lo stato:
   *"Nessun motore di intelligenza artificiale attivo. Avvia il motore locale oppure configura una chiave API cloud nelle Impostazioni."*
   Non viene simulato alcun risultato, non vengono generati dati fittizi e non viene creata alcuna falsa missione completata.
4. **Nessun cambio silenzioso:** L'utente mantiene sempre il controllo su dove transitano i propri dati personali.

---

## 12. AETHER DESIGN SYSTEM & FORM SYSTEM

### 12.1 Principi Guida Visivi
Il design di Aether unisce:
- **La pulizia e il respiro di Apple:** Bordi arrotondati calibrati (`rounded-xl` per le card, `rounded-lg` per i controlli), sfondi neutri opachi e translucidi (`backdrop-blur-md`), tipografia proporzionata.
- **La precisione e l'efficienza di Linear:** Contrasti chiari tra stati attivi e inattivi, micro-interazioni immediate, scorciatoie da tastiera visibili, assenza di elementi decorativi inutili.
- **La solidità e la modernità di Vercel:** Palette scura profonda e raffinata, bordi sottili e precisi (`border-zinc-800`), badge di stato minimali.

### 12.2 Struttura dei Componenti Condivisi
Tutti i componenti saranno collocati nella directory unificata `ui/src/design-system/`:

```
ui/src/design-system/
|-- layout/
|   |-- PageContainer.tsx      # Contenitore con padding e max-width coerenti
|   |-- Section.tsx            # Sezione logica con titolo, descrizione e azioni
|   |-- Stack.tsx              # Disposizione verticale/orizzontale flessibile
|   |-- Grid.tsx               # Griglia responsive standardizzata
|   |-- Panel.tsx              # Riquadro contenitore con bordo e sfondo scuro
|   |-- Modal.tsx              # Dialog modale accessibile con overlay scuro
|   `-- Drawer.tsx             # Pannello a scorrimento laterale
|-- typography/
|   |-- Heading.tsx            # Livelli H1, H2, H3, H4 con stili prefissati
|   |-- Text.tsx               # Testo corpo, muted, piccolo, codice inline
|   `-- Label.tsx              # Etichetta form semantica con supporto a campi obbligatori
|-- controls/
|   |-- Button.tsx             # Primario, Secondario, Terziario, Pericolo, con loading spinner
|   |-- IconButton.tsx         # Pulsante icona accessibile con tooltip integrato
|   |-- Switch.tsx             # Leva on/off accessibile per abilitazione funzioni
|   |-- SegmentedControl.tsx   # Selettore a tab a scorrimento (stile iOS/macOS)
|   |-- Select.tsx             # Menu a tendina coerente con tema scuro
|   `-- Checkbox.tsx           # Casella di spunta accessibile
|-- feedback/
|   |-- StatusBadge.tsx        # Pallino colorato + testo stato (Connesso, Errore, In attesa)
|   |-- AlertBanner.tsx        # Riquadro info, avviso o errore con icona e testo chiaro
|   |-- EmptyState.tsx         # Stato vuoto amichevole con icona, titolo, testo e azione
|   `-- LoadingSpinner.tsx     # Indicatore di caricamento standard
`-- form/
    |-- AetherForm.tsx         # Wrapper form con gestione submit e stato globale
    |-- AetherFormSection.tsx  # Raggruppamento campi con titolo e separatore
    |-- AetherField.tsx        # Wrapper singolo campo: etichetta + controllo + helper + errore
    |-- AetherInput.tsx        # Input di testo con icone, prefissi e validazione
    |-- AetherPasswordInput.tsx# Input password con pulsante mostra/nascondi integrato
    |-- AetherSelect.tsx       # Menu a tendina con ricerca opzionale
    |-- AetherTextarea.tsx     # Area di testo espandibile con conteggio caratteri
    |-- AetherHelperText.tsx   # Testo di aiuto sotto il campo
    |-- AetherFormError.tsx    # Messaggio di errore in italiano con animazione
    `-- AetherFormActions.tsx  # Barra pulsanti in fondo al form (Annulla / Salva)
```

---

## 13. UI/UX OVERHAUL & SERVIZI COLLEGATI

### 13.1 La Regola del Nonnino come Criterio di Accettazione (DoD)
Ogni schermata di Aether deve rispondere a 5 domande prima di essere considerata approvata:
1. **Cosa deve capire l'utente a colpo d'occhio?** (Lo scopo primario della pagina deve emergere in 3 secondi).
2. **Qual è l'azione principale da compiere?** (Deve esserci un solo pulsante dominante per sezione).
3. **Cosa può essere nascosto o differito?** (Tutti i tecnicismi e i dati grezzi finiscono dietro "Opzioni Avanzate").
4. **Quali parole sono inutilmente tecniche o oscure?** (Sostituire ogni gergo con il glossario canonico italiano).
5. **Quale stato reale deve essere evidente?** (Nessun valore a zero ingannevole; se un servizio non è attivo, spiegarne chiaramente il motivo).

### 13.2 La Nuova Schermata: "Servizi Collegati"
La vecchia pagina "Connections" viene ribattezzata **"Servizi Collegati"** e ripensata per l'utente comune:

```text
+---------------------------------------------------------------------------------+
| SERVIZI COLLEGATI                                                               |
| Collega le tue applicazioni quotidiane per consentire ad Aether di aiutarti.   |
+---------------------------------------------------------------------------------+
|                                                                                 |
|  [ G ] Google Calendar                                                          |
|        Sincronizza e gestisce i tuoi appuntamenti quotidiani                    |
|        Stato: [ ● Collegato e attivo ]                     [ Gestisci ]         |
|                                                                                 |
|  [ M ] Gmail                                                                    |
|        Cerca e prepara bozze di risposta per le tue email                       |
|        Stato: [ ○ Non collegato ]                          [ Collega con 1 Clic]|
|                                                                                 |
|  [ G ] GitHub                                                                   |
|        Esamina i tuoi progetti, crea rami e prepara modifiche                   |
|        Stato: [ ● Collegato e attivo ]                     [ Gestisci ]         |
|                                                                                 |
|  [ S ] Slack                                                                    |
|        Condivide aggiornamenti sui canali e notifica il team                    |
|        Stato: [ ○ Configurazione Richiesta ]               [ Configura ]        |
|                                                                                 |
+---------------------------------------------------------------------------------+
| [ > Opzioni Avanzate per Sviluppatori ]                                         |
|     (Credenziali personalizzate Google Cloud, Client ID custom, Scopes, Log)    |
+---------------------------------------------------------------------------------+
```

---

## 14. STRATEGIA DI LOCALIZZAZIONE & GLOSSARIO ITALIANO

### 14.1 Glossario Canonico Italiano di Aether

| Termine Tecnico Originale | Traduzione Ufficiale in Aether Italiano | Significato Pratico per l'Utente |
|---|---|---|
| **Execution Fabric / Hardware Mesh** | **Potenza e Risorse del Computer** | Indica le risorse del computer dedicate all'intelligenza artificiale. |
| **Zero-simulation hardware probing** | **Verifica delle risorse in tempo reale** | Misura reale della potenza del computer senza stime simulate. |
| **Metal / CUDA VRAM Pool** | **Memoria Scheda Video (GPU)** | Memoria grafica disponibile per eseguire i modelli locali. |
| **Compute Cores / Native Threads** | **Processore Principale (CPU)** | Potenza di calcolo per le attività di coordinamento e codice. |
| **Intelligent Workload Router** | **Gestione Intelligente dei Compiti** | Assegna automaticamente il lavoro al modello più indicato. |
| **Connector / Integration** | **Servizi Collegati** | Le tue app esterne collegate (Google, GitHub, Slack, ecc.). |
| **Personal Access Token (PAT)** | **Chiave di Accesso Personale** | Password di servizio fornita dal provider esterno. |
| **Redirect URI / Callback** | **Indirizzo di Rientro Sicuro** | Pagina su cui ritorna il browser al termine dell'accesso. |
| **Workforce / Multi-agent Mesh** | **I Tuoi Assistenti AI** | Squadra di assistenti specializzati al tuo servizio. |
| **Deliverable** | **Risultato Finale del Lavoro** | Il documento, codice o piano prodotto dagli assistenti. |
| **Mission** | **Obiettivo di Lavoro** | Un progetto strutturato con inizio, verifiche e conclusione. |
| **Approval Gate** | **Richiesta di Autorizzazione** | Quando Aether chiede il tuo permesso prima di un'azione importante. |
| **Flight Recorder Replay** | **Cronologia Dettagliata delle Azioni** | Visualizzazione passo-passo di tutto ciò che è stato eseguito. |

---

## 15. BENCHMARK & RICERCA UFFICIALE SUI PROVIDER

*(Riepilogo delle evidenze ufficiali documentate da OpenAI, Anthropic e Google Gemini, come analizzato nella revisione precedente: convergenza su OAuth 2.0 PKCE per native apps, autorizzazione esplicita prima di mutazioni esterne, standard MCP e categorizzazione Connected Apps).*

---

## 16. ROADMAP DI IMPLEMENTAZIONE SEQUENZIATA (FASE 0 - FASE 8)

La roadmap è strutturata per costruire prima le fondamenta dell'esperienza utente e del runtime, collegando i connettori e la workforce in modo naturale ed evitando sovrapposizioni o refactor disordinati:

```
FASE 0: Design System & Form System Core
  │
  ▼
FASE 1: Companion Runtime Surface (micro-HUD & scorciatoia macOS/Win)
  │
  ▼
FASE 2: Context & Capability Router + Connector Platform Foundation (Public Client & Broker Models)
  │
  ▼
FASE 3: Tier 1 Connectors (Validation Set: Google PKCE, GitHub Native, Slack Broker/BYOA, Telegram)
  │
  ▼
FASE 4: Dynamic Workforce Assembly (Assemblaggio dinamico basato su capability)
  │
  ▼
FASE 5: Mission / Connector / Workforce Integration (Golden Path end-to-end)
  │
  ▼
FASE 6: Complete UI/UX Overhaul (Regola del nonnino su tutte le schermate)
  │
  ▼
FASE 7: Screen Understanding & Assistenza Ambientale
  │
  ▼
FASE 8: Expansion + MCP Ecosystem + Production Gate
```

### Dettaglio Fasi:

- **Fase 0 — Design System & Form System Core:** Creazione della cartella `ui/src/design-system/` con tutti i componenti layout, tipografia, controlli, feedback e form riutilizzabili.
- **Fase 1 — Companion Runtime Surface:** Scorciatoia globale (`Cmd+Shift+Space`), verifica permessi macOS Accessibility, micro-HUD e gestione del ciclo di vita come superficie del runtime (non seconda app).
- **Fase 2 — Context & Capability Router + Connector Platform Foundation:** Motore decisionale di interpretazione intento, generazione context pack, least privilege, modello a oggetti del registro connettori, formalizzazione dell'architettura Public Client (PKCE nativo) vs Confidential Client (Auth Broker / BYOA) con zero segreti confidenziali embedded.
- **Fase 3 — Tier 1 Connectors (Validation Set — 7 Connettori Core + MCP):** Onboarding dei connettori del Validation Set conformemente al modello di auth (Google PKCE diretto nativo, GitHub browser PKCE o Device Flow, Slack con Auth Broker nel cloud o developer BYOA in open-source standalone, Telegram con setup bot guidato, Notion) con verifica rigorosa degli stati (`SETUP_REQUIRED`, `CONNECTED`).
- **Fase 4 — Dynamic Workforce Assembly:** Meccanismo per comporre dinamicamente squadre di agenti in base ai bisogni della missione, superando le strutture rigide hardcodate.
- **Fase 5 — Mission / Connector / Workforce Integration:** Connessione end-to-end: intento -> contesto -> connettori -> assemblea -> esecuzione -> approvazione -> verifica -> notifica.
- **Fase 6 — Complete UI/UX Overhaul:** Riprogettazione di Home, Prestazioni e Risorse, Creazione Contenuti Social, eliminando testi densi, errori 405 e gergo tecnico.
- **Fase 7 — Screen Understanding & Assistenza Ambientale:** Integrazione della comprensione dello schermo on-demand tramite provider vision-capable e overlay di annotazione visiva.
- **Fase 8 — Expansion + MCP Ecosystem + Production Gate:** Supporto per il client MCP conforme agli standard aperti, estensione a connettori secondari (Tier 2/3), audit di sicurezza e release finale.

---

## 17. STRATEGIA DI TESTING & VERIFICA

1. **Test del Router di Contesto:** Verificare che a fronte di prompt diversi il router selezioni il set minimo di capability e connettori senza concedere accessi superflui.
2. **Test di Assemblaggio della Workforce:** Verificare che per compiti di coding, marketing o segreteria vengano istanziati solo i ruoli pertinenti con i relativi tool.
3. **Test di Autenticazione e Sicurezza Token:** Test automatici su cifratura `SecretStore` AES-GCM, verifica del protocollo PKCE (generazione `code_verifier` e `code_challenge`), assenza totale di segreti confidenziali embedded nei binari, probe di stato veritieri (`SETUP_REQUIRED`, `CONNECTED` con health check reale riuscito, `EXPIRED`) e blocco SSRF.
4. **Manual Smoke Checklist Aggiornata (Senza Ollama Attivo):**
   - [ ] Apertura a freddo: l'app si avvia istantaneamente senza crash e segnala lo stato del motore in italiano semplice.
   - [ ] Invocazione Companion (`Cmd+Shift+Space`): il micro-HUD appare al centro dello schermo in <150ms e scompare con `Esc`.
   - [ ] Navigazione "Servizi Collegati": la pagina scorre fluidamente con la rotella del mouse e mostra card pulite con stato reale.
   - [ ] Onboarding Google/GitHub: l'autorizzazione si apre nel browser ufficiale con PKCE / Device Flow senza richiedere segreti confidenziali all'utente comune.
   - [ ] Gestione Provider Confidential (Slack): in assenza di broker, l'app mostra chiaramente `SETUP_REQUIRED` senza mai fingere una connessione.
   - [ ] Fallback Cloud Resiliente: se Ollama è spento e non c'è alcun provider cloud configurato, l'app mostra un avviso trasparente e non simula missioni completate.
   - [ ] Approvazione Azioni: un'operazione ad alto rischio (es. invio email o merge) genera una chiara scheda di approvazione preventiva.

---

## 18. RISCHI, DIPENDENZE & LIMITAZIONI TECNICHE

1. **Verifica delle App OAuth presso i Provider:** Google e Slack richiedono revisioni formali per l'uso pubblico degli scopes sensibili. Fornire indicazioni rassicuranti all'utente per l'uso personale e la possibilità di "Credenziali Sviluppatore" per chi desidera il controllo assoluto.
2. **Permessi di Sistema Operativo su macOS:** macOS può revocare o richiedere il rinnovo dei permessi di Accessibilità e Screen Recording dopo ogni ricompilazione dell'eseguibile. Il runtime deve rilevare preventivamente lo stato del permesso e offrire un pulsante diretto per le Impostazioni di Sistema.
3. **Consumo di Token e Costi Cloud:** L'instradamento verso modelli cloud deve sempre rispettare la trasparenza di spesa con avvisi chiari se il motore locale non è attivo.
4. **Dipendenza dal Broker per Confidential Clients:** Per le installazioni open-source standalone che non usano l'Auth Broker ospitato, i servizi confidenziali (Slack, Notion) richiedono configurazione manuale da parte dell'utente. Questa limitazione tecnica è esplicitata e documentata con onestà.

---

## 19. NUOVA DEFINITION OF DONE GLOBALE

Il completamento della trasformazione di Aether sarà certificato quando tutti i seguenti criteri saranno pienamente soddisfatti:

1. **Personal Assistant ("Aether, pensaci tu"):** L'utente può formulare un obiettivo in linguaggio naturale senza dover scegliere manualmente agenti, connettori o workflow tecnici.
2. **Context Retrieval Deterministico:** Aether raccoglie automaticamente e autonomamente il contesto pertinente dalla memoria e dai connettori collegati.
3. **Connector Resolution Trasparente:** Aether individua e interroga le sole capability esterne necessarie per soddisfare la richiesta.
4. **Dynamic Workforce Assembly:** La squadra di agenti viene creata e dimensionata su misura per la missione, senza strutture rigide preconfezionate.
5. **Risk-Based Approval:** Qualsiasi azione ad alto impatto (invio comunicazioni, modifiche a repository o dati esterni) viene presentata chiaramente all'utente e attende il suo consenso prima di mutare lo stato.
6. **Execution Boundary Invalicabile:** Tutte le operazioni passano attraverso i gate di sicurezza di `ExecutionAuthority`, con protezione SSRF e audit log completo.
7. **Verifica Reale dei Risultati:** Aether convalida l'esito del lavoro (es. esecuzione test, verifica risposta API) prima di notificare il completamento.
8. **Companion Ambientale & Veloce:** Il Companion è un micro-HUD leggero, richiamabile al volo con la scorciatoia da tastiera e dismissibile con `Esc`, non una seconda finestra persistente.
9. **Esperienza Utente Semplice ("Regola del Nonnino"):** Qualsiasi persona non tecnica può utilizzare l'applicazione con disinvoltura, senza imbattersi in gergo da server farm, campi tecnici non necessari o errori di rete crudi.
10. **Truthfulness Assoluta & Zero Segreti Confidenziali Embedded:**
    - Aether non incorpora né dipende dalla confidenzialità di client secret di terze parti dentro l'applicazione desktop open-source.
    - Lo stato `CONNECTED` riflette esclusivamente il superamento di autorizzazione, salvataggio token sicuro nel SecretStore e probe reale di salute riuscito (mai il solo completamento OAuth).
    - Lo stato `SETUP_REQUIRED` è veritiero e indica una reale mancanza di prerequisiti applicativi.

---

## 20. COSA NON FARE O RINVIARE A FASI SUCCESSIVE

- **NON incorporare né dipendere dalla confidenzialità di client secret provider nel codice sorgente o nei binari desktop:** Rispettare rigorosamente il modello Public Client (PKCE) o demandare all'Aether Auth Broker o al developer setup (BYOA).
- **NON modificare i componenti core di sicurezza:** Nessuna alterazione non richiesta alla crittografia di `SecretStore`, al motore transazionale di `sqlite.py` o al modulo `security.py`.
- **NON creare finti connettori:** Nessuna scorciatoia simulata per provider che richiedono setup manuale; mostrare con onestà lo stato `Configurazione Richiesta` (`SETUP_REQUIRED`).
- **NON re-implementare librerie esterne pesanti:** Mantenere il frontend leggero con Tailwind CSS e componenti modulari React interni.
- **NON espandere i connettori Tier 3 prima del completamento del Validation Set:** Consolidare prima la perfezione dei 7 connettori core e dell'Host MCP.

---

## 21. EXECUTIVE SUMMARY (SINTESI DIREZIONALE)

```text
Cosa dobbiamo costruire per trasformare Aether da quello che è oggi nel prodotto che vogliamo:

1. Realizzare il Personal AI Office: l'utente non sceglie agenti o tool, ma dice semplicemente "Aether, pensaci tu".
2. Introdurre il Context & Capability Router: interpretare l'intento, estrarre il contesto e applicare least privilege.
3. Adottare la Dynamic Workforce Assembly: creare dinamicamente la squadra di agenti su misura per ogni missione.
4. Formalizzare la Provider Auth Architecture: Public Client (PKCE nativo su desktop, zero segreti embedded) e broker per confidential apps.
5. Implementare il Modello di Rischio Multidimensionale: superare "read=safe", richiedendo approvazione per azioni ad alto impatto.
6. Trasformare il Companion in un micro-HUD ambientale: scorciatoia globale rapida su macOS, invisibile, veloce e dismissibile con Esc.
7. Riprogettare la UI con la "regola del nonnino": eliminare il gergo tecnico, garantire scorrimento fluido e gestire fallback senza errori crudi.

Risultato: Aether smette di sembrare una dashboard per sviluppatori e diventa il primo vero Personal AI Workforce Operating System.
```
