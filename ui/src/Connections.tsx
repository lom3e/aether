import React, { useState, useEffect, useContext, useMemo } from 'react';
import {
  Calendar, Mail, GitBranch, MessageSquare, FileText,
  RefreshCw, Clock, Zap, Globe, Send,
  Shield, Trash2, Copy, Check,
  Plus, CheckCircle2, ArrowRight, Layers
} from 'lucide-react';
import { apiUrl } from './api';
import { ToastContext } from './toast';
import { submitApprovalDecision } from './canonicalNotification';
import { openExternalUrl } from './desktop';

// Design System Core Imports
import {
  PageContainer,
  Section,
  Stack,
  Grid,
  Panel,
  Modal,
  Drawer,
  Heading,
  Text,
  Button,
  IconButton,
  Switch,
  SegmentedControl,
  StatusBadge,
  AlertBanner,
  EmptyState,
  LoadingSpinner,
  AetherForm,
  AetherField,
  AetherInput,
  AetherPasswordInput,
  AetherSelect,
  AetherFormActions,
} from './design-system';

interface OAuthProviderInfo {
  provider: string;
  name: string;
  supports_oauth: boolean;
  ready_for_user_connect: boolean;
  requires_developer_setup: boolean;
  redirect_uri: string;
  setup_url: string;
  has_client_id: boolean;
  has_client_secret: boolean;
  client_id_preview?: string;
}

interface ConnectionItem {
  id: string;
  provider: string;
  account_name: string;
  status: string;
  scopes: string[];
  capabilities: string[];
  auth_metadata?: Record<string, any>;
  last_synced_at?: string;
  last_verified_at?: string;
  last_verification_error?: string;
  last_successful_operation?: string;
  verification_method?: string;
  updated_at?: string;
}

interface CalendarEventItem {
  id: string;
  title: string;
  start_time: string;
  end_time?: string;
  description?: string;
  location?: string;
  is_all_day?: boolean;
  start_date?: string;
  end_date?: string;
  time_zone?: string;
  html_link?: string;
}

function getEventDateKey(evt: CalendarEventItem): string {
  if (evt.start_date) {
    return evt.start_date;
  }
  if (evt.start_time) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(evt.start_time.trim())) {
      return evt.start_time.trim();
    }
    const d = new Date(evt.start_time);
    if (!isNaN(d.getTime())) {
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    }
  }
  return 'Senza data';
}

