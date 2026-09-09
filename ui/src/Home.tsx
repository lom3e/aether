import { useState, useEffect, useContext, useRef } from 'react';
import {
  Sparkles, Send, CheckCircle2, Clock, AlertTriangle, ArrowRight,
  Plus, Calendar, FileText, Users, Activity, Check, X, Shield, RefreshCw,
  Mic, MicOff, Volume2, VolumeX, ExternalLink
} from 'lucide-react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { ToastContext } from './toast';
import { AutoArchitectModal } from './AutoArchitectModal';
import { TopHeader } from './TopHeader';
import { NotificationCenter } from './NotificationCenter';

interface HomeProps {
  navigate: (view: string, params?: any) => void;
  workspaceName: string;
  onNewTask?: () => void;
  onSelectConversation?: (id: string) => void;
  conversations?: any[];
  onOpenWorkspaceModal?: () => void;
}

interface StepItem {
  id: string;
  title: string;
  status: string;
  category: string;
  details?: any;
}

interface PersonalMsg {
  id: string;
  role: string;
  content: string;
  tier: string;
  steps: StepItem[];
  action_execution_id?: string;
  mission_id?: string;
  created_at: string;
}

export function Home({
  navigate,
  workspaceName,
  onNewTask,
  onOpenWorkspaceModal,
}: HomeProps) {
  const [promptInput, setPromptInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<PersonalMsg[]>([]);
  const [overview, setOverview] = useState<any>({
    pending_approvals: [],
    recent_activities: [],
    connected_apps_count: 0,
    active_works: [],
    recent_works: [],
    background_tasks: [],
    unread_notifications: 0,
  });
  const [isAutoArchitectOpen, setIsAutoArchitectOpen] = useState(false);

  // Voice state
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null);
  const recognitionRef = useRef<any>(null);

  const showToast = useContext(ToastContext);
  const { t } = useTranslation();

  const fetchOverview = () => {
    if (!workspaceName) return;
    fetch(apiUrl(`/api/personal/overview?workspace_id=${encodeURIComponent(workspaceName)}`))
      .then(res => res.json())
      .then(data => {
        if (data && typeof data === 'object') {
          setOverview(data);
        }
      })
      .catch(console.error);
  };

  useEffect(() => {
    if (workspaceName) {
      fetchOverview();
    }
  }, [workspaceName]);

  // Real-time SSE Connection (Phase D Event Hub)
  useEffect(() => {
    if (!workspaceName) return;

    let eventSource: EventSource | null = null;
    try {
      const token = (typeof window !== 'undefined' && (window as any).__AETHER_SESSION_TOKEN__) || '';
      const tokenQuery = token ? `&token=${encodeURIComponent(token)}` : '';
      eventSource = new EventSource(apiUrl(`/api/personal/events?workspace_id=${encodeURIComponent(workspaceName)}${tokenQuery}`));

      eventSource.addEventListener('step_update', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (data && data.step) {
            setMessages(prev => {
              if (prev.length === 0) return prev;
              const last = prev[prev.length - 1];
              if (last.role === 'assistant') {
                const exists = last.steps.some(s => s.id === data.step.id);
                const updated = exists
                  ? last.steps.map(s => s.id === data.step.id ? data.step : s)
                  : [...last.steps, data.step];
                return [...prev.slice(0, -1), { ...last, steps: updated }];
              }
              return prev;
            });
          }
        } catch {
          // Ignore parse errors
        }
      });

      eventSource.addEventListener('task_progress', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (data) {
            setOverview((prev: any) => {
              const bgTasks = prev.background_tasks || [];
              const exists = bgTasks.some((t: any) => t.id === data.task_id);
              const updated = exists
                ? bgTasks.map((t: any) => t.id === data.task_id ? {
                    ...t,
                    progress_pct: data.progress_pct,
                    current_step: data.step_title,
                    status: data.status,
                  } : t)
                : [{
                    id: data.task_id,
                    title: data.step_title,
                    status: data.status,
                    progress_pct: data.progress_pct,
                    current_step: data.step_title,
                  }, ...bgTasks];
              return { ...prev, background_tasks: updated };
            });
          }
        } catch {
          // Ignore
        }
      });

      eventSource.addEventListener('task_completed', () => {
        fetchOverview();
      });

      eventSource.addEventListener('notification', () => {
        fetchOverview();
      });
    } catch (err) {
      console.debug('EventSource not connected', err);
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [workspaceName]);

  // Voice Web Speech Recognition initialization
  useEffect(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      const rec = new SpeechRecognition();
      rec.continuous = false;
      rec.interimResults = true;
      rec.lang = 'en-US';

      rec.onresult = (event: any) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
        }
        if (transcript) {
          setPromptInput(transcript);
        }
      };

      rec.onerror = () => {
        setIsListening(false);
      };

      rec.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = rec;
    }
  }, []);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      showToast('Speech recognition not supported in this browser.', 'warning');
      return;
    }
    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
        showToast('Listening... Speak your request.', 'info');
      } catch (e) {
        console.error(e);
      }
    }
  };

  const handleSpeakText = (msgId: string, text: string) => {
    if (!('speechSynthesis' in window)) {
      showToast('Audio synthesis not supported in this browser.', 'warning');
      return;
    }
    if (isSpeaking && speakingMessageId === msgId) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      setSpeakingMessageId(null);
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => {
      setIsSpeaking(false);
      setSpeakingMessageId(null);
    };
    utterance.onerror = () => {
      setIsSpeaking(false);
      setSpeakingMessageId(null);
    };
    setIsSpeaking(true);
    setSpeakingMessageId(msgId);
    window.speechSynthesis.speak(utterance);
  };

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

  const handleSendPrompt = async (promptText: string) => {
    const text = promptText.trim();
    if (!text || isSubmitting) return;

    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
    }

    setIsSubmitting(true);
    const userMsg: PersonalMsg = {
      id: `usr-${Date.now()}`,
      role: 'user',
      content: text,
      tier: 'answer',
      steps: [],
      created_at: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMsg]);
    setPromptInput('');

    try {
      const res = await fetch(apiUrl('/api/personal/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: text,
          session_id: currentSessionId,
          workspace_id: workspaceName,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setCurrentSessionId(data.session_id);
        setMessages(prev => [...prev, data]);
        fetchOverview();
      } else {
        showToast('Error processing request.', 'error');
      }
    } catch (err) {
      console.error('Chat error', err);
      showToast('Network error while contacting Aether.', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleApproveAction = async (executionId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/actions/executions/${executionId}/approve`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approver: 'user' }),
      });
      if (res.ok) {
        showToast('Action confirmed and executed.', 'success');
        fetchOverview();
        // Update local message step status
        setMessages(prev => prev.map(msg => {
          if (msg.action_execution_id === executionId) {
            return {
              ...msg,
              steps: msg.steps.map(s => s.status === 'pending_approval' ? { ...s, status: 'completed', title: 'Action approved & executed' } : s),
            };
          }
          return msg;
        }));
      }
    } catch {
      showToast('Error approving action.', 'error');
    }
  };

  const handleRejectAction = async (executionId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/actions/executions/${executionId}/reject`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Declined by user' }),
      });
      if (res.ok) {
        showToast('Action declined.', 'info');
        fetchOverview();
        setMessages(prev => prev.map(msg => {
          if (msg.action_execution_id === executionId) {
            return {
              ...msg,
              steps: msg.steps.map(s => s.status === 'pending_approval' ? { ...s, status: 'failed', title: 'Action declined' } : s),
            };
          }
          return msg;
        }));
      }
    } catch {
      showToast('Error declining action.', 'error');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', flex: 1 }}>
      <TopHeader
        title="Personal Aether"
        subtitle={workspaceName}
        icon={Sparkles}
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <NotificationCenter workspaceName={workspaceName} onNavigate={navigate} />
            <button
              className="btn btn-ghost"
              onClick={fetchOverview}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
            >
              <RefreshCw size={14} /> Refresh
            </button>
          </div>
        }
      />
      <div style={{ flex: 1, overflowY: 'auto', padding: '32px 28px', maxWidth: '1000px', margin: '0 auto', width: '100%' }}>
        {/* Top Banner */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '28px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                Personal Aether
              </h1>
              <span className="badge badge-primary" style={{ fontSize: '12px', padding: '2px 8px' }}>
                {workspaceName}
              </span>
            </div>
            <p style={{ margin: '4px 0 0', fontSize: '14px', color: 'hsl(var(--muted-fg))' }}>
              Your operational AI companion. Your AI Workforce is ready. State your goal, and Aether takes care of it.
            </p>
          </div>
        </div>

        {/* Main Companion Input Box */}
        <div className="card" style={{
          padding: '24px',
          borderRadius: '16px',
          boxShadow: '0 8px 30px rgba(0,0,0,0.06)',
          marginBottom: '28px',
          border: '1px solid hsl(var(--primary)/0.2)',
          backgroundColor: 'hsl(var(--card))',
        }}>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
            <div style={{
              width: '40px',
              height: '40px',
              borderRadius: '12px',
              backgroundColor: isListening ? '#ef444420' : 'hsl(var(--primary)/0.15)',
              color: isListening ? '#ef4444' : 'hsl(var(--primary))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              transition: 'all 0.2s ease',
            }}>
              {isListening ? <Mic size={22} className="animate-pulse" /> : <Sparkles size={22} />}
            </div>
            <div style={{ flex: 1 }}>
              <textarea
                data-testid="companion-input-field"
                className="input"
                rows={2}
                placeholder={isListening ? "Listening... Speak your goal clearly" : "What would you like Aether to take care of? (e.g. 'Schedule a meeting with Sarah tomorrow', 'Create a brief', 'Run full market analysis')"}
                value={promptInput}
                onChange={e => setPromptInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendPrompt(promptInput);
                  }
                }}
                style={{ width: '100%', resize: 'none', fontSize: '14px', lineHeight: 1.5, border: 'none', outline: 'none', padding: '4px 0', background: 'transparent' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '12px', paddingTop: '10px', borderTop: '1px solid hsl(var(--border)/0.5)' }}>
                {/* Suggestion Chips */}
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => {
                      if (onNewTask) onNewTask();
                      else handleSendPrompt('New task');
                    }}
                    style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '12px', backgroundColor: 'hsl(var(--muted)/0.5)' }}
                  >
                    <Plus size={12} style={{ marginRight: '4px' }} /> Start a Task
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => handleSendPrompt('Schedule a meeting with Team tomorrow at 10am')}
                    style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '12px', backgroundColor: 'hsl(var(--muted)/0.5)' }}
                  >
                    <Calendar size={12} style={{ marginRight: '4px' }} /> Schedule Meeting
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => handleSendPrompt('Create a document named summary.md with product notes')}
                    style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '12px', backgroundColor: 'hsl(var(--muted)/0.5)' }}
                  >
                    <FileText size={12} style={{ marginRight: '4px' }} /> Create Document
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => handleSendPrompt('Launch mission: Analyze competitive landscape for Q4')}
                    style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '12px', backgroundColor: 'hsl(var(--muted)/0.5)' }}
                  >
                    <Users size={12} style={{ marginRight: '4px' }} /> Delegate to Workforce
                  </button>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {/* Push-to-Talk Microphone Button */}
                  <button
                    type="button"
                    data-testid="voice-mic-btn"
                    onClick={toggleListening}
                    title={isListening ? "Stop listening" : "Voice input (push to speak)"}
                    className={`btn ${isListening ? 'btn-danger' : 'btn-ghost'}`}
                    style={{
                      padding: '6px 10px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '13px',
                      color: isListening ? '#ef4444' : undefined,
                    }}
                  >
                    {isListening ? <MicOff size={16} /> : <Mic size={16} />}
                    <span style={{ fontSize: '12px' }}>{isListening ? 'Listening...' : 'Voice'}</span>
                  </button>

                  <button
                    data-testid="companion-submit-btn"
                    className="btn btn-primary"
                    disabled={!promptInput.trim() || isSubmitting}
                    onClick={() => handleSendPrompt(promptInput)}
                    style={{ padding: '6px 16px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                  >
                    {isSubmitting ? 'Thinking...' : 'Take Care of It'}
                    <Send size={14} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Live Conversation Stream (if any) */}
        {messages.length > 0 && (
          <div data-testid="companion-messages-container" style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '32px' }}>
            {messages.map(msg => (
              <div
                key={msg.id}
                className="card"
                style={{
                  padding: '18px 22px',
                  borderRadius: '14px',
                  backgroundColor: msg.role === 'user' ? 'hsl(var(--muted)/0.3)' : 'hsl(var(--card))',
                  border: msg.role === 'user' ? '1px solid hsl(var(--border))' : '1px solid hsl(var(--primary)/0.25)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 600, fontSize: '13px', color: msg.role === 'user' ? 'hsl(var(--fg))' : 'hsl(var(--primary))' }}>
                      {msg.role === 'user' ? 'You' : 'Personal Aether'}
                    </span>
                    <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                      {msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                    </span>
                  </div>

                  {msg.role === 'assistant' && (
                    <button
                      type="button"
                      onClick={() => handleSpeakText(msg.id, msg.content)}
                      title={isSpeaking && speakingMessageId === msg.id ? "Stop audio" : "Read aloud"}
                      className="btn btn-ghost"
                      style={{ padding: '4px', height: 'auto', color: 'hsl(var(--muted-fg))' }}
                    >
                      {isSpeaking && speakingMessageId === msg.id ? <VolumeX size={15} color="hsl(var(--primary))" /> : <Volume2 size={15} />}
                    </button>
                  )}
                </div>

                {/* Steps Stepper */}
                {msg.steps && msg.steps.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', margin: '10px 0 14px', padding: '10px 14px', backgroundColor: 'hsl(var(--muted)/0.2)', borderRadius: '8px' }}>
                    {msg.steps.map(st => (
                      <div key={st.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
                        {st.status === 'completed' ? (
                          <CheckCircle2 size={14} color="#10b981" />
                        ) : st.status === 'pending_approval' ? (
                          <AlertTriangle size={14} color="#f59e0b" />
                        ) : (
                          <Clock size={14} color="hsl(var(--primary))" />
                        )}
                        <span style={{ fontWeight: 500, color: st.status === 'pending_approval' ? '#f59e0b' : 'hsl(var(--fg))' }}>
                          {st.title}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                <div style={{ fontSize: '14px', lineHeight: 1.6, color: 'hsl(var(--fg))', whiteSpace: 'pre-wrap' }}>
                  {msg.content}
                </div>

                {/* Pending Approval Action Card in Message */}
                {msg.action_execution_id && msg.steps.some(s => s.status === 'pending_approval') && (
                  <div style={{ marginTop: '14px', padding: '12px 16px', borderRadius: '10px', backgroundColor: '#f59e0b10', border: '1px solid #f59e0b40', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Shield size={16} color="#f59e0b" />
                      <span style={{ fontSize: '13px', fontWeight: 600, color: '#f59e0b' }}>Confirmation Required</span>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        className="btn btn-ghost"
                        onClick={() => handleRejectAction(msg.action_execution_id!)}
                        style={{ fontSize: '12px', padding: '4px 10px', color: 'hsl(var(--destructive))' }}
                      >
                        <X size={13} style={{ marginRight: '4px' }} /> Decline
                      </button>
                      <button
                        className="btn btn-primary"
                        onClick={() => handleApproveAction(msg.action_execution_id!)}
                        style={{ fontSize: '12px', padding: '4px 14px', backgroundColor: '#10b981', borderColor: '#10b981' }}
                      >
                        <Check size={13} style={{ marginRight: '4px' }} /> Approve
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Real-time Background Operations (Phase D Background Tasks) */}
        {overview.background_tasks && overview.background_tasks.length > 0 && (
          <div data-testid="background-tasks-section" style={{ marginBottom: '32px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Clock size={16} className="text-primary" />
                <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                  Operational Tasks ({overview.background_tasks.length})
                </h2>
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {overview.background_tasks.map((task: any) => (
                <div
                  key={task.id}
                  className="card"
                  data-testid="background-task-card"
                  style={{
                    padding: '16px 20px',
                    borderRadius: '12px',
                    border: '1px solid hsl(var(--border))',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <span style={{ fontWeight: 600, fontSize: '14px' }}>{task.title || 'Operational Background Task'}</span>
                      <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                        {task.current_step || task.status}
                      </div>
                    </div>
                    <span
                      className={`badge ${task.status === 'completed' ? 'badge-success' : task.status === 'running' ? 'badge-primary' : 'badge-warning'}`}
                      style={{ fontSize: '11px', textTransform: 'capitalize' }}
                    >
                      {task.status}
                    </span>
                  </div>

                  {/* Progress Bar */}
                  <div style={{ width: '100%', height: '6px', borderRadius: '3px', backgroundColor: 'hsl(var(--muted))', overflow: 'hidden' }}>
                    <div
                      style={{
                        width: `${task.progress_pct || (task.status === 'completed' ? 100 : 25)}%`,
                        height: '100%',
                        backgroundColor: task.status === 'completed' ? '#10b981' : 'hsl(var(--primary))',
                        transition: 'width 0.4s ease',
                      }}
                    />
                  </div>

                  {task.deliverable_path && (
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
                      <button
                        className="btn btn-ghost"
                        onClick={() => navigate('missions')}
                        style={{ fontSize: '12px', padding: '4px 8px', color: 'hsl(var(--primary))', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                      >
                        <ExternalLink size={12} /> View Deliverable
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Pending Approvals Global Section (if any exists in workspace) */}
        {overview.pending_approvals && overview.pending_approvals.length > 0 && (
          <div style={{ marginBottom: '32px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <Shield size={18} color="#f59e0b" />
              <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                Pending Approvals ({overview.pending_approvals.length})
              </h2>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {overview.pending_approvals.map((appr: any) => (
                <div
                  key={appr.execution_id}
                  className="card"
                  style={{
                    padding: '16px 20px',
                    borderRadius: '12px',
                    border: '1px solid #f59e0b50',
                    backgroundColor: '#f59e0b08',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '15px' }}>{appr.action_name}</div>
                    <div style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                      {appr.description} • {JSON.stringify(appr.input_data)}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      className="btn btn-ghost"
                      onClick={() => handleRejectAction(appr.execution_id)}
                      style={{ fontSize: '12px', padding: '6px 12px', color: 'hsl(var(--destructive))' }}
                    >
                      Decline
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={() => handleApproveAction(appr.execution_id)}
                      style={{ fontSize: '12px', padding: '6px 16px', backgroundColor: '#10b981', borderColor: '#10b981' }}
                    >
                      Approve
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Hub Cards Grid: Work, Connections, Activity */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '28px' }}>
          {/* Work Hub Card */}
          <div
            className="card"
            style={{ padding: '20px', borderRadius: '12px', cursor: 'pointer' }}
            onClick={() => navigate('missions')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '15px' }}>
                <Users size={18} color="hsl(var(--primary))" /> Work in Progress
              </div>
              <ArrowRight size={16} color="hsl(var(--muted-fg))" />
            </div>
            <div style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
              {overview.active_works?.length > 0 ? (
                <span><strong>{overview.active_works.length}</strong> active missions running with digital workforce.</span>
              ) : (
                <span>No active missions. Click to view deliverables and execution history.</span>
              )}
            </div>
          </div>

          {/* Connections Hub Card */}
          <div
            className="card"
            style={{ padding: '20px', borderRadius: '12px', cursor: 'pointer' }}
            onClick={() => navigate('connections')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '15px' }}>
                <Calendar size={18} color="#4285F4" /> Connections & Apps
              </div>
              <ArrowRight size={16} color="hsl(var(--muted-fg))" />
            </div>
            <div style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
              <span><strong>{overview.connected_apps_count || 1}</strong> apps connected (Calendar sync active).</span>
            </div>
          </div>

          {/* Activity Hub Card */}
          <div
            className="card"
            style={{ padding: '20px', borderRadius: '12px', cursor: 'pointer' }}
            onClick={() => navigate('activity')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '15px' }}>
                <Activity size={18} color="#10b981" /> Activity Feed
              </div>
              <ArrowRight size={16} color="hsl(var(--muted-fg))" />
            </div>
            <div style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
              <span>View plain-language audit trail of operations and outcomes.</span>
            </div>
          </div>
        </div>

        {/* AutoArchitect Modal */}
        {isAutoArchitectOpen && (
          <AutoArchitectModal
            isOpen={isAutoArchitectOpen}
            onClose={() => setIsAutoArchitectOpen(false)}
            onSuccess={() => fetchOverview()}
          />
        )}
      </div>
    </div>
  );
}
