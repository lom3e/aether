import { useState } from 'react';
import { ChevronDown, ChevronRight, CheckCircle2, Clock, Bot, Search, ArrowRight, ShieldAlert, Cpu } from 'lucide-react';

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
}

export function ActivityFeed({ activities, isLive = false }: ActivityFeedProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  if (!activities || activities.length === 0) return null;

  const formatActivityMessage = (act: ActivityItem): { title: string; subtitle?: string; icon: any } => {
    const event = act.type || '';
    const agent = act.agent || 'Workforce';
    const meta = act.metadata || {};

    if (event === 'agent_started' || event === 'AGENT_STARTED') {
      return {
        title: `${agent} initialized cognitive loop`,
        subtitle: meta.instruction ? `Goal: ${meta.instruction}` : undefined,
        icon: <Cpu size={14} className="text-primary" />
      };
    }

    if (event === 'task_delegated' || event === 'TASK_DELEGATED') {
      const target = meta.target_agent || meta.tool_name || 'Specialist';
      return {
        title: `${agent} delegated sub-task to ${target}`,
        subtitle: meta.instruction ? `Instruction: ${meta.instruction.slice(0, 100)}...` : undefined,
        icon: <ArrowRight size={14} className="text-primary" />
      };
    }

    if (event === 'tool_called' || event === 'TOOL_CALLED') {
      const tool = meta.tool_name || 'tool';
      if (tool === 'search_knowledge') {
        const q = meta.arguments?.query || '';
        return {
          title: `${agent} searched company knowledge base`,
          subtitle: q ? `Query: "${q}"` : undefined,
          icon: <Search size={14} className="text-primary" />
        };
      }
      return {
        title: `${agent} called ${tool}`,
        subtitle: meta.arguments ? JSON.stringify(meta.arguments).slice(0, 80) : undefined,
        icon: <Bot size={14} className="text-primary" />
      };
    }

    if (event === 'tool_completed' || event === 'TOOL_COMPLETED') {
      const tool = meta.tool_name || 'tool';
      if (tool === 'search_knowledge') {
        return {
          title: `${agent} retrieved factual evidence from knowledge base`,
          icon: <CheckCircle2 size={14} style={{ color: 'hsl(var(--success))' }} />
        };
      }
      return {
        title: `${agent} completed ${tool}`,
        icon: <CheckCircle2 size={14} style={{ color: 'hsl(var(--success))' }} />
      };
    }

    if (event === 'interrupt' || event === 'INTERRUPT') {
      return {
        title: `${agent} requested human approval / input`,
        subtitle: act.message,
        icon: <ShieldAlert size={14} style={{ color: 'hsl(var(--warning))' }} />
      };
    }

    // Default
    return {
      title: act.message || `${agent} operational activity`,
      subtitle: meta ? JSON.stringify(meta).slice(0, 80) : undefined,
      icon: <Clock size={14} className="text-muted" />
    };
  };

  return (
    <div style={{
      margin: '12px 0',
      backgroundColor: 'hsl(var(--muted)/0.5)',
      borderRadius: 'var(--radius)',
      border: '1px solid hsl(var(--border))',
      overflow: 'hidden'
    }}>
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        style={{
          padding: '8px 14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
          userSelect: 'none',
          backgroundColor: 'hsl(var(--muted)/0.8)',
          fontSize: '12px',
          fontWeight: 600
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span style={{ color: 'hsl(var(--fg))' }}>Workforce Activity ({activities.length} steps)</span>
          {isLive && <span className="status-dot active" style={{ width: '6px', height: '6px' }} />}
        </div>
        <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
          {isExpanded ? 'Collapse' : 'Expand'}
        </span>
      </div>

      {isExpanded && (
        <div style={{ padding: '8px 14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {activities.map((act, i) => {
            const formatted = formatActivityMessage(act);
            return (
              <div
                key={act.id || i}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                  fontSize: '12px',
                  padding: '4px 0',
                  borderBottom: i < activities.length - 1 ? '1px solid hsl(var(--border)/0.4)' : 'none'
                }}
              >
                <div style={{ marginTop: '2px', flexShrink: 0 }}>
                  {formatted.icon}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                    <span className="badge" style={{ fontSize: '10px', padding: '1px 6px', background: 'hsl(var(--card))' }}>
                      {act.agent || 'Manager'}
                    </span>
                    <span style={{ fontWeight: 500, color: 'hsl(var(--fg))' }}>
                      {formatted.title}
                    </span>
                  </div>
                  {formatted.subtitle && (
                    <div style={{
                      fontSize: '11px',
                      color: 'hsl(var(--muted-fg))',
                      marginTop: '3px',
                      fontFamily: 'var(--font-mono)',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word'
                    }}>
                      {formatted.subtitle}
                    </div>
                  )}
                </div>
                <div style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))', flexShrink: 0, marginTop: '2px' }}>
                  {act.timestamp ? act.timestamp.split('T')[1]?.slice(0, 8) || '' : ''}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
