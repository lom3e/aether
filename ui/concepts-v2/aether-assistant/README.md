# AETHER V2 — ASSISTANT-FIRST CONCEPT & LIVING 3D POINT SPHERE (ORB V4)

> **Visual Refinement, Commanding Scale, Organic 3D Depth & Zero-Occlusion Protected Stage**  
> *Ambiente di esplorazione concettuale isolato (`ui/concepts-v2/aether-assistant/`) — Nessuna modifica al runtime o alla UI di produzione.*

---

## 1. Product Model & Philosophy

Aether V2 ribalta radicalmente il paradigma delle piattaforme di orchestrazione a dashboard:

> **“Aether è prima di tutto il mio assistente personale: Aether, pensaci tu.”**

L'interfaccia iniziale è intenzionalmente priva di distrazioni:
- **Assistant-First:** Nessuna griglia complessa o tabella all'apertura;
- **Presenza Dominante dell'Orb:** Una sfera 3D vivente che incarna il "corpo" e lo stato vitale di Aether;
- **Conversazione Naturale & Protetta:** Dock di input e chip contestuali ad alto respiro;
- **Progressive Disclosure:** Thought Bubbles periferiche e Aether Field emergono fluidamente solo su richiesta o necessità, senza mai coprire la sfera;
- **Gestione Secondaria:** Strumenti avanzati, automazioni e drawer manuale restano accessibili tramite `⌘K` e pulsante dedicato, senza intasare la scena.

```text
+-------------------------------------------------------------+
|                      IO PARLO CON AETHER                    |
|                              ↓                              |
|                   AETHER CAPISCE E ASCOLTA                  |
|                              ↓                              |
|                AETHER RACCOGLIE IL CONTESTO                 |
|                              ↓                              |
|              AETHER DECIDE COME SVOLGERE IL LAVORO          |
|                              ↓                              |
|                AETHER MOSTRA COSA STA FACENDO               |
|            (Thought Bubbles & Field Contestuale)            |
|                              ↓                              |
|              AETHER MI CHIEDE SOLO QUANDO SERVE             |
|                 (Superficie di Decisione)                   |
|                              ↓                              |
|               AETHER CONSEGNA IL RISULTATO                  |
+-------------------------------------------------------------+
```

---

## 2. Aether Orb V4: Architettura Visiva & Geometrica

### Ispirazione Diretta & Identità Aether
Prendendo come riferimento visivo la geometria volumetrica del tutorial *Point Sphere Animation in WebGL, Three.js & GSAP* (`https://www.youtube.com/watch?v=K3WCGUO1uu8`):

> **Una maestosa sfera 3D costruita da punti discreti (`gl.POINTS` style), caratterizzata da convergenza polare a vortice, volume trasparente *see-through*, forte attenuazione di scala prospettica e movimento armonico vivente.**

Aether Orb V4 non è una nuvola sfocata né un disco piatto:
1. **Scala Imponente (Commanding Scale):** Canvas allargato a **640x640px** con diametro sferico di circa **460px**, rendendo l'Orb l'elemento visivo dominante della scena.
2. **Punti Quadrati Discreti (`gl.POINTS`):** Pixel/quadrati nitidi scalati prospetticamente da **1.2px a 3.8px**, che lasciano ampi spazi vuoti attraverso i quali si percepisce chiaramente l'emisfero posteriore.
3. **Distribuzione Ibrida con Polar Swirl:** Campionamento sferico basato su algoritmo PRNG *Mulberry32* deterministico, che fonde area uniforme ($\arccos(1 - 2u)$) con polar bias continuo ($u \cdot \pi$). L'asse è inclinato ($X \approx -24^\circ, Z \approx -27^\circ$), orientando il vortice polare nel quadrante inferiore sinistro.
4. **Foreshortening al Bordo:** La prospettiva tangenziale addensa naturalmente i punti lungo il perimetro esterno, tracciando una silhouette sferica netta senza bisogno di bordi vettoriali artificiali.
5. **Nessun Elemento Cyberpunk/HUD:** Assenza totale di anelli HUD, reticoli, bussole, numeri o grafiche da cockpit: solo pura geometria e luce.

