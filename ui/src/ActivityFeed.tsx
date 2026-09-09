import { useState, useEffect } from 'react';
import {
  ChevronDown, ChevronRight, Sparkles, Check, AlertTriangle, Pause,
  Activity as ActivityIcon, RefreshCw, Clock, Target, Zap, Users, Link2
} from 'lucide-react';
import { useTranslation, type TranslationKey } from './i18n';
import { apiUrl } from './api';

export interface ActivityItem {
  id: string;
  agent: string;
  type: string;
  message: string;
  timestamp: string;
  duration_s?: number;
  metadata?: any;
}

interface ActivityFeedProps {
  activities?: ActivityItem[];
  isLive?: boolean;
  taskStatus?: string;
  navigate?: (view: string, params?: any) => void;
}

interface StoredActivityEvent {
  id: string;
  workspace_id: string;
  title: string;
  description: string;
  category: string;
  status: string;
  link_view?: string;
  link_id?: string;
  created_at: string;
  metadata?: any;
}

export function ActivityFeed({ activities, isLive = false, taskStatus = 'completed' }: ActivityFeedProps) {
  const [showTechnicalLogs, setShowTechnicalLogs] = useState(false);
  const [events, setEvents] = useState<StoredActivityEvent[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [loading, setLoading] = useState(false);
  const { t } = useTranslation();

  // If used as standalone view (activities not provided)
  const isStandalone = !activities;

  const fetchEvents = () => {
    setLoading(true);
    const catQuery = selectedCategory !== 'all' ? `&category=${selectedCategory}` : '';
    fetch(apiUrl(`/api/activity?limit=50${catQuery}`))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setEvents(data);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (isStandalone) {
      fetchEvents();
    }
  }, [isStandalone, selectedCategory]);

  if (isStandalone) {
    return (
      <div style={{ padding: '28px', maxWidth: '960px', margin: '0 auto' }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <div>
            <h1 style={{ fontSize: '24px', fontWeight: 700, margin: '0 0 6px', color: 'hsl(var(--fg))' }}>
              Activity Feed
            </h1>
            <p style={{ margin: 0, fontSize: '14px', color: 'hsl(var(--muted-fg))' }}>
              Chronological, human-readable timeline of all operations, actions, and decisions.
            </p>
          </div>
          <button
            className="btn btn-ghost"
            onClick={fetchEvents}
            disabled={loading}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>

        {/* Category Filters */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
          {['all', 'work', 'action', 'workforce', 'connection'].map(cat => (
            <button
              key={cat}
              className={`btn btn-ghost ${selectedCategory === cat ? 'active' : ''}`}
              onClick={() => setSelectedCategory(cat)}
              style={{
                fontSize: '13px',
                padding: '6px 14px',
                borderRadius: '20px',
                backgroundColor: selectedCategory === cat ? 'hsl(var(--primary)/0.15)' : 'hsl(var(--muted)/0.4)',
                color: selectedCategory === cat ? 'hsl(var(--primary))' : 'hsl(var(--fg))',
                fontWeight: selectedCategory === cat ? 600 : 400,
                textTransform: 'capitalize',
              }}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Timeline Events */}
        {events.length === 0 ? (
          <div className="card" style={{ padding: '48px 24px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
            <ActivityIcon size={36} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
            <div style={{ fontWeight: 600, fontSize: '16px', marginBottom: '4px' }}>No activity records found</div>
            <div style={{ fontSize: '13px' }}>Operations and requests will be logged here in plain language.</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {events.map(evt => {
              const getIcon = () => {
                switch (evt.category) {
                  case 'work': return <Target size={16} color="hsl(var(--primary))" />;
                  case 'action': return <Zap size={16} color="#f59e0b" />;
                  case 'workforce': return <Users size={16} color="#8b5cf6" />;
                  case 'connection': return <Link2 size={16} color="#10b981" />;
                  default: return <Sparkles size={16} color="hsl(var(--primary))" />;
                }
              };

              return (
                <div
                  key={evt.id}
                  className="card"
                  style={{
                    padding: '16px 20px',
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: '16px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
                    <div style={{
                      width: '36px',
                      height: '36px',
                      borderRadius: '10px',
                      backgroundColor: 'hsl(var(--muted)/0.6)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      marginTop: '2px',
                    }}>
                      {getIcon()}
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '15px', color: 'hsl(var(--fg))' }}>
                        {evt.title}
                      </div>
                      <div style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', marginTop: '3px', lineHeight: 1.4 }}>
                        {evt.description}
                      </div>
                      <div style={{ fontSize: '11.5px', color: 'hsl(var(--muted-fg))', marginTop: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Clock size={12} /> {new Date(evt.created_at).toLocaleString()}
                        <span style={{ opacity: 0.5 }}>•</span>
                        <span style={{ textTransform: 'capitalize' }}>{evt.category}</span>
                      </div>
                    </div>
                  </div>

                  <span style={{
                    fontSize: '11.5px',
                    fontWeight: 600,
                    padding: '3px 10px',
                    borderRadius: '12px',
                    backgroundColor: evt.status === 'completed' ? '#10b98115' : evt.status === 'pending_approval' ? '#f59e0b15' : '#ef444415',
                    color: evt.status === 'completed' ? '#10b981' : evt.status === 'pending_approval' ? '#f59e0b' : '#ef4444',
                    textTransform: 'capitalize',
                    whiteSpace: 'nowrap',
                  }}>
                    {evt.status.replace('_', ' ')}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  // Embedded Mode (in Chat)
  if (!activities || activities.length === 0) return null;

  const isInterrupted = taskStatus === 'interrupted' || activities.some(a => (a.type || '').toLowerCase().includes('interrupt'));
  const workforce = aggregateWorkforceState(activities, isLive, isInterrupted, t);

  return (
    <div
      style={{
        margin: '16px 0',
        borderRadius: '12px',
        border: '1px solid hsl(var(--border))',
        backgroundColor: 'hsl(var(--card))',
        boxShadow: '0 4px 16px -4px rgba(0,0,0,0.08)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '10px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid hsl(var(--border)/0.6)',
          backgroundColor: 'hsl(var(--muted)/0.4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Sparkles size={15} className="text-primary" />
          <span style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
            Aether Workforce
          </span>
          {isLive ? (
            <span
              className="badge badge-primary"
              style={{ fontSize: '10.5px', display: 'inline-flex', alignItems: 'center', gap: '5px' }}
            >
              <span className="status-dot active" style={{ width: '5px', height: '5px' }} />
              {t('statusRunning')}
            </span>
          ) : isInterrupted ? (
            <span
              className="badge badge-warning"
              style={{ fontSize: '10.5px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
            >
              <Pause size={10} />
              {t('statusInterrupted')}
            </span>
          ) : (
            <span
              className="badge badge-success"
              style={{ fontSize: '10.5px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
            >
              <Check size={10} strokeWidth={3} />
              {t('statusCompleted')}
            </span>
          )}
        </div>

        <button
          className="btn btn-ghost"
          style={{ padding: '3px 8px', fontSize: '11px', gap: '4px' }}
          onClick={() => setShowTechnicalLogs(!showTechnicalLogs)}
        >
          <span>{activities.length} {activities.length === 1 ? t('stepSingular') : t('stepPlural')}</span>
          {showTechnicalLogs ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </button>
      </div>

      {/* Workforce Timeline (Grouped & Humanized) */}
      <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {workforce.map(member => (
          <div
            key={member.rawName}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '12px',
              padding: '6px 8px',
              borderRadius: '8px',
              backgroundColor: member.isActive ? 'hsl(var(--primary)/0.06)' : 'transparent',
            }}
          >
            <div style={{ marginTop: '2px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {member.isActive ? (
                <span className="status-dot active" style={{ width: '8px', height: '8px' }} />
              ) : member.hasError ? (
                <AlertTriangle size={14} className="text-warning" />
              ) : (
                <Check size={14} className="text-success" />
              )}
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '12.5px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
                  {member.name}
                </span>
                {member.role && (
                  <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', opacity: 0.8 }}>
                    • {member.role}
                  </span>
                )}
              </div>
              <div style={{ fontSize: '12px', color: member.isActive ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                {member.currentAction}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Expandable Technical Log Drawer */}
      {showTechnicalLogs && (
        <div
          style={{
            borderTop: '1px solid hsl(var(--border)/0.5)',
            backgroundColor: 'hsl(var(--muted)/0.25)',
            padding: '10px 16px',
            maxHeight: '220px',
            overflowY: 'auto',
          }}
        >
          <div style={{ fontSize: '10.5px', fontWeight: 600, textTransform: 'uppercase', color: 'hsl(var(--muted-fg))', marginBottom: '6px', letterSpacing: '0.05em' }}>
            Technical Activity Log
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontFamily: 'monospace', fontSize: '11px' }}>
            {activities.map(act => (
              <div key={act.id} style={{ display: 'flex', gap: '8px', color: 'hsl(var(--muted-fg))' }}>
                <span style={{ opacity: 0.6, flexShrink: 0 }}>
                  {act.timestamp ? new Date(act.timestamp).toLocaleTimeString() : ''}
                </span>
                <span style={{ fontWeight: 600, color: 'hsl(var(--fg))', flexShrink: 0 }}>
                  [{act.agent || 'System'}]:
                </span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {formatTechnicalEvent(act)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function aggregateWorkforceState(
  activities: ActivityItem[],
  isLive: boolean,
  _isInterrupted: boolean,
  t: (key: TranslationKey) => string
) {
  const map = new Map<string, {
    rawName: string;
    name: string;
    role?: string;
    currentAction: string;
    isActive: boolean;
    hasError: boolean;
    lastSeen: number;
  }>();

  for (let i = 0; i < activities.length; i++) {
    const act = activities[i];
    const rawAgent = act.agent || 'Orchestrator';
    const isLastActionOfAgent = !activities.slice(i + 1).some(a => (a.agent || 'Orchestrator') === rawAgent);
    const timeNum = act.timestamp ? new Date(act.timestamp).getTime() : 0;

    const actionText = humanizeActivity(act, isLive && isLastActionOfAgent, t);
    const hasErr = (act.type || '').includes('error') || (act.type || '').includes('fail');

    map.set(rawAgent, {
      rawName: rawAgent,
      name: formatAgentName(rawAgent),
      role: act.metadata?.role || (rawAgent === 'Architect' ? 'Coordinator' : undefined),
      currentAction: actionText,
      isActive: isLive && isLastActionOfAgent,
      hasError: hasErr,
      lastSeen: timeNum,
    });
  }

  return Array.from(map.values());
}

function humanizeActivity(act: ActivityItem, isActive: boolean, t: (key: TranslationKey) => string): string {
  const event = act.type || '';
  const meta = act.metadata || {};

  if (event === 'thinking') {
    return isActive ? 'Analyzing task & planning steps...' : 'Completed plan';
  }

  if (event === 'tool_started' || event === 'tool_call') {
    const tool = meta.tool_name || '';
    if (tool === 'search_knowledge') {
      return isActive ? 'Consulting memory & knowledge...' : t('actionFoundDocs');
    }
    if (tool === 'search_web') {
      return isActive ? 'Searching external sources...' : t('actionWebSearched');
    }
    if (tool === 'write_file') {
      const p = meta.arguments?.path || meta.path || '';
      return isActive ? (p ? `${t('actionWritingFile')}: ${p}` : t('actionWritingFile')) : `${t('actionExecuted')} write_file`;
    }
    if (tool === 'patch_file') {
      const p = meta.arguments?.path || meta.path || '';
      return isActive ? (p ? `${t('actionPatchingFile')}: ${p}` : t('actionPatchingFile')) : `${t('actionExecuted')} patch_file`;
    }
    if (tool === 'delete_file') {
      const p = meta.arguments?.path || meta.path || '';
      return isActive ? (p ? `${t('actionDeletingFile')}: ${p}` : t('actionDeletingFile')) : `${t('actionExecuted')} delete_file`;
    }
    if (tool === 'list_directory') {
      const p = meta.arguments?.path || meta.path || '';
      return isActive ? (p ? `${t('actionExploringDir')}: ${p}` : t('actionExploringDir')) : `${t('actionExecuted')} list_directory`;
    }
    return isActive ? `${t('actionProcessing')} ${tool}...` : `${t('actionExecuted')} ${tool}`;
  }

  if (event === 'tool_completed') {
    const tool = meta.tool_name || '';
    if (tool === 'search_knowledge') {
      return t('actionFoundDocs');
    }
    if (tool === 'search_web') {
      return t('actionWebSearched');
    }
    return `${t('actionExecuted')} (${tool})`;
  }

  if (event === 'interrupt') {
    return t('actionWaitingApproval');
  }

  return isActive ? t('running') : t('actionCompleted');
}

function formatAgentName(raw: string): string {
  if (!raw) return 'Workforce';
  return raw
    .split(/[-_]/)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

function formatTechnicalEvent(act: ActivityItem): string {
  const event = act.type || 'activity';
  const meta = act.metadata ? JSON.stringify(act.metadata).slice(0, 70) : '';
  return `${event} ${meta}`;
}
