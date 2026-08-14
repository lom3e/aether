import { Cpu } from 'lucide-react';
import { useTranslation } from './i18n';

interface AgentInfo {
  name: string;
  role: string;
  provider?: string;
  model?: string;
  status?: 'idle' | 'working' | 'waiting' | 'completed' | 'failed';
}

interface WorkforcePresenceProps {
  teamName: string;
  agents: AgentInfo[];
  activeAgents?: string[];
  waitingAgent?: string | null;
}

export function WorkforcePresence({
  teamName,
  agents,
  activeAgents = [],
  waitingAgent = null
}: WorkforcePresenceProps) {
  const { t } = useTranslation();

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '16px',
      padding: '8px 16px',
      backgroundColor: 'hsl(var(--card))',
      borderRadius: 'var(--radius)',
      border: '1px solid hsl(var(--border))',
      fontSize: '12px',
      overflowX: 'auto'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', fontSize: '11px', flexShrink: 0 }}>
        <Cpu size={14} className="text-primary" />
        <span>{teamName || 'Workforce'}:</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'nowrap' }}>
        {agents.map((agent, i) => {
          const isWorking = activeAgents.includes(agent.name);
          const isWaiting = waitingAgent === agent.name;

          let dotClass = 'status-dot idle';
          let statusText = t('statusIdle');

          if (isWorking) {
            dotClass = 'status-dot active';
            statusText = t('statusWorking');
          } else if (isWaiting) {
            dotClass = 'status-dot waiting';
            statusText = t('statusWaiting');
          }

          return (
            <div
              key={agent.name || i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '4px 10px',
                borderRadius: '6px',
                backgroundColor: isWorking ? 'hsl(var(--primary)/0.1)' : 'hsl(var(--muted))',
                border: isWorking ? '1px solid hsl(var(--primary)/0.3)' : '1px solid transparent',
                transition: 'all 0.2s ease',
                flexShrink: 0
              }}
              title={`${agent.role || 'Agent'} (${agent.provider || ''} ${agent.model || ''}) - ${statusText}`}
            >
              <div className={dotClass} />
              <span style={{ fontWeight: isWorking ? 600 : 500, color: 'hsl(var(--fg))' }}>
                {agent.name}
              </span>
              <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                {agent.role ? `· ${agent.role.split(' ')[0]}` : ''}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
