import { useState } from 'react';
import { ChevronDown, ChevronRight, Sparkles, Check, AlertTriangle, Pause } from 'lucide-react';
import { useTranslation, type TranslationKey } from './i18n';

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
  activities: ActivityItem[];
  isLive?: boolean;
  taskStatus?: string;
}

export function ActivityFeed({ activities, isLive = false, taskStatus = 'completed' }: ActivityFeedProps) {
  const [showTechnicalLogs, setShowTechnicalLogs] = useState(false);
  const { t } = useTranslation();

  if (!activities || activities.length === 0) return null;

  const isInterrupted = taskStatus === 'interrupted' || activities.some(a => (a.type || '').toLowerCase().includes('interrupt'));

  // Aggregate activities by agent to show clean, humanized workforce timeline
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
              borderRadius: '6px',
              backgroundColor: member.status === 'active' ? 'hsl(var(--primary)/0.06)' : (member.status === 'interrupted' ? 'hsl(var(--warning-bg)/0.5)' : 'transparent'),
              transition: 'background-color 0.2s ease',
            }}
          >
            {/* Status Icon */}
            <div style={{ marginTop: '2px', flexShrink: 0 }}>
              {member.status === 'active' ? (
                <div
                  style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    backgroundColor: 'hsl(var(--primary)/0.18)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <span
                    className="status-dot active"
                    style={{ width: '8px', height: '8px', backgroundColor: 'hsl(var(--primary))' }}
                  />
                </div>
              ) : member.status === 'completed' ? (
                <div
                  style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    backgroundColor: 'hsl(var(--success-bg))',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'hsl(var(--success))',
                  }}
                >
                  <Check size={12} strokeWidth={3} />
                </div>
              ) : member.status === 'interrupted' ? (
                <div
                  style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    backgroundColor: 'hsl(var(--warning-bg))',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'hsl(var(--warning))',
                  }}
                >
                  <Pause size={11} />
                </div>
              ) : member.status === 'failed' ? (
                <div
                  style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    backgroundColor: 'hsl(var(--destructive)/0.15)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'hsl(var(--destructive))',
                  }}
                >
                  <AlertTriangle size={12} />
                </div>
              ) : (
                <div
                  style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    border: '1.5px solid hsl(var(--border))',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                />
              )}
            </div>

            {/* Agent Details */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
                  {member.displayName}
                </span>
                {member.role && (
                  <span className="badge" style={{ fontSize: '10px', padding: '1px 6px' }}>
                    {member.role}
                  </span>
                )}
              </div>
              <div
                style={{
                  fontSize: '12px',
                  color: member.status === 'active' ? 'hsl(var(--primary))' : (member.status === 'interrupted' ? 'hsl(var(--warning))' : 'hsl(var(--muted-fg))'),
                  marginTop: '2px',
                  fontWeight: member.status === 'active' ? 500 : 400,
                  lineHeight: 1.4,
                }}
              >
                {member.currentAction}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Optional Technical Details Drawer */}
      {showTechnicalLogs && (
        <div
          style={{
            borderTop: '1px solid hsl(var(--border)/0.6)',
            padding: '12px 16px',
            backgroundColor: 'hsl(var(--muted)/0.2)',
            maxHeight: '220px',
            overflowY: 'auto',
          }}
        >
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {t('technicalEventLog')}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {activities.map((act, i) => {
              const formatted = formatTechnicalEvent(act);
              return (
                <div
                  key={act.id || i}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontSize: '11.5px',
                    fontFamily: 'var(--font-mono)',
                    color: 'hsl(var(--muted-fg))',
                  }}
                >
                  <span style={{ color: 'hsl(var(--border))' }}>›</span>
                  <span style={{ color: 'hsl(var(--fg))' }}>{act.agent || 'Workforce'}:</span>
                  <span>{formatted}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers: Humanize & State Aggregation
// ---------------------------------------------------------------------------

interface AggregatedMember {
  rawName: string;
  displayName: string;
  role?: string;
  status: 'active' | 'completed' | 'waiting' | 'interrupted' | 'failed';
  currentAction: string;
}

function aggregateWorkforceState(
  activities: ActivityItem[],
  isLive: boolean,
  isInterrupted: boolean,
  t: (key: TranslationKey) => string
): AggregatedMember[] {
  const membersMap = new Map<string, { lastEvent: ActivityItem }>();

  for (const act of activities) {
    const raw = act.agent || 'workforce';
    if (raw.toLowerCase() === 'workforce' && membersMap.size > 0 && act.type === 'task_interrupted') {
      continue;
    }
    if (!membersMap.has(raw)) {
      membersMap.set(raw, { lastEvent: act });
    }
    const entry = membersMap.get(raw)!;
    entry.lastEvent = act;
  }

  const lastActivity = activities[activities.length - 1];
  const activeAgentRaw = lastActivity ? lastActivity.agent : null;

  const result: AggregatedMember[] = [];

  for (const [rawName, { lastEvent }] of membersMap.entries()) {
    const displayName = formatAgentName(rawName);
    const isCurrentlyActive = isLive && (rawName === activeAgentRaw);
    const isThisAgentInterrupted = isInterrupted && (rawName === activeAgentRaw || isCurrentlyActive);

    let status: AggregatedMember['status'] = isCurrentlyActive ? 'active' : 'completed';

    if (isThisAgentInterrupted || lastEvent.type === 'task_interrupted') {
      status = 'interrupted';
    } else if (lastEvent.type === 'interrupt' || lastEvent.type === 'INTERRUPT') {
      status = 'interrupted';
    }

    const currentAction = humanizeAgentAction(lastEvent, isCurrentlyActive, isThisAgentInterrupted, t);

    result.push({
      rawName,
      displayName,
      status,
      currentAction,
    });
  }

  return result;
}

function humanizeAgentAction(
  act: ActivityItem,
  isActive: boolean,
  isInterrupted: boolean = false,
  t: (key: TranslationKey) => string
): string {
  const event = (act.type || '').toLowerCase();
  const meta = act.metadata || {};

  if (isInterrupted || event === 'task_interrupted') {
    return t('actionInterrupted');
  }

  if (event === 'agent_started') {
    if (meta.instruction) {
      return isActive ? `${t('actionOrganizing')}: "${meta.instruction.slice(0, 60)}..."` : t('actionGoalAnalyzed');
    }
    return isActive ? t('actionPlanning') : t('actionPlanningComplete');
  }

  if (event === 'task_delegated') {
    const target = formatAgentName(meta.target_agent || meta.tool_name || 'Specialist');
    return `${t('actionDelegatedTo')} ${target}`;
  }

  if (event === 'tool_called') {
    const tool = meta.tool_name || '';
    if (tool === 'search_knowledge') {
      const q = meta.arguments?.query || meta.query || '';
      return isActive ? (q ? `${t('actionSearchingDocs')}: "${q}"` : t('actionConsultingKb')) : t('actionSearchedDocs');
    }
    return isActive ? `${t('actionProcessing')} ${tool}...` : `${t('actionExecuted')} ${tool}`;
  }

  if (event === 'tool_completed') {
    const tool = meta.tool_name || '';
    if (tool === 'search_knowledge') {
      return t('actionFoundDocs');
    }
    return `${t('actionOpComplete')} (${tool})`;
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
