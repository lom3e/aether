import { useState, useEffect, useContext, useMemo } from 'react';
import {
  Calendar, Mail, GitBranch, MessageSquare, FileText, CheckCircle2,
  AlertCircle, ShieldCheck, Settings, Plus, RefreshCw, Clock, Zap, Globe, Send,
  Check, X, Loader2, Search, ChevronDown, ChevronUp, AlertTriangle, Shield,
  Lock, Trash2
} from 'lucide-react';
import { apiUrl } from './api';
import { ToastContext } from './toast';
import { submitApprovalDecision } from './canonicalNotification';
import { useTranslation } from './i18n';

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
  icon: any;
  category: 'productivity' | 'dev' | 'communication';
  description: string;
  capabilitiesText: string;
  capabilitiesList: string[];
  color: string;
  builtIn: boolean;
  isOAuth: boolean;
}

export function Connections({ navigate: _navigate, initialExecutionId, initialTab }: ConnectionsProps) {
  const { t } = useTranslation();
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
  const [syncingProvider, setSyncingProvider] = useState<string | null>(null);
  const [verifyingProvider, setVerifyingProvider] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);

  // Manage Connection Drawer / Modal
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
  const [isCalendarPickerOpen, setIsCalendarPickerOpen] = useState(false);
  const [googleCalendars, setGoogleCalendars] = useState<{ id: string; summary: string; primary: boolean; description?: string }[]>([]);

  // New Event Form State
  const [isEventModalOpen, setIsEventModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newStartTime, setNewStartTime] = useState('');
  const [newLocation, setNewLocation] = useState('');
  const [creatingEvent, setCreatingEvent] = useState(false);

  // Config Modal State
  const [configModalProvider, setConfigModalProvider] = useState<ProviderDefinition | null>(null);
  const [isConfigured, setIsConfigured] = useState(false);
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

  const availableProviders: ProviderDefinition[] = [
    {
      id: 'calendar',
      name: 'Aether Calendar (Local)',
      icon: Calendar,
      category: 'productivity',
      description: 'Built-in local workspace schedule and event storage with zero external dependencies.',
      capabilitiesText: 'Can view schedule, list local events, and record meetings directly in workspace storage',
      capabilitiesList: [
        'Inspect workspace schedules & appointments',
        'Record meetings directly in local SQLite storage',
        'Zero cloud or external network dependencies',
        'Offline calendar event querying & indexing',
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
      description: 'Real Google Calendar integration via OAuth 2.0 PKCE. Reads calendars, syncs meetings, and schedules events.',
      capabilitiesText: 'Can read Google calendars and create or update events via official Google Calendar APIs',
      capabilitiesList: [
        'Read personal and organizational calendars',
        'Schedule and coordinate new meetings',
        'Update and cancel events with confirmation',
        'Bidirectional sync into workspace memory',
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
      description: 'Read and sync project documentation, deliverable specs, and workspace database tables.',
      capabilitiesText: 'Can read and synchronize workspace pages and databases',
      capabilitiesList: [
        'Search workspace pages & documents',
        'Read databases, schema properties, and entries',
        'Export verified deliverables directly to Notion pages',
        'Sync specifications into workspace knowledge',
      ],
      color: '#000000',
      builtIn: false,
      isOAuth: false,
    },
    {
      id: 'github',
      name: 'GitHub',
      icon: GitBranch,
      category: 'dev',
      description: 'Access repositories, codebases, commits, pull requests, and automated review workflows.',
      capabilitiesText: 'Can read repositories, create issues, and open pull requests',
      capabilitiesList: [
        'Inspect repositories, files, and tree structure',
        'List and inspect git branches',
        'Create, update, and comment on issues',
        'Open pull requests with automated summaries',
      ],
      color: '#2dba4e',
      builtIn: false,
      isOAuth: false,
    },
    {
      id: 'openapi',
      name: 'OpenAPI 3.x',
      icon: Zap,
      category: 'dev',
      description: 'Parse OpenAPI specifications to dynamically discover, validate, and execute REST operations.',
      capabilitiesText: 'Can discover endpoints, validate schemas, and execute API actions dynamically',
      capabilitiesList: [
        'Dynamically discover API tools and operations',
        'Validate input schemas against spec definitions',
        'Execute authenticated REST operations',
        'Support remote URLs and local schema files',
      ],
      color: '#8B5CF6',
      builtIn: false,
      isOAuth: false,
    },
    {
      id: 'http',
      name: 'Generic HTTP / API',
      icon: Globe,
      category: 'dev',
      description: 'Interact with external REST endpoints and Web APIs with security policies and header authentication.',
      capabilitiesText: 'Can perform authenticated HTTP operations (GET, POST, PUT, DELETE)',
      capabilitiesList: [
        'Authenticated HTTP requests (GET, POST, PUT, DELETE)',
        'Bearer Token, API Key, and Basic Auth authentication',
        'Custom header configuration',
        'Safe execution with confirmation gating',
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
      description: 'Receive notifications, post operational status reports, and notify channels with bot or webhook.',
      capabilitiesText: 'Can post messages and status updates to Slack channels with confirmation',
      capabilitiesList: [
        'Post status briefs and updates to team channels',
        'Send direct operational alerts',
        'Support Bot User OAuth tokens & Incoming Webhooks',
        'Configurable default destination channel',
      ],
      color: '#4A154B',
      builtIn: false,
      isOAuth: false,
    },
    {
      id: 'email',
      name: 'Email / SMTP',
      icon: Mail,
      category: 'communication',
      description: 'Draft briefs, prepare automated summaries, and dispatch outbound messages via secure SMTP.',
      capabilitiesText: 'Can draft and dispatch emails via SMTP with explicit user approval',
      capabilitiesList: [
        'Draft and send structured outbound emails',
        'STARTTLS and direct SSL/TLS encryption support',
        'Custom sender addresses and display aliases',
        'Supervised dispatch with explicit confirmation',
      ],
      color: '#EA4335',
      builtIn: false,
      isOAuth: false,
    },
    {
      id: 'telegram',
      name: 'Telegram Bot',
      icon: Send,
      category: 'communication',
      description: 'Mobile companion, real-time alerts, remote task delegation, and inline interactive approvals.',
      capabilitiesText: 'Can receive mobile commands, dispatch notifications, and handle interactive approvals',
      capabilitiesList: [
        'Direct push alerts to mobile devices',
        'Interactive inline approval buttons',
        'Authorized chat ID whitelist enforcement',
        'Remote companion command execution',
      ],
      color: '#229ED9',
      builtIn: false,
      isOAuth: false,
    },
  ];

  const fetchAll = () => {
    setLoading(true);
    Promise.all([
      fetch(apiUrl('/api/connections')).then(r => r.json()),
      fetch(apiUrl('/api/connections/calendar/events')).then(r => r.json()),
      fetch(apiUrl('/api/connections/google_calendar/events')).then(r => r.ok ? r.json() : []).catch(() => []),
      fetch(apiUrl('/api/actions/executions')).then(r => r.json()),
    ])
      .then(([conns, evts, gEvts, execs]) => {
        if (Array.isArray(conns)) setConnections(conns);
        if (Array.isArray(evts)) setCalendarEvents(evts);
        if (Array.isArray(gEvts)) setGoogleCalendarEvents(gEvts);
        if (Array.isArray(execs)) setExecutions(execs);
      })
      .catch(err => {
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

  useEffect(() => {
    if (activeTab === 'actions' && initialExecutionId && executions.length > 0) {
      setTimeout(() => {
        const el = document.getElementById(`exec-card-${initialExecutionId}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 100);
    }
  }, [activeTab, initialExecutionId, executions]);

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
        showToast(res.message || t('connActionApproved'), res.status === 'already_completed' ? 'info' : 'success');
        fetchAll();
      } else {
        showToast(res.message || 'Failed to approve action execution.', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Error approving action.', 'error');
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
        reason: 'Declined by user',
      });
      if (res.success) {
        showToast(res.message || t('connActionDeclined'), 'info');
        fetchAll();
      } else {
        showToast(res.message || 'Failed to decline action execution.', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Error declining action.', 'error');
    } finally {
      setActionLoadingId(null);
    }
  };

  const openConfigModal = (provider: ProviderDefinition, existingConn?: ConnectionItem) => {
    setConfigModalProvider(provider);
    setCredAccountName(existingConn?.account_name || `Personal ${provider.name}`);
    setIsConfigured(Boolean(existingConn && existingConn.status !== 'not_configured' && existingConn.status !== 'disconnected'));
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
      if (provider.id === 'slack') {
        if (meta.default_channel) setSlackDefaultChannel(meta.default_channel);
      }
      if (provider.id === 'http') {
        if (meta.base_url) setHttpBaseUrl(meta.base_url);
        if (meta.auth_type) setHttpAuthType(meta.auth_type);
      }
      if (provider.id === 'notion') {
        if (meta.default_database_id) setNotionDbId(meta.default_database_id);
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
          setTelegramAllowedChats(Array.isArray(meta.allowed_chat_ids) ? meta.allowed_chat_ids.join(', ') : String(meta.allowed_chat_ids));
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
        showToast(`Verified ${providerId} successfully.`, 'success');
      } else {
        showToast(data.message || `Verification failed for ${providerId}.`, 'error');
      }
      await fetchAll();
    } catch (err: any) {
      showToast(err.message || 'Verification request failed.', 'error');
    } finally {
      setVerifyingProvider(null);
    }
  };

  const diagnoseError = (rawErr?: string) => {
    if (!rawErr) return null;
    const errLow = rawErr.toLowerCase();
    if (errLow.includes('401') || errLow.includes('unauthorized') || errLow.includes('invalid token') || errLow.includes('bad credentials') || errLow.includes('invalid_grant') || errLow.includes('password') || errLow.includes('authentication')) {
      return {
        title: t('connErrAuth'),
        desc: t('connErrAuthDesc'),
        raw: rawErr,
      };
    }
    if (errLow.includes('403') || errLow.includes('forbidden') || errLow.includes('scope') || errLow.includes('permission') || errLow.includes('denied')) {
      return {
        title: t('connErrPerm'),
        desc: t('connErrPermDesc'),
        raw: rawErr,
      };
    }
    if (errLow.includes('refused') || errLow.includes('timeout') || errLow.includes('timed out') || errLow.includes('unreachable') || errLow.includes('dns') || errLow.includes('network')) {
      return {
        title: t('connErrNet'),
        desc: t('connErrNetDesc'),
        raw: rawErr,
      };
    }
    return {
      title: t('connErrConfig'),
      desc: t('connErrConfigDesc'),
      raw: rawErr,
    };
  };

  const getActionSummary = (exec: ActionExecutionItem) => {
    const input = exec.input_data || {};
    switch (exec.action_id) {
      case 'email.send':
        return `Send email to ${input.to || 'recipient'} — "${input.subject || '(no subject)'}"`;
      case 'github.create_issue':
        return `Create issue in ${input.owner ? `${input.owner}/${input.repository}` : (input.repository || 'repo')}: "${input.title || ''}"`;
      case 'github.inspect_repo':
        return `Inspect repository ${input.owner ? `${input.owner}/${input.repository}` : (input.repository || 'repo')}`;
      case 'github.list_branches':
        return `List branches in ${input.owner ? `${input.owner}/${input.repository}` : (input.repository || 'repo')}`;
      case 'github.list_issues':
        return `List issues in ${input.owner ? `${input.owner}/${input.repository}` : (input.repository || 'repo')}`;
      case 'github.create_pull_request':
        return `Open PR in ${input.owner ? `${input.owner}/${input.repository}` : (input.repository || 'repo')}: "${input.title || ''}"`;
      case 'slack.send_message':
        return `Post message to ${input.channel || 'channel'}: "${(input.text || '').slice(0, 60)}${(input.text || '').length > 60 ? '...' : ''}"`;
      case 'telegram.send_message':
        return `Send Telegram message to ${input.chat_id || 'authorized chat'}: "${(input.text || '').slice(0, 60)}${(input.text || '').length > 60 ? '...' : ''}"`;
      case 'calendar.create_event':
        return `Create event "${input.title || 'Event'}"${input.start_time ? ` at ${input.start_time}` : ''}`;
      case 'http.request':
        return `${(input.method || 'GET').toUpperCase()} ${input.url || input.endpoint || ''}`;
      case 'notion.search':
        return `Search Notion: "${input.query || ''}"`;
      case 'notion.create_page':
        return `Create Notion page: "${input.title || ''}"`;
      case 'notion.get_page':
        return `Get Notion page: ${input.page_id || ''}`;
      case 'notion.get_me':
        return `Check Notion bot info`;
      case 'openapi.execute_tool':
        return `Execute API tool: ${input.tool_name || input.operation_id || ''}`;
      case 'openapi.list_tools':
        return `List OpenAPI operations`;
      default:
        if (input.title) return String(input.title);
        if (input.name) return String(input.name);
        return exec.action_id;
    }
  };

  const getActionDetail = (exec: ActionExecutionItem) => {
    const input = exec.input_data || {};
    if (exec.action_id === 'email.send' && input.body) {
      return input.body.length > 80 ? input.body.slice(0, 80) + '...' : input.body;
    }
    if (exec.action_id === 'github.create_issue' && input.body) {
      return input.body.length > 80 ? input.body.slice(0, 80) + '...' : input.body;
    }
    if (exec.action_id === 'slack.send_message' && input.text) {
      return input.text.length > 80 ? input.text.slice(0, 80) + '...' : input.text;
    }
    if (exec.action_id === 'telegram.send_message' && input.text) {
      return input.text.length > 80 ? input.text.slice(0, 80) + '...' : input.text;
    }
    if (exec.action_id === 'notion.create_page' && input.content) {
      return input.content.length > 80 ? input.content.slice(0, 80) + '...' : input.content;
    }
    if (exec.action_id === 'openapi.execute_tool' && input.parameters) {
      const pStr = typeof input.parameters === 'string' ? input.parameters : JSON.stringify(input.parameters);
      return pStr.length > 80 ? pStr.slice(0, 80) + '...' : pStr;
    }
    return null;
  };

  const buildAuthMetadata = (providerId: string) => {
    const meta: Record<string, any> = {};
    if (providerId === 'github') {
      if (githubToken.trim()) meta.token = githubToken.trim();
    }
    if (providerId === 'slack') {
      if (slackToken.trim()) meta.bot_token = slackToken.trim();
      if (slackWebhook.trim()) meta.webhook_url = slackWebhook.trim();
      if (slackDefaultChannel.trim()) meta.default_channel = slackDefaultChannel.trim();
    }
    if (providerId === 'email') {
      if (emailUser.trim()) meta.username = emailUser.trim();
      if (emailPass.trim()) meta.password = emailPass.trim();
      if (emailHost.trim()) meta.smtp_host = emailHost.trim();
      if (emailPort.trim()) meta.smtp_port = parseInt(emailPort.trim(), 10) || 587;
      meta.use_tls = emailUseTls;
      meta.use_ssl = emailUseSsl;
      if (emailSenderAddr.trim()) meta.sender_address = emailSenderAddr.trim();
      if (emailTestRecipient.trim()) meta.test_recipient = emailTestRecipient.trim();
    }
    if (providerId === 'telegram') {
      if (telegramBotToken.trim()) meta.bot_token = telegramBotToken.trim();
      if (telegramDefaultChatId.trim()) meta.default_chat_id = telegramDefaultChatId.trim();
      if (telegramAllowedChats.trim()) meta.allowed_chat_ids = telegramAllowedChats.trim();
    }
    if (providerId === 'http') {
      if (httpBaseUrl.trim()) meta.base_url = httpBaseUrl.trim();
      if (httpAuthType.trim()) meta.auth_type = httpAuthType.trim();
      if (httpToken.trim()) meta.token = httpToken.trim();
    }
    if (providerId === 'notion') {
      if (notionToken.trim()) meta.token = notionToken.trim();
      if (notionDbId.trim()) meta.default_database_id = notionDbId.trim();
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
        message: data.message || (data.valid ? 'Credentials verified successfully.' : 'Verification failed.'),
      });
    } catch (err) {
      setTestResult({
        valid: false,
        message: 'Could not connect to backend server for verification.',
      });
    } finally {
      setTestingCreds(false);
    }
  };

  const handleSaveAndConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!configModalProvider) return;

    const authMeta = buildAuthMetadata(configModalProvider.id);
    setSavingCreds(true);
    try {
      const res = await fetch(apiUrl('/api/connections'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: configModalProvider.id,
          account_name: credAccountName.trim() || `Personal ${configModalProvider.name}`,
          auth_metadata: authMeta,
          live_check: false,
        }),
      });
      if (res.ok) {
        showToast(`Configuration saved for ${configModalProvider.name}.`, 'success');
        setConfigModalProvider(null);
        fetchAll();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Failed to save connection.', 'error');
      }
    } catch (err) {
      showToast('Error connecting service.', 'error');
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
          account_name: 'Aether Calendar (Local)',
          auth_metadata: { type: 'sqlite_built_in' },
        }),
      });
      if (res.ok) {
        showToast('Aether Calendar ready.', 'success');
        fetchAll();
      }
    } catch (e) {
      showToast('Failed to initialize Calendar.', 'error');
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
        showToast(`Disconnected ${disconnectTarget.name}.`, 'info');
        setDisconnectTarget(null);
        setManageProvider(null);
        fetchAll();
      } else {
        showToast('Failed to disconnect service.', 'error');
      }
    } catch (e) {
      showToast('Failed to disconnect service.', 'error');
    } finally {
      setDisconnecting(false);
    }
  };

  const handleSync = async (providerId: string) => {
    try {
      setSyncingProvider(providerId);
      const res = await fetch(apiUrl(`/api/connections/${providerId}/sync`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.summary || 'Sync failed');
      }
      showToast(`Synced ${data.items_synced || 0} items into workspace memory and knowledge!`, 'success');
      await fetchAll();
    } catch (err: any) {
      showToast(err.message || 'Failed to sync connection', 'error');
    } finally {
      setSyncingProvider(null);
    }
  };

  const handleSyncAll = async () => {
    try {
      setSyncingAll(true);
      const res = await fetch(apiUrl('/api/connections/sync'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Sync all failed');
      }
      showToast(`Synced ${data.total_items_synced || 0} external items into workspace intelligence!`, 'success');
      await fetchAll();
    } catch (err: any) {
      showToast(err.message || 'Failed to sync connections', 'error');
    } finally {
      setSyncingAll(false);
    }
  };

  const handleStartGoogleOAuth = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setGoogleAuthPending(true);
    try {
      const res = await fetch(apiUrl('/api/connections/google_calendar/oauth/start'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: googleClientId.trim() || undefined,
          client_secret: googleClientSecret.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Could not start Google authorization.');
      }
      setGoogleState(data.state || '');

      const width = 600;
      const height = 720;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;
      const popup = window.open(
        data.auth_url,
        'aether_google_oauth',
        `width=${width},height=${height},left=${left},top=${top},status=0,toolbar=0,menubar=0`
      );

      const messageHandler = (event: MessageEvent) => {
        if (event.data?.type === 'aether_oauth_success' && event.data?.provider === 'google_calendar') {
          window.removeEventListener('message', messageHandler);
          showToast(`Google Calendar connected & verified (${event.data.email || 'account'})!`, 'success');
          setIsGoogleModalOpen(false);
          setGoogleAuthPending(false);
          fetchAll();
        } else if (event.data?.type === 'aether_oauth_error' && event.data?.provider === 'google_calendar') {
          window.removeEventListener('message', messageHandler);
          showToast(`Google Calendar authorization failed: ${event.data.error || 'error'}`, 'error');
          setGoogleAuthPending(false);
          fetchAll();
        }
      };
      window.addEventListener('message', messageHandler);

      const pollTimer = setInterval(() => {
        if (!popup || popup.closed) {
          clearInterval(pollTimer);
          window.removeEventListener('message', messageHandler);
          setGoogleAuthPending(false);
          fetchAll();
        }
      }, 1000);
    } catch (err: any) {
      showToast(err.message || 'Failed to start Google OAuth', 'error');
      setGoogleAuthPending(false);
    }
  };

  const handleManualExchangeCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!googleManualCode.trim() || !googleState.trim()) {
      showToast('Both authorization code and state are required.', 'error');
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
        throw new Error(data.detail || 'Code exchange failed.');
      }
      if (data.valid) {
        showToast('Google Calendar authorized and verified successfully!', 'success');
        setIsGoogleModalOpen(false);
        setGoogleManualCode('');
        fetchAll();
      } else {
        showToast(`Verification failed: ${data.message}`, 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to exchange Google OAuth code', 'error');
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
        showToast('No Google calendars found or error loading calendars.', 'error');
      }
    } catch (err) {
      showToast('Failed to load Google calendars.', 'error');
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
        showToast(`Active Google Calendar set to: ${summary}`, 'success');
        setIsCalendarPickerOpen(false);
        fetchAll();
      }
    } catch (err) {
      showToast('Failed to select calendar.', 'error');
    }
  };

  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setCreatingEvent(true);
    try {
      const endpoint = selectedScheduleSource === 'google'
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
        showToast(selectedScheduleSource === 'google' ? 'Google Calendar event created.' : 'Aether Calendar event created.', 'success');
        setIsEventModalOpen(false);
        setNewTitle('');
        setNewStartTime('');
        setNewLocation('');
        fetchAll();
      }
    } catch (err) {
      showToast('Error creating calendar event.', 'error');
    } finally {
      setCreatingEvent(false);
    }
  };

  // Grouping and Filtering
  const filteredProviders = useMemo(() => {
    return availableProviders.filter(p => {
      if (categoryFilter !== 'all' && p.category !== categoryFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const conn = connections.find(c => c.provider === p.id);
        const nameMatch = p.name.toLowerCase().includes(query);
        const descMatch = p.description.toLowerCase().includes(query);
        const accountMatch = conn?.account_name?.toLowerCase().includes(query);
        const capMatch = p.capabilitiesList.some(cap => cap.toLowerCase().includes(query));
        if (!nameMatch && !descMatch && !accountMatch && !capMatch) return false;
      }
      return true;
    });
  }, [availableProviders, categoryFilter, searchQuery, connections]);

  const verifiedProviders = useMemo(() => {
    return filteredProviders.filter(p => {
      const conn = connections.find(c => c.provider === p.id);
      return conn && (conn.status === 'verified' || conn.status === 'connected');
    });
  }, [filteredProviders, connections]);

  const attentionProviders = useMemo(() => {
    return filteredProviders.filter(p => {
      const conn = connections.find(c => c.provider === p.id);
      if (!conn) return false;
      return (
        conn.status === 'configured' ||
        conn.status === 'verification_failed' ||
        conn.status === 'error' ||
        conn.status === 'verification_required' ||
        conn.status === 'needs_auth'
      );
    });
  }, [filteredProviders, connections]);

  const availableToConnectProviders = useMemo(() => {
    return filteredProviders.filter(p => {
      const conn = connections.find(c => c.provider === p.id);
      return !conn || conn.status === 'not_configured' || conn.status === 'disconnected';
    });
  }, [filteredProviders, connections]);

  // Overall metric counts across all providers
  const totalVerifiedCount = connections.filter(c => c.status === 'verified' || c.status === 'connected').length;
  const totalAttentionCount = connections.filter(c =>
    c.status === 'configured' ||
    c.status === 'verification_failed' ||
    c.status === 'error' ||
    c.status === 'verification_required' ||
    c.status === 'needs_auth'
  ).length;
  const totalAvailableCount = availableProviders.length - totalVerifiedCount - totalAttentionCount;

  // Filtered executions
  const filteredExecutions = useMemo(() => {
    if (actionStatusFilter === 'all') return executions;
    if (actionStatusFilter === 'pending') {
      return executions.filter(e => e.status === 'pending_approval' || e.status === 'waiting_approval');
    }
    if (actionStatusFilter === 'succeeded') {
      return executions.filter(e => e.status === 'success' || e.status === 'succeeded');
    }
    if (actionStatusFilter === 'failed') {
      return executions.filter(e => e.status === 'failed' || e.status === 'error');
    }
    return executions;
  }, [executions, actionStatusFilter]);

  // Manage Connection Details
  const activeManageConn = manageProvider ? connections.find(c => c.provider === manageProvider.id) : null;
  const manageRecentExecutions = manageProvider
    ? executions.filter(e => e.action_id.startsWith(manageProvider.id) || (manageProvider.id === 'google_calendar' && e.action_id.startsWith('calendar.'))).slice(0, 5)
    : [];

  return (
    <div style={{ padding: '28px', maxWidth: '1120px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, margin: '0 0 6px', color: 'hsl(var(--fg))' }}>
            {t('connHeaderTitle')}
          </h1>
          <p style={{ margin: 0, fontSize: '14px', color: 'hsl(var(--muted-fg))', maxWidth: '640px', lineHeight: 1.5 }}>
            {t('connHeaderSubtitle')}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <button
            className="btn btn-secondary"
            onClick={fetchAll}
            disabled={loading}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> {t('connRefresh')}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSyncAll}
            disabled={syncingAll}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
            title="Sync all connected external tools into workspace memory and knowledge"
          >
            <RefreshCw size={14} className={syncingAll ? 'animate-spin' : ''} />
            {syncingAll ? t('connSyncing') : t('connSyncAll')}
          </button>
        </div>
      </div>

      {/* Summary KPI Banner */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
        gap: '14px',
        marginBottom: '24px'
      }}>
        <div className="card" style={{ padding: '16px 20px', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '42px', height: '42px', borderRadius: '10px', backgroundColor: 'hsl(var(--primary)/0.1)', color: 'hsl(var(--primary))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Zap size={22} />
          </div>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'hsl(var(--fg))' }}>{availableProviders.length}</div>
            <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>{t('connTotalServices')}</div>
          </div>
        </div>

        <div className="card" style={{ padding: '16px 20px', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '14px', borderLeft: '4px solid #10b981' }}>
          <div style={{ width: '42px', height: '42px', borderRadius: '10px', backgroundColor: '#10b98115', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <CheckCircle2 size={22} />
          </div>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'hsl(var(--fg))' }}>{totalVerifiedCount}</div>
            <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>{t('connVerifiedCount')}</div>
          </div>
        </div>

        <div className="card" style={{ padding: '16px 20px', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '14px', borderLeft: totalAttentionCount > 0 ? '4px solid #f59e0b' : undefined }}>
          <div style={{ width: '42px', height: '42px', borderRadius: '10px', backgroundColor: '#f59e0b15', color: '#f59e0b', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <AlertCircle size={22} />
          </div>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'hsl(var(--fg))' }}>{totalAttentionCount}</div>
            <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>{t('connNeedsAttentionCount')}</div>
          </div>
        </div>

        <div className="card" style={{ padding: '16px 20px', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '42px', height: '42px', borderRadius: '10px', backgroundColor: 'hsl(var(--muted)/0.4)', color: 'hsl(var(--muted-fg))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Plus size={22} />
          </div>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'hsl(var(--fg))' }}>{totalAvailableCount}</div>
            <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>{t('connAvailableCount')}</div>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid hsl(var(--border))', marginBottom: '24px', flexWrap: 'wrap' }}>
        <button
          className={`btn btn-ghost ${activeTab === 'apps' ? 'active' : ''}`}
          onClick={() => setActiveTab('apps')}
          style={{
            borderBottom: activeTab === 'apps' ? '2px solid hsl(var(--primary))' : 'none',
            borderRadius: 0,
            padding: '10px 18px',
            fontWeight: 600,
            fontSize: '14px',
            color: activeTab === 'apps' ? 'hsl(var(--primary))' : undefined
          }}
        >
          {t('connTabConnectedApps')} ({totalVerifiedCount + totalAttentionCount})
        </button>
        <button
          className={`btn btn-ghost ${activeTab === 'calendar' ? 'active' : ''}`}
          onClick={() => setActiveTab('calendar')}
          style={{
            borderBottom: activeTab === 'calendar' ? '2px solid hsl(var(--primary))' : 'none',
            borderRadius: 0,
            padding: '10px 18px',
            fontWeight: 600,
            fontSize: '14px',
            color: activeTab === 'calendar' ? 'hsl(var(--primary))' : undefined
          }}
        >
          {t('connTabCalendarSchedule')} ({calendarEvents.length + googleCalendarEvents.length})
        </button>
        <button
          className={`btn btn-ghost ${activeTab === 'actions' ? 'active' : ''}`}
          onClick={() => setActiveTab('actions')}
          style={{
            borderBottom: activeTab === 'actions' ? '2px solid hsl(var(--primary))' : 'none',
            borderRadius: 0,
            padding: '10px 18px',
            fontWeight: 600,
            fontSize: '14px',
            color: activeTab === 'actions' ? 'hsl(var(--primary))' : undefined
          }}
        >
          {t('connTabActionLog')} ({executions.length})
        </button>
      </div>

      {/* TAB 1: CONNECTED APPS */}
      {activeTab === 'apps' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
          {/* Controls: Categories & Search */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              {(['all', 'productivity', 'dev', 'communication'] as CategoryType[]).map(cat => {
                const label = cat === 'all' ? t('connFilterAll')
                  : cat === 'productivity' ? t('connFilterProductivity')
                  : cat === 'dev' ? t('connFilterDev')
                  : t('connFilterComm');
                const isSelected = categoryFilter === cat;
                return (
                  <button
                    key={cat}
                    onClick={() => setCategoryFilter(cat)}
                    style={{
                      padding: '6px 14px',
                      borderRadius: '20px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      border: isSelected ? '1px solid hsl(var(--primary))' : '1px solid hsl(var(--border))',
                      backgroundColor: isSelected ? 'hsl(var(--primary)/0.12)' : 'transparent',
                      color: isSelected ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>

            <div style={{ position: 'relative', width: '280px' }}>
              <Search size={14} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'hsl(var(--muted-fg))' }} />
              <input
                type="text"
                className="input"
                placeholder={t('connSearchPlaceholder')}
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                style={{ width: '100%', paddingLeft: '34px', fontSize: '13px', borderRadius: '8px' }}
              />
            </div>
          </div>

          {/* Section 1: Verified & Operational */}
          {verifiedProviders.length > 0 && (
            <div>
              <div style={{ marginBottom: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#10b981' }} />
                  <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                    {t('connSecVerified')} ({verifiedProviders.length})
                  </h2>
                </div>
                <p style={{ margin: '3px 0 0 16px', fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
                  {t('connSecVerifiedDesc')}
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
                {verifiedProviders.map(p => {
                  const conn = connections.find(c => c.provider === p.id);
                  const Icon = p.icon;
                  const isGoogle = p.id === 'google_calendar';
                  const isLocalCal = p.id === 'calendar';

                  return (
                    <div
                      key={p.id}
                      className="card"
                      style={{
                        padding: '20px',
                        borderRadius: '12px',
                        border: '1px solid #10b98140',
                        borderLeft: '4px solid #10b981',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        gap: '16px',
                        backgroundColor: 'hsl(var(--card))',
                        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.04)',
                      }}
                    >
                      <div>
                        {/* Provider Header */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div style={{
                              width: '40px',
                              height: '40px',
                              borderRadius: '10px',
                              backgroundColor: `${p.color}15`,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              color: p.color,
                            }}>
                              <Icon size={20} />
                            </div>
                            <div>
                              <div style={{ fontWeight: 600, fontSize: '15px', color: 'hsl(var(--fg))' }}>{p.name}</div>
                              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>
                                {conn?.account_name || 'Active Account'}
                              </div>
                            </div>
                          </div>

                          <span style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            fontSize: '11px',
                            color: '#10b981',
                            fontWeight: 600,
                            backgroundColor: '#10b98115',
                            padding: '4px 10px',
                            borderRadius: '12px',
                          }}>
                            <CheckCircle2 size={13} /> {isGoogle ? t('connStatusConnectedVerified') : t('connStatusVerified')}
                          </span>
                        </div>

                        {/* Description */}
                        <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', margin: '0 0 12px', lineHeight: 1.45 }}>
                          {p.description}
                        </p>

                        {/* Key Capabilities Chips */}
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px', marginBottom: '12px' }}>
                          {p.capabilitiesList.slice(0, 3).map((cap, i) => (
                            <span
                              key={i}
                              style={{
                                fontSize: '11px',
                                backgroundColor: 'hsl(var(--muted)/0.4)',
                                color: 'hsl(var(--fg))',
                                padding: '2px 8px',
                                borderRadius: '4px',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '3px',
                              }}
                            >
                              <Check size={10} style={{ color: '#10b981' }} /> {cap}
                            </span>
                          ))}
                        </div>

                        {/* Live Metadata Badges */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                          {isGoogle && conn?.auth_metadata && (
                            <div style={{ color: '#4285F4', display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 500 }}>
                              <Calendar size={11} /> {t('connPrimaryCalendar')}: {conn.auth_metadata.selected_calendar_summary || conn.auth_metadata.selected_calendar_id || 'Primary'}
                            </div>
                          )}
                          {conn?.last_verified_at && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#10b981' }}>
                              <ShieldCheck size={11} /> {t('connLastVerified')}: {new Date(conn.last_verified_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}
                              {conn.verification_method ? ` (${conn.verification_method})` : ''}
                            </div>
                          )}
                          {conn?.last_synced_at && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <Clock size={11} /> {t('connLastSynced')}: {new Date(conn.last_synced_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}
                            </div>
                          )}
                          {conn?.last_successful_operation && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <Zap size={11} /> {t('connLastOp')}: {conn.last_successful_operation}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Primary Actions */}
                      <div style={{ display: 'flex', justifyContent: 'flex-end', flexWrap: 'wrap', gap: '8px', borderTop: '1px solid hsl(var(--border)/0.5)', paddingTop: '14px' }}>
                        {isLocalCal ? (
                          <button
                            className="btn btn-secondary"
                            onClick={() => {
                              setSelectedScheduleSource('local');
                              setActiveTab('calendar');
                            }}
                            style={{ fontSize: '12px', padding: '6px 12px' }}
                          >
                            {t('connViewSchedule')}
                          </button>
                        ) : isGoogle ? (
                          <>
                            <button
                              className="btn btn-secondary"
                              onClick={() => {
                                setSelectedScheduleSource('google');
                                setActiveTab('calendar');
                              }}
                              style={{ fontSize: '12px', padding: '6px 12px' }}
                            >
                              {t('connViewSchedule')}
                            </button>
                            <button
                              className="btn btn-secondary"
                              onClick={() => handleSync(p.id)}
                              disabled={syncingProvider === p.id}
                              style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                              title="Sync external entities into persistent memory and knowledge"
                            >
                              <RefreshCw size={12} className={syncingProvider === p.id ? 'animate-spin' : ''} />
                              {syncingProvider === p.id ? t('connSyncing') : t('connSyncNow')}
                            </button>
                            <button
                              className="btn btn-secondary"
                              onClick={handleOpenCalendarPicker}
                              style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                            >
                              <Calendar size={12} /> Select Calendar
                            </button>
                          </>
                        ) : (
                          <button
                            className="btn btn-secondary"
                            onClick={() => handleSync(p.id)}
                            disabled={syncingProvider === p.id}
                            style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                            title="Sync external entities into persistent memory and knowledge"
                          >
                            <RefreshCw size={12} className={syncingProvider === p.id ? 'animate-spin' : ''} />
                            {syncingProvider === p.id ? t('connSyncing') : t('connSyncNow')}
                          </button>
                        )}

                        <button
                          className="btn btn-secondary"
                          onClick={() => setManageProvider(p)}
                          style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                        >
                          <Settings size={12} /> {t('connManage')}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Section 2: Needs Attention */}
          {attentionProviders.length > 0 && (
            <div>
              <div style={{ marginBottom: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#f59e0b' }} />
                  <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                    {t('connSecNeedsAttention')} ({attentionProviders.length})
                  </h2>
                </div>
                <p style={{ margin: '3px 0 0 16px', fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
                  {t('connSecNeedsAttentionDesc')}
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
                {attentionProviders.map(p => {
                  const conn = connections.find(c => c.provider === p.id);
                  const Icon = p.icon;
                  const status = conn?.status;
                  const isFailed = status === 'verification_failed' || status === 'error';
                  const isNeedsAuth = status === 'verification_required' || status === 'needs_auth';
                  const isVerifying = verifyingProvider === p.id || (p.id === 'google_calendar' && googleAuthPending);
                  const diagnostic = diagnoseError(conn?.last_verification_error);

                  return (
                    <div
                      key={p.id}
                      className="card"
                      style={{
                        padding: '20px',
                        borderRadius: '12px',
                        border: isFailed ? '1px solid #ef444440' : '1px solid #f59e0b40',
                        borderLeft: isFailed ? '4px solid #ef4444' : '4px solid #f59e0b',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        gap: '16px',
                        backgroundColor: 'hsl(var(--card))',
                      }}
                    >
                      <div>
                        {/* Provider Header */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div style={{
                              width: '40px',
                              height: '40px',
                              borderRadius: '10px',
                              backgroundColor: `${p.color}15`,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              color: p.color,
                            }}>
                              <Icon size={20} />
                            </div>
                            <div>
                              <div style={{ fontWeight: 600, fontSize: '15px', color: 'hsl(var(--fg))' }}>{p.name}</div>
                              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>
                                {conn?.account_name || 'Configured'}
                              </div>
                            </div>
                          </div>

                          {isVerifying ? (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#f59e0b', fontWeight: 600, backgroundColor: '#f59e0b15', padding: '4px 10px', borderRadius: '12px' }}>
                              <RefreshCw size={12} className="animate-spin" /> {t('connStatusVerifying')}
                            </span>
                          ) : isFailed ? (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#ef4444', fontWeight: 600, backgroundColor: '#ef444415', padding: '4px 10px', borderRadius: '12px' }}>
                              <AlertCircle size={12} /> {t('connStatusVerifFailed')}
                            </span>
                          ) : isNeedsAuth ? (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#f59e0b', fontWeight: 600, backgroundColor: '#f59e0b15', padding: '4px 10px', borderRadius: '12px' }}>
                              <AlertCircle size={12} /> {t('connStatusNeedsAuth')}
                            </span>
                          ) : (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#38bdf8', fontWeight: 600, backgroundColor: '#38bdf815', padding: '4px 10px', borderRadius: '12px' }}>
                              <ShieldCheck size={12} /> {t('connStatusConfigured')}
                            </span>
                          )}
                        </div>

                        {/* Error Diagnostic Box */}
                        {isFailed && diagnostic ? (
                          <div style={{
                            padding: '10px 12px',
                            borderRadius: '8px',
                            backgroundColor: '#ef444410',
                            border: '1px solid #ef444420',
                            marginBottom: '12px',
                          }}>
                            <div style={{ fontWeight: 600, fontSize: '12px', color: '#ef4444', display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <AlertTriangle size={13} /> {diagnostic.title}
                            </div>
                            <div style={{ fontSize: '11px', color: 'hsl(var(--fg))', marginTop: '2px', lineHeight: 1.4 }}>
                              {diagnostic.desc}
                            </div>
                            {conn?.last_verification_error && (
                              <details style={{ marginTop: '6px', fontSize: '10px', color: 'hsl(var(--muted-fg))' }}>
                                <summary style={{ cursor: 'pointer', userSelect: 'none' }}>{t('connShowTechDetails')}</summary>
                                <pre style={{ margin: '4px 0 0', padding: '6px', backgroundColor: 'hsl(var(--muted)/0.5)', borderRadius: '4px', overflowX: 'auto', fontFamily: 'monospace' }}>
                                  {conn.last_verification_error}
                                </pre>
                              </details>
                            )}
                          </div>
                        ) : (
                          <div style={{
                            padding: '8px 12px',
                            borderRadius: '8px',
                            backgroundColor: '#38bdf810',
                            border: '1px solid #38bdf820',
                            marginBottom: '12px',
                            fontSize: '12px',
                            color: '#0284c7',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                          }}>
                            <ShieldCheck size={14} />
                            <span>Credentials saved in keychain. Awaiting live network probe.</span>
                          </div>
                        )}

                        <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', margin: 0, lineHeight: 1.4 }}>
                          {p.description}
                        </p>
                      </div>

                      {/* Primary Actions */}
                      <div style={{ display: 'flex', justifyContent: 'flex-end', flexWrap: 'wrap', gap: '8px', borderTop: '1px solid hsl(var(--border)/0.5)', paddingTop: '14px' }}>
                        {p.id === 'google_calendar' ? (
                          <button
                            className="btn btn-primary"
                            onClick={() => {
                              if (conn?.auth_metadata?.client_id) setGoogleClientId(conn.auth_metadata.client_id);
                              setIsGoogleModalOpen(true);
                            }}
                            disabled={isVerifying}
                            style={{ fontSize: '12px', padding: '6px 14px' }}
                          >
                            {isVerifying ? (
                              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <RefreshCw size={12} className="animate-spin" /> {t('connStatusVerifying')}
                              </span>
                            ) : (
                              t('connReconnect')
                            )}
                          </button>
                        ) : (
                          <button
                            className="btn btn-primary"
                            onClick={() => handleVerifyConnection(p.id)}
                            disabled={isVerifying}
                            style={{ fontSize: '12px', padding: '6px 14px', display: 'flex', alignItems: 'center', gap: '4px' }}
                          >
                            <ShieldCheck size={13} className={isVerifying ? 'animate-spin' : ''} />
                            {isVerifying ? t('connStatusVerifying') : isFailed ? t('connRetryVerify') : t('connVerify')}
                          </button>
                        )}

                        <button
                          className="btn btn-secondary"
                          onClick={() => setManageProvider(p)}
                          style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                        >
                          <Settings size={12} /> {t('connManage')}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Section 3: Available to Connect */}
          {availableToConnectProviders.length > 0 && (
            <div>
              <div style={{ marginBottom: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'hsl(var(--muted-fg))' }} />
                  <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                    {t('connSecAvailable')} ({availableToConnectProviders.length})
                  </h2>
                </div>
                <p style={{ margin: '3px 0 0 16px', fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
                  {t('connSecAvailableDesc')}
                </p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
                {availableToConnectProviders.map(p => {
                  const conn = connections.find(c => c.provider === p.id);
                  const Icon = p.icon;
                  const isDisconnected = conn?.status === 'disconnected';

                  return (
                    <div
                      key={p.id}
                      className="card"
                      style={{
                        padding: '20px',
                        borderRadius: '12px',
                        border: '1px solid hsl(var(--border))',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        gap: '16px',
                        backgroundColor: 'hsl(var(--card))',
                      }}
                    >
                      <div>
                        {/* Provider Header */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div style={{
                              width: '40px',
                              height: '40px',
                              borderRadius: '10px',
                              backgroundColor: `${p.color}15`,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              color: p.color,
                            }}>
                              <Icon size={20} />
                            </div>
                            <div>
                              <div style={{ fontWeight: 600, fontSize: '15px', color: 'hsl(var(--fg))' }}>{p.name}</div>
                              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                                {p.builtIn ? 'Local Workspace Engine' : isDisconnected ? t('connStatusDisconnected') : t('connStatusNotConfigured')}
                              </div>
                            </div>
                          </div>

                          <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', backgroundColor: 'hsl(var(--muted)/0.4)', padding: '3px 8px', borderRadius: '10px' }}>
                            {isDisconnected ? t('connStatusDisconnected') : t('connStatusNotConfigured')}
                          </span>
                        </div>

                        {/* Description */}
                        <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', margin: '0 0 12px', lineHeight: 1.45 }}>
                          {p.description}
                        </p>

                        {/* Capabilities Preview */}
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                          {p.capabilitiesList.slice(0, 2).map((cap, i) => (
                            <span
                              key={i}
                              style={{
                                fontSize: '11px',
                                backgroundColor: 'hsl(var(--muted)/0.4)',
                                color: 'hsl(var(--muted-fg))',
                                padding: '2px 8px',
                                borderRadius: '4px',
                              }}
                            >
                              • {cap}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Primary Connect Action */}
                      <div style={{ display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid hsl(var(--border)/0.5)', paddingTop: '14px' }}>
                        {p.id === 'calendar' ? (
                          <button
                            className="btn btn-primary"
                            onClick={handleConnectCalendar}
                            style={{ fontSize: '12px', padding: '6px 14px' }}
                          >
                            Initialize Calendar
                          </button>
                        ) : p.id === 'google_calendar' ? (
                          <button
                            className="btn btn-primary"
                            onClick={() => {
                              if (conn?.auth_metadata?.client_id) setGoogleClientId(conn.auth_metadata.client_id);
                              setIsGoogleModalOpen(true);
                            }}
                            style={{ fontSize: '12px', padding: '6px 14px', backgroundColor: '#4285F4', borderColor: '#4285F4', color: '#fff' }}
                          >
                            Connect Google Calendar
                          </button>
                        ) : (
                          <button
                            className="btn btn-primary"
                            onClick={() => openConfigModal(p, conn)}
                            style={{ fontSize: '12px', padding: '6px 14px' }}
                          >
                            {isDisconnected ? t('connReconnect') : t('connConnect')}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: CALENDAR SCHEDULE */}
      {activeTab === 'calendar' && (
        <div>
          {/* Calendar Source Switcher */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className={`btn ${selectedScheduleSource === 'local' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setSelectedScheduleSource('local')}
                style={{ fontSize: '12px', padding: '6px 14px' }}
              >
                Aether Calendar (Local) ({calendarEvents.length})
              </button>
              {connections.some(c => c.provider === 'google_calendar' && (c.status === 'verified' || c.status === 'connected')) && (
                <button
                  className={`btn ${selectedScheduleSource === 'google' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setSelectedScheduleSource('google')}
                  style={{
                    fontSize: '12px',
                    padding: '6px 14px',
                    backgroundColor: selectedScheduleSource === 'google' ? '#4285F4' : undefined,
                    borderColor: selectedScheduleSource === 'google' ? '#4285F4' : undefined,
                    color: selectedScheduleSource === 'google' ? '#fff' : undefined,
                  }}
                >
                  Google Calendar ({googleCalendarEvents.length})
                </button>
              )}
            </div>

            <button
              className="btn btn-primary"
              onClick={() => setIsEventModalOpen(true)}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
            >
              <Plus size={14} /> New Event ({selectedScheduleSource === 'google' ? 'Google' : 'Local'})
            </button>
          </div>

          <div style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', marginBottom: '12px' }}>
            {selectedScheduleSource === 'google'
              ? 'Real Google Calendar events synchronized via official Google Calendar API:'
              : 'Real scheduled events managed via Aether Local Calendar (SQLite storage):'}
          </div>

          {((selectedScheduleSource === 'google' ? googleCalendarEvents : calendarEvents).length === 0) ? (
            <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
              <Calendar size={32} style={{ margin: '0 auto 12px', opacity: 0.5, color: selectedScheduleSource === 'google' ? '#4285F4' : undefined }} />
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>
                {selectedScheduleSource === 'google' ? 'No Google Calendar events found' : 'No local calendar events found'}
              </div>
              <div style={{ fontSize: '13px' }}>
                {selectedScheduleSource === 'google'
                  ? 'Click "New Event" to create an event on Google Calendar, or click "Sync Now" on the Google Calendar card.'
                  : 'Ask Personal Aether to schedule an appointment or click "New Event".'}
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {(selectedScheduleSource === 'google' ? googleCalendarEvents : calendarEvents).map(evt => (
                <div
                  key={evt.id}
                  className="card"
                  style={{
                    padding: '16px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    borderRadius: '10px',
                    borderLeft: selectedScheduleSource === 'google' ? '3px solid #4285F4' : '3px solid #06b6d4',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                    <div style={{
                      width: '42px',
                      height: '42px',
                      borderRadius: '8px',
                      backgroundColor: selectedScheduleSource === 'google' ? '#4285F415' : 'hsl(var(--primary)/0.1)',
                      color: selectedScheduleSource === 'google' ? '#4285F4' : 'hsl(var(--primary))',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontWeight: 700,
                      fontSize: '11px',
                    }}>
                      <Calendar size={18} />
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '15px', color: 'hsl(var(--fg))' }}>{evt.title}</div>
                      <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', display: 'flex', gap: '12px', marginTop: '2px' }}>
                        <span><Clock size={12} style={{ display: 'inline', marginRight: '4px' }} />{evt.start_time.replace('T', ' ').slice(0, 16)}</span>
                        {evt.location && <span>Location: {evt.location}</span>}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{
                      fontSize: '11px',
                      color: selectedScheduleSource === 'google' ? '#4285F4' : '#06b6d4',
                      backgroundColor: selectedScheduleSource === 'google' ? '#4285F415' : '#06b6d415',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontWeight: 600,
                    }}>
                      {selectedScheduleSource === 'google' ? 'Google Calendar' : 'Local Workspace'}
                    </span>
                    <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 600, backgroundColor: '#10b98115', padding: '3px 10px', borderRadius: '12px' }}>
                      Confirmed
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: ACTION EXECUTIONS LOG */}
      {activeTab === 'actions' && (
        <div>
          {/* Action Status Filters */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>Filter:</span>
            {['all', 'pending', 'succeeded', 'failed'].map(f => (
              <button
                key={f}
                onClick={() => setActionStatusFilter(f)}
                style={{
                  padding: '4px 10px',
                  borderRadius: '12px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  border: actionStatusFilter === f ? '1px solid hsl(var(--primary))' : '1px solid hsl(var(--border))',
                  backgroundColor: actionStatusFilter === f ? 'hsl(var(--primary)/0.12)' : 'transparent',
                  color: actionStatusFilter === f ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
                }}
              >
                {f.toUpperCase()}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {filteredExecutions.length === 0 ? (
              <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
                <Zap size={32} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
                <div style={{ fontWeight: 600, marginBottom: '4px' }}>No action executions recorded yet</div>
                <div style={{ fontSize: '13px' }}>Actions executed by Aether or requiring approval will be audited here.</div>
              </div>
            ) : (
              filteredExecutions.map(exec => {
                const summary = getActionSummary(exec);
                const detail = getActionDetail(exec);
                const isTargeted = initialExecutionId === exec.id;
                return (
                  <div
                    key={exec.id}
                    id={`exec-card-${exec.id}`}
                    className="card"
                    style={{
                      padding: '16px 20px',
                      borderRadius: '10px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                      border: isTargeted ? '2px solid hsl(var(--primary))' : undefined,
                      boxShadow: isTargeted ? '0 0 16px rgba(99, 102, 241, 0.25)' : undefined,
                      transition: 'all 0.3s ease',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '8px' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{
                            fontSize: '11px',
                            fontWeight: 700,
                            padding: '2px 8px',
                            borderRadius: '4px',
                            backgroundColor: 'hsl(var(--muted)/0.4)',
                            color: 'hsl(var(--fg))',
                          }}>
                            {exec.action_id}
                          </span>
                          <span style={{ fontWeight: 600, fontSize: '14px', color: 'hsl(var(--fg))' }}>
                            {summary}
                          </span>
                        </div>
                        {detail && (
                          <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '4px', paddingLeft: '4px', fontStyle: 'italic' }}>
                            "{detail}"
                          </div>
                        )}
                        <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '6px' }}>
                          ID: {exec.id} • {exec.created_at ? new Date(exec.created_at).toLocaleString() : ''}
                        </div>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                        <span style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          padding: '3px 10px',
                          borderRadius: '10px',
                          backgroundColor: (exec.status === 'success' || exec.status === 'succeeded') ? '#10b98115' : (exec.status === 'pending_approval' || exec.status === 'waiting_approval') ? '#f59e0b15' : (exec.status === 'running' || exec.status === 'queued') ? '#3b82f615' : '#ef444415',
                          color: (exec.status === 'success' || exec.status === 'succeeded') ? '#10b981' : (exec.status === 'pending_approval' || exec.status === 'waiting_approval') ? '#f59e0b' : (exec.status === 'running' || exec.status === 'queued') ? '#3b82f6' : '#ef4444',
                        }}>
                          {exec.status.toUpperCase()}
                        </span>
                      </div>
                    </div>

                    {exec.error_message && (
                      <div style={{
                        fontSize: '12px',
                        color: '#ef4444',
                        backgroundColor: '#ef444410',
                        border: '1px solid #ef444420',
                        padding: '8px 12px',
                        borderRadius: '6px',
                        marginTop: '4px',
                      }}>
                        <strong>Error:</strong> {exec.error_message}
                      </div>
                    )}

                    {(exec.status === 'success' || exec.status === 'succeeded') && exec.output_data && (
                      <div style={{
                        fontSize: '12px',
                        color: 'hsl(var(--muted-fg))',
                        backgroundColor: 'hsl(var(--muted)/0.2)',
                        padding: '6px 10px',
                        borderRadius: '6px',
                        fontFamily: 'monospace',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}>
                        Result: {typeof exec.output_data === 'string' ? exec.output_data : JSON.stringify(exec.output_data).slice(0, 160)}
                      </div>
                    )}

                    {(exec.status === 'pending_approval' || exec.status === 'waiting_approval') && (
                      <div style={{ display: 'flex', gap: '8px', marginTop: '8px', justifyContent: 'flex-end', borderTop: '1px solid hsl(var(--border)/0.4)', paddingTop: '10px' }}>
                        <button
                          onClick={() => handleRejectAction(exec.id)}
                          disabled={actionLoadingId === exec.id}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            padding: '6px 12px',
                            borderRadius: '6px',
                            border: '1px solid hsl(var(--border))',
                            backgroundColor: 'transparent',
                            color: '#ef4444',
                            fontSize: '12px',
                            fontWeight: 600,
                            cursor: actionLoadingId === exec.id ? 'not-allowed' : 'pointer',
                            opacity: actionLoadingId === exec.id ? 0.6 : 1,
                          }}
                        >
                          {actionLoadingId === exec.id ? <Loader2 size={13} className="animate-spin" /> : <X size={13} />}
                          Decline
                        </button>
                        <button
                          onClick={() => handleApproveAction(exec.id)}
                          disabled={actionLoadingId === exec.id}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            padding: '6px 14px',
                            borderRadius: '6px',
                            border: 'none',
                            backgroundColor: '#10b981',
                            color: '#ffffff',
                            fontSize: '12px',
                            fontWeight: 600,
                            cursor: actionLoadingId === exec.id ? 'not-allowed' : 'pointer',
                            opacity: actionLoadingId === exec.id ? 0.6 : 1,
                          }}
                        >
                          {actionLoadingId === exec.id ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                          Approve & Run
                        </button>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* MANAGE CONNECTION MODAL / DRAWER */}
      {manageProvider && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.65)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div className="card" style={{ width: '560px', maxHeight: '90vh', overflowY: 'auto', padding: '28px', borderRadius: '14px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '12px',
                  backgroundColor: `${manageProvider.color}15`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: manageProvider.color,
                }}>
                  <manageProvider.icon size={24} />
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'hsl(var(--fg))' }}>
                    {manageProvider.name}
                  </h3>
                  <div style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
                    {activeManageConn?.account_name || 'Configured Integration'}
                  </div>
                </div>
              </div>
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setManageProvider(null);
                  setShowTechDetails(false);
                }}
                style={{ padding: '6px', borderRadius: '50%' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Status & Identity Card */}
            <div style={{
              padding: '14px 16px',
              borderRadius: '10px',
              backgroundColor: 'hsl(var(--muted)/0.3)',
              border: '1px solid hsl(var(--border))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <div>
                <div style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>
                  Current Status
                </div>
                <div style={{ fontSize: '14px', fontWeight: 600, color: 'hsl(var(--fg))', marginTop: '2px' }}>
                  {activeManageConn?.status ? activeManageConn.status.toUpperCase() : 'NOT CONFIGURED'}
                </div>
              </div>

              {activeManageConn?.status === 'verified' || activeManageConn?.status === 'connected' ? (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#10b981', fontWeight: 600, backgroundColor: '#10b98115', padding: '4px 10px', borderRadius: '12px' }}>
                  <CheckCircle2 size={14} /> Operational
                </span>
              ) : activeManageConn?.status === 'verification_failed' ? (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#ef4444', fontWeight: 600, backgroundColor: '#ef444415', padding: '4px 10px', borderRadius: '12px' }}>
                  <AlertCircle size={14} /> Verification Failed
                </span>
              ) : (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#f59e0b', fontWeight: 600, backgroundColor: '#f59e0b15', padding: '4px 10px', borderRadius: '12px' }}>
                  <AlertCircle size={14} /> Needs Attention
                </span>
              )}
            </div>

            {/* What Aether Can Do */}
            <div>
              <div style={{ fontSize: '14px', fontWeight: 700, color: 'hsl(var(--fg))', marginBottom: '8px' }}>
                {t('connWhatAetherCanDo')}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {manageProvider.capabilitiesList.map((cap, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'hsl(var(--fg))' }}>
                    <Check size={14} style={{ color: '#10b981', flexShrink: 0 }} />
                    <span>{cap}</span>
                  </div>
                ))}
              </div>
              <div style={{
                marginTop: '10px',
                padding: '8px 12px',
                borderRadius: '8px',
                backgroundColor: 'hsl(var(--muted)/0.2)',
                fontSize: '11px',
                color: 'hsl(var(--muted-fg))',
                lineHeight: 1.4,
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}>
                <Shield size={14} style={{ color: 'hsl(var(--primary))', flexShrink: 0 }} />
                <span>{t('connSafetyNote')}</span>
              </div>
            </div>

            {/* Recent Activity */}
            <div>
              <div style={{ fontSize: '14px', fontWeight: 700, color: 'hsl(var(--fg))', marginBottom: '8px' }}>
                {t('connRecentActivity')}
              </div>
              {manageRecentExecutions.length === 0 ? (
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontStyle: 'italic', padding: '8px 0' }}>
                  {t('connNoRecentActivity')}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {manageRecentExecutions.map(exec => (
                    <div
                      key={exec.id}
                      style={{
                        padding: '8px 12px',
                        borderRadius: '6px',
                        backgroundColor: 'hsl(var(--muted)/0.2)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        fontSize: '12px',
                      }}
                    >
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '340px' }}>
                        <span style={{ fontWeight: 600, marginRight: '6px' }}>{exec.action_id}:</span>
                        <span style={{ color: 'hsl(var(--muted-fg))' }}>{getActionSummary(exec)}</span>
                      </div>
                      <span style={{
                        fontSize: '10px',
                        fontWeight: 600,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        backgroundColor: (exec.status === 'success' || exec.status === 'succeeded') ? '#10b98115' : '#ef444415',
                        color: (exec.status === 'success' || exec.status === 'succeeded') ? '#10b981' : '#ef4444',
                      }}>
                        {exec.status.toUpperCase()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Advanced Diagnostics Toggle */}
            <div style={{ borderTop: '1px solid hsl(var(--border))', paddingTop: '12px' }}>
              <button
                type="button"
                onClick={() => setShowTechDetails(!showTechDetails)}
                style={{
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  fontSize: '12px',
                  fontWeight: 600,
                  color: 'hsl(var(--muted-fg))',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  cursor: 'pointer',
                }}
              >
                {showTechDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {t('connDiagnostics')}
              </button>

              {showTechDetails && (
                <div style={{
                  marginTop: '10px',
                  padding: '12px',
                  borderRadius: '8px',
                  backgroundColor: 'hsl(var(--muted)/0.2)',
                  fontSize: '11px',
                  fontFamily: 'monospace',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  color: 'hsl(var(--fg))',
                }}>
                  <div><strong>{t('connConnId')}:</strong> {activeManageConn?.id || 'none'}</div>
                  <div><strong>{t('connMethod')}:</strong> {activeManageConn?.verification_method || 'none'}</div>
                  <div><strong>{t('connScopes')}:</strong> {activeManageConn?.scopes?.join(', ') || 'default'}</div>
                  <div><strong>{t('connLastVerified')}:</strong> {activeManageConn?.last_verified_at || 'Never'}</div>
                  <div><strong>{t('connLastSynced')}:</strong> {activeManageConn?.last_synced_at || 'Never'}</div>
                  <div><strong>Last Successful Op:</strong> {activeManageConn?.last_successful_operation || 'None'}</div>
                  {activeManageConn?.last_verification_error && (
                    <div style={{ color: '#ef4444' }}>
                      <strong>Last Error:</strong> {activeManageConn.last_verification_error}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Modal Actions */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid hsl(var(--border))', paddingTop: '16px' }}>
              <button
                className="btn btn-ghost"
                onClick={() => setDisconnectTarget({ id: manageProvider.id, name: manageProvider.name })}
                style={{ color: '#ef4444', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}
              >
                <Trash2 size={13} /> {t('connDisconnect')}
              </button>

              <div style={{ display: 'flex', gap: '8px' }}>
                {!manageProvider.builtIn && !manageProvider.isOAuth && (
                  <button
                    className="btn btn-secondary"
                    onClick={() => {
                      const p = manageProvider;
                      const c = activeManageConn;
                      setManageProvider(null);
                      if (p) openConfigModal(p, c || undefined);
                    }}
                    style={{ fontSize: '12px' }}
                  >
                    {t('connEditCredentials')}
                  </button>
                )}

                {manageProvider.isOAuth ? (
                  <>
                    <button
                      className="btn btn-secondary"
                      onClick={() => {
                        setManageProvider(null);
                        handleOpenCalendarPicker();
                      }}
                      style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                    >
                      <Calendar size={12} /> Select Calendar
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={() => {
                        if (activeManageConn?.auth_metadata?.client_id) setGoogleClientId(activeManageConn.auth_metadata.client_id);
                        setManageProvider(null);
                        setIsGoogleModalOpen(true);
                      }}
                      style={{ fontSize: '12px', backgroundColor: '#4285F4', borderColor: '#4285F4', color: '#fff' }}
                    >
                      Re-authorize Google
                    </button>
                  </>
                ) : (
                  <button
                    className="btn btn-primary"
                    onClick={async () => {
                      await handleVerifyConnection(manageProvider.id);
                    }}
                    disabled={verifyingProvider === manageProvider.id}
                    style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                  >
                    <ShieldCheck size={13} className={verifyingProvider === manageProvider.id ? 'animate-spin' : ''} />
                    {verifyingProvider === manageProvider.id ? t('connStatusVerifying') : t('connReverify')}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* DISCONNECT CONFIRMATION MODAL */}
      {disconnectTarget && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.7)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1100,
        }}>
          <div className="card" style={{ width: '420px', padding: '24px', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '10px', backgroundColor: '#ef444415', color: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <AlertTriangle size={20} />
              </div>
              <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 600 }}>
                {t('connDisconnectTitle').replace('{provider}', disconnectTarget.name)}
              </h3>
            </div>

            <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', lineHeight: 1.5, margin: 0 }}>
              {t('connDisconnectDesc')}
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '6px' }}>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setDisconnectTarget(null)}
                disabled={disconnecting}
              >
                {t('connCancel')}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={confirmDisconnect}
                disabled={disconnecting}
                style={{ backgroundColor: '#ef4444', borderColor: '#ef4444', color: '#fff' }}
              >
                {disconnecting ? 'Disconnecting...' : t('connConfirmDisconnect')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CREATE EVENT MODAL */}
      {isEventModalOpen && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div className="card" style={{ width: '400px', padding: '24px', borderRadius: '12px' }}>
            <h3 style={{ margin: '0 0 16px', fontSize: '18px', fontWeight: 600 }}>Create Calendar Event</h3>
            <form onSubmit={handleCreateEvent} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Title</label>
                <input
                  type="text"
                  className="input"
                  required
                  placeholder="e.g. Planning Meeting"
                  value={newTitle}
                  onChange={e => setNewTitle(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Start Time (ISO or description)</label>
                <input
                  type="text"
                  className="input"
                  placeholder="2026-09-15T10:00:00Z"
                  value={newStartTime}
                  onChange={e => setNewStartTime(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Location</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g. Zoom / Office"
                  value={newLocation}
                  onChange={e => setNewLocation(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '10px' }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setIsEventModalOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={creatingEvent}
                >
                  {creatingEvent ? 'Creating...' : 'Save Event'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CREDENTIAL CONFIGURATION MODAL */}
      {configModalProvider && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.65)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div className="card" style={{ width: '500px', maxHeight: '90vh', overflowY: 'auto', padding: '26px', borderRadius: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <div style={{
                width: '38px',
                height: '38px',
                borderRadius: '10px',
                backgroundColor: `${configModalProvider.color}15`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: configModalProvider.color,
              }}>
                <configModalProvider.icon size={22} />
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>Configure {configModalProvider.name}</h3>
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                  {isConfigured ? 'Update credentials (leave secrets blank to keep current)' : 'Provide authentic credentials to enable real agentic actions'}
                </div>
              </div>
            </div>

            {/* Keychain Protection Notice */}
            <div style={{
              padding: '8px 12px',
              borderRadius: '8px',
              backgroundColor: 'hsl(var(--muted)/0.3)',
              border: '1px solid hsl(var(--border))',
              marginBottom: '14px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '11px',
              color: 'hsl(var(--muted-fg))',
            }}>
              <Lock size={13} style={{ color: '#10b981', flexShrink: 0 }} />
              <span>{t('connSecuredKeychain')}</span>
            </div>

            {/* Test result message if any */}
            {testResult && (
              <div style={{
                padding: '10px 14px',
                borderRadius: '8px',
                marginBottom: '16px',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                backgroundColor: testResult.valid ? '#10b98115' : '#ef444415',
                color: testResult.valid ? '#10b981' : '#ef4444',
                border: `1px solid ${testResult.valid ? '#10b98130' : '#ef444430'}`
              }}>
                {testResult.valid ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                <span>{testResult.message}</span>
              </div>
            )}

            <form onSubmit={handleSaveAndConnect} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Account Name / Label</label>
                <input
                  type="text"
                  className="input"
                  required
                  placeholder={`e.g. Primary ${configModalProvider.name}`}
                  value={credAccountName}
                  onChange={e => setCredAccountName(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>

              {/* Provider-specific inputs */}
              {configModalProvider.id === 'github' && (
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Personal Access Token (PAT)</label>
                  <input
                    type="password"
                    className="input"
                    required={!isConfigured}
                    placeholder={isConfigured ? '•••••••••••••••• (leave blank to keep current)' : 'ghp_xxxxxxxxxxxxxxxxxxxx or github_pat_...'}
                    value={githubToken}
                    onChange={e => { setGithubToken(e.target.value); setTestResult(null); }}
                    style={{ width: '100%' }}
                  />
                  <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                    Requires repo and workflow read/write permissions.
                  </div>
                </div>
              )}

              {configModalProvider.id === 'slack' && (
                <>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Bot User OAuth Token</label>
                    <input
                      type="password"
                      className="input"
                      placeholder={isConfigured ? '•••••••••••••••• (leave blank to keep current)' : 'xoxb-xxxxxxxxxxxx-xxxxxxxxxxxx'}
                      value={slackToken}
                      onChange={e => { setSlackToken(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                  </div>
                  <div style={{ textAlign: 'center', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>— OR —</div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Incoming Webhook URL</label>
                    <input
                      type="url"
                      className="input"
                      placeholder={isConfigured ? '•••••••••••••••• (leave blank to keep current)' : 'https://hooks.slack.com/services/...'}
                      value={slackWebhook}
                      onChange={e => { setSlackWebhook(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Default Channel (Optional)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. #general"
                      value={slackDefaultChannel}
                      onChange={e => { setSlackDefaultChannel(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                  </div>
                </>
              )}

              {configModalProvider.id === 'email' && (
                <>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Email Address / Username</label>
                    <input
                      type="email"
                      className="input"
                      required
                      placeholder="user@example.com"
                      value={emailUser}
                      onChange={e => { setEmailUser(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>App Password / Token</label>
                    <input
                      type="password"
                      className="input"
                      required={!isConfigured}
                      placeholder={isConfigured ? '•••••••••••••••• (leave blank to keep current)' : 'Application specific password'}
                      value={emailPass}
                      onChange={e => { setEmailPass(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '8px' }}>
                    <div>
                      <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>SMTP Host</label>
                      <input
                        type="text"
                        className="input"
                        placeholder="smtp.gmail.com"
                        value={emailHost}
                        onChange={e => { setEmailHost(e.target.value); setTestResult(null); }}
                        style={{ width: '100%' }}
                      />
                    </div>
                    <div>
                      <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Port</label>
                      <input
                        type="text"
                        className="input"
                        placeholder="587"
                        value={emailPort}
                        onChange={e => { setEmailPort(e.target.value); setTestResult(null); }}
                        style={{ width: '100%' }}
                      />
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '16px', alignItems: 'center', marginTop: '2px' }}>
                    <label style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={emailUseTls}
                        onChange={e => { setEmailUseTls(e.target.checked); setTestResult(null); }}
                      />
                      <span>Use STARTTLS</span>
                    </label>
                    <label style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={emailUseSsl}
                        onChange={e => { setEmailUseSsl(e.target.checked); setTestResult(null); }}
                      />
                      <span>Direct SSL (Port 465)</span>
                    </label>
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Sender Address / Name (Optional)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. Aether Assistant <assistant@example.com>"
                      value={emailSenderAddr}
                      onChange={e => { setEmailSenderAddr(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Test Recipient (Optional)</label>
                    <input
                      type="email"
                      className="input"
                      placeholder="Send live verification test message to this email"
                      value={emailTestRecipient}
                      onChange={e => { setEmailTestRecipient(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                  </div>
                </>
              )}

              {configModalProvider.id === 'telegram' && (
                <>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Telegram Bot Token</label>
                    <input
                      type="password"
                      className="input"
                      required={!isConfigured}
                      placeholder={isConfigured ? '•••••••••••••••• (leave blank to keep current)' : '123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ'}
                      value={telegramBotToken}
                      onChange={e => { setTelegramBotToken(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                      Obtained from @BotFather on Telegram.
                    </div>
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Default Chat ID (Optional)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. 987654321"
                      value={telegramDefaultChatId}
                      onChange={e => { setTelegramDefaultChatId(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                      Your Telegram user ID or group chat ID for direct alerts and approvals.
                    </div>
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Authorized Chat IDs (Optional)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="Comma-separated IDs (e.g. 987654321, 123456789)"
                      value={telegramAllowedChats}
                      onChange={e => { setTelegramAllowedChats(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                      Restrict companion access to specific authorized Telegram accounts.
                    </div>
                  </div>
                </>
              )}

              {configModalProvider.id === 'http' && (
                <>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Base URL (Optional)</label>
                    <input
                      type="url"
                      className="input"
                      placeholder="https://api.example.com"
                      value={httpBaseUrl}
                      onChange={e => { setHttpBaseUrl(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                      Default base URL for relative endpoints.
                    </div>
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Authentication Type</label>
                    <select
                      className="input"
                      value={httpAuthType}
                      onChange={e => { setHttpAuthType(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    >
                      <option value="none">No Auth (Public)</option>
                      <option value="bearer">Bearer Token</option>
                      <option value="api_key">API Key (X-API-Key header)</option>
                      <option value="basic">Basic Auth (Username:Password or Base64)</option>
                    </select>
                  </div>
                  {httpAuthType !== 'none' && (
                    <div>
                      <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Token / API Key</label>
                      <input
                        type="password"
                        className="input"
                        placeholder={isConfigured ? '•••••••••••••••• (leave blank to keep current)' : 'Secret token, key, or credentials'}
                        value={httpToken}
                        onChange={e => { setHttpToken(e.target.value); setTestResult(null); }}
                        style={{ width: '100%' }}
                      />
                    </div>
                  )}
                </>
              )}

              {configModalProvider.id === 'notion' && (
                <>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Integration Token</label>
                    <input
                      type="password"
                      className="input"
                      required={!isConfigured}
                      placeholder={isConfigured ? '•••••••••••••••• (leave blank to keep current)' : 'secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx'}
                      value={notionToken}
                      onChange={e => { setNotionToken(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                      Internal integration secret token (starts with secret_ or ntn_).
                    </div>
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Default Database ID (Optional)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d"
                      value={notionDbId}
                      onChange={e => { setNotionDbId(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                      UUID of the default Notion database to create or search records.
                    </div>
                  </div>
                </>
              )}

              {configModalProvider.id === 'openapi' && (
                <>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Specification URL (Optional)</label>
                    <input
                      type="url"
                      className="input"
                      placeholder="https://api.example.com/openapi.json"
                      value={openapiSpecUrl}
                      onChange={e => { setOpenapiSpecUrl(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                      Remote URL pointing to OpenAPI 3.x / Swagger JSON or YAML.
                    </div>
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Local File Path (Optional)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="/path/to/spec.json or docs/api.yaml"
                      value={openapiSpecPath}
                      onChange={e => { setOpenapiSpecPath(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                      Absolute or workspace-relative path to local OpenAPI schema.
                    </div>
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>API Server Base URL (Optional)</label>
                    <input
                      type="url"
                      className="input"
                      placeholder="https://api.example.com/v1"
                      value={openapiBaseUrl}
                      onChange={e => { setOpenapiBaseUrl(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    />
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                      Overrides server URL defined in the OpenAPI specification.
                    </div>
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Authentication Type</label>
                    <select
                      className="input"
                      value={openapiAuthType}
                      onChange={e => { setOpenapiAuthType(e.target.value); setTestResult(null); }}
                      style={{ width: '100%' }}
                    >
                      <option value="none">No Auth (Public)</option>
                      <option value="bearer">Bearer Token</option>
                      <option value="api_key">API Key (X-API-Key header)</option>
                      <option value="basic">Basic Auth</option>
                    </select>
                  </div>
                  {openapiAuthType !== 'none' && (
                    <div>
                      <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Token / API Key</label>
                      <input
                        type="password"
                        className="input"
                        placeholder={isConfigured ? '•••••••••••••••• (leave blank to keep current)' : 'Secret token or key'}
                        value={openapiToken}
                        onChange={e => { setOpenapiToken(e.target.value); setTestResult(null); }}
                        style={{ width: '100%' }}
                      />
                    </div>
                  )}
                </>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '14px', paddingTop: '14px', borderTop: '1px solid hsl(var(--border))' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={testingCreds || savingCreds}
                  onClick={handleTestCreds}
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}
                >
                  <ShieldCheck size={14} />
                  {testingCreds ? 'Verifying...' : 'Test Connection'}
                </button>

                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setConfigModalProvider(null)}
                    disabled={savingCreds}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={savingCreds}
                  >
                    {savingCreds ? 'Saving...' : isConfigured ? 'Update & Save' : 'Save & Connect'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* GOOGLE CALENDAR OAUTH MODAL */}
      {isGoogleModalOpen && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.65)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div className="card" style={{ width: '500px', maxHeight: '90vh', overflowY: 'auto', padding: '26px', borderRadius: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <div style={{
                width: '42px',
                height: '42px',
                borderRadius: '10px',
                backgroundColor: '#4285F415',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#4285F4',
              }}>
                <Calendar size={22} />
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>Connect Google Calendar</h3>
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                  Official OAuth 2.0 PKCE flow with direct Google API authorization
                </div>
              </div>
            </div>

            <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', lineHeight: 1.5, margin: '0 0 16px' }}>
              Aether connects directly to official Google APIs without third-party proxying.
              Clicking <strong>Authorize with Google</strong> will open Google's consent screen.
            </p>

            <form onSubmit={handleStartGoogleOAuth} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>
                  Google Client ID (Optional)
                </label>
                <input
                  type="text"
                  className="input"
                  placeholder="Leave blank to use default desktop client or env setting"
                  value={googleClientId}
                  onChange={e => setGoogleClientId(e.target.value)}
                  style={{ width: '100%', fontSize: '13px' }}
                />
                <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                  If using your own Google Cloud project credentials.
                </div>
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>
                  Google Client Secret (Optional)
                </label>
                <input
                  type="password"
                  className="input"
                  placeholder="Optional for desktop PKCE flows"
                  value={googleClientSecret}
                  onChange={e => setGoogleClientSecret(e.target.value)}
                  style={{ width: '100%', fontSize: '13px' }}
                />
              </div>

              <div style={{
                backgroundColor: 'hsl(var(--muted)/0.2)',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
                padding: '10px 14px',
                fontSize: '11px',
                color: 'hsl(var(--muted-fg))',
                lineHeight: 1.4,
              }}>
                <strong>Authorized Redirect URI:</strong><br />
                <code style={{ fontSize: '10px', color: 'hsl(var(--fg))' }}>
                  http://127.0.0.1:8000/api/connections/google_calendar/oauth/callback
                </code>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '6px' }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setIsGoogleModalOpen(false)}
                  disabled={googleAuthPending}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={googleAuthPending}
                  style={{ backgroundColor: '#4285F4', borderColor: '#4285F4', color: '#fff' }}
                >
                  {googleAuthPending ? (
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <RefreshCw size={12} className="animate-spin" /> Verifica in corso...
                    </span>
                  ) : (
                    'Authorize with Google'
                  )}
                </button>
              </div>
            </form>

            {/* Manual fallback exchange for headless or popup blocked */}
            <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid hsl(var(--border))' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
                Manual Authorization Code Entry (Fallback)
              </div>
              <p style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', margin: '0 0 10px' }}>
                If your browser did not redirect automatically, paste the authorization code returned by Google below:
              </p>
              <form onSubmit={handleManualExchangeCode} style={{ display: 'flex', gap: '8px' }}>
                <input
                  type="text"
                  className="input"
                  placeholder="4/0A..."
                  value={googleManualCode}
                  onChange={e => setGoogleManualCode(e.target.value)}
                  style={{ flex: 1, fontSize: '12px' }}
                />
                <button
                  type="submit"
                  className="btn btn-secondary"
                  disabled={googleAuthPending || !googleManualCode.trim()}
                  style={{ fontSize: '12px' }}
                >
                  Submit & Verify
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* GOOGLE CALENDAR SELECTOR MODAL */}
      {isCalendarPickerOpen && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.65)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div className="card" style={{ width: '440px', maxHeight: '80vh', overflowY: 'auto', padding: '24px', borderRadius: '12px' }}>
            <h3 style={{ margin: '0 0 8px', fontSize: '18px', fontWeight: 600 }}>Select Active Google Calendar</h3>
            <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', margin: '0 0 16px' }}>
              Choose which Google Calendar Aether should read and schedule events into:
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '20px' }}>
              {googleCalendars.map(cal => (
                <div
                  key={cal.id}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '8px',
                    border: '1px solid hsl(var(--border))',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '14px' }}>
                      {cal.summary} {cal.primary && <span style={{ fontSize: '10px', backgroundColor: '#4285F420', color: '#4285F4', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>Primary</span>}
                    </div>
                    {cal.description && (
                      <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                        {cal.description}
                      </div>
                    )}
                  </div>
                  <button
                    className="btn btn-primary"
                    onClick={() => handleSelectCalendar(cal.id, cal.summary)}
                    style={{ fontSize: '11px', padding: '4px 10px' }}
                  >
                    Select
                  </button>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setIsCalendarPickerOpen(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
