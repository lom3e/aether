import { useState, useEffect, useCallback } from 'react';
import { Bot, ArrowLeft, Cpu, ArrowRight, Edit2 } from 'lucide-react';
import { AgentBuilder } from './AgentBuilder';
import { TopHeader } from './TopHeader';
import { apiUrl } from './api';
import { useTranslation } from './i18n';

export function AgentProfile({ name, navigate }: { name: string, navigate: (view: string, params?: any) => void }) {
  const [agent, setAgent] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const { t } = useTranslation();

  const fetchAgent = useCallback(() => {
    fetch(apiUrl('/api/agents'))
      .then(res => res.json())
      .then(data => {
        const found = data.find((a: any) => a.name === name);
        if (found) {
          setAgent(found);
        }
        setLoading(false);
      })
      .catch(console.error);
  }, [name]);

  useEffect(() => {
    fetchAgent();
  }, [fetchAgent]);

  if (loading) {
    return (
      <div className="app-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ color: 'hsl(var(--muted-fg))', fontSize: '14px' }}>{t('loading')}</div>
      </div>
    );
  }

  if (!agent) {
    return (
      <div style={{ padding: '48px', textAlign: 'center' }}>
        <Bot size={48} className="text-muted" style={{ margin: '0 auto 16px' }} />
        <h3>{t('agentNotFound')}</h3>
        <button className="btn btn-primary" style={{ marginTop: '16px' }} onClick={() => navigate('agents')}>
          {t('backToAgents')}
        </button>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <TopHeader
        title={t('agentProfile')}
        leading={
          <button className="btn btn-ghost" style={{ padding: '6px' }} onClick={() => navigate('agents')}>
            <ArrowLeft size={16} />
          </button>
        }
        actions={
          <button className="btn btn-secondary" onClick={() => setIsEditing(true)}>
            <Edit2 size={14} /> {t('editAgent')}
          </button>
        }
      />

      <div style={{ maxWidth: '840px', margin: '36px auto', padding: '0 32px' }}>
        {/* Header Banner */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px', marginBottom: '32px' }}>
          <div style={{
            width: '64px',
            height: '64px',
            borderRadius: '12px',
            backgroundColor: 'hsl(var(--primary)/0.15)',
            color: 'hsl(var(--primary))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '24px',
            fontWeight: 700
          }}>
            {agent.name.substring(0, 2).toUpperCase()}
          </div>
          <div>
            <h1 style={{ fontSize: '24px', marginBottom: '4px' }}>{agent.name}</h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <span className="badge badge-primary">{agent.role}</span>
              <span className="badge badge-success">{t('statusReady')}</span>
              <span className="badge">
                {agent.provider || t('teamDefault')} {agent.model ? `· ${agent.model}` : ''}
              </span>
            </div>
          </div>
        </div>

        {/* Instructions Card */}
        <div className="card" style={{ marginBottom: '24px', padding: '24px' }}>
          <h3 style={{ fontSize: '15px', marginBottom: '12px' }}>{t('instructions')}</h3>
          <div style={{
            whiteSpace: 'pre-wrap',
            color: 'hsl(var(--fg))',
            fontSize: '13.5px',
            lineHeight: 1.6,
            fontFamily: 'var(--font-sans)',
            backgroundColor: 'hsl(var(--muted)/0.4)',
            padding: '16px',
            borderRadius: 'var(--radius)',
            border: '1px solid hsl(var(--border)/0.5)'
          }}>
            {agent.description || agent.instructions || <span className="text-muted italic">{t('noPromptProvided')}</span>}
          </div>
        </div>

        {/* Skills & Delegations Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          <div className="card" style={{ padding: '22px' }}>
            <h3 style={{ fontSize: '15px', marginBottom: '12px' }}>{t('skills')}</h3>
            {agent.skills && agent.skills.length > 0 ? (
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {agent.skills.map((s: string) => (
                  <span key={s} className="badge" style={{ padding: '4px 10px', fontSize: '12px' }}>
                    <Cpu size={13} className="text-primary" /> {s}
                  </span>
                ))}
              </div>
            ) : (
              <span className="text-muted" style={{ fontSize: '13px' }}>{t('noSkillsAttached')}</span>
            )}
          </div>

          <div className="card" style={{ padding: '22px' }}>
            <h3 style={{ fontSize: '15px', marginBottom: '12px' }}>{t('delegatesTo')}</h3>
            {agent.delegates_to && agent.delegates_to.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {agent.delegates_to.map((target: string) => (
                  <div key={target} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'hsl(var(--fg))' }}>
                    <ArrowRight size={14} className="text-primary" />
                    <span>{target}</span>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-muted" style={{ fontSize: '13px' }}>{t('leafAgentDesc')}</span>
            )}
          </div>
        </div>
      </div>

      {isEditing && (
        <AgentBuilder
          initialData={agent}
          onClose={() => setIsEditing(false)}
          onSave={() => {
            setIsEditing(false);
            fetchAgent();
          }}
        />
      )}
    </div>
  );
}
