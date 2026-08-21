import { useEffect, useState } from 'react';
import { Bot, Cpu, Plus } from 'lucide-react';
import { AgentBuilder } from './AgentBuilder';
import { TopHeader } from './TopHeader';
import { apiUrl } from './api';
import { useTranslation } from './i18n';

export function Agents({ navigate }: { navigate: (view: string, params?: any) => void }) {
  const [agents, setAgents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isBuilding, setIsBuilding] = useState(false);
  const { t } = useTranslation();

  const fetchAgents = () => {
    fetch(apiUrl('/api/agents'))
      .then(res => res.json())
      .then(data => {
        setAgents(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to load agents", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchAgents();
  }, []);

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <TopHeader
        title={t('agentsTitle')}
        icon={Bot}
        actions={
          <button
            className="btn btn-primary"
            onClick={() => setIsBuilding(true)}
          >
            <Plus size={16} /> {t('createAgent')}
          </button>
        }
      />

      <div style={{ maxWidth: '1100px', margin: '36px auto', padding: '0 32px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
          {agents.map((agent, i) => (
            <div
              key={i}
              className="card card-interactive"
              onClick={() => navigate('agent', agent.name)}
              style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', height: '100%', padding: '22px' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{
                    width: '38px',
                    height: '38px',
                    borderRadius: '8px',
                    backgroundColor: 'hsl(var(--primary)/0.12)',
                    color: 'hsl(var(--primary))',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '15px',
                    fontWeight: 700
                  }}>
                    {agent.name.substring(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <h3 style={{ fontSize: '15px', margin: 0 }}>{agent.name}</h3>
                    <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>{agent.role}</div>
                  </div>
                </div>
                <div className="status-dot idle" title={t('configured')} />
              </div>

              <div style={{ marginBottom: '14px', fontSize: '13px', color: 'hsl(var(--muted-fg))', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', minHeight: '38px', lineHeight: 1.5 }}>
                {agent.description || agent.instructions || <em>{t('autonomousAgentDesc')}</em>}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px', fontSize: '11.5px', color: 'hsl(var(--muted-fg))' }}>
                <span className="badge" style={{ fontSize: '10.5px' }}>
                  {agent.provider || 'default'}
                </span>
                {agent.model && (
                  <span className="badge" style={{ fontSize: '10.5px' }}>
                    {agent.model}
                  </span>
                )}
              </div>

              {agent.skills && agent.skills.length > 0 && (
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: 'auto', paddingTop: '12px', borderTop: '1px solid hsl(var(--border)/0.4)' }}>
                  {agent.skills.map((s: string) => (
                    <span key={s} className="badge" style={{ background: 'hsl(var(--muted))', fontSize: '10.5px' }}>
                      <Cpu size={11} className="text-primary" /> {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}

          {agents.length === 0 && !loading && (
            <div className="card" style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '48px' }}>
              <Bot size={40} className="text-muted" style={{ margin: '0 auto 16px' }} />
              <h3 style={{ fontSize: '18px', marginBottom: '6px' }}>{t('noAgentsConfigured')}</h3>
              <p className="text-muted" style={{ fontSize: '13.5px', marginBottom: '20px' }}>{t('noAgentsConfiguredDesc')}</p>
              <button className="btn btn-primary" onClick={() => setIsBuilding(true)}>
                <Plus size={16} /> {t('createAgent')}
              </button>
            </div>
          )}
        </div>
      </div>

      {isBuilding && (
        <AgentBuilder
          onClose={() => setIsBuilding(false)}
          onSave={fetchAgents}
        />
      )}
    </div>
  );
}