function formatDayLabel(dateKey: string): { label: string; isToday: boolean } {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) {
    return { label: dateKey, isToday: false };
  }
  const [y, m, d] = dateKey.split('-').map(Number);
  const eventDate = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const targetDateOnly = new Date(y, m - 1, d);
  targetDateOnly.setHours(0, 0, 0, 0);

  const diffDays = Math.round((targetDateOnly.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

  const formattedDate = eventDate.toLocaleDateString('it-IT', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  const capDate = formattedDate.charAt(0).toUpperCase() + formattedDate.slice(1);

  if (diffDays === 0) {
    return { label: `Oggi — ${capDate}`, isToday: true };
  }
  if (diffDays === 1) {
    return { label: `Domani — ${capDate}`, isToday: false };
  }
  if (diffDays === -1) {
    return { label: `Ieri — ${capDate}`, isToday: false };
  }
  return { label: capDate, isToday: false };
}

function formatEventTime(evt: CalendarEventItem): string {
  const isAllDay = evt.is_all_day || /^\d{4}-\d{2}-\d{2}$/.test(evt.start_time?.trim() || '');
  if (isAllDay) {
    return 'Tutto il giorno';
  }
  try {
    const start = new Date(evt.start_time);
    if (isNaN(start.getTime())) return '';
    const startStr = start.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
    if (evt.end_time) {
      const end = new Date(evt.end_time);
      if (!isNaN(end.getTime())) {
        const endStr = end.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
        return `${startStr} – ${endStr}`;
      }
    }
    return startStr;
  } catch {
    return '';
  }
}


interface ActionExecutionItem {
  id: string;
  action_id: string;
  status: string;
  input_data: any;
  output_data: any;
  created_at: string;
  error_message?: string;
}

interface ConnectionsProps {
  navigate?: (view: string, params?: any) => void;
  initialExecutionId?: string | null;
  initialTab?: 'apps' | 'calendar' | 'actions';
}

type CategoryType = 'all' | 'productivity' | 'dev' | 'communication';

interface ProviderDefinition {
  id: string;
  name: string;
  icon: React.ComponentType<{ size?: number; color?: string; className?: string }>;
  category: 'productivity' | 'dev' | 'communication';
  description: string;
  capabilitiesText: string;
  capabilitiesList: string[];
  color: string;
  builtIn: boolean;
  isOAuth: boolean;
}

const AVAILABLE_PROVIDERS: ProviderDefinition[] = [
  {
    id: 'calendar',
    name: 'Aether Calendario (Locale)',
    icon: Calendar,
    category: 'productivity',
    description: 'Agenda e archivio impegni integrato nel tuo spazio di lavoro, attivo anche senza connessione internet.',
    capabilitiesText: 'Consulta appuntamenti e memorizza incontri nello spazio di lavoro locale',
    capabilitiesList: [
      'Consulta impegni e riunioni',
      'Archiviazione sicura su database locale',
      'Funziona senza dipendenze cloud',
      'Indicizzazione automatica per la workforce',
    ],
    color: '#06b6d4',
    builtIn: true,
    isOAuth: false,
  },
  {
    id: 'google_calendar',
    name: 'Google Calendar',
    icon: Calendar,
    category: 'productivity',
    description: 'Integrazione ufficiale con Google per coordinare impegni personali e professionali con autorizzazione diretta.',
    capabilitiesText: 'Leggi calendari Google e pianifica riunioni con autorizzazione controllata',
    capabilitiesList: [
      'Lettura calendari personali e di team',
      'Pianificazione automatica di riunioni',
      'Aggiornamento impegni con supervisione',
      'Sincronizzazione continua nello spazio di lavoro',
    ],
    color: '#4285F4',
    builtIn: false,
    isOAuth: true,
  },
  {
    id: 'notion',
    name: 'Notion',
    icon: FileText,
    category: 'productivity',
    description: 'Sincronizza pagine di progetto, documentazione aziendale e tabelle di deliverable.',
    capabilitiesText: 'Accedi a database e pagine Notion per recuperare e pubblicare contenuti',
    capabilitiesList: [
      'Ricerca e indicizzazione note di progetto',
      'Lettura tabelle e proprietà di database',
      'Pubblicazione deliverable verificati',
      'Sincronizzazione bidirezionale con la memoria',
    ],
    color: '#000000',
    builtIn: false,
    isOAuth: true,
  },
  {
    id: 'github',
    name: 'GitHub',
    icon: GitBranch,
    category: 'dev',
    description: 'Accedi a repository, rami di sviluppo, issue e review automatiche di pull request.',
    capabilitiesText: 'Ispeziona codice sorgente, apri issue e suggerisci pull request supervisionate',
    capabilitiesList: [
      'Ispezione albero di codice e file',
      'Monitoraggio rami e commit recenti',
      'Creazione issue e note tecniche',
      'Preparazione pull request verificate',
    ],
    color: '#2dba4e',
    builtIn: false,
    isOAuth: true,
  },
  {
    id: 'openapi',
    name: 'Specifica OpenAPI 3.x',
    icon: Zap,
    category: 'dev',
    description: 'Collega qualsiasi API REST aziendale tramite il relativo file di specifica OpenAPI.',
    capabilitiesText: 'Scopri dinamicamente gli endpoint e valida le chiamate tramite schema formale',
    capabilitiesList: [
      'Scansione automatica degli endpoint disponibili',
      'Validazione rigorosa degli input',
      'Supporto per token e chiavi API',
      'Esecuzione controllata delle chiamate REST',
    ],
    color: '#8B5CF6',
    builtIn: false,
    isOAuth: false,
  },
  {
    id: 'http',
    name: 'Webhook / API HTTP Generica',
    icon: Globe,
    category: 'dev',
    description: 'Interagisci con servizi web generici e webhook personalizzati con policy di sicurezza.',
    capabilitiesText: 'Esegui chiamate HTTP (GET, POST, PUT, DELETE) con autenticazione via intestazione',
    capabilitiesList: [
      'Chiamate HTTP con intestazioni custom',
      'Supporto Bearer Token, API Key e Basic Auth',
      'Protezione SSRF e controllo degli accessi',
      'Supervisione delle azioni di modifica',
    ],
    color: '#6366f1',
    builtIn: false,
    isOAuth: false,
  },
  {
    id: 'slack',
    name: 'Slack',
    icon: MessageSquare,
    category: 'communication',
    description: 'Invia brief operativi, notifica i canali di team e ricevi feedback dalle conversazioni.',
    capabilitiesText: 'Pubblica aggiornamenti di stato e avvisi sui canali con approvazione',
    capabilitiesList: [
      'Invio report di avanzamento ai canali',
      'Notifiche operative in tempo reale',
      'Supporto Bot Token o Incoming Webhook',
      'Canale di destinazione predefinito configurabile',
    ],
    color: '#4A154B',
    builtIn: false,
    isOAuth: true,
  },
  {
    id: 'email',
    name: 'Email Aziendale / SMTP',
    icon: Mail,
    category: 'communication',
    description: 'Prepara bozze di riepilogo, redigi comunicazioni e invia email verificate via SMTP sicuro.',
    capabilitiesText: 'Prepara e invia email via SMTP previa esplicita approvazione dell\'utente',
    capabilitiesList: [
      'Composizione guidata di email strutturate',
      'Cifratura STARTTLS e SSL/TLS nativa',
      'Indirizzo mittente e alias personalizzabili',
      'Invio controllato con gating di approvazione',
    ],
    color: '#EA4335',
    builtIn: false,
    isOAuth: false,
  },
  {
    id: 'telegram',
    name: 'Telegram Companion Bot',
    icon: Send,
    category: 'communication',
    description: 'Comunica con Aether da smartphone, ricevi notifiche istantanee e approva azioni in mobilità.',
    capabilitiesText: 'Ricevi comandi da smartphone e gestisci approvazioni con bottoni interattivi',
    capabilitiesList: [
      'Notifiche push istantanee su Telegram',
      'Approvazione rapida di task con pulsanti inline',
      'Protezione tramite lista di utenti autorizzati',
      'Esecuzione remota di compiti per il Companion',
    ],
    color: '#229ED9',
    builtIn: false,
    isOAuth: false,
  },
];

export function Connections({ initialExecutionId, initialTab }: ConnectionsProps) {
  const showToast = useContext(ToastContext);

  const [activeTab, setActiveTab] = useState<'apps' | 'calendar' | 'actions'>(
    initialTab || (initialExecutionId ? 'actions' : 'apps')
  );
  const [categoryFilter, setCategoryFilter] = useState<CategoryType>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [actionStatusFilter, setActionStatusFilter] = useState<string>('all');

  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [connections, setConnections] = useState<ConnectionItem[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEventItem[]>([]);
  const [executions, setExecutions] = useState<ActionExecutionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [verifyingProvider, setVerifyingProvider] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);

  // Manage Connection Drawer
  const [manageProvider, setManageProvider] = useState<ProviderDefinition | null>(null);
  const [showTechDetails, setShowTechDetails] = useState(false);

  // Disconnect Confirmation Modal
  const [disconnectTarget, setDisconnectTarget] = useState<{ id: string; name: string } | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);

  // Google Calendar States
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState<CalendarEventItem[]>([]);
  const [selectedScheduleSource, setSelectedScheduleSource] = useState<'local' | 'google'>('local');
  const [isGoogleModalOpen, setIsGoogleModalOpen] = useState(false);
  const [googleClientId, setGoogleClientId] = useState('');
  const [googleClientSecret, setGoogleClientSecret] = useState('');
  const [googleAuthPending, setGoogleAuthPending] = useState(false);
  const [googleManualCode, setGoogleManualCode] = useState('');
  const [googleState, setGoogleState] = useState('');
  const [googleAdvOpen, setGoogleAdvOpen] = useState(false);
  const [isCalendarPickerOpen, setIsCalendarPickerOpen] = useState(false);
  const [googleCalendars, setGoogleCalendars] = useState<{ id: string; summary: string; primary: boolean; description?: string }[]>([]);

  // OAuth Management States
  const [oauthProviders, setOauthProviders] = useState<Record<string, OAuthProviderInfo>>({});
  const [oauthPendingProvider, setOauthPendingProvider] = useState<string | null>(null);

  // Dedicated Developer App Setup Modal (GitHub, Slack, Notion)
  const [devSetupModalProvider, setDevSetupModalProvider] = useState<ProviderDefinition | null>(null);
  const [devClientId, setDevClientId] = useState('');
  const [devClientSecret, setDevClientSecret] = useState('');
  const [savingDevConfig, setSavingDevConfig] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  // Dedicated Guided Telegram Modal
  const [isTelegramModalOpen, setIsTelegramModalOpen] = useState(false);
  const [telegramAdvOpen, setTelegramAdvOpen] = useState(false);
  const [verifyingTelegram, setVerifyingTelegram] = useState(false);

  // New Event Form State
  const [isEventModalOpen, setIsEventModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newStartTime, setNewStartTime] = useState('');
  const [newLocation, setNewLocation] = useState('');
  const [creatingEvent, setCreatingEvent] = useState(false);

  // Config Modal State (Generic Credentials)
  const [configModalProvider, setConfigModalProvider] = useState<ProviderDefinition | null>(null);
  const [credAccountName, setCredAccountName] = useState('');
  const [githubToken, setGithubToken] = useState('');
  const [slackToken, setSlackToken] = useState('');
  const [slackWebhook, setSlackWebhook] = useState('');
  const [slackDefaultChannel, setSlackDefaultChannel] = useState('');
  const [emailUser, setEmailUser] = useState('');
  const [emailPass, setEmailPass] = useState('');
  const [emailHost, setEmailHost] = useState('smtp.gmail.com');
  const [emailPort, setEmailPort] = useState('587');
  const [emailUseTls, setEmailUseTls] = useState(true);
  const [emailUseSsl, setEmailUseSsl] = useState(false);
  const [emailSenderAddr, setEmailSenderAddr] = useState('');
  const [emailTestRecipient, setEmailTestRecipient] = useState('');
  const [httpBaseUrl, setHttpBaseUrl] = useState('');
  const [httpAuthType, setHttpAuthType] = useState('none');
  const [httpToken, setHttpToken] = useState('');
  const [notionToken, setNotionToken] = useState('');
  const [notionDbId, setNotionDbId] = useState('');
  const [telegramBotToken, setTelegramBotToken] = useState('');
  const [telegramDefaultChatId, setTelegramDefaultChatId] = useState('');
  const [telegramAllowedChats, setTelegramAllowedChats] = useState('');
  const [openapiSpecUrl, setOpenapiSpecUrl] = useState('');
  const [openapiSpecPath, setOpenapiSpecPath] = useState('');
  const [openapiBaseUrl, setOpenapiBaseUrl] = useState('');
  const [openapiAuthType, setOpenapiAuthType] = useState('none');
  const [openapiToken, setOpenapiToken] = useState('');
  const [testingCreds, setTestingCreds] = useState(false);
  const [savingCreds, setSavingCreds] = useState(false);
  const [testResult, setTestResult] = useState<{ valid: boolean; message: string } | null>(null);

  const fetchAll = () => {
    setLoading(true);
    Promise.all([
      fetch(apiUrl('/api/connections')).then((r) => r.json()),
      fetch(apiUrl('/api/connections/calendar/events')).then((r) => r.json()),
      fetch(apiUrl('/api/connections/google_calendar/events')).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch(apiUrl('/api/actions/executions')).then((r) => r.json()),
      fetch(apiUrl('/api/connections/oauth/providers')).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
    ])
      .then(([conns, evts, gEvts, execs, oauths]) => {
        if (Array.isArray(conns)) setConnections(conns);
        if (Array.isArray(evts)) setCalendarEvents(evts);
        if (Array.isArray(gEvts)) setGoogleCalendarEvents(gEvts);
        if (Array.isArray(execs)) setExecutions(execs);
        if (oauths && typeof oauths === 'object') {
          setOauthProviders(oauths as Record<string, OAuthProviderInfo>);
        }
      })
      .catch((err) => {
        console.error('Error loading connections data', err);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchAll();
  }, []);

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab);
    } else if (initialExecutionId) {
      setActiveTab('actions');
    }
  }, [initialTab, initialExecutionId]);

  const handleApproveAction = async (executionId: string) => {
    if (actionLoadingId === executionId) return;
    setActionLoadingId(executionId);
    try {
      const res = await submitApprovalDecision({
        target_type: 'action_execution',
        target_id: executionId,
        decision: 'approve',
        approver: 'user',
      });
      if (res.success) {
        showToast(res.message || 'Operazione approvata con successo.', 'success');
        fetchAll();
      } else {
        showToast(res.message || 'Impossibile approvare l\'operazione.', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Errore durante l\'approvazione.', 'error');
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleRejectAction = async (executionId: string) => {
    if (actionLoadingId === executionId) return;
    setActionLoadingId(executionId);
    try {
      const res = await submitApprovalDecision({
        target_type: 'action_execution',
        target_id: executionId,
        decision: 'reject',
        reason: 'Rifiutato dall\'utente',
      });
      if (res.success) {
        showToast(res.message || 'Operazione rifiutata.', 'info');
        fetchAll();
      } else {
        showToast(res.message || 'Impossibile rifiutare l\'operazione.', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Errore durante il rifiuto.', 'error');
    } finally {
      setActionLoadingId(null);
    }
  };

  const openConfigModal = (provider: ProviderDefinition, existingConn?: ConnectionItem) => {
    setConfigModalProvider(provider);
    setCredAccountName(existingConn?.account_name || `Account ${provider.name}`);
    setTestResult(null);
    setGithubToken('');
    setSlackToken('');
    setSlackWebhook('');
    setSlackDefaultChannel('');
    setEmailUser('');
    setEmailPass('');
    setEmailHost('smtp.gmail.com');
    setEmailPort('587');
    setEmailUseTls(true);
    setEmailUseSsl(false);
    setEmailSenderAddr('');
    setEmailTestRecipient('');
    setHttpBaseUrl('');
    setHttpAuthType('none');
    setHttpToken('');
    setNotionToken('');
    setNotionDbId('');
    setTelegramBotToken('');
    setTelegramDefaultChatId('');
    setTelegramAllowedChats('');
    setOpenapiSpecUrl('');
    setOpenapiSpecPath('');
    setOpenapiBaseUrl('');
    setOpenapiAuthType('none');
    setOpenapiToken('');

    if (existingConn?.auth_metadata) {
      const meta = existingConn.auth_metadata;
      if (provider.id === 'email') {
        if (meta.username) setEmailUser(meta.username);
        if (meta.smtp_host) setEmailHost(meta.smtp_host);
        if (meta.smtp_port) setEmailPort(String(meta.smtp_port));
        if (meta.use_tls !== undefined) setEmailUseTls(Boolean(meta.use_tls));
        if (meta.use_ssl !== undefined) setEmailUseSsl(Boolean(meta.use_ssl));
        if (meta.sender_address) setEmailSenderAddr(meta.sender_address);
        if (meta.test_recipient) setEmailTestRecipient(meta.test_recipient);
      }
      if (provider.id === 'slack' && meta.default_channel) {
        setSlackDefaultChannel(meta.default_channel);
      }
      if (provider.id === 'http') {
        if (meta.base_url) setHttpBaseUrl(meta.base_url);
        if (meta.auth_type) setHttpAuthType(meta.auth_type);
      }
      if (provider.id === 'notion' && meta.default_database_id) {
        setNotionDbId(meta.default_database_id);
      }
      if (provider.id === 'openapi') {
        if (meta.spec_url) setOpenapiSpecUrl(meta.spec_url);
        if (meta.spec_path) setOpenapiSpecPath(meta.spec_path);
        if (meta.base_url) setOpenapiBaseUrl(meta.base_url);
        if (meta.auth_type) setOpenapiAuthType(meta.auth_type);
      }
      if (provider.id === 'telegram') {
        if (meta.default_chat_id) setTelegramDefaultChatId(String(meta.default_chat_id));
        if (meta.allowed_chat_ids) {
          setTelegramAllowedChats(
            Array.isArray(meta.allowed_chat_ids)
              ? meta.allowed_chat_ids.join(', ')
              : String(meta.allowed_chat_ids)
          );
        }
      }
    }
  };

  const handleVerifyConnection = async (providerId: string) => {
    try {
      setVerifyingProvider(providerId);
      const res = await fetch(apiUrl(`/api/connections/${providerId}/verify`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ live_check: true }),
      });
      const data = await res.json();
      if (data.valid) {
        showToast('Verifica completata: il servizio è attivo e funzionante.', 'success');
      } else {
        showToast(data.message || 'La verifica ha rilevato un problema di autenticazione.', 'error');
      }
      await fetchAll();
    } catch (err: any) {
      showToast(err.message || 'Richiesta di verifica non riuscita.', 'error');
    } finally {
      setVerifyingProvider(null);
    }
  };

  const buildAuthMetadata = (providerId: string) => {
    const meta: Record<string, any> = {};
    if (providerId === 'github') meta.token = githubToken.trim();
    if (providerId === 'slack') {
      if (slackToken.trim()) meta.token = slackToken.trim();
      if (slackWebhook.trim()) meta.webhook_url = slackWebhook.trim();
      if (slackDefaultChannel.trim()) meta.default_channel = slackDefaultChannel.trim();
    }
    if (providerId === 'email') {
      meta.username = emailUser.trim();
      meta.password = emailPass;
      meta.smtp_host = emailHost.trim();
      meta.smtp_port = parseInt(emailPort, 10) || 587;
      meta.use_tls = emailUseTls;
      meta.use_ssl = emailUseSsl;
      if (emailSenderAddr.trim()) meta.sender_address = emailSenderAddr.trim();
      if (emailTestRecipient.trim()) meta.test_recipient = emailTestRecipient.trim();
    }
    if (providerId === 'http') {
      meta.base_url = httpBaseUrl.trim();
      meta.auth_type = httpAuthType;
      if (httpToken.trim()) meta.token = httpToken.trim();
    }
    if (providerId === 'notion') {
      meta.token = notionToken.trim();
      if (notionDbId.trim()) meta.default_database_id = notionDbId.trim();
    }
    if (providerId === 'telegram') {
      meta.bot_token = telegramBotToken.trim();
      if (telegramDefaultChatId.trim()) meta.default_chat_id = telegramDefaultChatId.trim();
      if (telegramAllowedChats.trim()) {
        meta.allowed_chat_ids = telegramAllowedChats.split(',').map((s) => s.trim()).filter(Boolean);
      }
    }
    if (providerId === 'openapi') {
      if (openapiSpecUrl.trim()) meta.spec_url = openapiSpecUrl.trim();
      if (openapiSpecPath.trim()) meta.spec_path = openapiSpecPath.trim();
      if (openapiBaseUrl.trim()) meta.base_url = openapiBaseUrl.trim();
      if (openapiAuthType.trim()) meta.auth_type = openapiAuthType.trim();
      if (openapiToken.trim()) meta.token = openapiToken.trim();
    }
    return meta;
  };

  const handleTestCreds = async () => {
    if (!configModalProvider) return;
    setTestingCreds(true);
    setTestResult(null);
    try {
      const authMeta = buildAuthMetadata(configModalProvider.id);
      const res = await fetch(apiUrl(`/api/connections/${configModalProvider.id}/verify`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          auth_metadata: authMeta,
          live_check: true,
        }),
      });
      const data = await res.json();
      setTestResult({
        valid: Boolean(data.valid),
        message: data.message || (data.valid ? 'Credenziali verificate con successo.' : 'Verifica non riuscita.'),
      });
    } catch {
      setTestResult({
        valid: false,
        message: 'Impossibile contattare il server locale per la verifica.',
      });
    } finally {
      setTestingCreds(false);
    }
  };

  const handleSaveAndConnect = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!configModalProvider) return;

    const authMeta = buildAuthMetadata(configModalProvider.id);
    setSavingCreds(true);
    try {
      const res = await fetch(apiUrl('/api/connections'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: configModalProvider.id,
          account_name: credAccountName.trim() || `Account ${configModalProvider.name}`,
          auth_metadata: authMeta,
          live_check: false,
        }),
      });
      if (res.ok) {
        showToast(`Servizio ${configModalProvider.name} collegato con successo.`, 'success');
        setConfigModalProvider(null);
        fetchAll();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Impossibile salvare la connessione.', 'error');
      }
    } catch {
      showToast('Errore durante il salvataggio del servizio.', 'error');
    } finally {
      setSavingCreds(false);
    }
  };

  const handleConnectCalendar = async () => {
    try {
      const res = await fetch(apiUrl('/api/connections'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: 'calendar',
          account_name: 'Aether Calendario (Locale)',
          auth_metadata: { type: 'sqlite_built_in' },
        }),
      });
      if (res.ok) {
        showToast('Calendario locale pronto e attivo.', 'success');
        fetchAll();
      }
    } catch {
      showToast('Impossibile inizializzare il calendario locale.', 'error');
    }
  };

  const confirmDisconnect = async () => {
    if (!disconnectTarget) return;
    setDisconnecting(true);
    try {
      const res = await fetch(apiUrl(`/api/connections/${disconnectTarget.id}/disconnect`), {
        method: 'POST',
      });
      if (res.ok) {
        showToast(`Servizio ${disconnectTarget.name} scollegato.`, 'info');
        setDisconnectTarget(null);
        setManageProvider(null);
        fetchAll();
      } else {
        showToast('Impossibile scollegare il servizio.', 'error');
      }
    } catch {
      showToast('Errore di comunicazione durante la disconnessione.', 'error');
    } finally {
      setDisconnecting(false);
    }
  };

  const handleSyncAll = async () => {
    setSyncingAll(true);
    try {
      const res = await fetch(apiUrl('/api/connections/sync_all'), { method: 'POST' });
      const data = await res.json();
      const total = data.total_items_ingested || 0;
      if (total === 0) {
        showToast('Sincronizzazione completata: nessun nuovo elemento rilevato.', 'info');
      } else {
        showToast(`Sincronizzati ${total} elementi nella memoria dello spazio di lavoro!`, 'success');
      }
      await fetchAll();
    } catch (err: any) {
      showToast(err.message || 'Impossibile sincronizzare i servizi.', 'error');
    } finally {
      setSyncingAll(false);
    }
  };

  const handleStartGoogleOAuth = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const gInfo = oauthProviders['google_calendar'];
    const trimmedId = googleClientId.trim();
    const trimmedSecret = googleClientSecret.trim();

    if (!gInfo?.has_client_id && !trimmedId) {
      showToast('Configura il tuo Google Client ID prima di avviare l\'autorizzazione.', 'error');
      return;
    }

    setGoogleAuthPending(true);
    try {
      // If user provided or changed client ID or secret in modal, save config first
      if (trimmedId || trimmedSecret) {
        await fetch(apiUrl('/api/connections/google_calendar/oauth/config'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: trimmedId || undefined,
            client_secret: trimmedSecret || undefined,
          }),
        });
      }

      const res = await fetch(apiUrl('/api/connections/google_calendar/oauth/start'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: trimmedId || undefined,
          client_secret: trimmedSecret || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Impossibile avviare l\'autorizzazione Google.');
      }
      setGoogleState(data.state || '');

      // Open in host/system browser directly
      await openExternalUrl(data.auth_url);

      const messageHandler = (event: MessageEvent) => {
        if (event.data?.type === 'aether_oauth_success' && event.data?.provider === 'google_calendar') {
          window.removeEventListener('message', messageHandler);
          clearInterval(pollTimer);
          showToast('Google Calendar collegato con successo!', 'success');
          setIsGoogleModalOpen(false);
          setGoogleAuthPending(false);
          fetchAll();
        } else if (event.data?.type === 'aether_oauth_error' && event.data?.provider === 'google_calendar') {
          window.removeEventListener('message', messageHandler);
          clearInterval(pollTimer);
          showToast(`Autorizzazione Google fallita: ${event.data.error || 'errore'}`, 'error');
          setGoogleAuthPending(false);
          fetchAll();
        }
      };
      window.addEventListener('message', messageHandler);

      let attempts = 0;
      const pollTimer = setInterval(async () => {
        attempts++;
        if (attempts > 80) {
          clearInterval(pollTimer);
          window.removeEventListener('message', messageHandler);
          setGoogleAuthPending(false);
          return;
        }
        try {
          const checkRes = await fetch(apiUrl('/api/connections'));
          if (checkRes.ok) {
            const conns = await checkRes.json();
            if (Array.isArray(conns)) {
              const gc = conns.find((c: any) => c.provider === 'google_calendar');
              if (gc && (gc.status === 'verified' || gc.status === 'connected')) {
                clearInterval(pollTimer);
                window.removeEventListener('message', messageHandler);
                showToast('Google Calendar collegato e verificato!', 'success');
                setIsGoogleModalOpen(false);
                setGoogleAuthPending(false);
                fetchAll();
              }
            }
          }
        } catch {}
      }, 1500);
    } catch (err: any) {
      showToast(err.message || 'Errore durante l\'avvio di Google OAuth', 'error');
      setGoogleAuthPending(false);
    }
  };

  const copyToClipboard = (text: string, fieldKey: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(fieldKey);
    setTimeout(() => setCopiedField(null), 2000);
    showToast('Copiato negli appunti!', 'info');
  };

  const handleStartOAuth = async (provider: string) => {
    setOauthPendingProvider(provider);
    try {
      const res = await fetch(apiUrl(`/api/connections/${provider}/oauth/start`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Impossibile avviare l'autorizzazione per ${provider}.`);
      }
      if (data.auth_url) {
        await openExternalUrl(data.auth_url);
        const nameMap: Record<string, string> = {
          google_calendar: 'Google Calendar',
          github: 'GitHub',
          slack: 'Slack',
          notion: 'Notion',
        };
        const pName = nameMap[provider] || provider;
        showToast(`Apertura pagina di autorizzazione per ${pName}...`, 'info');

        let attempts = 0;
        const pollTimer = setInterval(async () => {
          attempts++;
          if (attempts > 80) {
            clearInterval(pollTimer);
            setOauthPendingProvider(null);
            return;
          }
          try {
            const checkRes = await fetch(apiUrl('/api/connections'));
            if (checkRes.ok) {
              const conns = await checkRes.json();
              if (Array.isArray(conns)) {
                const conn = conns.find((c: any) => c.provider === provider);
                if (conn && (conn.status === 'verified' || conn.status === 'connected')) {
                  clearInterval(pollTimer);
                  setOauthPendingProvider(null);
                  showToast(`${pName} collegato e attivo!`, 'success');
                  fetchAll();
                }
              }
            }
          } catch {}
        }, 1500);
      }
    } catch (err: any) {
      showToast(err.message || 'Errore durante l\'avvio dell\'autorizzazione.', 'error');
      setOauthPendingProvider(null);
    }
  };

  const openDevSetupModal = (p: ProviderDefinition) => {
    setDevSetupModalProvider(p);
    const existing = connections.find((c) => c.provider === p.id);
    if (existing?.auth_metadata?.client_id) {
      setDevClientId(existing.auth_metadata.client_id);
    } else {
      setDevClientId('');
    }
    setDevClientSecret('');
    setTestResult(null);
  };

  const handleSaveDevOAuthConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!devSetupModalProvider) return;
    if (!devClientId.trim() || !devClientSecret.trim()) {
      showToast('Client ID e Client Secret sono obbligatori.', 'error');
      return;
    }
    setSavingDevConfig(true);
    try {
      const res = await fetch(apiUrl(`/api/connections/${devSetupModalProvider.id}/oauth/config`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: devClientId.trim(),
          client_secret: devClientSecret.trim(),
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Impossibile salvare la configurazione per sviluppatori.');
      }
      showToast('Credenziali applicazione salvate con successo!', 'success');
      await fetchAll();
      const targetProv = devSetupModalProvider.id;
      setDevSetupModalProvider(null);
      await handleStartOAuth(targetProv);
    } catch (err: any) {
      showToast(err.message || 'Errore salvataggio credenziali.', 'error');
    } finally {
      setSavingDevConfig(false);
    }
  };

  const openTelegramModal = (conn?: ConnectionItem) => {
    if (conn && conn.auth_metadata) {
      setTelegramBotToken(conn.auth_metadata.bot_token || '');
      setTelegramDefaultChatId(conn.auth_metadata.default_chat_id || '');
      setTelegramAllowedChats(conn.auth_metadata.allowed_chat_ids || '');
    } else {
      setTelegramBotToken('');
      setTelegramDefaultChatId('');
      setTelegramAllowedChats('');
    }
    setTestResult(null);
    setIsTelegramModalOpen(true);
  };

  const handleConnectTelegramGuided = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!telegramBotToken.trim()) {
      showToast('Il Bot Token è obbligatorio per Telegram.', 'error');
      return;
    }
    setVerifyingTelegram(true);
    setTestResult(null);
    try {
      const authMeta: Record<string, any> = {
        bot_token: telegramBotToken.trim(),
        live_check: true,
      };
      if (telegramDefaultChatId.trim()) authMeta.default_chat_id = telegramDefaultChatId.trim();
      if (telegramAllowedChats.trim()) authMeta.allowed_chat_ids = telegramAllowedChats.trim();

      const verifyRes = await fetch(apiUrl('/api/connections/telegram/verify'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auth_metadata: authMeta, live_check: true }),
      });
      const verifyData = await verifyRes.json();
      if (!verifyData.valid) {
        setTestResult({ valid: false, message: verifyData.message || 'Verifica del token non riuscita.' });
        return;
      }

      const saveRes = await fetch(apiUrl('/api/connections'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: 'telegram',
          account_name: 'Telegram Companion',
          auth_metadata: authMeta,
          live_check: true,
        }),
      });
      if (saveRes.ok) {
        showToast('Telegram Companion collegato e attivo!', 'success');
        setIsTelegramModalOpen(false);
        fetchAll();
      } else {
        const err = await saveRes.json();
        setTestResult({ valid: false, message: err.detail || 'Impossibile salvare la connessione Telegram.' });
      }
    } catch (err: any) {
      setTestResult({ valid: false, message: err.message || 'Errore di connessione al server.' });
    } finally {
      setVerifyingTelegram(false);
    }
  };

  const handleManualExchangeCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!googleManualCode.trim() || !googleState.trim()) {
      showToast('Codice di autorizzazione e parametro di stato sono entrambi richiesti.', 'error');
      return;
    }
    setGoogleAuthPending(true);
    try {
      const res = await fetch(apiUrl('/api/connections/google_calendar/oauth/exchange'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: googleManualCode.trim(),
          state: googleState.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Scambio del codice di autorizzazione fallito.');
      }
      if (data.valid) {
        showToast('Google Calendar autorizzato e verificato con successo!', 'success');
        setIsGoogleModalOpen(false);
        setGoogleManualCode('');
        fetchAll();
      } else {
        showToast(`Verifica fallita: ${data.message}`, 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Errore durante l\'autorizzazione Google.', 'error');
    } finally {
      setGoogleAuthPending(false);
    }
  };

  const handleOpenCalendarPicker = async () => {
    try {
      const res = await fetch(apiUrl('/api/connections/google_calendar/calendars'));
      const data = await res.json();
      if (data.calendars && Array.isArray(data.calendars)) {
        setGoogleCalendars(data.calendars);
        setIsCalendarPickerOpen(true);
      } else {
        showToast('Nessun calendario Google trovato o errore di lettura.', 'error');
      }
    } catch {
      showToast('Impossibile caricare i calendari Google.', 'error');
    }
  };

  const handleSelectCalendar = async (calId: string, summary: string) => {
    try {
      const res = await fetch(apiUrl('/api/connections/google_calendar/select-calendar'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          calendar_id: calId,
          calendar_summary: summary,
        }),
      });
      if (res.ok) {
        showToast(`Calendario attivo impostato su: ${summary}`, 'success');
        setIsCalendarPickerOpen(false);
        fetchAll();
      }
    } catch {
      showToast('Impossibile selezionare il calendario.', 'error');
    }
  };

  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setCreatingEvent(true);
    try {
      const endpoint =
        selectedScheduleSource === 'google'
          ? '/api/connections/google_calendar/events'
          : '/api/connections/calendar/events';

      const res = await fetch(apiUrl(endpoint), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newTitle.trim(),
          start_time: newStartTime || new Date().toISOString(),
          location: newLocation.trim(),
        }),
      });
      if (res.ok) {
        showToast(
          selectedScheduleSource === 'google'
            ? 'Appuntamento creato su Google Calendar.'
            : 'Appuntamento registrato sul calendario locale.',
          'success'
        );
        setIsEventModalOpen(false);
        setNewTitle('');
        setNewStartTime('');
        setNewLocation('');
        fetchAll();
      }
    } catch {
      showToast('Errore durante la creazione dell\'appuntamento.', 'error');
    } finally {
      setCreatingEvent(false);
    }
  };

  // Grouping & Filtering
  const filteredProviders = useMemo(() => {
    return AVAILABLE_PROVIDERS.filter((p) => {
      if (categoryFilter !== 'all' && p.category !== categoryFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const conn = connections.find((c) => c.provider === p.id);
        const nameMatch = p.name.toLowerCase().includes(query);
        const descMatch = p.description.toLowerCase().includes(query);
        const accountMatch = conn?.account_name?.toLowerCase().includes(query);
        const capMatch = p.capabilitiesList.some((cap) => cap.toLowerCase().includes(query));
        if (!nameMatch && !descMatch && !accountMatch && !capMatch) return false;
      }
      return true;
    });
  }, [categoryFilter, searchQuery, connections]);

  // Chronologically grouped calendar events
  const groupedEvents = useMemo(() => {
    const list = selectedScheduleSource === 'local' ? calendarEvents : googleCalendarEvents;
    const groups: { dateKey: string; label: string; isToday: boolean; events: CalendarEventItem[] }[] = [];
    const map = new Map<string, CalendarEventItem[]>();

    list.forEach((evt) => {
      const key = getEventDateKey(evt);
      if (!map.has(key)) {
        map.set(key, []);
      }
      map.get(key)!.push(evt);
    });

    const sortedKeys = Array.from(map.keys()).sort();
    sortedKeys.forEach((key) => {
      const { label, isToday } = formatDayLabel(key);
      groups.push({
        dateKey: key,
        label,
        isToday,
        events: map.get(key)!,
      });
    });

    return groups;
  }, [selectedScheduleSource, calendarEvents, googleCalendarEvents]);

  // Filtered executions
  const filteredExecutions = useMemo(() => {
    if (actionStatusFilter === 'all') return executions;
    if (actionStatusFilter === 'pending') {
      return executions.filter((e) => e.status === 'pending_approval' || e.status === 'waiting_approval');
    }
    if (actionStatusFilter === 'succeeded') {
      return executions.filter((e) => e.status === 'success' || e.status === 'succeeded');
    }
    if (actionStatusFilter === 'failed') {
      return executions.filter((e) => e.status === 'failed' || e.status === 'error');
    }
    return executions;
  }, [executions, actionStatusFilter]);

  // Primary Connect Action Handler
  const handlePrimaryAction = (provider: ProviderDefinition, conn?: ConnectionItem) => {
    const isConn = conn && (conn.status === 'verified' || conn.status === 'connected');
    if (isConn) {
      setManageProvider(provider);
      return;
    }

    if (provider.id === 'calendar') {
      handleConnectCalendar();
      return;
    }

    if (provider.id === 'google_calendar') {
      const existing = connections.find((c) => c.provider === 'google_calendar');
      if (existing?.auth_metadata?.client_id && !googleClientId) {
        setGoogleClientId(existing.auth_metadata.client_id);
      }
      setIsGoogleModalOpen(true);
      return;
    }

    if (provider.id === 'telegram') {
      openTelegramModal(conn);
      return;
    }

    // Providers with OAuth capability (GitHub, Slack, Notion)
    const oInfo = oauthProviders[provider.id];
    if (provider.isOAuth && oInfo?.supports_oauth) {
      if (oInfo.ready_for_user_connect) {
        handleStartOAuth(provider.id);
      } else {
        openDevSetupModal(provider);
      }
      return;
    }

    // Default configuration form
    openConfigModal(provider, conn);
  };

  return (
    <PageContainer size="xl">
      {/* 1. Header Section */}
      <Section
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Layers size={26} color="hsl(var(--primary))" />
            <Heading level={1}>Servizi Collegati</Heading>
          </div>
        }
        description="Collega le app che usi ogni giorno e lascia che Aether le utilizzi quando servono."
        actions={
          <Stack direction="row" gap="sm" align="center">
            <Button
              variant="secondary"
              size="sm"
              onClick={fetchAll}
              disabled={loading}
              leftIcon={<RefreshCw size={14} className={loading ? 'animate-spin' : ''} />}
            >
              Aggiorna
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSyncAll}
              disabled={syncingAll}
              leftIcon={<RefreshCw size={14} className={syncingAll ? 'animate-spin' : ''} />}
            >
              {syncingAll ? 'Sincronizzazione…' : 'Sincronizza tutto'}
            </Button>
          </Stack>
        }
      />

      {/* 2. Navigation View Switcher (Tabs) */}
      <Stack direction="column" gap="lg" style={{ marginBottom: '24px' }}>
        <SegmentedControl
          value={activeTab}
          onChange={(tab) => setActiveTab(tab as any)}
          options={[
            {
              value: 'apps',
              label: 'Servizi',
              icon: <Globe size={15} />,
            },
            {
              value: 'calendar',
              label: 'Calendario & Agenda',
              icon: <Calendar size={15} />,
            },
            {
              value: 'actions',
              label: 'Storico Operazioni & Approvazioni',
              icon: <Clock size={15} />,
            },
          ]}
        />
      </Stack>

      {/* =========================================================================
          TAB 1: SERVIZI COLLEGATI (APPS)
          ========================================================================= */}
      {activeTab === 'apps' && (
        <Stack direction="column" gap="lg">
          {/* Filter Bar: Categories & Search */}
          <Panel variant="default" style={{ padding: '14px 18px' }}>
            <Stack
              direction="row"
              gap="md"
              align="center"
              justify="between"
              wrap
            >
              <SegmentedControl
                value={categoryFilter}
                onChange={(cat) => setCategoryFilter(cat as CategoryType)}
                options={[
                  { value: 'all', label: 'Tutti i servizi' },
                  { value: 'productivity', label: 'Produttività' },
                  { value: 'dev', label: 'Sviluppo' },
                  { value: 'communication', label: 'Comunicazione' },
                ]}
              />

              <div style={{ minWidth: '240px', flex: '1', maxWidth: '340px' }}>
                <AetherInput
                  placeholder="Cerca servizio o capacità…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            </Stack>
          </Panel>

          {/* Provider Grid */}
          {filteredProviders.length === 0 ? (
            <EmptyState
              icon={<Globe size={28} />}
              title="Nessun servizio trovato"
              description="Nessun servizio corrisponde ai criteri di ricerca o alla categoria selezionata."
              action={
                <Button variant="secondary" onClick={() => { setSearchQuery(''); setCategoryFilter('all'); }}>
                  Reimposta filtri
                </Button>
              }
            />
          ) : (
            <Grid minItemWidth={330} gap="lg">
              {filteredProviders.map((provider) => {
                const conn = connections.find((c) => c.provider === provider.id);
                const isConnected = conn && (conn.status === 'verified' || conn.status === 'connected');
                const isConnecting = oauthPendingProvider === provider.id || verifyingProvider === provider.id;
                const IconComponent = provider.icon;

                // Truthful status determination
                const oInfo = oauthProviders[provider.id];
                const needsDevSetup = provider.isOAuth && oInfo?.supports_oauth && !oInfo.ready_for_user_connect;

                let displayStatus = 'NOT_CONFIGURED';
                if (isConnecting) {
                  displayStatus = 'CONNECTING';
                } else if (conn && conn.status !== 'not_configured') {
                  displayStatus = conn.status;
                } else if (needsDevSetup) {
                  displayStatus = 'SETUP_REQUIRED';
                }

                return (
                  <Panel
                    key={provider.id}
                    variant="default"
                    className="ds-panel--interactive"
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      height: '100%',
                    }}
                    onClick={() => handlePrimaryAction(provider, conn)}
                  >
                    <Stack direction="column" gap="md">
                      {/* Card Header: Icon, Title & Status Badge */}
                      <Stack direction="row" gap="md" align="center" justify="between">
                        <Stack direction="row" gap="md" align="center">
                          <div
                            style={{
                              width: '42px',
                              height: '42px',
                              borderRadius: '10px',
                              backgroundColor: `${provider.color}18`,
                              color: provider.color,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0,
                            }}
                          >
                            <IconComponent size={22} color={provider.color} />
                          </div>
                          <Stack gap="none">
                            <Heading level={4}>{provider.name}</Heading>
                            {isConnected && conn?.account_name && (
                              <Text size="xs" variant="muted" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Shield size={12} color="hsl(var(--success))" />
                                {conn.account_name}
                              </Text>
                            )}
                          </Stack>
                        </Stack>

                        <StatusBadge status={displayStatus} />
                      </Stack>

                      {/* Card Body: Simple description */}
                      <Text size="sm" variant="muted" style={{ minHeight: '40px' }}>
                        {provider.description}
                      </Text>

                      {/* Capabilities pill */}
                      <div
                        style={{
                          backgroundColor: 'hsl(var(--muted) / 0.4)',
                          borderRadius: '6px',
                          padding: '6px 10px',
                          fontSize: '12px',
                          color: 'hsl(var(--fg))',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                      >
                        <Zap size={13} color="hsl(var(--primary))" style={{ flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {provider.capabilitiesText}
                        </span>
                      </div>

                      {/* Error notice if connection failed */}
                      {conn && (conn.status === 'error' || conn.status === 'verification_failed') && (
                        <AlertBanner variant="error" title="Attenzione richiesta">
                          {conn.last_verification_error || 'Autenticazione scaduta o non valida.'}
                        </AlertBanner>
                      )}
                    </Stack>

                    {/* Card Footer: Single Primary Action */}
                    <div
                      style={{
                        marginTop: '16px',
                        paddingTop: '14px',
                        borderTop: '1px solid hsl(var(--border))',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '8px',
                      }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {isConnected ? (
                        <>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => setManageProvider(provider)}
                            leftIcon={<Shield size={14} />}
                          >
                            Gestisci
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={verifyingProvider === provider.id}
                            onClick={() => handleVerifyConnection(provider.id)}
                            leftIcon={
                              verifyingProvider === provider.id ? (
                                <LoadingSpinner size="sm" />
                              ) : (
                                <RefreshCw size={13} />
                              )
                            }
                          >
                            Verifica
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant={needsDevSetup ? 'secondary' : 'primary'}
                          size="sm"
                          fullWidth
                          disabled={isConnecting}
                          onClick={() => handlePrimaryAction(provider, conn)}
                          rightIcon={<ArrowRight size={14} />}
                        >
                          {isConnecting
                            ? 'Connessione…'
                            : provider.isOAuth
                            ? (needsDevSetup ? 'Configura' : 'Collega')
                            : 'Configura'}
                        </Button>
                      )}
                    </div>
                  </Panel>
                );
              })}
            </Grid>
          )}
        </Stack>
      )}

      {/* =========================================================================
          TAB 2: CALENDARIO & AGENDA
          ========================================================================= */}
      {activeTab === 'calendar' && (
        <Stack direction="column" gap="lg">
          <Panel variant="default" style={{ padding: '16px 20px' }}>
            <Stack direction="row" gap="md" align="center" justify="between" wrap>
              <SegmentedControl
                value={selectedScheduleSource}
                onChange={(src) => setSelectedScheduleSource(src as any)}
                options={[
                  {
                    value: 'local',
                    label: 'Calendario Locale Aether',
                    icon: <Calendar size={15} />,
                  },
                  {
                    value: 'google',
                    label: 'Google Calendar (Cloud)',
                    icon: <Globe size={15} />,
                  },
                ]}
              />

              <Stack direction="row" gap="sm">
                {selectedScheduleSource === 'google' && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleOpenCalendarPicker}
                    leftIcon={<Calendar size={14} />}
                  >
                    Seleziona calendario
                  </Button>
                )}
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setIsEventModalOpen(true)}
                  leftIcon={<Plus size={14} />}
                >
                  Nuovo appuntamento
                </Button>
              </Stack>
            </Stack>
          </Panel>

          {/* Events List */}
          {groupedEvents.length === 0 ? (
            <EmptyState
              icon={<Calendar size={28} />}
              title="Nessun appuntamento in programma"
              description={
                selectedScheduleSource === 'google'
                  ? 'Nessun evento in programma nei prossimi giorni. Assicurati che l\'integrazione sia attiva o sincronizza gli eventi.'
                  : 'Il calendario locale è vuoto. Aggiungi il tuo primo impegno per iniziare.'
              }
              action={
                <Button
                  variant="primary"
                  onClick={() => setIsEventModalOpen(true)}
                  leftIcon={<Plus size={15} />}
                >
                  Aggiungi appuntamento
                </Button>
              }
            />
          ) : (
            <Stack direction="column" gap="xl">
              {groupedEvents.map((group) => (
                <div key={group.dateKey}>
                  {/* Day Header */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: '12px',
                      paddingBottom: '8px',
                      borderBottom: '1px solid hsl(var(--border) / 0.6)',
                    }}
                  >
                    <Stack direction="row" gap="sm" align="center">
                      <Heading level={4} style={{ fontSize: '15px', margin: 0 }}>
                        {group.label}
                      </Heading>
                      {group.isToday && (
                        <span
                          style={{
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '2px 8px',
                            borderRadius: '10px',
                            backgroundColor: 'hsl(var(--primary) / 0.15)',
                            color: 'hsl(var(--primary))',
                            textTransform: 'uppercase',
                            letterSpacing: '0.04em',
                          }}
                        >
                          Oggi
                        </span>
                      )}
                    </Stack>
                    <Text size="xs" variant="muted">
                      {group.events.length} {group.events.length === 1 ? 'evento' : 'eventi'}
                    </Text>
                  </div>

                  {/* Day Events */}
                  <Grid minItemWidth={300} gap="md">
                    {group.events.map((evt) => {
                      const timeStr = formatEventTime(evt);
                      const isAllDay = timeStr === 'Tutto il giorno';

                      return (
                        <Panel key={evt.id} variant="default" style={{ padding: '16px' }}>
                          <Stack direction="column" gap="sm">
                            <Stack direction="row" align="center" justify="between" gap="sm">
                              <Heading level={4} style={{ fontSize: '15px' }}>
                                {evt.title}
                              </Heading>
                              <span
                                style={{
                                  fontSize: '12px',
                                  fontWeight: 500,
                                  padding: '3px 8px',
                                  borderRadius: '6px',
                                  backgroundColor: isAllDay
                                    ? 'hsl(var(--primary) / 0.12)'
                                    : 'hsl(var(--muted) / 0.5)',
                                  color: isAllDay ? 'hsl(var(--primary))' : 'hsl(var(--fg))',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '5px',
                                  flexShrink: 0,
                                }}
                              >
                                <Clock size={12} />
                                {timeStr}
                              </span>
                            </Stack>

                            {evt.description && (
                              <Text size="xs" variant="muted" style={{ lineHeight: '1.4' }}>
                                {evt.description}
                              </Text>
                            )}

                            {evt.location && (
                              <Text
                                size="xs"
                                variant="muted"
                                style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
                              >
                                📍 {evt.location}
                              </Text>
                            )}
                          </Stack>
                        </Panel>
                      );
                    })}
                  </Grid>
                </div>
              ))}
            </Stack>
          )}
        </Stack>
      )}

      {/* =========================================================================
          TAB 3: STORICO OPERAZIONI & APPROVAZIONI
          ========================================================================= */}
      {activeTab === 'actions' && (
        <Stack direction="column" gap="lg">
          <Panel variant="default" style={{ padding: '14px 18px' }}>
            <Stack direction="row" gap="md" align="center" justify="between" wrap>
              <SegmentedControl
                value={actionStatusFilter}
                onChange={(f) => setActionStatusFilter(f)}
                options={[
                  { value: 'all', label: 'Tutte le azioni' },
                  { value: 'pending', label: 'In attesa di approvazione' },
                  { value: 'succeeded', label: 'Completate' },
                  { value: 'failed', label: 'Fallite o respinte' },
                ]}
              />
              <Text size="xs" variant="muted">
                {filteredExecutions.length} operazioni registrate
              </Text>
            </Stack>
          </Panel>

          {filteredExecutions.length === 0 ? (
            <EmptyState
              icon={<Clock size={28} />}
              title="Nessuna operazione registrata"
              description="Quando Aether eseguirà o richiederà l'approvazione di azioni esterne (email, appuntamenti, commit), compariranno qui."
            />
          ) : (
            <Stack direction="column" gap="md">
              {filteredExecutions.map((exec) => {
                const isPending =
                  exec.status === 'pending_approval' || exec.status === 'waiting_approval';
                const isSuccess = exec.status === 'success' || exec.status === 'succeeded';

                return (
                  <Panel
                    key={exec.id}
                    variant="default"
                    id={`exec-card-${exec.id}`}
                    style={{
                      borderLeft: isPending
                        ? '3px solid hsl(var(--warning))'
                        : isSuccess
                        ? '3px solid hsl(var(--success))'
                        : '3px solid hsl(var(--destructive))',
                    }}
                  >
                    <Stack direction="row" gap="md" align="center" justify="between" wrap>
                      <Stack direction="column" gap="xs">
                        <Stack direction="row" gap="sm" align="center">
                          <Heading level={4}>{exec.action_id}</Heading>
                          <StatusBadge
                            status={
                              isPending
                                ? 'setup_required'
                                : isSuccess
                                ? 'connected'
                                : 'error'
                            }
                            label={
                              isPending
                                ? 'In attesa di approvazione'
                                : isSuccess
                                ? 'Completata con successo'
                                : 'Non riuscita'
                            }
                          />
                        </Stack>
                        <Text size="xs" variant="muted">
                          {new Date(exec.created_at).toLocaleString('it-IT')} — ID: {exec.id}
                        </Text>
                      </Stack>

                      {isPending && (
                        <Stack direction="row" gap="sm">
                          <Button
                            variant="primary"
                            size="sm"
                            loading={actionLoadingId === exec.id}
                            onClick={() => handleApproveAction(exec.id)}
                          >
                            Approva ed esegui
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            loading={actionLoadingId === exec.id}
                            onClick={() => handleRejectAction(exec.id)}
                          >
                            Rifiuta
                          </Button>
                        </Stack>
                      )}
                    </Stack>

                    {exec.error_message && (
                      <div style={{ marginTop: '12px' }}>
                        <AlertBanner variant="error" title="Dettaglio errore">
                          {exec.error_message}
                        </AlertBanner>
                      </div>
                    )}
                  </Panel>
                );
              })}
            </Stack>
          )}
        </Stack>
      )}

      {/* =========================================================================
          MODALE 1: GOOGLE CALENDAR CONNECT (USER-FRIENDLY & TRUTHFUL PKCE SETUP)
          ========================================================================= */}
      {(() => {
        const googleOAuthInfo = oauthProviders['google_calendar'];
        const googleConn = connections.find((c) => c.provider === 'google_calendar');
        const hasClientId = Boolean(googleOAuthInfo?.has_client_id || (googleConn && googleConn.auth_metadata?.client_id));
        const hasClientSecret = Boolean(googleOAuthInfo?.has_client_secret || (googleConn && googleConn.auth_metadata?.client_secret));
        const lastError = googleConn?.last_verification_error || '';
        const isMissingSecretError = lastError.toLowerCase().includes('client_secret');
        const isFullyConfigured = hasClientId && hasClientSecret && !isMissingSecretError;
        const canSubmit = hasClientId || Boolean(googleClientId.trim());

        return (
          <Modal
            isOpen={isGoogleModalOpen}
            onClose={() => setIsGoogleModalOpen(false)}
            size="md"
            title="Collega Google Calendar"
            description="Autorizza Aether ad accedere ai tuoi calendari per coordinare la tua agenda in locale."
            footer={
              <AetherFormActions align="between">
                <Button variant="ghost" onClick={() => setIsGoogleModalOpen(false)}>
                  Annulla
                </Button>
                <Button
                  variant="primary"
                  size="md"
                  disabled={!canSubmit}
                  loading={googleAuthPending}
                  onClick={handleStartGoogleOAuth}
                  leftIcon={<Globe size={16} />}
                >
                  {googleAuthPending
                    ? 'In attesa di autorizzazione…'
                    : isFullyConfigured
                    ? 'Autorizza con Google'
                    : 'Salva e Autorizza con Google'}
                </Button>
              </AetherFormActions>
            }
          >
            <Stack direction="column" gap="lg">
              {isMissingSecretError && (
                <AlertBanner variant="error" title="Client Secret richiesto da Google">
                  Google ha rifiutato l'autorizzazione precedente perché per questo Client ID (tipo 'Applicazione web') è obbligatorio il <strong>Client Secret</strong>.
                  Inserisci il Client Secret (es. <code>GOCSPX-...</code>) generato su Google Cloud Console e premi <strong>Salva e Autorizza</strong>.
                </AlertBanner>
              )}

              {!isFullyConfigured ? (
                <>
                  {!isMissingSecretError && (
                    <AlertBanner variant="info" title="Configurazione Credenziali Google Cloud">
                      Aether si connette direttamente alle API di Google Calendar dal tuo computer. Per autorizzare l'accesso, inserisci il tuo <strong>Client ID</strong> e il <strong>Client Secret</strong> (se la tua app su Google Cloud è di tipo 'Applicazione web').
                    </AlertBanner>
                  )}

                  <Panel variant="default" style={{ padding: '16px' }}>
                    <Text size="sm" weight="semibold" style={{ marginBottom: '8px' }}>
                      Come ottenere le credenziali su Google Cloud (gratuito e personale):
                    </Text>
                    <ol style={{ fontSize: '13px', color: 'hsl(var(--fg))', margin: 0, paddingLeft: '20px', lineHeight: '1.6' }}>
                      <li>
                        Apri la <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer" style={{ color: 'hsl(var(--primary))', textDecoration: 'underline' }}>Google Cloud Console &rarr; Credenziali</a> (verifica che <em>Google Calendar API</em> sia abilitata nella libreria API).
                      </li>
                      <li>
                        Clicca su <strong>Crea credenziali</strong> &rarr; <strong>ID client OAuth</strong>.
                      </li>
                      <li>
                        Seleziona come tipo di applicazione <strong>Applicazione web</strong> (oppure <strong>Applicazione desktop</strong>).
                      </li>
                      <li>
                        Se hai scelto <em>Applicazione web</em>, aggiungi come URI di reindirizzamento autorizzato: <code>http://127.0.0.1:8000/api/connections/google_calendar/oauth/callback</code>.
                      </li>
                      <li>
                        Copia l'<strong>ID client</strong> e il <strong>Client Secret</strong> generati e incollali qui sotto.
                      </li>
                    </ol>
                  </Panel>

                  <AetherForm onSubmit={handleStartGoogleOAuth}>
                    <AetherField label="Google Client ID" required helperText="Identificativo OAuth (termina con .apps.googleusercontent.com)">
                      <AetherInput
                        placeholder="es. 123456789-abcdef.apps.googleusercontent.com"
                        value={googleClientId}
                        onChange={(e) => setGoogleClientId(e.target.value)}
                        autoFocus={!googleClientId}
                      />
                    </AetherField>

                    <AetherField
                      label={isMissingSecretError ? "Google Client Secret (Richiesto da Google)" : "Google Client Secret"}
                      helperText="Obbligatorio per Applicazioni Web (es. GOCSPX-...). Opzionale solo per Applicazioni Desktop con PKCE."
                    >
                      <AetherPasswordInput
                        placeholder="es. GOCSPX-..."
                        value={googleClientSecret}
                        onChange={(e) => setGoogleClientSecret(e.target.value)}
                        autoFocus={Boolean(isMissingSecretError)}
                      />
                    </AetherField>
                  </AetherForm>
                </>
              ) : (
                <>
                  <AlertBanner variant="info" title="Autorizzazione Sicura e Trasparente">
                    Il flusso di autorizzazione aprirà il tuo browser di sistema ufficiale. Nessuna password personale viene mai condivisa con Aether e i tuoi token restano memorizzati in modo cifrato esclusivamente sul tuo dispositivo.
                  </AlertBanner>

                  <Panel variant="default" style={{ padding: '14px' }}>
                    <Stack direction="row" align="center" justify="between">
                      <div>
                        <Text size="sm" weight="medium">
                          Client ID e Client Secret
                        </Text>
                        <Text size="xs" variant="muted">
                          ID: {googleOAuthInfo?.client_id_preview || (googleClientId ? `${googleClientId.slice(0, 8)}...` : 'Configurato')} • Secret: {hasClientSecret ? 'Configurato' : 'Non configurato'}
                        </Text>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setGoogleAdvOpen(!googleAdvOpen)}
                      >
                        {googleAdvOpen ? 'Chiudi' : 'Modifica credenziali'}
                      </Button>
                    </Stack>

                    {googleAdvOpen && (
                      <div style={{ marginTop: '16px', paddingTop: '14px', borderTop: '1px solid hsl(var(--border))' }}>
                        <AetherForm onSubmit={handleStartGoogleOAuth}>
                          <AetherField label="Google Client ID" required helperText="Identificativo OAuth (termina con .apps.googleusercontent.com)">
                            <AetherInput
                              placeholder="es. 123456789.apps.googleusercontent.com"
                              value={googleClientId}
                              onChange={(e) => setGoogleClientId(e.target.value)}
                            />
                          </AetherField>

                          <AetherField label="Google Client Secret" helperText="Obbligatorio per Applicazioni Web (es. GOCSPX-...)">
                            <AetherPasswordInput
                              placeholder="es. GOCSPX-..."
                              value={googleClientSecret}
                              onChange={(e) => setGoogleClientSecret(e.target.value)}
                            />
                          </AetherField>
                        </AetherForm>
                      </div>
                    )}
                  </Panel>

                  {googleState && (
                    <Panel variant="default" style={{ padding: '12px' }}>
                      <AetherForm onSubmit={handleManualExchangeCode}>
                        <AetherField label="Codice autorizzazione da incollare (se il redirect automatico è bloccato)">
                          <AetherInput
                            placeholder="Incolla qui il codice di autorizzazione restituito dal browser"
                            value={googleManualCode}
                            onChange={(e) => setGoogleManualCode(e.target.value)}
                          />
                        </AetherField>
                        <Button
                          variant="secondary"
                          size="sm"
                          style={{ marginTop: '8px' }}
                          onClick={handleManualExchangeCode}
                          loading={googleAuthPending}
                        >
                          Scambia codice manuale
                        </Button>
                      </AetherForm>
                    </Panel>
                  )}
                </>
              )}
            </Stack>
          </Modal>
        );
      })()}

      {/* =========================================================================
          MODALE 2: DEVELOPER APP SETUP MODAL (GITHUB, SLACK, NOTION)
          ========================================================================= */}
      <Modal
        isOpen={Boolean(devSetupModalProvider)}
        onClose={() => setDevSetupModalProvider(null)}
        size="md"
        title={`Collega ${devSetupModalProvider?.name || 'Servizio'}`}
        description="Autorizza il servizio per consentire ad Aether di operare in sicurezza."
        footer={
          <AetherFormActions>
            <Button variant="ghost" onClick={() => setDevSetupModalProvider(null)}>
              Annulla
            </Button>
            <Button
              variant="primary"
              loading={savingDevConfig}
              onClick={handleSaveDevOAuthConfig}
            >
              Salva e autorizza nel browser
            </Button>
          </AetherFormActions>
        }
      >
        <AetherForm onSubmit={handleSaveDevOAuthConfig}>
          <AlertBanner variant="info" title="Configurazione Applicazione">
            Per garantire privacy e controllo totale, puoi registrare una OAuth App o inserire credenziali dedicate.
          </AlertBanner>

          {devSetupModalProvider && oauthProviders[devSetupModalProvider.id] && (
            <Panel variant="default" style={{ padding: '12px 14px' }}>
              <Text size="xs" variant="muted" style={{ marginBottom: '6px' }}>
                Redirect URI per la tua App:
              </Text>
              <Stack direction="row" gap="sm" align="center">
                <AetherInput
                  readOnly
                  value={oauthProviders[devSetupModalProvider.id].redirect_uri}
                />
                <IconButton
                  icon={copiedField === 'redirect' ? <Check size={16} /> : <Copy size={16} />}
                  ariaLabel="Copia Redirect URI"
                  onClick={() =>
                    copyToClipboard(
                      oauthProviders[devSetupModalProvider.id].redirect_uri,
                      'redirect'
                    )
                  }
                />
              </Stack>
            </Panel>
          )}

          <AetherField label="Client ID" required>
            <AetherInput
              placeholder="Inserisci il Client ID fornito dal servizio"
              value={devClientId}
              onChange={(e) => setDevClientId(e.target.value)}
            />
          </AetherField>

          <AetherField label="Client Secret" required>
            <AetherPasswordInput
              placeholder="Inserisci il Client Secret fornito dal servizio"
              value={devClientSecret}
              onChange={(e) => setDevClientSecret(e.target.value)}
            />
          </AetherField>
        </AetherForm>
      </Modal>

      {/* =========================================================================
          MODALE 3: TELEGRAM COMPANION GUIDED MODAL
          ========================================================================= */}
      <Modal
        isOpen={isTelegramModalOpen}
        onClose={() => setIsTelegramModalOpen(false)}
        size="md"
        title="Collega Telegram Companion"
        description="Ricevi notifiche push e approva attività di Aether direttamente dal tuo smartphone."
        footer={
          <AetherFormActions>
            <Button variant="ghost" onClick={() => setIsTelegramModalOpen(false)}>
              Annulla
            </Button>
            <Button
              variant="primary"
              loading={verifyingTelegram}
              onClick={handleConnectTelegramGuided}
              leftIcon={<Send size={15} />}
            >
              Verifica e collega bot
            </Button>
          </AetherFormActions>
        }
      >
        <AetherForm onSubmit={handleConnectTelegramGuided}>
          <Panel variant="default" style={{ padding: '16px' }}>
            <Heading level={4} style={{ marginBottom: '8px' }}>
              Come ottenere il token del bot in 3 passi:
            </Heading>
            <Stack direction="column" gap="xs">
              <Text size="sm">
                1. Apri Telegram e cerca l'account ufficiale <strong>@BotFather</strong>
              </Text>
              <Text size="sm">
                2. Invia il comando <code>/newbot</code> e segui le istruzioni per dargli un nome
              </Text>
              <Text size="sm">
                3. Copia la chiave <strong>API Token</strong> generata e incollala nel campo qui sotto
              </Text>
            </Stack>
          </Panel>

          <AetherField label="Bot Token di Telegram" required>
            <AetherPasswordInput
              placeholder="es. 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
              value={telegramBotToken}
              onChange={(e) => setTelegramBotToken(e.target.value)}
            />
          </AetherField>

          {testResult && (
            <AlertBanner
              variant={testResult.valid ? 'success' : 'error'}
              title={testResult.valid ? 'Verifica riuscita' : 'Verifica non riuscita'}
            >
              {testResult.message}
            </AlertBanner>
          )}

          <Panel variant="default" style={{ padding: '12px 14px' }}>
            <Stack direction="row" align="center" justify="between">
              <div>
                <Text size="sm" weight="medium">
                  Impostazioni di sicurezza avanzate
                </Text>
                <Text size="xs" variant="muted">
                  Limita i comandi solo al tuo specifico Chat ID Telegram
                </Text>
              </div>
              <Switch checked={telegramAdvOpen} onChange={setTelegramAdvOpen} />
            </Stack>

            {telegramAdvOpen && (
              <div style={{ marginTop: '14px', paddingTop: '12px', borderTop: '1px solid hsl(var(--border))' }}>
                <AetherField label="Chat ID predefinito (opzionale)">
                  <AetherInput
                    placeholder="es. 987654321"
                    value={telegramDefaultChatId}
                    onChange={(e) => setTelegramDefaultChatId(e.target.value)}
                  />
                </AetherField>
              </div>
            )}
          </Panel>
        </AetherForm>
      </Modal>

      {/* =========================================================================
          MODALE 4: CONFIGURAZIONE GENERICA CREDENZIALI (EMAIL, HTTP, OPENAPI)
          ========================================================================= */}
      <Modal
        isOpen={Boolean(configModalProvider)}
        onClose={() => setConfigModalProvider(null)}
        size="md"
        title={`Configura ${configModalProvider?.name || 'Servizio'}`}
        description="Inserisci le informazioni di connessione per abilitare il servizio."
        footer={
          <AetherFormActions align="between">
            <Button
              variant="outline"
              size="sm"
              loading={testingCreds}
              onClick={handleTestCreds}
            >
              Testa connessione
            </Button>
            <Stack direction="row" gap="sm">
              <Button variant="ghost" onClick={() => setConfigModalProvider(null)}>
                Annulla
              </Button>
              <Button
                variant="primary"
                loading={savingCreds}
                onClick={handleSaveAndConnect}
              >
                Salva e attiva
              </Button>
            </Stack>
          </AetherFormActions>
        }
      >
        <AetherForm onSubmit={handleSaveAndConnect}>
          <AetherField label="Nome account di riferimento">
            <AetherInput
              value={credAccountName}
              onChange={(e) => setCredAccountName(e.target.value)}
            />
          </AetherField>

          {configModalProvider?.id === 'email' && (
            <Stack direction="column" gap="md">
              <AetherField label="Server SMTP" required>
                <AetherInput
                  placeholder="smtp.gmail.com"
                  value={emailHost}
                  onChange={(e) => setEmailHost(e.target.value)}
                />
              </AetherField>

              <Grid cols={2} gap="md">
                <AetherField label="Porta" required>
                  <AetherInput
                    placeholder="587"
                    value={emailPort}
                    onChange={(e) => setEmailPort(e.target.value)}
                  />
                </AetherField>
                <AetherField label="Indirizzo mittente">
                  <AetherInput
                    placeholder="nome@dominio.it"
                    value={emailSenderAddr}
                    onChange={(e) => setEmailSenderAddr(e.target.value)}
                  />
                </AetherField>
              </Grid>

              <AetherField label="Nome utente / Email login" required>
                <AetherInput
                  value={emailUser}
                  onChange={(e) => setEmailUser(e.target.value)}
                />
              </AetherField>

              <AetherField label="Password o App Password" required>
                <AetherPasswordInput
                  value={emailPass}
                  onChange={(e) => setEmailPass(e.target.value)}
                />
              </AetherField>
            </Stack>
          )}

          {configModalProvider?.id === 'http' && (
            <Stack direction="column" gap="md">
              <AetherField label="URL di base dell'endpoint" required>
                <AetherInput
                  placeholder="https://api.esempio.it/v1"
                  value={httpBaseUrl}
                  onChange={(e) => setHttpBaseUrl(e.target.value)}
                />
              </AetherField>

              <AetherField label="Tipo di autenticazione">
                <AetherSelect
                  value={httpAuthType}
                  onChange={(e) => setHttpAuthType(e.target.value)}
                  options={[
                    { value: 'none', label: 'Nessuna autenticazione' },
                    { value: 'bearer', label: 'Bearer Token' },
                    { value: 'api_key', label: 'Header API Key (X-Api-Key)' },
                  ]}
                />
              </AetherField>

              {httpAuthType !== 'none' && (
                <AetherField label="Token o Chiave segreta" required>
                  <AetherPasswordInput
                    value={httpToken}
                    onChange={(e) => setHttpToken(e.target.value)}
                  />
                </AetherField>
              )}
            </Stack>
          )}

          {configModalProvider?.id === 'openapi' && (
            <Stack direction="column" gap="md">
              <AetherField label="URL specifica OpenAPI (JSON/YAML)">
                <AetherInput
                  placeholder="https://api.servizio.it/openapi.json"
                  value={openapiSpecUrl}
                  onChange={(e) => setOpenapiSpecUrl(e.target.value)}
                />
              </AetherField>

              <AetherField label="Oppure percorso file locale">
                <AetherInput
                  placeholder="/Users/nome/progetti/spec.yaml"
                  value={openapiSpecPath}
                  onChange={(e) => setOpenapiSpecPath(e.target.value)}
                />
              </AetherField>
            </Stack>
          )}

          {testResult && (
            <AlertBanner
              variant={testResult.valid ? 'success' : 'error'}
              title={testResult.valid ? 'Test superato' : 'Test fallito'}
            >
              {testResult.message}
            </AlertBanner>
          )}
        </AetherForm>
      </Modal>

      {/* =========================================================================
          MODALE 5: NUOVO APPUNTAMENTO CALENDARIO
          ========================================================================= */}
      <Modal
        isOpen={isEventModalOpen}
        onClose={() => setIsEventModalOpen(false)}
        size="md"
        title="Crea nuovo appuntamento"
        description={
          selectedScheduleSource === 'google'
            ? 'L\'evento verrà sincronizzato direttamente con il tuo account Google.'
            : 'L\'evento verrà memorizzato nel database locale del tuo spazio di lavoro.'
        }
        footer={
          <AetherFormActions>
            <Button variant="ghost" onClick={() => setIsEventModalOpen(false)}>
              Annulla
            </Button>
            <Button
              variant="primary"
              loading={creatingEvent}
              onClick={handleCreateEvent}
            >
              Crea evento
            </Button>
          </AetherFormActions>
        }
      >
        <AetherForm onSubmit={handleCreateEvent}>
          <AetherField label="Titolo dell'appuntamento" required>
            <AetherInput
              placeholder="es. Allineamento settimanale di progetto"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
            />
          </AetherField>

          <AetherField label="Data e ora di inizio" required>
            <AetherInput
              type="datetime-local"
              value={newStartTime}
              onChange={(e) => setNewStartTime(e.target.value)}
            />
          </AetherField>

          <AetherField label="Luogo o Link riunione (opzionale)">
            <AetherInput
              placeholder="es. Google Meet / Ufficio Milano"
              value={newLocation}
              onChange={(e) => setNewLocation(e.target.value)}
            />
          </AetherField>
        </AetherForm>
      </Modal>

      {/* =========================================================================
          MODALE 6: SELETTORE CALENDARIO GOOGLE ATTIVO
          ========================================================================= */}
      <Modal
        isOpen={isCalendarPickerOpen}
        onClose={() => setIsCalendarPickerOpen(false)}
        size="md"
        title="Seleziona Calendario Google"
        description="Scegli quale dei tuoi calendari Google utilizzare per la sincronizzazione delle attività."
      >
        <Stack direction="column" gap="sm">
          {googleCalendars.map((cal) => (
            <Panel
              key={cal.id}
              variant="default"
              className="ds-panel--interactive"
              onClick={() => handleSelectCalendar(cal.id, cal.summary)}
            >
              <Stack direction="row" justify="between" align="center">
                <div>
                  <Text weight="semibold">{cal.summary}</Text>
                  {cal.description && (
                    <Text size="xs" variant="muted">
                      {cal.description}
                    </Text>
                  )}
                </div>
                {cal.primary && (
                  <StatusBadge status="connected" label="Principale" />
                )}
              </Stack>
            </Panel>
          ))}
        </Stack>
      </Modal>

      {/* =========================================================================
          DRAWER: GESTISCI SERVIZIO COLLEGATO
          ========================================================================= */}
      <Drawer
        isOpen={Boolean(manageProvider)}
        onClose={() => setManageProvider(null)}
        title={manageProvider?.name}
        description="Dettagli e gestione dell'integrazione attiva."
        footer={
          <AetherFormActions align="between">
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                if (manageProvider) {
                  setDisconnectTarget({ id: manageProvider.id, name: manageProvider.name });
                }
              }}
              leftIcon={<Trash2 size={14} />}
            >
              Scollega servizio
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setManageProvider(null)}>
              Chiudi
            </Button>
          </AetherFormActions>
        }
      >
        {manageProvider && (() => {
          const conn = connections.find((c) => c.provider === manageProvider.id);

          return (
            <Stack direction="column" gap="lg">
              {/* Header card with status */}
              <Panel variant="default" style={{ padding: '16px' }}>
                <Stack direction="row" justify="between" align="center">
                  <Stack gap="none">
                    <Text size="xs" variant="muted">Stato operativo</Text>
                    <Heading level={4}>{conn?.account_name || manageProvider.name}</Heading>
                  </Stack>
                  <StatusBadge status={conn?.status || 'NOT_CONFIGURED'} />
                </Stack>
              </Panel>

              {/* Capabilities checklist */}
              <div>
                <Heading level={5} style={{ marginBottom: '8px' }}>
                  Capacità concesse ad Aether:
                </Heading>
                <Stack direction="column" gap="xs">
                  {manageProvider.capabilitiesList.map((cap, i) => (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        fontSize: '13px',
                        color: 'hsl(var(--fg))',
                      }}
                    >
                      <CheckCircle2 size={15} color="hsl(var(--success))" />
                      <span>{cap}</span>
                    </div>
                  ))}
                </Stack>
              </div>

              {/* Live probe action */}
              <Panel variant="default" style={{ padding: '14px' }}>
                <Stack direction="row" justify="between" align="center">
                  <div>
                    <Text size="sm" weight="medium">Verifica integrità</Text>
                    <Text size="xs" variant="muted">
                      Invia un ping reale per validare la raggiungibilità del servizio
                    </Text>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    loading={verifyingProvider === manageProvider.id}
                    onClick={() => handleVerifyConnection(manageProvider.id)}
                  >
                    Verifica ora
                  </Button>
                </Stack>
              </Panel>

              {/* Advanced info toggle */}
              <Panel variant="default" style={{ padding: '12px 14px' }}>
                <Stack direction="row" justify="between" align="center">
                  <Text size="xs" variant="muted">Dettagli tecnici avanzati</Text>
                  <Switch checked={showTechDetails} onChange={setShowTechDetails} />
                </Stack>

                {showTechDetails && conn && (
                  <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: '1px solid hsl(var(--border))' }}>
                    <Text size="xs" mono style={{ wordBreak: 'break-all' }}>
                      ID Interno: {conn.id}
                      <br />
                      Ultima sincronizzazione: {conn.last_synced_at || 'Mai'}
                      <br />
                      Ultima verifica: {conn.last_verified_at || 'Mai'}
                    </Text>
                  </div>
                )}
              </Panel>
            </Stack>
          );
        })()}
      </Drawer>

      {/* =========================================================================
          MODALE: CONFERMA DISCONNESSIONE
          ========================================================================= */}
      <Modal
        isOpen={Boolean(disconnectTarget)}
        onClose={() => setDisconnectTarget(null)}
        size="sm"
        title="Scollegare il servizio?"
        description={`Sei sicuro di voler scollegare ${disconnectTarget?.name}? Aether non potrà più coordinare o interagire con questo servizio finché non verrà ricollegato.`}
        footer={
          <AetherFormActions>
            <Button variant="ghost" onClick={() => setDisconnectTarget(null)}>
              Annulla
            </Button>
            <Button
              variant="destructive"
              loading={disconnecting}
              onClick={confirmDisconnect}
            >
              Scollega definitivamente
            </Button>
          </AetherFormActions>
        }
      >
        <AlertBanner variant="warning" title="Attenzione">
          Eventuali credenziali e token salvati verranno rimossi in sicurezza dal SecretStore locale.
        </AlertBanner>
      </Modal>
    </PageContainer>
  );
}