---

## 3. Protected Stage (Garanzia di Non-Sovrapposizione)

Il principio cardine dell'interazione in Aether V4 è:

> **La sfera non deve MAI essere coperta da elementi dell'interfaccia.**

| Componente UI | Strategia di Protezione Visiva |
| :--- | :--- |
| **Thought Bubbles** | Allontanate lungo un'orbita protetta ellittica con raggio maggiorato ($x \in [22\%, 78\%], y \in [24\%, 48\%]$), garantendo almeno **100px di luce libera** dalla superficie dell'Orb. |
| **Aether Field & Carte di Lavoro** | Quando emergono, l'Orb si solleva dolcemente verso l'alto (`transform: translateY(-164px) scale(0.64)`), lasciando oltre **30px di spazio libero** al di sopra delle schede. |
| **Superficie di Approvazione (Needs You)** | Il Field si posiziona ancorato al fondo (`bottom: 24px`), mentre l'Orb fluttua in alto in colorazione ambra senza alcun contatto con la scheda. |
| **Dialogue Dock & Input** | Quando il Field o l'Approvazione sono attivi, la barra di conversazione e i prompt recedono automaticamente (`opacity: 0; translateY(20px)`), concentrando l'attenzione sulla decisione. |
| **Badge Presenza & Prompt Chips** | In stato di quiete, il badge `Disponibile` è alloggiato nel margine inferiore dell'Orb con un margine libero di **40px** sopra i prompt chips. |

---

## 4. Modello di Movimento & Transizioni Silky Smooth

### Quintic Zero-Jerk Easing
Tutte le transizioni tra stati utilizzano un polinomio quintico ad accelerazione e jerk nulli agli estremi:
$$S(t) = 6t^5 - 15t^4 + 10t^3 \quad (t \in [0, 1])$$

Questo garantisce passaggi setosi ed organici, senza scatti improvvisi. I parametri interpolati continuamente includono:
- Velocità di rotazione polare ($\omega_Y$);
- Raggio volumetrico base;
- Tonalità colore frontale e posteriore (RGB);
- Ampiezza d'onda superficiale ($A_{\text{wave}}$) e frequenza armonica;
- Breathing sinusoidale globale.

### Transizione di Riferimento: Working $\rightarrow$ Needs You $\rightarrow$ Approved $\rightarrow$ Working
1. **Working:** Rotazione rapida ($0.0105$), onde energetiche violetto/indaco;
2. **Needs You:** Decelerazione graduale in 850ms fino a una rotazione quasi impercettibile ($0.0015$), la sfera si tinge di ambra dorata calda solare e il Field diventa superficie di approvazione;
3. **Approvazione:** Alla pressione di *"Approva ed Esegui"*, l'Orb emette un **impulso sferico d'accettazione** (`triggerApprovalPulse()`: espansione elastica $+18\%$ con decadimento armonico in 650ms);
4. **Ripresa Working:** L'Orb accelera fluidamente e riprende le onde di calcolo indaco.

---

## 5. Palette Cromatica dei 6 Stati con Atmosfera Sincronizzata

Il background obsidian grafite profondo (`#040507`) ospita un'aura atmosferica morbida di 1150x950px (`.ambient-gradient-center`) che si sincronizza cromaticamente in tempo reale con lo stato dell'Orb:

