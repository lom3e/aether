# P2 Roadmap — Product Polish, Branding & Distribution

**Milestone Target:** `v1.4.2`  
**Focus:** Website Polish, Real DMG Distribution, Fixed Purple Logo, Preset Icons, Design Tokens, Tooltips, Toast System  
**Status:** Planned  

---

## 1. Feature Specifications

---

### P2-A: Website — Visual Polish, Branding & Real Distribution

#### Obiettivo
Allineare il sito web ufficiale (`aether.dev` o landing page) con la realtà della release `v1.4.0 Alpha`, eliminando feature non ancora rilasciate, fissando l'identità visiva del brand ed esponendo il download diretto del bundle `.dmg`.

#### Dettagli degli Interventi
1. **Rimozione "Aether Studio"**: Eliminare ogni menzione o riferimento promozionale a "Aether Studio" per evitare ambiguità con il prodotto Aether Desktop.
2. **Logo Viola Fisso**: Standardizzare il branding su `logo_viola.svg` come identità visiva primaria ufficiale.
3. **Download Diretto macOS Apple Silicon (`.dmg`)**:
   * Sostituire bottoni generici con il link diretto alla release ufficiale GitHub per il download di `Aether.dmg`.
   * Mostrare badge di compatibilità chiaro: *macOS 13+ (Apple Silicon M1/M2/M3/M4)*.
4. **Tag / Versione Dinamico**:
   * Aggiornare automaticamente la versione mostrata sulla landing page (es. `v1.4.0 Alpha`) interrogando la GitHub API `/repos/lom3e/aether/releases/latest` o tramite workflow di build statico.
5. **Onestà sulle Piattaforme (Evitare False Advertising)**:
   * Per Windows e Linux, indicare chiaramente: *"Coming Soon in Q4 2026"* con pulsante *"Notify me"*, senza mostrare pulsanti di download ingannevoli per piattaforme non ancora disponibili.
6. **Animazioni e Fluidezza**:
   * Integrare transizioni moderne (CSS framer-like o scroll reveals leggeri) per le card delle feature e la showcase del prodotto.

#### Acceptance Criteria
```gherkin
Given:
  Un visitatore accede alla landing page del sito web.
When:
  Visualizza la hero section.
Then:
  Il logo visualizzato è il logo viola ufficiale.
  La versione mostrata coincide con l'ultima release GitHub pubblicata.
  Il pulsante "Download for macOS" scarica direttamente l'installer .dmg di Aether.
  Le opzioni Windows indicano "Coming Soon" senza consentire download non validi.
```

---

### P2-B: Desktop — Branding Fisso & Refinement Visivo (Teams, Agents, Knowledge)

#### Obiettivo
Elevare la qualità estetica dell'applicazione desktop native, portando Teams, Agents e Knowledge al medesimo livello di polish grafico della Chat e dell'Onboarding.

#### Dettagli degli Interventi
1. **Logo Viola Fisso nella Desktop Shell**:
   * Utilizzare il logo viola per gli splash screen, modali e TopHeader, mantenendo versioni monocromatiche chiare esclusivamente per il dark mode toggle contrastato.
2. **Preset Icons per Marketplace & Teams**:
   * Aggiungere icone grafiche distinte per ogni preset di team (es. `Starter Workforce` 🚀, `Product & Architecture` 🏛️, `Marketing & Content` ✍️, `Research Lab` 🔬).
3. **Miglioramento Estetico Vista Teams**:
   * Visualizzazione a schede con griglia ordinata, preview dei membri del team, badge di ruolo, numero di agenti e indicatore di team predefinito.
4. **Miglioramento Estetico Vista Agents**:
   * Card moderne con avatar colorati, lista compatta delle skill assegnate, indicatore del modello LLM utilizzato e pulsante di modifica rapida.
5. **Miglioramento Estetico Vista Knowledge**:
   * Tabella documenti elegante con suddivisione netta tra documenti di sistema (con badge "Ufficiale / Read-only") e documenti utente (con conteggio parole, data di aggiunta, azioni rapide di eliminazione).

---

### P2-C: Sistema Universale di Tooltips & Micro-interazioni

