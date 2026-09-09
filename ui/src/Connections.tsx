import { useState, useEffect, useContext } from 'react';
import {
  Calendar, Mail, GitBranch, MessageSquare, FileText, CheckCircle2,
  Plus, RefreshCw, Clock, Zap
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

  const showToast = useContext(ToastContext);

  const availableProviders = [
    {
      id: 'calendar',
      name: 'Google Calendar / Sync',
      icon: Calendar,
      description: 'Sync schedule, check availability, and book appointments with approval.',
      color: '#4285F4',
      builtIn: true,
    },
    {
      id: 'github',
      name: 'GitHub',
      icon: GitBranch,
      description: 'Access repositories, codebases, commits, and pull requests.',
      color: '#2dba4e',
      builtIn: false,
    },
    {
      id: 'email',
      name: 'Email / Gmail',
      icon: Mail,
      description: 'Read incoming briefs, prepare summaries, and draft outbound messages.',
      color: '#EA4335',
      builtIn: false,
    },
    {
      id: 'slack',
      name: 'Slack',
      icon: MessageSquare,
      description: 'Receive notifications and post status reports in team channels.',
      color: '#4A154B',
      builtIn: false,
    },
    {
      id: 'notion',
      name: 'Notion',
      icon: FileText,
      description: 'Read and sync project documentation and database tables.',
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

  const handleConnect = async (provider: string) => {
    try {
      const res = await fetch(apiUrl('/api/connections'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          account_name: `Default ${provider.toUpperCase()}`,
        }),
      });
      if (res.ok) {
        showToast(`Connected ${provider} successfully.`, 'success');
        fetchAll();
      }
    } catch (e) {
      showToast('Failed to connect service.', 'error');
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
                          {conn ? conn.account_name : 'Not connected'}
                        </div>
                      </div>
                    </div>
                    {isConnected ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#10b981', fontWeight: 600 }}>
                        <CheckCircle2 size={14} /> Connected
                      </span>
                    ) : (
                      <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                        Ready
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
                      {p.id === 'calendar' && (
                        <button
                          className="btn btn-secondary"
                          onClick={() => setActiveTab('calendar')}
                          style={{ fontSize: '12px', padding: '6px 12px' }}
                        >
                          View Schedule
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
                      onClick={() => handleConnect(p.id)}
                      style={{ fontSize: '12px', padding: '6px 14px' }}
                    >
                      Connect
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
            executions.map(exec => (
              <div
                key={exec.id}
                className="card"
                style={{
                  padding: '14px 18px',
                  borderRadius: '10px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 600, fontSize: '14px' }}>{exec.action_id}</span>
                    <span style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: '10px',
                      backgroundColor: exec.status === 'success' ? '#10b98115' : exec.status === 'pending_approval' ? '#f59e0b15' : '#ef444415',
                      color: exec.status === 'success' ? '#10b981' : exec.status === 'pending_approval' ? '#f59e0b' : '#ef4444',
                    }}>
                      {exec.status.toUpperCase()}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                    ID: {exec.id} • {exec.created_at ? new Date(exec.created_at).toLocaleString() : ''}
                  </div>
                </div>
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', maxWidth: '300px', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {JSON.stringify(exec.input_data)}
                </div>
              </div>
            ))
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
    </div>
  );
}