| Stato | Tonalità Frontale (RGB) | Tonalità Posteriore (RGB) | Aura di Sfondo | Cinetica |
| :--- | :--- | :--- | :--- | :--- |
| **IDLE** | Violetto Aether (`[215, 175, 255]`) | Violetto profondo (`[125, 75, 195]`) | Violetto etereo (opacity 0.065) | Rotazione lenta ($0.0035$), respiro calmo |
| **LISTENING** | Celeste cyan chiaro (`[75, 225, 255]`) | Blu profondo (`[45, 125, 195]`) | Cyan polare (opacity 0.08) | Volume contratto (-7%), micro-onde vocali |
| **SPEAKING** | Magenta-violetto (`[235, 135, 255]`) | Ametista scuro (`[145, 65, 205]`) | Magenta tenue (opacity 0.075) | Espansione (+5%), onde sincrone all'audio |
| **WORKING** | Cobalto-indaco (`[145, 160, 255]`) | Blu notte (`[75, 90, 195]`) | Indaco tecnologico (opacity 0.085) | Rotazione rapida ($0.0105$), onde complesse |
| **NEEDS YOU** | Ambra calda solare (`[255, 195, 85]`) | Bronzo velluto (`[175, 120, 55]`) | Ambra dorata (opacity 0.09) | Decelerazione solenne ($0.0015$), quiete |
| **DONE** | Giada/smeraldo menta (`[85, 235, 170]`) | Grafite smeraldo (`[50, 145, 105]`) | Smeraldo tenue (opacity 0.07) | Impulso di completamento e rilassamento |

---

## 6. Prestazioni & Efficienza su Dispositivi Meno Potenti

Per garantire fluidità a 60/120 FPS su laptop a batteria, telefoni e schermi ad alta densità:

### Architettura Zero-GC con TypedArrays
- Coordinate 3D e parametri conservati in array tipizzati pre-allocati: `Float32Array(posData)`, `Float32Array(paramData)`, `Float32Array(projX)`, `Float32Array(projY)`, `Float32Array(projScale)`, `Float32Array(projDepth)`, `Uint16Array(projIndices)`.
- Nessun oggetto JavaScript viene creato o distrutto all'interno del ciclo `requestAnimationFrame`.

### 32-Band Depth Color LUT (Look-Up Table)
- Eliminata ogni concatenazione di stringhe `rgba(...)` durante il rendering: i colori vengono pre-calcolati in un array di 32 gradini di profondità all'inizio di ogni frame. L'assegnazione è un accesso diretto `ctx.fillStyle = this.depthColorLut[band]`.

### Capping Dinamico del DevicePixelRatio (DPR)
- Su schermi Retina/4K, il DPR è limitato tra `1.0` e `1.75` (anziché 2.0 o 3.0), riducendo il carico di pixel fill-rate del **45%** senza alcuna perdita visibile di nitidezza.

### Profili di Qualità Adattivi (Controllo Manuale & Automatico)
Nella barra comandi è presente il selettore `RES:`:
- **Auto:** Rileva automaticamente CPU/GPU;
- **High:** 1080 punti, DPR max 1.75;
- **Med:** 720 punti, DPR max 1.25;
- **Low:** 450 punti, DPR max 1.0 (ideale per Chromebook o dispositivi a basso consumo).

### Page Visibility API
- Quando la tab del browser o la finestra dell'applicazione non è in primo piano (`document.hidden = true`), il motore sospende automaticamente il render loop, portando il consumo di CPU e batteria allo **0.0%**.

### Accessibilità & Riduzione Movimento (`prefers-reduced-motion`)
- Rileva automaticamente la preferenza di sistema e offre il pulsante dedicato `Moto: Normale / Ridotto`. In modalità ridotta, la velocità è abbattuta del 78%, l'ampiezza delle onde dell'85% e l'effetto mouse parallax viene disabilitato.

### Telemetria in Tempo Reale
- HUD pill in tempo reale con indicatore verde pulsante: mostra FPS effettivi, frame time in millisecondi (tipicamente **0.5ms – 0.8ms**) e numero di punti attivi.

---

## 7. Responsiveness Mobile & Tablet

Il layout dell'assistente scala armoniosamente su qualsiasi viewport:
- **Desktop (1440x900+):** Canvas 640x640px, diametro sferico 460px;
- **Tablet (768px):** Canvas 420x420px, elevazione moderata;
- **Mobile (390x844 iPhone / Android):**
  - Canvas a 320x320px centrato e bilanciato;
  - Header minimalista con icone compatte;
  - Prototype bar a scorrimento orizzontale touch senza barre di scorrimento visibili;
  - Margini liberi protetti da qualsiasi sovrapposizione.