#### Obiettivo
Fornire feedback visivo immediato e spiegazioni contestuali per ogni pulsante, icona o metrica presente nell'interfaccia.

#### Dettagli degli Interventi
* Introduzione di un componente `<Tooltip content="..." delay={300} />` basato su CSS moderno con posizionamento automatico (top/bottom/left/right).
* Tooltip esplicativi per:
  * Indicatori di stato del provider.
  * Tasti di azione rapida nei messaggi (Copia, Modifica prompt, Riprova risposta, Elimina).
  * Badge delle skill e dei tool degli agenti.
  * Controlli della finestra e dello storico conversazioni.
* Micro-interazioni fluide (hover state con scala delicata `1.02`, transizioni di colore a `150ms ease`).

---

### P2-D: Toast Notification System Polish

#### Obiettivo
Rendere le notifiche toast non invasive, eleganti, raggruppabili e posizionate nell'angolo inferiore destro con supporto per icone contestuali (Success, Error, Info, Warning) e timer di dismiss visivo.

---

### P2-E: Visualizzazione Topologia del Team (Team Topology Graph)

#### Obiettivo
Consentire all'utente di visualizzare la struttura di delega del team attivo tramite un diagramma visivo compatto (Manager al centro con frecce di delega verso gli specialisti).

---

## 2. Elenco dei Task Atomici (P2)

| Task ID | Descrizione Operativa | Componenti Coinvolti | Stato |
| :--- | :--- | :--- | :--- |
| **P2-01** | **Website: Rimozione Studio e standardizzazione Logo Viola**: Pulizia testi, rimozione selettore multi-logo ed esportazione del logo viola ufficiale del brand. | `website/src/components/`, `website/src/app/` | **Completed (v1.5.0)** |
| **P2-02** | **Website: Aggiornamento versioni e Download DMG reale**: Download diretto `Aether.dmg`, pill di versione dinamica e compatibility strip macOS / Windows. | `website/src/components/AlphaCTA.tsx`, `website/src/lib/i18n/` | **Completed (v1.5.0)** |
| **P2-03** | **Website: Modern animations & mobile polish**: Animazioni hero interattive su canvas, particelle fluide e responsive optimization. | `website/src/components/Hero.tsx`, `website/src/components/` | **Completed (v1.5.0)** |
| **P2-04** | **Icone Preset per Marketplace & Team Builder**: Associazione icone tematiche a ciascun template manifest in `presets/builtin/manifest.yaml`. | `presets/`, `ui/src/Teams.tsx`, `ui/src/Marketplace.tsx`, `ui/src/identity.tsx` | **Completed (v1.5.0)** |
| **P2-05** | **Polish Visivo Viste Teams, Agents e Knowledge**: Applicazione card con hover effect, avatar ed identità semantica (`IdentityBadge`), badge semantici per provider/modello/scope e allineamento responsive. | `ui/src/Teams.tsx`, `ui/src/Agents.tsx`, `ui/src/Knowledge.tsx`, `ui/src/index.css` | **Completed (v1.5.0)** |
| **P2-06** | **Implementazione Componente Tooltip Universale**: Componente `<Tooltip>` con calcolo coordinate via portale React, supporto hover/focus, delay 200ms, auto-flip e accessibilità (`role="tooltip"`, `aria-label`). | `ui/src/Tooltip.tsx`, `ui/src/index.css`, `ui/src/*.tsx` | **Completed (v1.5.0)** |
| **P2-07** | **Refining Toast Notifications**: Sistema multi-toast con slide-in animato, timer bar con progress shrink, icone semantiche (success, error, warning, info), auto-dismiss con pause-on-hover, dismiss manuale e supporto screen reader (`role="status"` / `role="alert"`). | `ui/src/toast.tsx`, `ui/src/index.css`, `ui/src/App.tsx` | **Completed (v1.5.0)** |
| **P2-08** | **Visualizzatore Topologia Team**: Grafo SVG dinamico reattivo della workforce con nodi Manager (👑) e Specialist, frecce di delega orientate basate su `delegates_to`, identità semantica (icona, colore), hover highlighting interattivo e responsive design. | `ui/src/TeamTopology.tsx`, `ui/src/Teams.tsx`, `src/aether/server/routes.py` | **Completed (v1.5.0)** |
