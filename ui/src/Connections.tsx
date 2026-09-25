import { useState, useEffect, useContext } from 'react';
import {
  Calendar, Mail, GitBranch, MessageSquare, FileText, CheckCircle2,
  AlertCircle, ShieldCheck, Settings, Plus, RefreshCw, Clock, Zap, Globe, Send
} from 'lucide-react';
import { apiUrl } from './api';
import { ToastContext } from './toast';

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

export function Connections({ navigate: _navigate }: { navigate?: (view: string, params?: any) => void }) {
  const [activeTab, setActiveTab] = useState<'apps' | 'calendar' | 'actions'>('apps');
  const [connections, setConnections] = useState<ConnectionItem[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEventItem[]>([]);
  const [executions, setExecutions] = useState<ActionExecutionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncingProvider, setSyncingProvider] = useState<string | null>(null);
  const [verifyingProvider, setVerifyingProvider] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);

  // Google Calendar States (Macro-pass P0.2)
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
  const [configModalProvider, setConfigModalProvider] = useState<{
    id: string;
    name: string;
    icon: any;
    description: string;
    capabilitiesText: string;
    color: string;
    builtIn: boolean;
  } | null>(null);
  const [isConfigured, setIsConfigured] = useState(false);
  const [credAccountName, setCredAccountName] = useState('');
  const [githubToken, setGithubToken] = useState('');
  const [slackToken, setSlackToken] = useState('');
  const [slackWebhook, setSlackWebhook] = useState('');
  const [emailUser, setEmailUser] = useState('');
  const [emailPass, setEmailPass] = useState('');
  const [emailHost, setEmailHost] = useState('smtp.gmail.com');
  const [emailPort, setEmailPort] = useState('587');
  const [httpBaseUrl, setHttpBaseUrl] = useState('');
  const [httpAuthType, setHttpAuthType] = useState('none');
  const [httpToken, setHttpToken] = useState('');
  const [notionToken, setNotionToken] = useState('');
  const [telegramBotToken, setTelegramBotToken] = useState('');
  const [telegramDefaultChatId, setTelegramDefaultChatId] = useState('');
  const [telegramAllowedChats, setTelegramAllowedChats] = useState('');
  const [testingCreds, setTestingCreds] = useState(false);
  const [savingCreds, setSavingCreds] = useState(false);
  const [testResult, setTestResult] = useState<{ valid: boolean; message: string } | null>(null);

  const showToast = useContext(ToastContext);

  const availableProviders = [
    {
      id: 'calendar',
      name: 'Aether Calendar (Local)',
      icon: Calendar,
      description: 'Built-in local workspace schedule and event storage with zero external dependencies.',
      capabilitiesText: 'Can view schedule, list local events, and record meetings directly in workspace storage',
      color: '#06b6d4',
      builtIn: true,
      isOAuth: false,
    },
    {
      id: 'google_calendar',
      name: 'Google Calendar',
      icon: Calendar,
      description: 'Real Google Calendar integration via OAuth 2.0 PKCE. Reads calendars, syncs meetings, and schedules events.',
      capabilitiesText: 'Can read Google calendars and create or update events via official Google Calendar APIs',
      color: '#4285F4',
      builtIn: false,
      isOAuth: true,
    },
    {
      id: 'github',
      name: 'GitHub',
      icon: GitBranch,
      description: 'Access repositories, codebases, commits, and pull requests.',
      capabilitiesText: 'Can read repositories, create issues, and open pull requests',
      color: '#2dba4e',
      builtIn: false,
      isOAuth: false,
    },
    {
      id: 'email',
      name: 'Email / Gmail',
      icon: Mail,
      description: 'Read incoming briefs, prepare summaries, and draft outbound messages.',
      capabilitiesText: 'Can draft and dispatch emails via SMTP with explicit user approval',
      color: '#EA4335',
      builtIn: false,
      isOAuth: false,
    },
    {
      id: 'slack',
      name: 'Slack',
      icon: MessageSquare,
      description: 'Receive notifications and post status reports in team channels.',
      capabilitiesText: 'Can post messages and status updates to Slack channels with confirmation',
      color: '#4A154B',
      builtIn: false,
      isOAuth: false,
    },
    {
      id: 'telegram',
      name: 'Telegram Bot',
      icon: Send,
      description: 'Mobile companion, real-time alerts, remote task delegation, and inline approvals.',
      capabilitiesText: 'Can receive mobile commands, dispatch notifications, and handle interactive approvals',
      color: '#229ED9',
      builtIn: false,
      isOAuth: false,
    },
    {
      id: 'http',
      name: 'Generic HTTP / API',
      icon: Globe,
      description: 'Interact with external REST endpoints and Web APIs with security policies.',
      capabilitiesText: 'Can perform authenticated HTTP operations (GET, POST, PUT, DELETE)',
      color: '#6366f1',
      builtIn: false,
      isOAuth: false,
    },
    {
      id: 'notion',
      name: 'Notion',
      icon: FileText,
      description: 'Read and sync project documentation and database tables.',
      capabilitiesText: 'Can read and synchronize workspace pages and databases',
      color: '#000000',
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

  const openConfigModal = (provider: (typeof availableProviders)[0], existingConn?: ConnectionItem) => {
    setConfigModalProvider(provider);
    setCredAccountName(existingConn?.account_name || `Personal ${provider.name}`);
    setIsConfigured(Boolean(existingConn && existingConn.status !== 'not_configured' && existingConn.status !== 'disconnected'));
    setTestResult(null);
    setGithubToken('');
    setSlackToken('');
    setSlackWebhook('');
    setEmailUser('');
    setEmailPass('');
    setEmailHost('smtp.gmail.com');
    setEmailPort('587');
    setHttpBaseUrl('');
    setHttpAuthType('none');
    setHttpToken('');
    setNotionToken('');
    setTelegramBotToken('');
    setTelegramDefaultChatId('');
    setTelegramAllowedChats('');

    if (existingConn?.auth_metadata) {
      const meta = existingConn.auth_metadata;
      // Populate non-secret configuration parameters
      if (provider.id === 'email') {
        if (meta.username) setEmailUser(meta.username);
        if (meta.smtp_host) setEmailHost(meta.smtp_host);
        if (meta.smtp_port) setEmailPort(String(meta.smtp_port));
      }
      if (provider.id === 'http') {
        if (meta.base_url) setHttpBaseUrl(meta.base_url);
        if (meta.auth_type) setHttpAuthType(meta.auth_type);
      }
      if (provider.id === 'telegram') {
        if (meta.default_chat_id) setTelegramDefaultChatId(String(meta.default_chat_id));
        if (meta.allowed_chat_ids) {
          setTelegramAllowedChats(Array.isArray(meta.allowed_chat_ids) ? meta.allowed_chat_ids.join(', ') : String(meta.allowed_chat_ids));
        }
      }
      // Sensitive fields (token, password, secret) remain blank to prevent leakage
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
    }
    if (providerId === 'email') {
      if (emailUser.trim()) meta.username = emailUser.trim();
      if (emailPass.trim()) meta.password = emailPass.trim();
      if (emailHost.trim()) meta.smtp_host = emailHost.trim();
      if (emailPort.trim()) meta.smtp_port = parseInt(emailPort.trim(), 10) || 587;
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

  const handleDisconnect = async (provider: string) => {
    try {
      const res = await fetch(apiUrl(`/api/connections/${provider}/disconnect`), {
        method: 'POST',
      });
      if (res.ok) {
        showToast(`Disconnected ${provider}.`, 'info');
        fetchAll();
      }
    } catch (e) {
      showToast('Failed to disconnect service.', 'error');
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

      // Open popup
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

      // Poll for popup closure
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

  return (
    <div style={{ padding: '28px', maxWidth: '1080px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, margin: '0 0 6px', color: 'hsl(var(--fg))' }}>
            Connections & Integrations
          </h1>
          <p style={{ margin: 0, fontSize: '14px', color: 'hsl(var(--muted-fg))' }}>
            Connect your external tools to allow Aether to take real operational actions with safety confirmation.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className="btn btn-ghost"
            onClick={fetchAll}
            disabled={loading}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div style={{ display: 'flex', gap: '6px', borderBottom: '1px solid hsl(var(--border))', marginBottom: '24px' }}>
        <button
          className={`btn btn-ghost ${activeTab === 'apps' ? 'active' : ''}`}
          onClick={() => setActiveTab('apps')}
          style={{ borderBottom: activeTab === 'apps' ? '2px solid hsl(var(--primary))' : 'none', borderRadius: 0, padding: '8px 16px', fontWeight: 600 }}
        >
          Connected Apps ({connections.filter(c => c.status === 'verified' || c.status === 'connected' || c.status === 'configured').length})
        </button>
        <button
          className={`btn btn-ghost ${activeTab === 'calendar' ? 'active' : ''}`}
          onClick={() => setActiveTab('calendar')}
          style={{ borderBottom: activeTab === 'calendar' ? '2px solid hsl(var(--primary))' : 'none', borderRadius: 0, padding: '8px 16px', fontWeight: 600 }}
        >
          Calendar Schedule ({calendarEvents.length})
        </button>
        <button
          className={`btn btn-ghost ${activeTab === 'actions' ? 'active' : ''}`}
          onClick={() => setActiveTab('actions')}
          style={{ borderBottom: activeTab === 'actions' ? '2px solid hsl(var(--primary))' : 'none', borderRadius: 0, padding: '8px 16px', fontWeight: 600 }}
        >
          Action Log ({executions.length})
        </button>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center' }}>
          <button
            className="btn btn-secondary"
            onClick={handleSyncAll}
            disabled={syncingAll}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '6px 12px' }}
            title="Sync all connected external tools into workspace memory and knowledge"
          >
            <RefreshCw size={12} className={syncingAll ? 'animate-spin' : ''} />
            {syncingAll ? 'Syncing...' : 'Sync All'}
          </button>
        </div>
      </div>

      {/* Tab 1: Apps Grid */}
      {activeTab === 'apps' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
          {availableProviders.map(p => {
            const conn = connections.find(c => c.provider === p.id);
            const status = conn?.status;
            const isVerified = status === 'verified' || status === 'connected';
            const isConfiguredStatus = status === 'configured';
            const isVerificationFailed = status === 'verification_failed' || status === 'error';
            const isVerificationRequired = status === 'verification_required' || status === 'needs_auth';
            const isDisconnected = status === 'disconnected';
            const Icon = p.icon;

            return (
              <div
                key={p.id}
                className="card"
                style={{
                  padding: '20px',
                  borderRadius: '12px',
                  border: isVerified
                    ? '1px solid hsl(var(--primary)/0.4)'
                    : isConfiguredStatus
                    ? '1px solid #38bdf840'
                    : isVerificationFailed
                    ? '1px solid #ef444440'
                    : '1px solid hsl(var(--border))',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '16px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{
                        width: '38px',
                        height: '38px',
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
                        <div style={{ fontWeight: 600, fontSize: '15px' }}>{p.name}</div>
                        <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                          {conn ? conn.account_name : (p.builtIn ? 'Local Workspace Engine' : 'Not configured')}
                        </div>
                      </div>
                    </div>
                    {p.id === 'google_calendar' && (googleAuthPending || verifyingProvider === 'google_calendar') ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#f59e0b', fontWeight: 600 }}>
                        <RefreshCw size={14} className="animate-spin" /> Verifica in corso
                      </span>
                    ) : p.id === 'google_calendar' && isVerificationFailed ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#ef4444', fontWeight: 600 }}>
                        <AlertCircle size={14} /> Authorization Failed
                      </span>
                    ) : isVerified ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#10b981', fontWeight: 600 }}>
                        <CheckCircle2 size={14} /> {p.id === 'google_calendar' ? 'Connected & Verified' : 'Verified'}
                      </span>
                    ) : isConfiguredStatus ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#38bdf8', fontWeight: 600 }}>
                        <ShieldCheck size={14} /> Configured
                      </span>
                    ) : isVerificationFailed ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#ef4444', fontWeight: 600 }}>
                        <AlertCircle size={14} /> Verification Failed
                      </span>
                    ) : isVerificationRequired ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#f59e0b', fontWeight: 600 }}>
                        <AlertCircle size={14} /> Needs Auth
                      </span>
                    ) : isDisconnected ? (
                      <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                        Disconnected
                      </span>
                    ) : (
                      <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                        {p.builtIn ? 'Ready (Local)' : 'Not configured'}
                      </span>
                    )}
                  </div>
                  <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', margin: 0, lineHeight: 1.4 }}>
                    {p.description}
                  </p>
                  {p.id === 'google_calendar' && conn && isVerified && (
                    <div style={{ fontSize: '11px', color: '#4285F4', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '6px', fontWeight: 500 }}>
                      <Calendar size={11} /> Calendar: {conn.auth_metadata?.selected_calendar_summary || conn.auth_metadata?.selected_calendar_id || 'Primary'}
                    </div>
                  )}
                  {conn?.last_verified_at && (
                    <div style={{ fontSize: '11px', color: '#10b981', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '6px' }}>
                      <CheckCircle2 size={11} /> Verified: {new Date(conn.last_verified_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}
                      {conn.verification_method ? ` (${conn.verification_method})` : ''}
                    </div>
                  )}
                  {conn?.last_successful_operation && (
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '3px' }}>
                      <Zap size={11} /> Last Op: {conn.last_successful_operation}
                    </div>
                  )}
                  {isVerificationFailed && conn?.last_verification_error && (
                    <div style={{ fontSize: '11px', color: '#ef4444', marginTop: '5px', lineHeight: 1.3 }}>
                      {conn.last_verification_error}
                    </div>
                  )}
                  {isConfiguredStatus && (
                    <div style={{ fontSize: '11px', color: '#38bdf8', marginTop: '5px' }}>
                      Credentials saved. Live probe pending.
                    </div>
                  )}
                  {conn?.last_synced_at && (
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '4px' }}>
                      <Clock size={11} /> Last synced: {new Date(conn.last_synced_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', flexWrap: 'wrap', gap: '8px', borderTop: '1px solid hsl(var(--border)/0.5)', paddingTop: '14px' }}>
                  {p.id === 'calendar' ? (
                    <>
                      {isVerified ? (
                        <>
                          <button
                            className="btn btn-secondary"
                            onClick={() => {
                              setSelectedScheduleSource('local');
                              setActiveTab('calendar');
                            }}
                            style={{ fontSize: '12px', padding: '6px 12px' }}
                          >
                            View Schedule
                          </button>
                          <button
                            className="btn btn-ghost"
                            onClick={() => handleDisconnect(p.id)}
                            style={{ fontSize: '12px', padding: '6px 12px', color: 'hsl(var(--destructive))' }}
                          >
                            Disconnect
                          </button>
                        </>
                      ) : (
                        <button
                          className="btn btn-primary"
                          onClick={handleConnectCalendar}
                          style={{ fontSize: '12px', padding: '6px 14px' }}
                        >
                          Initialize Calendar
                        </button>
                      )}
                    </>
                  ) : p.id === 'google_calendar' ? (
                    <>
                      {isVerified ? (
                        <>
                          <button
                            className="btn btn-secondary"
                            onClick={() => {
                              setSelectedScheduleSource('google');
                              setActiveTab('calendar');
                            }}
                            style={{ fontSize: '12px', padding: '6px 12px' }}
                          >
                            View Schedule
                          </button>
                          <button
                            className="btn btn-secondary"
                            onClick={() => handleSync(p.id)}
                            disabled={syncingProvider === p.id}
                            style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                            title="Sync external entities into persistent memory and knowledge"
                          >
                            <RefreshCw size={12} className={syncingProvider === p.id ? 'animate-spin' : ''} />
                            {syncingProvider === p.id ? 'Syncing...' : 'Sync Now'}
                          </button>
                          <button
                            className="btn btn-secondary"
                            onClick={handleOpenCalendarPicker}
                            style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                          >
                            <Settings size={12} /> Select Calendar
                          </button>
                          <button
                            className="btn btn-ghost"
                            onClick={() => handleDisconnect(p.id)}
                            style={{ fontSize: '12px', padding: '6px 12px', color: 'hsl(var(--destructive))' }}
                          >
                            Disconnect / Revoke
                          </button>
                        </>
                      ) : (googleAuthPending || verifyingProvider === 'google_calendar') ? (
                        <button
                          className="btn btn-secondary"
                          disabled
                          style={{ fontSize: '12px', padding: '6px 14px', display: 'flex', alignItems: 'center', gap: '4px' }}
                        >
                          <RefreshCw size={12} className="animate-spin" /> Verifica in corso...
                        </button>
                      ) : isVerificationFailed ? (
                        <button
                          className="btn btn-primary"
                          onClick={() => {
                            if (conn?.auth_metadata?.client_id) setGoogleClientId(conn.auth_metadata.client_id);
                            setIsGoogleModalOpen(true);
                          }}
                          style={{ fontSize: '12px', padding: '6px 14px' }}
                        >
                          Retry Authorization
                        </button>
                      ) : (
                        <button
                          className="btn btn-primary"
                          onClick={() => {
                            if (conn?.auth_metadata?.client_id) setGoogleClientId(conn.auth_metadata.client_id);
                            setIsGoogleModalOpen(true);
                          }}
                          style={{ fontSize: '12px', padding: '6px 14px' }}
                        >
                          Connect Google Calendar
                        </button>
                      )}
                    </>
                  ) : (
                    <>
                      {isVerified && (
                        <button
                          className="btn btn-secondary"
                          onClick={() => handleSync(p.id)}
                          disabled={syncingProvider === p.id}
                          style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                          title="Sync external entities into persistent memory and knowledge"
                        >
                          <RefreshCw size={12} className={syncingProvider === p.id ? 'animate-spin' : ''} />
                          {syncingProvider === p.id ? 'Syncing...' : 'Sync Now'}
                        </button>
                      )}
                      {(isConfiguredStatus || isVerificationFailed || isVerified) && (
                        <button
                          className={`btn ${isConfiguredStatus || isVerificationFailed ? 'btn-primary' : 'btn-secondary'}`}
                          onClick={() => handleVerifyConnection(p.id)}
                          disabled={verifyingProvider === p.id}
                          style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                          title="Perform live credentials test"
                        >
                          <ShieldCheck size={12} className={verifyingProvider === p.id ? 'animate-spin' : ''} />
                          {verifyingProvider === p.id ? 'Verifying...' : isVerificationFailed ? 'Retry Verify' : 'Verify'}
                        </button>
                      )}
                      {conn && !isDisconnected ? (
                        <>
                          <button
                            className="btn btn-secondary"
                            onClick={() => openConfigModal(p, conn)}
                            style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                          >
                            <Settings size={12} /> Configure
                          </button>
                          <button
                            className="btn btn-ghost"
                            onClick={() => handleDisconnect(p.id)}
                            style={{ fontSize: '12px', padding: '6px 12px', color: 'hsl(var(--destructive))' }}
                          >
                            Disconnect
                          </button>
                        </>
                      ) : (
                        <button
                          className="btn btn-primary"
                          onClick={() => openConfigModal(p, conn)}
                          style={{ fontSize: '12px', padding: '6px 14px' }}
                        >
                          Configure & Connect
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Tab 2: Calendar Schedule */}
      {activeTab === 'calendar' && (
        <div>
          {/* Calendar Source Switcher */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
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

      {/* Tab 3: Action Executions Log */}
      {activeTab === 'actions' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {executions.length === 0 ? (
            <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
              <Zap size={32} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>No action executions recorded yet</div>
              <div style={{ fontSize: '13px' }}>Actions executed by Aether or requiring approval will be audited here.</div>
            </div>
          ) : (
            executions.map(exec => {
              const summary = getActionSummary(exec);
              const detail = getActionDetail(exec);
              return (
                <div
                  key={exec.id}
                  className="card"
                  style={{
                    padding: '16px 20px',
                    borderRadius: '10px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
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
                        backgroundColor: exec.status === 'success' ? '#10b98115' : exec.status === 'pending_approval' ? '#f59e0b15' : '#ef444415',
                        color: exec.status === 'success' ? '#10b981' : exec.status === 'pending_approval' ? '#f59e0b' : '#ef4444',
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

                  {exec.status === 'success' && exec.output_data && (
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
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Create Event Modal */}
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

      {/* Credential Configuration Modal */}
      {configModalProvider && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div className="card" style={{ width: '480px', maxHeight: '90vh', overflowY: 'auto', padding: '24px', borderRadius: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
              <div style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                backgroundColor: `${configModalProvider.color}15`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: configModalProvider.color,
              }}>
                <configModalProvider.icon size={20} />
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>Configure {configModalProvider.name}</h3>
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                  {isConfigured ? 'Update credentials (leave secrets blank to keep existing)' : 'Provide authentic credentials to enable real agentic actions'}
                </div>
              </div>
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
                    Internal integration token with read/write database permissions.
                  </div>
                </div>
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

      {/* Google Calendar OAuth Flow Modal */}
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
          <div className="card" style={{ width: '500px', maxHeight: '90vh', overflowY: 'auto', padding: '24px', borderRadius: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <div style={{
                width: '40px',
                height: '40px',
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
                  Real OAuth 2.0 Authorization with PKCE & Live Verification
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
                  {googleAuthPending ? 'Verifica in corso...' : 'Authorize with Google'}
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

      {/* Google Calendar Selector Modal */}
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
