/**
 * Home page copy, IT and EN. Every claim here is checked against docs/FUTURE_ROADMAP.md and docs/product/*.
 * tests/claims.test.ts keeps banned phrases out of this file.
 */
export interface Copy {
  meta: { title: string; description: string; ogTitle: string };
  nav: { demo: string; screen: string; memory: string; teams: string; privacy: string; faq: string; download: string; builders: string };
  hero: { l1: string; l2: string; l2Pc: string; sub: string; cta: string; secondary: string; note: string; notePc: string; orbLabel: string };
  demo: {
    title: string;
    sub: string;
    label: string;
    placeholder: string;
    scenarios: { id: "screen" | "report" | "remember"; chip: string; ask: string; working: string; approval?: { title: string; detail: string }; done: string }[];
    approve: string;
    reject: string;
    rejected: string;
    reset: string;
    states: Record<"idle" | "working" | "needs-you" | "done", string>;
    note: string;
  };
  real: { title: string; sub: string; caption: string; video: { label: string; caption: string; play: string; pause: string }; shots: { alt: string; label: string }[] };
  screen: {
    title: string;
    sub: string;
    steps: { tab: string; title: string; text: string }[];
    ui: { entire: string; entireHint: string; area: string; areaHint: string; preview: string; sendTo: string; ask: string; send: string; discard: string; answer: string; marks: string };
    promise: string[];
  };
  memory: {
    title: string;
    sub: string;
    categories: { name: string; line: string }[];
    knowledge: { title: string; text: string };
    learn: { title: string; before: string; correction: string; after: string; text: string };
    remember: { title: string; text: string };
    versions: { title: string; text: string };
  };
  teams: {
    title: string;
    sub: string;
    presets: { name: string; line: string }[];
    architect: { title: string; text: string };
    community: { title: string; text: string };
  };
  privacy: {
    title: string;
    sub: string;
    columns: { stays: { title: string; items: string[] }; goes: { title: string; items: string[] }; asks: { title: string; items: string[] } };
    footnote: string;
  };
  models: { title: string; sub: string; providers: string[]; note: string };
  download: {
    title: string;
    sub: string;
    button: string;
    version: string;
    requirements: string;
    first: { title: string; steps: string[]; why: string };
    windows: { title: string; text: string };
    roadmap: { title: string; items: string[] };
    github: string;
    changelog: string;
    free: string;
  };
  faq: { title: string; items: { q: string; a: string }[] };
  footer: { tagline: string; taglinePc: string; product: string; project: string; legal: string; builders: string; about: string; privacy: string; cookies: string; cookieSettings: string; github: string; changelog: string; copy: string; built: string };
}

