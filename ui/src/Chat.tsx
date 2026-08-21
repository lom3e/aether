import { useState, useEffect, useRef, useContext } from 'react';
import { Send, Sparkles, Square, Plus } from 'lucide-react';
import { ToastContext } from './toast';
import { apiUrl, getSessionToken } from './api';
import { useTranslation } from './i18n';
import { useTheme } from './theme';
import { WorkforcePresence } from './WorkforcePresence';
import { MessageItem, type ChatMessage } from './MessageItem';
import { ActivityFeed, type ActivityItem } from './ActivityFeed';

interface ChatProps {
  conversationId: string | null;
  onNewConversation?: () => void;
  onSelectConversation?: (id: string, tempTitle?: string) => void;
  onConversationUpdated: () => void;
  hasWorkspace?: boolean;
  onOpenWorkspaceModal?: () => void;
}

export function Chat({
  conversationId,
  onSelectConversation,
  onConversationUpdated,
  hasWorkspace = true,
  onOpenWorkspaceModal,
}: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [taskStatus, setTaskStatus] = useState<string>('active');
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [teamInfo, setTeamInfo] = useState<{ name: string; agents: any[] }>({ name: 'Workforce', agents: [] });
  const [activeAgents, setActiveAgents] = useState<string[]>([]);
  const [waitingAgent, setWaitingAgent] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(true);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const showToast = useContext(ToastContext);
  const { t, language } = useTranslation();
  const { isDark } = useTheme();

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

  // Load conversation messages and persisted activities from SQLite when conversationId changes
  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      setActivities([]);
      setTaskStatus('active');
      setLoading(false);
      return;
    }

    fetch(apiUrl(`/api/conversations/${conversationId}`))
      .then(res => res.json())
      .then(data => {
        if (data && data.messages) {
          setMessages(data.messages);
          setActivities(data.activities || []);
          setTaskStatus(data.status || 'completed');
          setLoading(data.status === 'active' && data.messages.length > 0);
        } else {
          setMessages([]);
          setActivities([]);
          setTaskStatus('active');
          setLoading(false);
        }
      })
      .catch(() => {
        setMessages([]);
        setActivities([]);
        setTaskStatus('active');
        setLoading(false);
      });
  }, [conversationId]);

  // Connect WebSocket with resilient auto-reconnect
  useEffect(() => {
    let isMounted = true;

    const connectWebSocket = () => {
      if (!isMounted) return;
      const token = getSessionToken();
      const baseWs = apiUrl('/ws/chat').replace(/^http/, 'ws');
      const wsUrl = token ? `${baseWs}?token=${encodeURIComponent(token)}` : baseWs;
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        if (!isMounted) return;
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        if (!isMounted) return;
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'task_started') {
            if (!data.session_id || data.session_id === conversationId) {
              setLoading(true);
              setTaskStatus('active');
              setActiveAgents(['manager']);
            }
            onConversationUpdated();
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

            if (data.agent && !activeAgents.includes(data.agent)) {
              setActiveAgents(prev => Array.from(new Set([...prev, data.agent])));
            }
          } else if (data.type === 'interrupt') {
            if (!data.session_id || data.session_id === conversationId) {
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
            }
          } else if (data.type === 'task_completed') {
            if (!data.session_id || data.session_id === conversationId) {
              setLoading(false);
              setTaskStatus(data.success ? 'completed' : 'failed');
              setActiveAgents([]);
              setWaitingAgent(null);

              if (conversationId) {
                fetch(apiUrl(`/api/conversations/${conversationId}`))
                  .then(res => res.json())
                  .then(convData => {
                    if (convData && convData.messages) {
                      setMessages(convData.messages);
                      if (convData.activities) setActivities(convData.activities);
                    }
                  })
                  .catch(console.error);
              } else {
                if (data.success && data.content) {
                  const botMsg: ChatMessage = {
                    id: String(Date.now()),
                    role: 'assistant',
                    agent_name: data.agent || 'Manager',
                    content: data.content,
                    created_at: new Date().toISOString()
                  };
                  setMessages(prev => [...prev, botMsg]);
                } else if (!data.success) {
                  const errorMsg: ChatMessage = {
                    id: String(Date.now()),
                    role: 'assistant',
                    agent_name: data.agent || 'Workforce',
                    content: '',
                    created_at: new Date().toISOString(),
                    metadata: {
                      is_error: true,
                      error: data.error_details || { message: data.error || 'Task failed.' }
                    }
                  };
                  setMessages(prev => [...prev, errorMsg]);
                }
              }
            }
            onConversationUpdated();
          } else if (data.type === 'task_stopped') {
            if (!data.session_id || data.session_id === conversationId) {
              setLoading(false);
              setTaskStatus('interrupted');
              setActiveAgents([]);
              setWaitingAgent(null);
              showToast('Task execution stopped by user.', 'info');
              if (conversationId) {
                fetch(apiUrl(`/api/conversations/${conversationId}`))
                  .then(res => res.json())
                  .then(convData => {
                    if (convData) {
                      if (convData.messages) setMessages(convData.messages);
                      if (convData.activities) setActivities(convData.activities);
                    }
                  })
                  .catch(console.error);
              }
            }
            onConversationUpdated();
          } else if (data.type === 'error') {
            if (!data.session_id || data.session_id === conversationId) {
              setLoading(false);
              setTaskStatus('failed');
              setActiveAgents([]);
              setWaitingAgent(null);
              if (conversationId) {
                fetch(apiUrl(`/api/conversations/${conversationId}`))
                  .then(res => res.json())
                  .then(convData => {
                    if (convData && convData.messages) {
                      setMessages(convData.messages);
                      if (convData.activities) setActivities(convData.activities);
                    }
                  })
                  .catch(console.error);
              } else {
                const errorMsg: ChatMessage = {
                  id: String(Date.now()),
                  role: 'assistant',
                  agent_name: 'Workforce',
                  content: '',
                  created_at: new Date().toISOString(),
                  metadata: {
                    is_error: true,
                    error: { message: data.message || 'Task encountered an error.', code: 'TASK_FAILED', retryable: true }
                  }
                };
                setMessages(prev => [...prev, errorMsg]);
              }
            }
          }
        } catch (err) {
          console.error('Error processing WebSocket message:', err);
        }
      };

      ws.onerror = () => {
        if (!isMounted) return;
        setLoading(false);
      };

      ws.onclose = (event) => {
        if (!isMounted) return;
        setIsConnected(false);
        if (event.code !== 1000 && event.code !== 1001) {
          const attempts = reconnectAttemptsRef.current;
          if (attempts < 5) {
            const delay = Math.min(1000 * Math.pow(2, attempts), 10000);
            reconnectAttemptsRef.current += 1;
            reconnectTimeoutRef.current = setTimeout(() => {
              if (isMounted) connectWebSocket();
            }, delay);
          }
        }
      };
    };

    connectWebSocket();

    return () => {
      isMounted = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (socketRef.current) {
        socketRef.current.close(1000);
      }
    };
  }, [conversationId]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activities, loading]);

  const handleSend = () => {
    if (!hasWorkspace) {
      if (onOpenWorkspaceModal) onOpenWorkspaceModal();
      return;
    }
    if (!input.trim() || loading) return;

    const userPrompt = input.trim();
    setInput('');

    // Generate atomic session ID if in draft mode
    const activeId = conversationId || ('conv_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 8));

    const cleanLine = userPrompt.split('\n')[0].trim().replace(/^[#*\-–—\d.\s]+/, '');
    const tempTitle = cleanLine.length > 45 ? cleanLine.slice(0, 42) + '...' : (cleanLine || 'New Task');

    const userMsg: ChatMessage = {
      id: String(Date.now()),
      role: 'user',
      content: userPrompt,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);
    setActivities([]);
    setLoading(true);
    setTaskStatus('active');

    if (!conversationId && onSelectConversation) {
      onSelectConversation(activeId, tempTitle);
    }

    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({
        type: 'run_task',
        content: userPrompt,
        session_id: activeId
      }));
    } else {
      showToast('Connecting to workforce server...', 'info');
    }
  };

  const handleStopTask = () => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: 'stop', session_id: conversationId || undefined }));
    }
  };

  const handleInterruptResponse = (response: string) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({
        type: 'interrupt_response',
        content: response,
        session_id: conversationId || undefined
      }));
      setWaitingAgent(null);
    }
  };

  const handleEditMessage = async (messageId: string, newContent: string) => {
    if (!conversationId) return;

    try {
      let targetId = messageId;
      const checkRes = await fetch(apiUrl(`/api/conversations/${conversationId}`));
      if (checkRes.ok) {
        const convData = await checkRes.json();
        if (convData && convData.messages && convData.messages.length > 0) {
          const match = convData.messages.find((m: any) => m.id === messageId);
          if (!match) {
            const userMsgMatch = convData.messages.find((m: any) => m.role === 'user');
            if (userMsgMatch) {
              targetId = userMsgMatch.id;
            }
          }
        }
      }

      const res = await fetch(apiUrl(`/api/conversations/${conversationId}/messages/${targetId}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: newContent, truncate_after: true })
      });

      if (res.ok) {
        const updatedConv = await res.json();
        if (updatedConv && updatedConv.messages) {
          setMessages(updatedConv.messages);
        }
        setActivities([]);
        setLoading(true);
        setTaskStatus('active');

        if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.send(JSON.stringify({
            type: 'retry_user',
            session_id: conversationId,
            message_id: targetId,
            content: newContent
          }));
        }
      }
    } catch (err) {
      console.error('Failed to edit message', err);
      showToast('Failed to edit message', 'error');
    }
  };

  const handleDeleteMessage = async (messageId: string) => {
    if (!conversationId) return;

    try {
      let targetId = messageId;
      const checkRes = await fetch(apiUrl(`/api/conversations/${conversationId}`));
      if (checkRes.ok) {
        const convData = await checkRes.json();
        if (convData && convData.messages && convData.messages.length > 0) {
          const match = convData.messages.find((m: any) => m.id === messageId);
          if (!match) {
            const userMsgMatch = convData.messages.find((m: any) => m.role === 'user');
            if (userMsgMatch) {
              targetId = userMsgMatch.id;
            }
          }
        }
      }

      const res = await fetch(apiUrl(`/api/conversations/${conversationId}/messages/${targetId}`), {
        method: 'DELETE'
      });
      if (res.ok) {
        const updatedConv = await res.json();
        if (updatedConv && updatedConv.messages) {
          setMessages(updatedConv.messages);
        }
        onConversationUpdated();
        showToast('Message deleted.', 'info');
      }
    } catch (err) {
      console.error('Failed to delete message', err);
      showToast('Failed to delete message', 'error');
    }
  };

  const handleRetryUser = (messageId: string, content: string) => {
    handleEditMessage(messageId, content);
  };

  const handleRetryResponse = () => {
    if (!conversationId) return;
    setActivities([]);
    setLoading(true);
    setTaskStatus('active');

    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({
        type: 'retry_response',
        session_id: conversationId
      }));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const hasMessages = messages.length > 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', backgroundColor: 'hsl(var(--bg))' }}>
      {/* Top Presence Bar */}
      <WorkforcePresence
        teamName={teamInfo.name}
        agents={teamInfo.agents}
        activeAgents={activeAgents}
        waitingAgent={waitingAgent}
      />

      {/* Reconnection Banner */}
      {!isConnected && (
        <div
          data-testid="ws-disconnected-banner"
          style={{
            padding: '8px 24px',
            backgroundColor: 'hsl(var(--warning-bg))',
            borderBottom: '1px solid hsl(var(--warning)/0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '12.5px',
            color: 'hsl(var(--warning))',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div className="status-dot active" style={{ backgroundColor: 'hsl(var(--warning))' }} />
            <span>{t('connectionLost')}</span>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '2px 10px', fontSize: '11px', height: '26px' }}
            onClick={() => {
              if (socketRef.current) {
                socketRef.current.close();
              }
            }}
          >
            {t('retry')}
          </button>
        </div>
      )}

      {/* Messages Scroll Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 0', display: 'flex', flexDirection: 'column' }}>
        {!hasWorkspace ? (
          /* No Active Workspace Warning */
          <div style={{
            maxWidth: '520px',
            margin: 'auto',
            textAlign: 'center',
            padding: '40px 24px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center'
          }}>
            <div style={{
              width: '60px',
              height: '60px',
              borderRadius: '16px',
              backgroundColor: 'hsl(var(--primary)/0.12)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '20px'
            }}>
              <img
                src={isDark ? "/brand/logo_bianco.svg" : "/brand/logo_viola.svg"}
                alt="Aether"
                width="34"
                height="34"
                style={{ display: 'block' }}
              />
            </div>

            <h2 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '8px', color: 'hsl(var(--fg))' }}>
              {t('firstCreateWorkspace')}
            </h2>
            <p className="text-muted" style={{ fontSize: '14px', maxWidth: '440px', marginBottom: '24px', lineHeight: 1.6 }}>
              {t('firstCreateWorkspaceDesc')}
            </p>

            <button
              className="btn btn-primary"
              style={{ padding: '10px 22px', fontSize: '14px', display: 'inline-flex', alignItems: 'center', gap: '8px' }}
              onClick={onOpenWorkspaceModal}
            >
              <Plus size={16} />
              <span>{language === 'it' ? '+ Crea workspace' : '+ Create workspace'}</span>
            </button>
          </div>
        ) : !hasMessages ? (
          /* Empty / Draft Welcome State */
          <div style={{
            maxWidth: '680px',
            margin: 'auto',
            textAlign: 'center',
            padding: '40px 20px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center'
          }}>
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '16px',
              backgroundColor: 'hsl(var(--primary)/0.12)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'hsl(var(--primary))',
              marginBottom: '20px'
            }}>
              <Sparkles size={28} />
            </div>

            <h2 style={{ fontSize: '24px', fontWeight: 600, marginBottom: '8px' }}>
              {t('emptyChatTitle')}
            </h2>
            <p className="text-muted" style={{ fontSize: '14px', maxWidth: '480px', marginBottom: '28px', lineHeight: 1.5 }}>
              {t('emptyChatSubtitle')}
            </p>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center', maxWidth: '540px' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setInput(t('promptSuggestion1Prompt'))}
              >
                {t('promptSuggestion1Title')}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setInput(t('promptSuggestion2Prompt'))}
              >
                {t('promptSuggestion2Title')}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setInput(t('promptSuggestion3Prompt'))}
              >
                {t('promptSuggestion3Title')}
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
                onRetry={(content) => handleRetryUser(msg.id, content)}
                onEditMessage={handleEditMessage}
                onDeleteMessage={handleDeleteMessage}
                onRetryResponse={handleRetryResponse}
              />
            ))}

            {/* Activities Stream (Persisted & Live) */}
            {activities.length > 0 && (
              <div style={{ padding: '0 24px' }}>
                <ActivityFeed activities={activities} isLive={loading} taskStatus={taskStatus} />
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
            ref={textareaRef}
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
            placeholder={!hasWorkspace ? t('createWorkspaceFirstPlaceholder') : t('chatInputPlaceholder')}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            disabled={!hasWorkspace || loading}
          />

          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '8px 12px 10px',
            borderTop: '1px solid hsl(var(--border)/0.3)'
          }}>
            <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
              {t('chatKeyboardHint')}
            </div>

            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              {loading ? (
                <button
                  type="button"
                  className="btn btn-destructive"
                  style={{ height: '34px', padding: '0 14px', gap: '6px' }}
                  onClick={handleStopTask}
                >
                  <Square size={13} fill="currentColor" />
                  <span>{t('stop')}</span>
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ height: '34px', padding: '0 16px', gap: '6px' }}
                  onClick={handleSend}
                  disabled={!hasWorkspace || !input.trim()}
                >
                  <Send size={13} />
                  <span>{t('runTask')}</span>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
