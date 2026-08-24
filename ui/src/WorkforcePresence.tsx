import { Cpu, Folder } from 'lucide-react';
import { useTranslation } from './i18n';
import { Tooltip } from './Tooltip';

interface AgentInfo {
  name: string;
  role: string;
  provider?: string;
  model?: string;
  icon?: string;
  color?: string;
  skills?: string[];
  tools?: string[];
  tool_count?: number;
  status?: 'idle' | 'working' | 'waiting' | 'completed' | 'failed';
}

interface WorkforcePresenceProps {
  teamName: string;
  agents: AgentInfo[];
  activeAgents?: string[];
  waitingAgent?: string | null;
  project?: {
    type?: string;
    path?: string;
    name?: string;
    exists?: boolean;
  } | null;
}

export function WorkforcePresence({
  teamName,
  agents,
  activeAgents = [],
  waitingAgent = null,
  project = null
}: WorkforcePresenceProps) {
  const { t } = useTranslation();

  return (
    <header
      data-testid="workforce-presence-header"
      className="top-header"
      style={{
        height: '56px',
        borderBottom: '1px solid hsl(var(--border))',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        backgroundColor: 'hsl(var(--bg))',
        fontSize: '12px',
        overflowX: 'auto',
        flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', fontSize: '11px' }}>
          <Cpu size={15} className="text-primary" />
          <span>{teamName || 'Workforce'}:</span>
        </div>

        {project && project.name && (
          <Tooltip content={project.path || project.name} position="bottom">
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '3px 8px',
                borderRadius: '6px',
                backgroundColor: 'hsl(var(--muted)/0.7)',
                border: '1px solid hsl(var(--border))',
                fontSize: '11.5px',
                color: 'hsl(var(--fg))'
              }}
            >
              <Folder size={13} className="text-primary" />
              <span style={{ fontWeight: 500, maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {project.name}
              </span>
            </div>
          </Tooltip>
        )}
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
            <Tooltip
              key={agent.name || i}
              content={`${agent.role || 'Agent'} (${agent.provider || ''} ${agent.model || ''}) · ${statusText}`}
              position="bottom"
            >
              <div
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
              >
                <div className={dotClass} />
                <span style={{ fontWeight: isWorking ? 600 : 500, color: 'hsl(var(--fg))' }}>
                  {agent.name}
                </span>
                <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                  {agent.role ? `· ${agent.role.split(' ')[0]}` : ''}
                </span>
              </div>
            </Tooltip>
          );
        })}
      </div>
    </header>
  );
}