export const it: Copy = {
  meta: {
    title: "Aether — Il tuo assistente personale sul tuo Mac",
    description:
      "Aether è un assistente personale che vive sul tuo computer: guarda lo schermo solo quando glielo chiedi, ricorda, impara dalle tue correzioni e chiede il tuo ok prima di agire. Open source.",
    ogTitle: "Aether — Il tuo assistente. Sul tuo Mac.",
  },
  nav: { demo: "Companion", screen: "Schermo", memory: "Memoria", teams: "Squadre", privacy: "Privacy", faq: "FAQ", download: "Scarica", builders: "Per sviluppatori" },
  hero: {
    l1: "Il tuo assistente.",
    l2: "Sul tuo Mac.",
    l2Pc: "Sul tuo PC.",
    sub: "Aether vive sul tuo computer. Guarda lo schermo solo quando glielo chiedi, ricorda quello che gli dici, impara quando lo correggi e chiede il tuo sì prima di agire.",
    cta: "Scarica per macOS",
    secondary: "Guardalo lavorare",
    note: "Gratuito e open source (MIT). Per Mac con Apple Silicon.",
    notePc: "Gratuito e open source (MIT). Per ora solo per macOS: Windows e Linux non sono ancora pubblicati.",
    orbLabel: "L'orb di Aether, la presenza del Companion",
  },
  demo: {
    title: "Chiamalo. Chiedi. Decidi tu.",
    sub: "Il Companion è un orb sempre a portata di scorciatoia. Quando lavora lo vedi, quando ha bisogno di te ti chiama. Prova la scena qui sotto.",
    label: "Demo guidata",
    placeholder: "Scegli una richiesta",
    scenarios: [
      {
        id: "screen",
        chip: "Spiegami questa schermata",
        ask: "Spiegami questa schermata.",
        working: "Guardo l'immagine che hai scelto di condividere…",
        done: "È un modulo d'ordine con tre campi. Il campo «Partita IVA» è vuoto: è l'unico obbligatorio rimasto.",
      },
      {
        id: "report",
        chip: "Prepara il report clienti",
        ask: "Prepara il report clienti di ottobre.",
        working: "Leggo i documenti del workspace e scrivo la bozza…",
        approval: { title: "Salvare «report-ottobre.md» nella cartella del workspace?", detail: "Se il file esiste, la versione precedente viene conservata." },
        done: "Fatto: report-ottobre.md è nella cartella del workspace.",
      },
      {
        id: "remember",
        chip: "Ricordati che preferisco report brevi",
        ask: "Ricordati che preferisco report di una pagina.",
        working: "Salvo la preferenza…",
        done: "Ricordato: preferisci report di una pagina. Lo userò nelle prossime richieste.",
      },
    ],
    approve: "Approva",
    reject: "Rifiuta",
    rejected: "Non fatto. Nessuna modifica ai tuoi file.",
    reset: "Ricomincia",
    states: { idle: "Pronto", working: "Al lavoro", "needs-you": "Serve il tuo ok", done: "Fatto" },
    note: "Scena illustrativa con risposte scritte a mano: nell'app le risposte arrivano dal modello che scegli tu.",
  },
  real: {
    title: "Questo è Aether. Per davvero.",
    sub: "Schermate dell'app su Mac, non mockup.",
    caption: "Schermate reali, con un workspace di prova.",
    video: {
      label: "Registrazione dello schermo dell'app",
      caption: "Il Companion si richiama, cattura un'area, mostra l'anteprima e l'utente disegna una freccia. Poi scarta: non viene inviato nulla.",
      play: "Riproduci il video",
      pause: "Metti in pausa il video",
    },
    shots: [
      { alt: "La finestra principale di Aether con la richiesta «Di cosa hai bisogno oggi?»", label: "La finestra principale" },
      { alt: "Il Companion aperto, con le richieste suggerite", label: "Il Companion" },
      { alt: "Il Companion mentre scegli schermo intero o un'area", label: "Scegli cosa condividere" },
      { alt: "L'anteprima della cattura con gli strumenti per disegnare", label: "Controlli l'anteprima" },
    ],
  },
  screen: {
    title: "Guarda quando glielo chiedi.",
    sub: "Aether non osserva il tuo schermo di nascosto. Una cattura è un gesto tuo: scegli, controlli l'anteprima, decidi se inviarla.",
    steps: [
      { tab: "Scegli", title: "Schermo intero o un'area.", text: "Premi il pulsante della fotocamera nel Companion. Il Companion si nasconde un istante, così non finisce nell'immagine." },
      { tab: "Controlla", title: "Vedi cosa verrà inviato.", text: "Anteprima prima di tutto. Puoi cerchiare, evidenziare o indicare con una freccia: i tuoi segni entrano nell'immagine." },
      { tab: "Chiedi", title: "Una risposta nella tua conversazione.", text: "L'immagine va solo a un modello che sa leggere le immagini. Se il tuo non può, Aether te lo dice e non invia nulla." },
    ],
    ui: {
      entire: "Schermo intero",
      entireHint: "Il display principale.",
      area: "Seleziona un'area",
      areaHint: "Trascina per scegliere. Esc annulla.",
      preview: "Anteprima: questo è ciò che verrà inviato",
      sendTo: "Va al modello che hai scelto solo quando premi Invia.",
      ask: "Che cosa indica la freccia?",
      send: "Invia",
      discard: "Scarta",
      answer: "È il pulsante «Salva bozza»: conserva il documento senza inviarlo.",
      marks: "1 freccia",
    },
    promise: ["Mai in background.", "Mai salvata.", "Solo con il permesso di macOS."],
  },
  memory: {
    title: "Si ricorda. Impara. Si corregge.",
    sub: "La memoria di Aether è tua, sul tuo computer, e puoi leggerla e modificarla. Più lo usi, meno devi ripetere.",
    categories: [
      { name: "Fatti", line: "Cosa è vero su di te e sul tuo lavoro." },
      { name: "Preferenze", line: "Come ti piacciono le cose fatte." },
      { name: "Decisioni", line: "Cosa hai già deciso e perché." },
      { name: "Procedure", line: "Come lavori, passo per passo." },
      { name: "Persone", line: "Clienti, colleghi, contatti." },
      { name: "Progetti", line: "Cosa è in corso e per quando." },
      { name: "Risultati", line: "Cosa è stato consegnato." },
      { name: "Lezioni", line: "Regole nate dalle tue correzioni." },
    ],
    knowledge: { title: "Una base di conoscenza tua.", text: "Documenti e relazioni diventano un grafo di conoscenza che Aether consulta quando risponde. Lo vedi e lo modifichi." },
    learn: {
      title: "Correggilo una volta.",
      before: "Bozza di Aether: «Gentile cliente, in allegato il preventivo…»",
      correction: "La tua correzione: «Con i clienti uso il tu.»",
      after: "Lezione salvata: nelle mail ai clienti usa il tu.",
      text: "Le correzioni diventano lezioni, con la prova che le ha generate. Le lezioni tornano nelle richieste successive.",
    },
    remember: { title: "«Ricorda che…»", text: "Dillo e basta: la frase diventa una memoria esplicita, richiamata nelle sessioni successive." },
    versions: { title: "Niente sovrascritture a sorpresa.", text: "Quando Aether modifica un tuo documento, la versione precedente resta salvata." },
  },
  teams: {
    title: "Una squadra su misura.",
    sub: "Per i lavori grandi Aether coordina agenti specializzati, ognuno con il suo ruolo, i suoi strumenti e le sue regole. Li personalizzi tu.",
    presets: [
      { name: "Ricerca", line: "Un coordinatore che pianifica e specialisti che leggono, confrontano e riassumono." },
      { name: "Sviluppo", line: "Una squadra che affronta il codice con ruoli separati e controlli." },
      { name: "Operations", line: "Per i processi di tutti i giorni di un'attività." },
      { name: "Starter", line: "Il punto di partenza per costruire la tua." },
    ],
    architect: { title: "Descrivila e basta.", text: "Racconta cosa ti serve: l'Auto-Architect propone la squadra, tu rivedi ruoli e strumenti prima di applicarla." },
    community: { title: "Squadre della community, in arrivo.", text: "Pubblicare e installare squadre di altri, con un riepilogo dei permessi, è nella roadmap. Oggi le squadre si creano e si installano in locale, da preset." },
  },
  privacy: {
    title: "Tuo, per costruzione.",
    sub: "Aether gira sul tuo computer. Sei tu a decidere dove va il tuo testo.",
    columns: {
      stays: { title: "Resta sul tuo Mac", items: ["Memoria, conoscenza e conversazioni", "I tuoi documenti e il workspace", "Le chiavi dei provider, in un archivio cifrato sul Mac", "Le catture dello schermo: solo in memoria, mai salvate"] },
      goes: { title: "Va dove scegli tu", items: ["Con un modello locale (Ollama): nulla esce dal computer", "Con un provider cloud: il testo della richiesta va a quel provider", "Nessun provider di riserva: se il tuo non risponde, Aether lo dice"] },
      asks: { title: "Chiede prima di agire", items: ["Le azioni sensibili aspettano la tua approvazione", "Cosa verrà fatto è scritto in chiaro", "Un rifiuto non cambia nulla"] },
    },
    footnote: "Aether ti dice che cosa ha verificato davvero e non dichiara riuscito ciò che non lo è.",
  },
  models: {
    title: "Il modello lo scegli tu.",
    sub: "Collega il provider che preferisci con la tua chiave, o usa un modello locale.",
    providers: ["Groq", "OpenAI", "Anthropic", "Gemini", "Ollama (locale)"],
    note: "Per guardare lo schermo serve un modello con visione. Aether controlla quale hai scelto e ti avvisa prima di catturare qualcosa.",
  },
  download: {
    title: "Provalo sul tuo Mac.",
    sub: "Gratis e open source. Nessun account da creare.",
    button: "Scarica Aether.dmg",
    version: "Ultima versione pubblicata",
    requirements: "Mac con Apple Silicon.",
    first: {
      title: "Il primo avvio",
      steps: ["Apri il .dmg e trascina Aether in Applicazioni.", "Alla prima apertura macOS potrebbe bloccarla: apri Impostazioni di Sistema → Privacy e sicurezza e scegli «Apri comunque».", "Per guardare lo schermo, abilita Aether in Registrazione schermo e riaprilo."],
      why: "L'app non è ancora notarizzata da Apple: per questo macOS chiede una conferma. Il codice è aperto, puoi verificarlo.",
    },
    windows: { title: "Windows", text: "L'installer è compilato e provato in automatico, ma non ancora su un PC vero. Per ora non lo pubblichiamo." },
    roadmap: { title: "In arrivo", items: ["Telegram come seconda superficie", "Risposte vocali", "Indicazioni direttamente sullo schermo", "Squadre della community"] },
    github: "Codice su GitHub",
    changelog: "Novità",
    free: "Gratuito, licenza MIT.",
  },
  faq: {
    title: "Domande",
    items: [
      { q: "Mi guarda lo schermo di continuo?", a: "No. Cattura solo quando premi il pulsante, ti mostra l'anteprima e invia soltanto se premi Invia. Non c'è nessuna acquisizione in background e l'immagine non viene salvata." },
      { q: "I miei dati restano sul computer?", a: "Memoria, conoscenza, documenti e conversazioni sì. Il testo di una richiesta va al provider che scegli: con un modello locale non esce nulla, con un provider cloud sì, verso quel provider." },
      { q: "Quanto costa?", a: "Aether è gratuito e open source (MIT). Paghi, se vuoi, il provider cloud che colleghi con la tua chiave. Con un modello locale non paghi nessuno." },
      { q: "Che modelli posso usare?", a: "Groq, OpenAI, Anthropic, Gemini oppure Ollama in locale. Non c'è un modello di riserva: usa quello che scegli." },
      { q: "Può usare il mouse e la tastiera al posto mio?", a: "Non ancora. Oggi guarda, spiega, prepara documenti e chiede approvazione. Il controllo di mouse e tastiera, se arriverà, passerà da permessi e approvazioni espliciti." },
      { q: "Perché macOS mi chiede una conferma al primo avvio?", a: "Perché l'app non è ancora notarizzata da Apple. È una limitazione nostra, non del tuo Mac: i passaggi sono nella sezione Download." },
      { q: "Si aggiorna da sola?", a: "Dalla versione 1.7.1 sì: l'app cerca le nuove versioni, verifica la firma e installa solo quando premi il pulsante in Impostazioni → Generale → Aggiornamenti. Se hai la 1.7.0, scarica la 1.7.1 una volta a mano." },
      { q: "E su Windows?", a: "Non ancora pubblicato. L'installer è provato in automatico, non su un PC reale." },
    ],
  },
  footer: {
    tagline: "Il tuo assistente. Sul tuo Mac.",
    taglinePc: "Il tuo assistente. Sul tuo PC.",
    product: "Prodotto",
    project: "Progetto",
    legal: "Legale",
    builders: "Per sviluppatori",
    about: "Chi siamo",
    privacy: "Privacy",
    cookies: "Cookie",
    cookieSettings: "Preferenze cookie",
    github: "GitHub",
    changelog: "Novità",
    copy: "© 2026 Aether Community. Software open source, licenza MIT.",
    built: "Sviluppato con cura da LMLabs",
  },
};