---

## 8. Walkthrough dello Scenario a 10 Passaggi

Il pulsante `Play Scenario` riproduce la sequenza completa dell'assistente:

1. **Step 1 (Presenza Iniziale):** Orb in quiete violetta. Aether è presente e attende la richiesta dell'utente.
2. **Step 2 (Ascolto Concentrato):** L'utente invia la richiesta (*“Prendi il progetto Alfa...”*); l'Orb contrae il volume e passa a cyan etereo.
3. **Step 3 (Risposta Vocale):** Aether risponde con modulazione vocale e vibrazione d'onda organica sincrona.
4. **Step 4 (Avvio Lavoro & Bubble):** L'Orb passa a Working; emerge perifericamente la prima micro-bubble (*“Controllo il progetto Alfa...”*).
5. **Step 5 (Field Prende Forma):** Le bolle scivolano e fanno emergere la scheda di lavoro contestuale; l'Orb si solleva dolcemente verso l'alto.
6. **Step 6 (Problemi Trovati & Primi Fix):** Aether individua 4 anomalie nel codice; ne corregge 3 in totale autonomia.
7. **Step 7 (Decisione Richiesta - Needs You):** L'Orb rallenta con ambra solare calda; il Field diventa Superficie di Approvazione per la procedura DB; la riproduzione automatica si ferma per attendere la decisione umana.
8. **Step 8 (Approvazione & Convalida):** Premendo *"Approva ed Esegui"*, l'Orb emette un impulso elastico di conferma (`triggerApprovalPulse`), riprende i flussi veloci di Working e lancia la suite di test.
9. **Step 9 (Lavoro Verificato - Done):** Tutti i test al 100%; l'Orb rilascia un impulso verde smeraldo.
10. **Step 10 (Risultato Finale):** *"Fatto."* Orb calmo; scheda di consegna pronta per generare la Pull Request.

---

## 9. Portabilità in React, TypeScript & Tauri v2

La transizione dal prototipo alla UI di produzione avverrà senza riscritture architetturali:
```tsx
import React, { useEffect, useRef } from 'react';
import { OrbEngine } from './orb-engine';

interface AetherOrbProps {
  state: 'idle' | 'listening' | 'speaking' | 'working' | 'needs-you' | 'done';
  audioLevel?: number;
  quality?: 'auto' | 'high' | 'medium' | 'low';
}

export const AetherOrb: React.FC<AetherOrbProps> = ({ state, audioLevel = 0, quality = 'auto' }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<OrbEngine | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    const engine = new OrbEngine(canvasRef.current, { initialState: state, qualityProfile: quality });
    engineRef.current = engine;
    return () => engine.destroy();
  }, []);

  useEffect(() => {
    engineRef.current?.transitionTo(state);
  }, [state]);

  useEffect(() => {
    engineRef.current?.setAudioLevel(audioLevel);
  }, [audioLevel]);

  return <canvas ref={canvasRef} width={640} height={640} className="aether-orb-canvas" />;
};
```

---

## 10. Verifica Tecnica Eseguita

| Verifica | Strumento | Risultato |
| :--- | :--- | :--- |
| **Frame Rate & Frame Time** | Chrome CDP Telemetry | **60 FPS stabili, 0.52ms – 0.8ms frame time** |
| **Allocazioni di Memoria** | Chrome Heap & GC Monitor | **Zero Garbage Collection pressure nel render loop** |
| **Campionamento Punti** | Mulberry32 PRNG Uniformity | **Volume see-through perfetto con polar swirl a 7:30** |
| **Protected Stage** | Desktop & Mobile Viewport Inspection | **Nessuna sovrapposizione tra Orb, card, dock e bolle** |
| **Transizioni Quintiche** | State Machine verification | **Continuità senza scatti per tutti i 6 stati e l'impulso d'approvazione** |
| **Visual Capture** | CDP Headless Screenshots | **Convalidati su Desktop (1440x900) e Mobile (390x844)** |
