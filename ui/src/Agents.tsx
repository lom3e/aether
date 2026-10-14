import { useEffect, useState } from 'react';
import { Bot, Plus, MessageSquare, Sparkles, ChevronDown, ChevronUp } from 'lucide-react';
import { AgentBuilder } from './AgentBuilder';
import { TopHeader } from './TopHeader';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { IdentityBadge } from './identity';

export function Agents({ navigate }: { navigate: (view: string, params?: any) => void }) {
  const [agents, setAgents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isBuilding, setIsBuilding] = useState(false);
  const [expandedTech, setExpandedTech] = useState<Record<string, boolean>>({});
  const { t } = useTranslation();

  const toggleTech = (name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedTech(prev => ({ ...prev, [name]: !prev[name] }));
  };

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
        title={t('syAssistantsAndAgents')}
        icon={Bot}
        actions={
          <button
            className="btn btn-primary"
            onClick={() => setIsBuilding(true)}
          >
            <Plus size={16} /> {t('syNewAssistant')}
          </button>
        }
      />

      <div style={{ maxWidth: '1100px', margin: '36px auto', padding: '0 32px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(320px, 100%), 1fr))', gap: '20px' }}>
          {agents.map((agent, i) => (
            <div
              key={i}
              className="card card-interactive"
              onClick={() => navigate('agent', agent.name)}
              style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', height: '100%', padding: '22px' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <IdentityBadge
                    icon={agent.icon || 'Bot'}
                    color={agent.color || 'violet'}
                    size={20}
                    containerSize={38}
                  />
                  <div>
                    <h3 style={{ fontSize: '15px', margin: 0, fontWeight: 600 }}>{agent.name}</h3>
                    <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>{agent.role || t('syAutonomousAssistant')}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontSize: '11px', color: '#10b981', fontWeight: 500 }}>{t('syReady')}</span>
                  <div className="status-dot idle" />
                </div>
              </div>

              <div style={{ marginBottom: '14px', fontSize: '13px', color: 'hsl(var(--muted-fg))', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', minHeight: '38px', lineHeight: 1.5 }}>
                {agent.description || agent.instructions || t('syAssistantSetUpToCollaborateOn')}
              </div>

              {agent.skills && agent.skills.length > 0 && (
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '14px' }}>
                  {agent.skills.map((s: string) => (
                    <span key={s} className="badge" style={{ background: 'hsl(var(--muted))', fontSize: '11px' }}>
                      <Sparkles size={11} className="text-primary" /> {s}
                    </span>
                  ))}
                </div>
              )}

              {/* Action buttons */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto', paddingTop: '12px', borderTop: '1px solid hsl(var(--border)/0.4)' }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ fontSize: '12px', padding: '6px 14px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate('agent', agent.name);
                  }}
                >
                  <MessageSquare size={13} /> {t('agentTalk')}
                </button>

                {(agent.is_external || agent.model || agent.endpoint_url) && (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    style={{ fontSize: '11px', padding: '4px 8px', color: 'hsl(var(--muted-fg))' }}
                    onClick={(e) => toggleTech(agent.name, e)}
                  >
                    Dettagli tecnici {expandedTech[agent.name] ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>
                )}
              </div>

              {/* Hidden/expandable technical parameters */}
              {expandedTech[agent.name] && (
                <div style={{ marginTop: '10px', padding: '8px 10px', backgroundColor: 'hsl(var(--muted)/0.3)', borderRadius: '6px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {agent.provider && <div><strong>Provider:</strong> {agent.provider}</div>}
                  {agent.model && <div><strong>Modello:</strong> {agent.model}</div>}
                  {agent.endpoint_url && <div><strong>Endpoint:</strong> <code>{agent.endpoint_url}</code></div>}
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