export const en: Copy = {
  meta: {
    title: "Aether — Your personal assistant, on your Mac",
    description:
      "Aether is a personal assistant that lives on your computer: it looks at your screen only when you ask, remembers, learns from your corrections and asks your OK before it acts. Open source.",
    ogTitle: "Aether — Your assistant. On your Mac.",
  },
  nav: { demo: "Companion", screen: "Screen", memory: "Memory", teams: "Teams", privacy: "Privacy", faq: "FAQ", download: "Download", builders: "For developers" },
  hero: {
    l1: "Your assistant.",
    l2: "On your Mac.",
    l2Pc: "On your PC.",
    sub: "Aether lives on your computer. It looks at your screen only when you ask, remembers what you tell it, learns when you correct it and asks your yes before it acts.",
    cta: "Download for macOS",
    secondary: "Watch it work",
    note: "Free and open source (MIT). For Macs with Apple Silicon.",
    notePc: "Free and open source (MIT). For now macOS only: Windows and Linux are not published yet.",
    orbLabel: "The Aether orb, the Companion's presence",
  },
  demo: {
    title: "Call it. Ask. You decide.",
    sub: "The Companion is an orb one shortcut away. You see it when it works and it calls you when it needs you. Try the scene below.",
    label: "Guided demo",
    placeholder: "Pick a request",
    scenarios: [
      {
        id: "screen",
        chip: "Explain this screen",
        ask: "Explain this screen.",
        working: "Looking at the image you chose to share…",
        done: "It is an order form with three fields. «VAT number» is empty: it is the only required field left.",
      },
      {
        id: "report",
        chip: "Prepare the client report",
        ask: "Prepare the October client report.",
        working: "Reading the workspace documents and drafting…",
        approval: { title: "Save «october-report.md» in the workspace folder?", detail: "If the file exists, the previous version is kept." },
        done: "Done: october-report.md is in the workspace folder.",
      },
      {
        id: "remember",
        chip: "Remember I prefer short reports",
        ask: "Remember that I prefer one-page reports.",
        working: "Saving the preference…",
        done: "Remembered: you prefer one-page reports. I will use it in your next requests.",
      },
    ],
    approve: "Approve",
    reject: "Reject",
    rejected: "Not done. Your files are unchanged.",
    reset: "Start over",
    states: { idle: "Ready", working: "Working", "needs-you": "Needs your OK", done: "Done" },
    note: "An illustrative scene with hand-written answers: in the app the answers come from the model you choose.",
  },
  real: {
    title: "This is Aether. For real.",
    sub: "Screenshots of the Mac app, not mockups.",
    caption: "Real screenshots, with a test workspace.",
    video: {
      label: "Screen recording of the app",
      caption: "The Companion is summoned, captures an area, shows the preview and the user draws an arrow. Then they discard it: nothing is sent.",
      play: "Play the video",
      pause: "Pause the video",
    },
    shots: [
      { alt: "Aether's main window with the prompt “What do you need today?”", label: "The main window" },
      { alt: "The Companion open, with suggested requests", label: "The Companion" },
      { alt: "The Companion while you choose entire screen or an area", label: "Choose what to share" },
      { alt: "The capture preview with the drawing tools", label: "You check the preview" },
    ],
  },
  screen: {
    title: "It looks when you ask.",
    sub: "Aether never watches your screen in secret. A capture is your gesture: you choose, check the preview and decide whether to send it.",
    steps: [
      { tab: "Choose", title: "Entire screen or an area.", text: "Press the camera button in the Companion. The Companion hides for a moment so it is not in the picture." },
      { tab: "Check", title: "See what will be sent.", text: "Preview first. Circle, highlight or point with an arrow: your marks become part of the image." },
      { tab: "Ask", title: "An answer in your conversation.", text: "The image goes only to a model that can read images. If yours cannot, Aether tells you and sends nothing." },
    ],
    ui: {
      entire: "Entire screen",
      entireHint: "The main display.",
      area: "Select an area",
      areaHint: "Drag to choose. Esc cancels.",
      preview: "Preview: this is what will be sent",
      sendTo: "Goes to the model you chose only when you press Send.",
      ask: "What does the arrow point to?",
      send: "Send",
      discard: "Discard",
      answer: "It is the «Save draft» button: it keeps the document without sending it.",
      marks: "1 arrow",
    },
    promise: ["Never in the background.", "Never saved.", "Only with macOS permission."],
  },
  memory: {
    title: "It remembers. It learns. It corrects itself.",
    sub: "Aether's memory is yours, on your computer, and you can read and edit it. The more you use it, the less you repeat.",
    categories: [
      { name: "Facts", line: "What is true about you and your work." },
      { name: "Preferences", line: "How you like things done." },
      { name: "Decisions", line: "What you already decided and why." },
      { name: "Processes", line: "How you work, step by step." },
      { name: "People", line: "Clients, colleagues, contacts." },
      { name: "Projects", line: "What is running and by when." },
      { name: "Outcomes", line: "What was delivered." },
      { name: "Lessons", line: "Rules born from your corrections." },
    ],
    knowledge: { title: "A knowledge base that is yours.", text: "Documents and relationships become a knowledge graph Aether consults when it answers. You can see it and edit it." },
    learn: {
      title: "Correct it once.",
      before: "Aether's draft: “Dear customer, please find the quote attached…”",
      correction: "Your correction: “I use first names with customers.”",
      after: "Lesson saved: in customer emails, use first names.",
      text: "Corrections become lessons, with the evidence that produced them. Lessons come back in later requests.",
    },
    remember: { title: "“Remember that…”", text: "Just say it: the sentence becomes an explicit memory, recalled in later sessions." },
    versions: { title: "No surprise overwrites.", text: "When Aether edits one of your documents, the previous version stays saved." },
  },
  teams: {
    title: "A team built for you.",
    sub: "For bigger jobs Aether coordinates specialised agents, each with its own role, tools and rules. You customise them.",
    presets: [
      { name: "Research", line: "A coordinator who plans and specialists who read, compare and summarise." },
      { name: "Development", line: "A team that tackles code with separate roles and checks." },
      { name: "Operations", line: "For a business's everyday processes." },
      { name: "Starter", line: "The starting point to build your own." },
    ],
    architect: { title: "Just describe it.", text: "Tell it what you need: the Auto-Architect proposes the team, and you review roles and tools before applying it." },
    community: { title: "Community teams, coming.", text: "Publishing and installing other people's teams, with a permissions summary, is on the roadmap. Today teams are created and installed locally, from presets." },
  },
  privacy: {
    title: "Yours, by construction.",
    sub: "Aether runs on your computer. You decide where your text goes.",
    columns: {
      stays: { title: "Stays on your Mac", items: ["Memory, knowledge and conversations", "Your documents and workspace", "Provider keys, in an encrypted store on your Mac", "Screen captures: in memory only, never saved"] },
      goes: { title: "Goes where you choose", items: ["With a local model (Ollama): nothing leaves your computer", "With a cloud provider: your request text goes to that provider", "No fallback provider: if yours does not answer, Aether says so"] },
      asks: { title: "Asks before it acts", items: ["Sensitive actions wait for your approval", "What will happen is written plainly", "A rejection changes nothing"] },
    },
    footnote: "Aether tells you what it really verified and never reports as done what is not.",
  },
  models: {
    title: "You choose the model.",
    sub: "Connect the provider you prefer with your own key, or use a local model.",
    providers: ["Groq", "OpenAI", "Anthropic", "Gemini", "Ollama (local)"],
    note: "Looking at the screen needs a vision-capable model. Aether checks which one you picked and warns you before capturing anything.",
  },
  download: {
    title: "Try it on your Mac.",
    sub: "Free and open source. No account to create.",
    button: "Download Aether.dmg",
    version: "Latest published version",
    requirements: "Mac with Apple Silicon.",
    first: {
      title: "First launch",
      steps: ["Open the .dmg and drag Aether to Applications.", "On first open macOS may block it: open System Settings → Privacy & Security and choose “Open Anyway”.", "To let it look at the screen, enable Aether under Screen Recording and reopen it."],
      why: "The app is not notarized by Apple yet, which is why macOS asks for a confirmation. The code is open: you can check it.",
    },
    windows: { title: "Windows", text: "The installer is built and tested automatically, but not yet on a real PC. We are not publishing it for now." },
    roadmap: { title: "Coming", items: ["Telegram as a second surface", "Spoken answers", "Pointing directly on the screen", "Community teams"] },
    github: "Code on GitHub",
    changelog: "What's new",
    free: "Free, MIT license.",
  },
  faq: {
    title: "Questions",
    items: [
      { q: "Does it watch my screen all the time?", a: "No. It captures only when you press the button, shows you the preview and sends only if you press Send. There is no background capture and the image is not saved." },
      { q: "Does my data stay on my computer?", a: "Memory, knowledge, documents and conversations do. The text of a request goes to the provider you choose: with a local model nothing leaves your computer, with a cloud provider it goes to that provider." },
      { q: "How much does it cost?", a: "Aether is free and open source (MIT). If you want, you pay the cloud provider you connect with your own key. With a local model you pay no one." },
      { q: "Which models can I use?", a: "Groq, OpenAI, Anthropic, Gemini or Ollama locally. There is no fallback model: it uses the one you choose." },
      { q: "Can it use my mouse and keyboard for me?", a: "Not yet. Today it looks, explains, drafts documents and asks for approval. Mouse and keyboard control, if it comes, will go through explicit permissions and approvals." },
      { q: "Why does macOS ask for a confirmation on first launch?", a: "Because the app is not notarized by Apple yet. That is our limitation, not your Mac's: the steps are in the Download section." },
      { q: "Does it update itself?", a: "From version 1.7.1, yes: the app looks for new versions, verifies the signature and installs only when you press the button in Settings → General → Updates. If you have 1.7.0, download 1.7.1 once by hand." },
      { q: "What about Windows?", a: "Not published yet. The installer is tested automatically, not on a real PC." },
    ],
  },
  footer: {
    tagline: "Your assistant. On your Mac.",
    taglinePc: "Your assistant. On your PC.",
    product: "Product",
    project: "Project",
    legal: "Legal",
    builders: "For developers",
    about: "About",
    privacy: "Privacy",
    cookies: "Cookies",
    cookieSettings: "Cookie preferences",
    github: "GitHub",
    changelog: "What's new",
    copy: "© 2026 Aether Community. Open source software, MIT license.",
    built: "Built with care by LMLabs",
  },
};

export const copy = { it, en } as const;
export type Lang = keyof typeof copy;
export const LANGS: Lang[] = ["it", "en"];
export const isLang = (v: string): v is Lang => v === "it" || v === "en";
