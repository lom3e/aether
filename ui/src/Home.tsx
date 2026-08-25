import { useState, useEffect } from 'react';
import {
  Plus, Bot, Database, Layers, MessageSquare,
  ArrowRight, ShieldCheck, Cpu, Sparkles
} from 'lucide-react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { TopHeader } from './TopHeader';
import { AutoArchitectModal } from './AutoArchitectModal';

interface HomeProps {
  navigate: (view: string) => void;
  workspaceName: string;
  onNewTask: () => void;
  onSelectConversation: (id: string) => void;
  conversations: any[];
  onOpenWorkspaceModal?: () => void;
}

export function Home({
  navigate,
  workspaceName,
  onNewTask,
  onSelectConversation,
  conversations,
  onOpenWorkspaceModal,
}: HomeProps) {
  const [workspaceData, setWorkspaceData] = useState<any>(null);
  const [isAutoArchitectOpen, setIsAutoArchitectOpen] = useState(false);
  const { t } = useTranslation();

  useEffect(() => {
    if (!workspaceName) {
      setWorkspaceData(null);
      return;
    }
    fetch(apiUrl('/api/workspace'))
      .then(res => res.json())
      .then(data => setWorkspaceData(data))
      .catch(console.error);
  }, [workspaceName]);

  // If no workspace exists or is active, show the explicit no-workspace empty state
  if (!workspaceName) {
    return (
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 24px' }}>
        <div className="card" style={{ maxWidth: '520px', width: '100%', padding: '44px 36px', textAlign: 'center', boxShadow: '0 12px 36px rgba(0,0,0,0.08)' }}>
          <div style={{
            width: '64px',
            height: '64px',
            borderRadius: '16px',
            backgroundColor: 'hsl(var(--primary)/0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 20px',
          }}>
            <img
              src="/brand/logo_viola.svg"
              alt="Aether"
              width="36"
              height="36"
              style={{ display: 'block' }}
            />
          </div>
          <h2 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '10px', color: 'hsl(var(--fg))' }}>
            {t('createFirstWorkspace')}
          </h2>
          <p className="text-muted" style={{ fontSize: '14px', lineHeight: 1.6, marginBottom: '28px', maxWidth: '420px', margin: '0 auto 28px' }}>
            {t('noActiveWorkspaceDesc')}
          </p>
          <button
            className="btn btn-primary"
            style={{ padding: '10px 24px', fontSize: '14px', margin: '0 auto', display: 'inline-flex', alignItems: 'center', gap: '8px' }}
            onClick={onOpenWorkspaceModal ? onOpenWorkspaceModal : () => navigate('settings')}
          >
            <Plus size={16} />
            <span>{t('createWorkspaceBtn')}</span>
          </button>
        </div>
      </div>
    );
  }

  const agents = workspaceData?.agents || [];
  const knowledgeChunks = workspaceData?.knowledge_chunks || 0;

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <TopHeader
        title={t('homeWelcome')}
        subtitle={
          <span className="badge badge-primary" style={{ fontSize: '11.5px', padding: '2px 8px' }}>
            {workspaceName}
          </span>
        }
        icon={Cpu}
        actions={
          <button
            className="btn btn-primary"
            style={{ fontSize: '12.5px', padding: '6px 14px' }}
            onClick={onNewTask}
          >
            <Plus size={15} /> {t('startTaskAction')}
          </button>
        }
      />
      <div style={{ padding: '36px 40px' }}>
        <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
          <p className="text-muted" style={{ fontSize: '15px', marginBottom: '28px', maxWidth: '680px' }}>
            {t('homeSubtitle')}
          </p>

        {/* Workforce Overview Banner */}
        <div className="card" style={{ padding: '24px', marginBottom: '32px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Cpu className="text-primary" size={20} />
              <h3 style={{ margin: 0, fontSize: '16px' }}>{t('activeTeam')}</h3>
            </div>
            <button className="btn btn-secondary" style={{ fontSize: '12px', padding: '4px 10px' }} onClick={() => navigate('teams')}>
              {t('manageTeam')} <ArrowRight size={13} />
            </button>
          </div>

          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            {agents.map((agent: any, idx: number) => (
              <div
                key={idx}
                style={{
                  flex: '1 1 200px',
                  padding: '12px 16px',
                  backgroundColor: 'hsl(var(--muted)/0.5)',
                  borderRadius: 'var(--radius)',
                  border: '1px solid hsl(var(--border))',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px'
                }}
              >
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  backgroundColor: 'hsl(var(--primary)/0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'hsl(var(--primary))',
                  fontWeight: 600,
                  fontSize: '13px'
                }}>
                  <Bot size={18} />
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '13px' }}>{agent.name}</div>
                  <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>{agent.role}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Actions Grid */}
        <div style={{ marginBottom: '36px' }}>
          <h2 style={{ fontSize: '18px', marginBottom: '16px' }}>{t('quickActions')}</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
            <div
              className="card card-interactive"
              onClick={() => setIsAutoArchitectOpen(true)}
              style={{
                cursor: 'pointer',
                padding: '20px',
                background: 'linear-gradient(135deg, hsl(var(--primary)/0.12) 0%, hsl(var(--card)) 100%)',
                border: '1px solid hsl(var(--primary)/0.35)',
              }}
            >
              <div style={{ width: '36px', height: '36px', borderRadius: '8px', backgroundColor: 'hsl(var(--primary)/0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'hsl(var(--primary))', marginBottom: '12px' }}>
                <Sparkles size={20} />
              </div>
              <h3 style={{ fontSize: '15px', marginBottom: '4px', color: 'hsl(var(--primary))', fontWeight: 600 }}>
                {t('designWithAi') || '✨ Progetta con l\'IA'}
              </h3>
              <p className="text-muted" style={{ fontSize: '12.5px', margin: 0 }}>
                {t('autoArchitectHomeCardDesc') || 'Descrivi il tuo obiettivo e l\'IA configurerà la tua squadra su misura.'}
              </p>
            </div>

            <div
              className="card card-interactive"
              onClick={onNewTask}
              style={{ cursor: 'pointer', padding: '20px' }}
            >
              <div style={{ width: '36px', height: '36px', borderRadius: '8px', backgroundColor: 'hsl(var(--primary)/0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'hsl(var(--primary))', marginBottom: '12px' }}>
                <Plus size={20} />
              </div>
              <h3 style={{ fontSize: '15px', marginBottom: '4px' }}>{t('startTaskAction')}</h3>
              <p className="text-muted" style={{ fontSize: '12.5px', margin: 0 }}>{t('startTaskDesc')}</p>
            </div>

            <div
              className="card card-interactive"
              onClick={() => navigate('agents')}
              style={{ cursor: 'pointer', padding: '20px' }}
            >
              <div style={{ width: '36px', height: '36px', borderRadius: '8px', backgroundColor: 'hsl(var(--primary)/0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'hsl(var(--primary))', marginBottom: '12px' }}>
                <Bot size={20} />
              </div>
              <h3 style={{ fontSize: '15px', marginBottom: '4px' }}>{t('createAgentAction')}</h3>
              <p className="text-muted" style={{ fontSize: '12.5px', margin: 0 }}>{t('createAgentDesc')}</p>
            </div>

            <div
              className="card card-interactive"
              onClick={() => navigate('knowledge')}
              style={{ cursor: 'pointer', padding: '20px' }}
            >
              <div style={{ width: '36px', height: '36px', borderRadius: '8px', backgroundColor: 'hsl(var(--primary)/0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'hsl(var(--primary))', marginBottom: '12px' }}>
                <Database size={20} />
              </div>
              <h3 style={{ fontSize: '15px', marginBottom: '4px' }}>{t('addKnowledgeAction')}</h3>
              <p className="text-muted" style={{ fontSize: '12.5px', margin: 0 }}>{t('addKnowledgeDesc')}</p>
            </div>

            <div
              className="card card-interactive"
              onClick={() => navigate('marketplace')}
              style={{ cursor: 'pointer', padding: '20px' }}
            >
              <div style={{ width: '36px', height: '36px', borderRadius: '8px', backgroundColor: 'hsl(var(--primary)/0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'hsl(var(--primary))', marginBottom: '12px' }}>
                <Layers size={20} />
              </div>
              <h3 style={{ fontSize: '15px', marginBottom: '4px' }}>{t('usePresetAction')}</h3>
              <p className="text-muted" style={{ fontSize: '12.5px', margin: 0 }}>{t('usePresetDesc')}</p>
            </div>
          </div>
        </div>

        {/* Recent Conversations */}
        <div style={{ marginBottom: '36px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <h2 style={{ fontSize: '18px' }}>{t('recentConversations')}</h2>
            <button className="btn btn-ghost" style={{ fontSize: '12px' }} onClick={() => navigate('chat')}>
              {t('viewAll')}
            </button>
          </div>

          {conversations && conversations.length > 0 ? (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('taskTitle')}</th>
                    <th>{t('status')}</th>
                    <th>{t('lastUpdated')}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {conversations.slice(0, 5).map(conv => (
                    <tr
                      key={conv.id}
                      onClick={() => onSelectConversation(conv.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: conv.unread ? 600 : 500 }}>
                          <MessageSquare size={16} className={conv.unread ? 'text-primary' : 'text-muted'} />
                          <span>{conv.title || t('untitledTask')}</span>
                          {conv.unread && (
                            <span
                              className="unread-dot"
                              style={{
                                width: '7px',
                                height: '7px',
                                borderRadius: '50%',
                                backgroundColor: 'hsl(var(--primary))',
                                display: 'inline-block',
                                boxShadow: '0 0 6px hsl(var(--primary)/0.6)'
                              }}
                            />
                          )}
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${conv.status === 'completed' ? 'badge-success' : (conv.status === 'interrupted' ? 'badge-warning' : (conv.status === 'waiting' ? 'badge-warning' : 'badge-primary'))}`}>
                          {conv.status === 'interrupted' ? t('statusInterrupted') : (conv.status === 'completed' ? t('statusCompleted') : (conv.status === 'waiting' ? t('statusWaiting') : t('statusActive')))}
                        </span>
                      </td>
                      <td className="text-muted" style={{ fontSize: '12px' }}>
                        {new Date(conv.updated_at).toLocaleDateString()} {new Date(conv.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <ArrowRight size={15} className="text-muted" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="card" style={{ textAlign: 'center', padding: '32px' }}>
              <MessageSquare size={32} className="text-muted" style={{ margin: '0 auto 12px' }} />
              <p className="text-muted" style={{ fontSize: '14px', margin: 0 }}>
                {t('noConversationsYet')}
              </p>
            </div>
          )}
        </div>

        {/* System & Storage Metrics */}
        <div className="card" style={{ padding: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'hsl(var(--card))' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <ShieldCheck size={20} className="text-primary" />
            <div>
              <div style={{ fontSize: '13px', fontWeight: 600 }}>{t('systemStatus')}</div>
              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                {t('systemStatusDesc')}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '20px' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>{t('indexedChunks')}</div>
              <div style={{ fontSize: '16px', fontWeight: 600 }}>{knowledgeChunks}</div>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>{t('navAgents')}</div>
              <div style={{ fontSize: '16px', fontWeight: 600 }}>{agents.length}</div>
            </div>
          </div>
        </div>
      </div>
      </div>

      {isAutoArchitectOpen && (
        <AutoArchitectModal
          isOpen={isAutoArchitectOpen}
          onClose={() => setIsAutoArchitectOpen(false)}
          onSuccess={() => navigate('teams')}
        />
      )}
    </div>
  );
}
