import { createContext, useContext, useState, type ReactNode } from 'react';

export type Language = 'en' | 'it';

export const translations = {
  en: {
    // Navigation
    navHome: 'Home',
    navConversations: 'Conversations',
    navAgents: 'Agents',
    navTeams: 'Teams',
    navKnowledge: 'Knowledge',
    navSettings: 'Settings',
    navMarketplace: 'Marketplace',
    newTask: 'New Task',
    searchPlaceholder: 'Search or type Cmd+K...',
    workspace: 'Workspace',
    workforce: 'Workforce',
    platform: 'Platform',

    // Home
    homeWelcome: 'Your AI Workforce is ready',
    homeSubtitle: 'Coordinate autonomous agents, assign complex goals, and observe execution in real time.',
    activeTeam: 'Active Team',
    recentConversations: 'Recent Conversations',
    quickActions: 'Quick Actions',
    startTaskAction: 'Start a Task',
    createAgentAction: 'Create Agent',
    addKnowledgeAction: 'Add Knowledge',
    usePresetAction: 'Use Preset',
    noConversationsYet: 'No conversations yet. Start your first task!',
    systemStatus: 'System Status',
    indexedChunks: 'Indexed Knowledge Chunks',
    activeProvider: 'Active Provider',

    // Chat
    chatInputPlaceholder: 'Assign a task to the workforce (e.g., analyze our company strategy)...',
    runTask: 'Run Task',
    running: 'Working...',
    taskComplete: 'Task complete',
    taskFailed: 'Task failed',
    approvalRequired: 'Human Approval Required',
    inputRequired: 'User Input Required',
    approve: 'Approve',
    reject: 'Reject',
    submit: 'Submit',
    copyText: 'Copy',
    copied: 'Copied!',
    retry: 'Retry',
    emptyChatTitle: 'What should the workforce do?',
    emptyChatSubtitle: 'Assign a goal. The Manager will coordinate research, analysis, and deliverable creation.',
    workforcePresence: 'Workforce Presence',
    statusWorking: 'Working',
    statusIdle: 'Idle',
    statusWaiting: 'Waiting for Input',
    statusCompleted: 'Completed',
    statusFailed: 'Failed',
    statusActive: 'Active',

    // Conversations
    conversationsTitle: 'Conversations',
    newConversation: 'New Conversation',
    renameConversation: 'Rename',
    deleteConversation: 'Delete',
    noConversationsFound: 'No conversations found',
    confirmDeleteConversation: 'Are you sure you want to delete this conversation?',

    // Agents
    agentsTitle: 'Agents',
    createAgent: 'Create Agent',
    agentProfile: 'Agent Profile',
    role: 'Role',
    model: 'Model',
    provider: 'Provider',
    skills: 'Skills',
    knowledgeAccess: 'Knowledge Access',
    delegatesTo: 'Delegates to',
    noAgentsConfigured: 'No agents configured in this team.',
    instructions: 'Instructions & Prompt',
    overview: 'Overview',
    recentActivity: 'Recent Activity',

    // Teams
    teamsTitle: 'Teams & Workforces',
    createTeam: 'Create Team',
    usePreset: 'Use Preset',
    teamBuilder: 'Team Builder',
    entryAgent: 'Entry / Manager Agent',
    teamName: 'Team Name',
    teamDescription: 'Description',
    saveTeam: 'Save Team',

    // Knowledge
    knowledgeTitle: 'Knowledge Base',
    uploadDocument: 'Upload Document',
    systemKnowledge: 'System Knowledge',
    workspaceKnowledge: 'Workspace Knowledge',
    readOnlyProtected: 'Built-in (Read-only)',
    allScopes: 'All',
    scope: 'Scope',
    filename: 'Filename',
    size: 'Size',
    chunks: 'Chunks',
    indexedAt: 'Indexed',
    status: 'Status',
    noDocumentsFound: 'No documents in this view',
    deleteDocument: 'Delete Document',

    // Settings
    settingsTitle: 'Settings',
    generalTab: 'General',
    providersTab: 'AI Providers',
    workforceTab: 'Workforce',
    storageTab: 'Storage & Memory',
    advancedTab: 'Advanced & Diagnostics',
    language: 'Language',
    theme: 'Theme',
    themeLight: 'Light',
    themeDark: 'Dark',
    themeSystem: 'System',
    providerTimeout: 'Provider Timeout (seconds)',
    timeoutHelp: 'Local models (Ollama) typically require 120s+ for long multi-turn generations. Cloud providers default to 30s.',
    testConnection: 'Test Connection',
    testing: 'Testing...',
    connectionSuccess: 'Connection successful',
    saveSettings: 'Save Settings',
    apiKey: 'API Key',

    // Marketplace
    marketplaceTitle: 'Workforce Packs & Marketplace',
    officialPresets: 'Official Starter Presets',
    communityPacks: 'Community Ecosystem',
    comingSoon: 'Coming Soon',
    installPreset: 'Install & Activate Preset',

    // Command Palette
    cmdPaletteTitle: 'Command Palette',
    cmdNewTask: 'Start New Task',
    cmdNewConv: 'Create New Conversation',
    cmdGoHome: 'Go to Home',
    cmdGoAgents: 'Go to Agents',
    cmdGoTeams: 'Go to Teams',
    cmdGoKnowledge: 'Go to Knowledge',
    cmdGoSettings: 'Go to Settings',
    cmdGoMarketplace: 'Go to Marketplace',
    cmdToggleTheme: 'Toggle Light / Dark Theme',
    cmdSwitchLang: 'Switch Language (EN / IT)',

    // Common
    cancel: 'Cancel',
    save: 'Save',
    delete: 'Delete',
    close: 'Close',
    loading: 'Loading...',
    success: 'Success',
    error: 'Error',
  },
  it: {
    // Navigation
    navHome: 'Home',
    navConversations: 'Conversazioni',
    navAgents: 'Agenti',
    navTeams: 'Team',
    navKnowledge: 'Conoscenza',
    navSettings: 'Impostazioni',
    navMarketplace: 'Marketplace',
    newTask: 'Nuovo Task',
    searchPlaceholder: 'Cerca o premi Cmd+K...',
    workspace: 'Workspace',
    workforce: 'Workforce',
    platform: 'Piattaforma',

    // Home
    homeWelcome: 'La tua AI Workforce è pronta',
    homeSubtitle: 'Coordina agenti autonomi, assegna obiettivi complessi e osserva l\'esecuzione in tempo reale.',
    activeTeam: 'Team Attivo',
    recentConversations: 'Conversazioni Recenti',
    quickActions: 'Azioni Rapide',
    startTaskAction: 'Avvia un Task',
    createAgentAction: 'Crea Agente',
    addKnowledgeAction: 'Aggiungi Documenti',
    usePresetAction: 'Usa Preset',
    noConversationsYet: 'Nessuna conversazione. Avvia il tuo primo task!',
    systemStatus: 'Stato del Sistema',
    indexedChunks: 'Chunk di Conoscenza Indicizzati',
    activeProvider: 'Provider Attivo',

    // Chat
    chatInputPlaceholder: 'Assegna un obiettivo alla workforce (es. analizza la strategia aziendale)...',
    runTask: 'Esegui Task',
    running: 'In elaborazione...',
    taskComplete: 'Task completato',
    taskFailed: 'Task non riuscito',
    approvalRequired: 'Approvazione Umana Richiesta',
    inputRequired: 'Input Utente Richiesto',
    approve: 'Approva',
    reject: 'Rifiuta',
    submit: 'Invia',
    copyText: 'Copia',
    copied: 'Copiato!',
    retry: 'Riprova',
    emptyChatTitle: 'Cosa deve fare la workforce?',
    emptyChatSubtitle: 'Assegna un obiettivo. Il Manager coordinerà la ricerca, l\'analisi e la stesura del deliverable.',
    workforcePresence: 'Presenza Workforce',
    statusWorking: 'In corso',
    statusIdle: 'In attesa',
    statusWaiting: 'In attesa di input',
    statusCompleted: 'Completato',
    statusFailed: 'Fallito',
    statusActive: 'Attivo',

    // Conversations
    conversationsTitle: 'Conversazioni',
    newConversation: 'Nuova Conversazione',
    renameConversation: 'Rinomina',
    deleteConversation: 'Elimina',
    noConversationsFound: 'Nessuna conversazione trovata',
    confirmDeleteConversation: 'Sei sicuro di voler eliminare questa conversazione?',

    // Agents
    agentsTitle: 'Agenti',
    createAgent: 'Crea Agente',
    agentProfile: 'Profilo Agente',
    role: 'Ruolo',
    model: 'Modello',
    provider: 'Provider',
    skills: 'Skill',
    knowledgeAccess: 'Accesso Knowledge',
    delegatesTo: 'Delega a',
    noAgentsConfigured: 'Nessun agente configurato in questo team.',
    instructions: 'Istruzioni e Prompt',
    overview: 'Panoramica',
    recentActivity: 'Attività Recente',

    // Teams
    teamsTitle: 'Team e Workforce',
    createTeam: 'Crea Team',
    usePreset: 'Usa Preset',
    teamBuilder: 'Team Builder',
    entryAgent: 'Agente Entry / Manager',
    teamName: 'Nome del Team',
    teamDescription: 'Descrizione',
    saveTeam: 'Salva Team',

    // Knowledge
    knowledgeTitle: 'Base di Conoscenza',
    uploadDocument: 'Carica Documento',
    systemKnowledge: 'System Knowledge',
    workspaceKnowledge: 'Workspace Knowledge',
    readOnlyProtected: 'Preinstallata (Read-only)',
    allScopes: 'Tutti',
    scope: 'Ambito',
    filename: 'Nome File',
    size: 'Dimensione',
    chunks: 'Chunk',
    indexedAt: 'Indicizzato il',
    status: 'Stato',
    noDocumentsFound: 'Nessun documento in questa vista',
    deleteDocument: 'Elimina Documento',

    // Settings
    settingsTitle: 'Impostazioni',
    generalTab: 'Generale',
    providersTab: 'Provider AI',
    workforceTab: 'Workforce',
    storageTab: 'Storage & Memoria',
    advancedTab: 'Avanzate & Diagnostica',
    language: 'Lingua',
    theme: 'Tema',
    themeLight: 'Chiaro',
    themeDark: 'Scuro',
    themeSystem: 'Sistema',
    providerTimeout: 'Timeout Provider (secondi)',
    timeoutHelp: 'I modelli locali (Ollama) richiedono tipicamente 120s+ per generazioni lunghe. I provider cloud usano 30s.',
    testConnection: 'Testa Connessione',
    testing: 'Verifica in corso...',
    connectionSuccess: 'Connessione riuscita con successo',
    saveSettings: 'Salva Impostazioni',
    apiKey: 'Chiave API',

    // Marketplace
    marketplaceTitle: 'Pacchetti Workforce & Marketplace',
    officialPresets: 'Preset Starter Ufficiali',
    communityPacks: 'Ecosistema Community',
    comingSoon: 'In Arrivo',
    installPreset: 'Installa e Attiva Preset',

    // Command Palette
    cmdPaletteTitle: 'Command Palette',
    cmdNewTask: 'Avvia Nuovo Task',
    cmdNewConv: 'Crea Nuova Conversazione',
    cmdGoHome: 'Vai alla Home',
    cmdGoAgents: 'Vai agli Agenti',
    cmdGoTeams: 'Vai ai Team',
    cmdGoKnowledge: 'Vai alla Conoscenza',
    cmdGoSettings: 'Vai alle Impostazioni',
    cmdGoMarketplace: 'Vai al Marketplace',
    cmdToggleTheme: 'Alterna Tema Chiaro / Scuro',
    cmdSwitchLang: 'Cambia Lingua (EN / IT)',

    // Common
    cancel: 'Annulla',
    save: 'Salva',
    delete: 'Elimina',
    close: 'Chiudi',
    loading: 'Caricamento...',
    success: 'Operazione riuscita',
    error: 'Errore',
  }
};

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (key: keyof typeof translations['en']) => string;
}

export const LanguageContext = createContext<LanguageContextType>({
  language: 'en',
  setLanguage: () => {},
  t: (key) => translations.en[key] || key,
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => {
    const saved = localStorage.getItem('aether_language');
    if (saved === 'en' || saved === 'it') return saved;
    return navigator.language.startsWith('it') ? 'it' : 'en';
  });

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem('aether_language', lang);
  };

  const t = (key: keyof typeof translations['en']): string => {
    const dict = translations[language] || translations.en;
    return dict[key] || translations.en[key] || key;
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useTranslation() {
  return useContext(LanguageContext);
}
