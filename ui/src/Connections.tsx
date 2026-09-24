import { useState, useEffect, useContext } from 'react';
import {
  Calendar, Mail, GitBranch, MessageSquare, FileText, CheckCircle2,
  AlertCircle, ShieldCheck, Settings, Plus, RefreshCw, Clock, Zap, Globe
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
  const [testingCreds, setTestingCreds] = useState(false);
  const [savingCreds, setSavingCreds] = useState(false);
  const [testResult, setTestResult] = useState<{ valid: boolean; message: string } | null>(null);

  const showToast = useContext(ToastContext);

  const availableProviders = [
    {
      id: 'calendar',
      name: 'Google Calendar / Sync',
      icon: Calendar,
      description: 'Sync schedule, check availability, and book appointments with approval.',
      capabilitiesText: 'Can view availability, list events, and schedule meetings with confirmation',
      color: '#4285F4',
      builtIn: true,
    },
    {
      id: 'github',
      name: 'GitHub',
      icon: GitBranch,
      description: 'Access repositories, codebases, commits, and pull requests.',
      capabilitiesText: 'Can read repositories, create issues, and open pull requests',
      color: '#2dba4e',
      builtIn: false,
    },
    {
      id: 'email',
      name: 'Email / Gmail',
      icon: Mail,
      description: 'Read incoming briefs, prepare summaries, and draft outbound messages.',
      capabilitiesText: 'Can draft and dispatch emails via SMTP with explicit user approval',
      color: '#EA4335',
      builtIn: false,
    },
    {
      id: 'slack',
      name: 'Slack',
      icon: MessageSquare,
      description: 'Receive notifications and post status reports in team channels.',
      capabilitiesText: 'Can post messages and status updates to Slack channels with confirmation',
      color: '#4A154B',
      builtIn: false,
    },
    {
      id: 'http',
      name: 'Generic HTTP / API',
      icon: Globe,
      description: 'Interact with external REST endpoints and Web APIs with security policies.',
      capabilitiesText: 'Can perform authenticated HTTP operations (GET, POST, PUT, DELETE)',
      color: '#6366f1',
      builtIn: false,
    },
    {
      id: 'notion',
      name: 'Notion',
      icon: FileText,
      description: 'Read and sync project documentation and database tables.',
      capabilitiesText: 'Can read and synchronize workspace pages and databases',
      color: '#000000',
      builtIn: false,
    },
  ];

  const fetchAll = () => {
    setLoading(true);
    Promise.all([
      fetch(apiUrl('/api/connections')).then(r => r.json()),
      fetch(apiUrl('/api/connections/calendar/events')).then(r => r.json()),
      fetch(apiUrl('/api/actions/executions')).then(r => r.json()),
    ])
      .then(([conns, evts, execs]) => {
        if (Array.isArray(conns)) setConnections(conns);
        if (Array.isArray(evts)) setCalendarEvents(evts);
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
    setIsConfigured(Boolean(existingConn && existingConn.status === 'connected'));
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
      // Sensitive fields (token, password, secret) remain blank to prevent leakage
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
        }),
      });
      const data = await res.json();
      setTestResult({
        valid: Boolean(data.valid),
        message: data.message || (data.valid ? 'Credentials format verified.' : 'Verification failed.'),
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
      const verifyRes = await fetch(apiUrl(`/api/connections/${configModalProvider.id}/verify`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auth_metadata: authMeta }),
      });
      const verifyData = await verifyRes.json();
      if (!verifyData.valid) {
        setTestResult({
          valid: false,
          message: verifyData.message || 'Invalid credentials format. Please review requirements.',
        });
        setSavingCreds(false);
        return;
      }

      const res = await fetch(apiUrl('/api/connections'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: configModalProvider.id,
          account_name: credAccountName.trim() || `Personal ${configModalProvider.name}`,
          auth_metadata: authMeta,
        }),
      });
      if (res.ok) {
        showToast(`Connected ${configModalProvider.name} successfully.`, 'success');
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
          account_name: 'Primary Calendar (Sync)',
          auth_metadata: { type: 'sqlite_built_in' },
        }),
      });
      if (res.ok) {
        showToast('Connected Calendar successfully.', 'success');
        fetchAll();
      }
    } catch (e) {
      showToast('Failed to connect Calendar.', 'error');
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

  const handleCreateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setCreatingEvent(true);
    try {
      const res = await fetch(apiUrl('/api/connections/calendar/events'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newTitle.trim(),
          start_time: newStartTime || new Date().toISOString(),
          location: newLocation.trim(),
        }),
      });
      if (res.ok) {
        showToast('Calendar event created.', 'success');
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
          Connected Apps ({connections.filter(c => c.status === 'connected').length})
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
      </div>

      {/* Tab 1: Apps Grid */}
      {activeTab === 'apps' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
          {availableProviders.map(p => {
            const conn = connections.find(c => c.provider === p.id);
            const isConnected = conn?.status === 'connected';
            const hasAuth = p.builtIn || (conn?.auth_metadata && Object.keys(conn.auth_metadata).length > 0);
            const Icon = p.icon;

            return (
              <div
                key={p.id}
                className="card"
                style={{
                  padding: '20px',
                  borderRadius: '12px',
                  border: isConnected ? '1px solid hsl(var(--primary)/0.4)' : '1px solid hsl(var(--border))',
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
                          {conn ? conn.account_name : (p.builtIn ? 'Local Engine' : 'Not configured')}
                        </div>
                      </div>
                    </div>
                    {isConnected ? (
                      hasAuth ? (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#10b981', fontWeight: 600 }}>
                          <CheckCircle2 size={14} /> Connected
                        </span>
                      ) : (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#f59e0b', fontWeight: 600 }}>
                          Needs Auth
                        </span>
                      )
                    ) : (
                      <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                        {p.builtIn ? 'Ready' : 'Not configured'}
                      </span>
                    )}
                  </div>
                  <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', margin: 0, lineHeight: 1.4 }}>
                    {p.description}
                  </p>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', borderTop: '1px solid hsl(var(--border)/0.5)', paddingTop: '14px' }}>
                  {isConnected ? (
                    <>
                      {p.id === 'calendar' ? (
                        <button
                          className="btn btn-secondary"
                          onClick={() => setActiveTab('calendar')}
                          style={{ fontSize: '12px', padding: '6px 12px' }}
                        >
                          View Schedule
                        </button>
                      ) : (
                        <button
                          className="btn btn-secondary"
                          onClick={() => openConfigModal(p, conn)}
                          style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                        >
                          <Settings size={12} /> Configure
                        </button>
                      )}
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
                      onClick={() => {
                        if (p.builtIn) {
                          handleConnectCalendar();
                        } else {
                          openConfigModal(p);
                        }
                      }}
                      style={{ fontSize: '12px', padding: '6px 14px' }}
                    >
                      {p.builtIn ? 'Connect' : 'Configure & Connect'}
                    </button>
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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div style={{ fontSize: '14px', color: 'hsl(var(--muted-fg))' }}>
              Real scheduled events managed via Aether Calendar connection:
            </div>
            <button
              className="btn btn-primary"
              onClick={() => setIsEventModalOpen(true)}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
            >
              <Plus size={14} /> New Event
            </button>
          </div>

          {calendarEvents.length === 0 ? (
            <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
              <Calendar size={32} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>No calendar events found</div>
              <div style={{ fontSize: '13px' }}>Ask Personal Aether to schedule an appointment or click "New Event".</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {calendarEvents.map(evt => (
                <div
                  key={evt.id}
                  className="card"
                  style={{
                    padding: '16px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    borderRadius: '10px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                    <div style={{
                      width: '42px',
                      height: '42px',
                      borderRadius: '8px',
                      backgroundColor: 'hsl(var(--primary)/0.1)',
                      color: 'hsl(var(--primary))',
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
                  <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 600, backgroundColor: '#10b98115', padding: '3px 10px', borderRadius: '12px' }}>
                    Confirmed
                  </span>
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
                    required
                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx or github_pat_..."
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
                      placeholder="xoxb-xxxxxxxxxxxx-xxxxxxxxxxxx"
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
                      placeholder="https://hooks.slack.com/services/..."
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
                      required
                      placeholder="Application specific password"
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
                        placeholder="Secret token, key, or credentials"
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
                    required
                    placeholder="secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
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
    </div>
  );
}
