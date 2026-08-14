import { useState, useEffect, useRef, useContext } from 'react';
import { Send, Sparkles, RotateCw } from 'lucide-react';
import { ToastContext } from './toast';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { WorkforcePresence } from './WorkforcePresence';
import { MessageItem, type ChatMessage } from './MessageItem';
import { ActivityFeed, type ActivityItem } from './ActivityFeed';

interface ChatProps {
  conversationId: string | null;
  onNewConversation?: () => void;
  onConversationUpdated: () => void;
}

export function Chat({ conversationId, onConversationUpdated }: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [teamInfo, setTeamInfo] = useState<{ name: string; agents: any[] }>({ name: 'Workforce', agents: [] });
  const [activeAgents, setActiveAgents] = useState<string[]>([]);
  const [waitingAgent, setWaitingAgent] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const showToast = useContext(ToastContext);
  const { t } = useTranslation();

  // Load team info
  useEffect(() => {
    fetch(apiUrl('/api/workspace'))
      .then(res => res.json())
      .then(data => {
        if (data) {
          setTeamInfo({
            name: data.name || 'Workforce',
            agents: data.agents || []
          });
        }
      })
      .catch(console.error);
  }, []);

  // Load conversation messages from SQLite when conversationId changes
  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      setActivities([]);
      return;
    }

    fetch(apiUrl(`/api/conversations/${conversationId}`))
      .then(res => res.json())
      .then(data => {
        if (data && data.messages) {
          setMessages(data.messages);
        } else {
          setMessages([]);
        }
        setActivities([]);
      })
      .catch(() => {
        setMessages([]);
      });
  }, [conversationId]);

  // Connect WebSocket
  useEffect(() => {
    const wsUrl = apiUrl('/ws/chat').replace(/^http/, 'ws');
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'task_started') {
          setLoading(true);
          setActiveAgents(['manager']);
        } else if (data.type === 'activity') {
          const newAct: ActivityItem = {
            id: String(Date.now() + Math.random()),
            agent: data.agent || 'Workforce',
            type: data.event || data.activity_type || '',
            message: data.message || '',
            timestamp: new Date().toISOString(),
            metadata: data.metadata || data.data
          };
          setActivities(prev => [...prev, newAct]);

          // Update active agents in presence bar
          if (data.agent && !activeAgents.includes(data.agent)) {
            setActiveAgents(prev => Array.from(new Set([...prev, data.agent])));
          }
        } else if (data.type === 'interrupt') {
          setWaitingAgent(data.agent || 'manager');
          const interruptMsg: ChatMessage = {
            id: data.interrupt_id || String(Date.now()),
            role: 'assistant',
            agent_name: data.agent || 'Workforce Coordinator',
            content: data.message || '',
            interrupt: {
              type: data.interrupt_type || 'approval',
              message: data.message || '',
              interrupt_id: data.interrupt_id
            }
          };
          setMessages(prev => [...prev, interruptMsg]);
        } else if (data.type === 'task_completed') {
          setLoading(false);
          setActiveAgents([]);
          setWaitingAgent(null);

          if (data.content) {
            const botMsg: ChatMessage = {
              id: String(Date.now()),
              role: 'assistant',
              agent_name: data.agent || 'Manager',
              content: data.content,
              created_at: new Date().toISOString()
            };
            setMessages(prev => [...prev, botMsg]);
          }
          onConversationUpdated();
        } else if (data.type === 'error') {
          setLoading(false);
          setActiveAgents([]);
          setWaitingAgent(null);
          showToast(data.message || 'Task encountered an error.', 'error');
        }
      } catch (err) {
        console.error('Error processing WebSocket message:', err);
      }
    };

    ws.onerror = () => {
      setLoading(false);
    };

    return () => {
      ws.close();
    };
  }, [conversationId]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activities, loading]);

  const handleSend = () => {
    if (!input.trim() || loading) return;

    const userPrompt = input.trim();
    setInput('');

    const userMsg: ChatMessage = {
      id: String(Date.now()),
      role: 'user',
      content: userPrompt,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);
    setActivities([]);
    setLoading(true);

    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({
        type: 'run_task',
        content: userPrompt,
        session_id: conversationId || undefined
      }));
    } else {
      showToast('Connecting to workforce server...', 'info');
    }
  };

  const handleInterruptResponse = (response: string) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({
        type: 'interrupt_response',
        content: response
      }));
      setWaitingAgent(null);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Top Header with Presence */}
      <div className="top-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className="top-header-title">
            <Sparkles size={18} className="text-primary" />
            <span>AI Workforce Chat</span>
          </div>
        </div>

        <WorkforcePresence
          teamName={teamInfo.name}
          agents={teamInfo.agents}
          activeAgents={activeAgents}
          waitingAgent={waitingAgent}
        />
      </div>

      {/* Messages Scroll Area */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
        {messages.length === 0 && !loading ? (
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '32px',
            textAlign: 'center'
          }}>
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '16px',
              backgroundColor: 'hsl(var(--primary)/0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'hsl(var(--primary))',
              marginBottom: '18px'
            }}>
              <Sparkles size={28} />
            </div>
            <h2 style={{ fontSize: '20px', marginBottom: '8px' }}>{t('emptyChatTitle')}</h2>
            <p className="text-muted" style={{ maxWidth: '460px', fontSize: '14px', marginBottom: '24px' }}>
              {t('emptyChatSubtitle')}
            </p>

            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center', maxWidth: '600px' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setInput('Spiegami come funziona la separazione tra System Knowledge e Workspace Knowledge in Aether.')}
              >
                Knowledge Architecture
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setInput('Analizza l\'azienda Acme Robotics e prepara un executive summary per il management.')}
              >
                Acme Robotics Analysis
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setInput('Qual è il ruolo del Manager e come delega i task alla workforce?')}
              >
                Manager Delegation
              </button>
            </div>
          </div>
        ) : (
          <div style={{ maxWidth: '900px', width: '100%', margin: '0 auto', flex: 1 }}>
            {messages.map((msg, i) => (
              <MessageItem
                key={msg.id || i}
                message={msg}
                onInterruptResponse={handleInterruptResponse}
                onRetry={(content) => { setInput(content); }}
              />
            ))}

            {/* Live Activities Stream */}
            {activities.length > 0 && (
              <div style={{ padding: '0 24px' }}>
                <ActivityFeed activities={activities} isLive={loading} />
              </div>
            )}

            {loading && activities.length === 0 && (
              <div style={{ padding: '16px 24px', display: 'flex', alignItems: 'center', gap: '10px', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
                <div className="status-dot active" />
                <span>{t('running')}</span>
              </div>
            )}

            <div ref={messagesEndRef} style={{ height: '16px' }} />
          </div>
        )}
      </div>

      {/* Bottom Input Area */}
      <div style={{
        padding: '16px 24px 20px',
        borderTop: '1px solid hsl(var(--border))',
        backgroundColor: 'hsl(var(--card))'
      }}>
        <div style={{
          maxWidth: '900px',
          margin: '0 auto',
          position: 'relative',
          backgroundColor: 'hsl(var(--bg))',
          borderRadius: '10px',
          border: '1px solid hsl(var(--input))',
          boxShadow: '0 2px 6px rgba(0,0,0,0.05)',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <textarea
            className="form-textarea"
            style={{
              border: 'none',
              background: 'transparent',
              padding: '14px 16px',
              resize: 'none',
              minHeight: '60px',
              maxHeight: '200px',
              boxShadow: 'none',
              fontSize: '14px'
            }}
            placeholder={t('chatInputPlaceholder')}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            disabled={loading}
          />

          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '8px 12px 10px',
            borderTop: '1px solid hsl(var(--border)/0.3)'
          }}>
            <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
              Press <kbd style={{ padding: '2px 4px', background: 'hsl(var(--muted))', borderRadius: '3px' }}>Enter</kbd> to run, <kbd style={{ padding: '2px 4px', background: 'hsl(var(--muted))', borderRadius: '3px' }}>Shift+Enter</kbd> for newline
            </div>

            <button
              className="btn btn-primary"
              style={{ padding: '6px 14px' }}
              onClick={handleSend}
              disabled={!input.trim() || loading}
            >
              {loading ? <RotateCw size={14} className="spin" /> : <Send size={14} />}
              <span>{t('runTask')}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
