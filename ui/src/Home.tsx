import { useState, useEffect, useContext, useRef } from 'react';
import { translateStepTitle } from './stepTitles';
import {
  Sparkles, Send, CheckCircle2, Clock, AlertTriangle, ArrowRight,
  Plus, Calendar, FileText, Users, Activity, Check, X, Shield, RefreshCw,
  Mic, MicOff, Volume2, VolumeX, ExternalLink, Loader2
} from 'lucide-react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { ToastContext } from './toast';
import { AutoArchitectModal } from './AutoArchitectModal';
import { TopHeader } from './TopHeader';
import { NotificationCenter } from './NotificationCenter';
import { submitApprovalDecision, approvalToastKind, approvalIsFinished, approvalIsInProgress } from './canonicalNotification';

interface HomeProps {
  navigate: (view: string, params?: any) => void;
  workspaceName: string;
  initialApprovalId?: string | null;
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
  session_id?: string;
  metadata?: Record<string, any>;
  created_at: string;
}

export function Home({
  navigate,
  workspaceName,
  initialApprovalId,
  onNewTask,
  onOpenWorkspaceModal,
}: HomeProps) {
  const [promptInput, setPromptInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
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

  // Deep-link auto-scroll and focus for pending approvals
  useEffect(() => {
    if (initialApprovalId && overview.pending_approvals?.length > 0) {
      const el = document.getElementById(`approval-card-${initialApprovalId}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [initialApprovalId, overview.pending_approvals]);

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
      showToast(t('homeUiSpeechRecognitionNotSupportedInThis'), 'warning');
      return;
    }
    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
        showToast(t('homeUiListeningSpeakYourRequest'), 'info');
      } catch (e) {
        console.error(e);
      }
    }
  };

  const handleSpeakText = (msgId: string, text: string) => {
    if (!('speechSynthesis' in window)) {
      showToast(t('homeUiAudioSynthesisNotSupportedInThis'), 'warning');
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
        const errData = await res.json().catch(() => ({}));
        const errMsg = errData.detail || t('homeUiErrorProcessingRequest');
        showToast(errMsg, 'error');
        setMessages(prev => [...prev, {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `⚠️ **Request failed:** ${errMsg}`,
          tier: 'answer',
          steps: [{
            id: `step-err-${Date.now()}`,
            title: t('homeUiRequestFailed'),
            status: 'failed',
            category: 'error',
            details: { error: errMsg },
          }],
          created_at: new Date().toISOString(),
        }]);
      }
    } catch (err: any) {
      console.error(t('sdChatError'), err);
      const errMsg = err?.message || t('homeUiNetworkErrorWhileContactingAether');
      showToast(errMsg, 'error');
      setMessages(prev => [...prev, {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ **Network error:** ${errMsg}`,
        tier: 'answer',
        steps: [{
          id: `step-err-${Date.now()}`,
          title: t('homeUiNetworkConnectionFailed'),
          status: 'failed',
          category: 'error',
          details: { error: errMsg },
        }],
        created_at: new Date().toISOString(),
      }]);
    } finally {
      setIsSubmitting(false);
    }
  };

  useEffect(() => {
    if (initialApprovalId && overview.pending_approvals?.length > 0) {
      setTimeout(() => {
        const el = document.getElementById(`approval-card-${initialApprovalId}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 300);
    }
  }, [initialApprovalId, overview.pending_approvals]);

  const handleApproveAction = async (executionId: string) => {
    if (actionLoading === executionId) return;
    setActionLoading(executionId);
    try {
      const res = await submitApprovalDecision({
        target_type: 'action_execution',
        target_id: executionId,
        decision: 'approve',
        approver: 'user',
        workspaceName,
      });

      if (res.success) {
        showToast(res.message, approvalToastKind(res, 'approve'));
        fetchOverview();
        // Update the local step with what really happened: finished, still going, or merely started.
        const finished = approvalIsFinished(res);
        const inProgress = approvalIsInProgress(res);
        setMessages(prev => prev.map(msg => {
          if (msg.action_execution_id === executionId) {
            return {
              ...msg,
              steps: msg.steps.map(s => (s.status === 'pending_approval' || s.status === 'waiting_approval')
                ? (finished
                    ? { ...s, status: 'completed', title: t('homeUiActionApprovedExecuted') }
                    : inProgress
                    ? { ...s, status: 'running', title: t('homeUiActionApprovedStillInProgress') }
                    : { ...s, status: 'running', title: t('homeUiActionApproved') })
                : s),
            };
          }
          return msg;
        }));
      } else {
        showToast(res.message, 'error');
        fetchOverview(); // the action may have failed after approval: show its real state
        setMessages(prev => prev.map(msg => {
          if (msg.action_execution_id === executionId && res.status === 'failed') {
            return {
              ...msg,
              steps: msg.steps.map(s => (s.status === 'pending_approval' || s.status === 'waiting_approval') ? { ...s, status: 'failed', title: t('homeUiActionApprovedButFailed') } : s),
            };
          }
          return msg;
        }));
      }
    } catch (err: any) {
      showToast(err.message || t('homeUiErrorApprovingAction'), 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRejectAction = async (executionId: string) => {
    if (actionLoading === executionId) return;
    setActionLoading(executionId);
    try {
      const res = await submitApprovalDecision({
        target_type: 'action_execution',
        target_id: executionId,
        decision: 'reject',
        reason: t('sdDeclinedByUser'),
        workspaceName,
      });

      if (res.success) {
        showToast(res.message, 'info');
        fetchOverview();
        setMessages(prev => prev.map(msg => {
          if (msg.action_execution_id === executionId) {
            return {
              ...msg,
              steps: msg.steps.map(s => (s.status === 'pending_approval' || s.status === 'waiting_approval') ? { ...s, status: 'failed', title: t('homeUiActionDeclined') } : s),
            };
          }
          return msg;
        }));
      } else {
        showToast(res.message, 'error');
      }
    } catch (err: any) {
      showToast(err.message || t('homeUiErrorDecliningAction'), 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleApproveProposal = async (proposalId: string) => {
    if (actionLoading === proposalId) return;
    setActionLoading(proposalId);
    try {
      const res = await fetch(apiUrl(`/api/personal/proposals/${encodeURIComponent(proposalId)}/accept`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (res.ok) {
        const accepted = await res.json().catch(() => ({} as any));
        showToast(t('homeUiProposalAcceptedAndAuthorizedForExecution'), 'success');
        fetchOverview();
        setMessages(prev => prev.map(msg => {
          if (msg.metadata?.proposal_id === proposalId) {
            return {
              ...msg,
              metadata: { ...msg.metadata, status: 'accepted' },
              steps: msg.steps.map(s => s.details?.proposal_id === proposalId ? { ...s, status: 'completed', title: t('homeUiProposalAccepted') } : s),
            };
          }
          return msg;
        }));

        // Acceptance only grants the authority: the work starts when the request is sent again WITH it (the backend
        // still asks for any further approval). Without this step nothing ever ran after "accepted".
        const authority = accepted?.authority;
        const proposalIdx = messages.findIndex(m => m.metadata?.proposal_id === proposalId);
        const original = [...messages.slice(0, proposalIdx >= 0 ? proposalIdx : messages.length)].reverse().find(m => m.role === 'user');
        // A clarified proposal carries the user's answer inside its objective: that, not the first message, is what was approved.
        const approvedMsg = messages.find(m => m.metadata?.proposal_id === proposalId);
        const promptToRun = approvedMsg?.metadata?.supersedes_proposal_id && approvedMsg?.metadata?.proposal?.objective
          ? approvedMsg.metadata.proposal.objective
          : original?.content;
        if (authority && promptToRun) {
          const follow = await fetch(apiUrl('/api/personal/chat'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              prompt: promptToRun,
              session_id: currentSessionId,
              workspace_id: workspaceName,
              authority,
            }),
          });
          if (follow.ok) {
            const data = await follow.json();
            setMessages(prev => [...prev, data]);
            fetchOverview();
          } else {
            const errData = await follow.json().catch(() => ({}));
            showToast(errData.detail || t('homeUiTheAcceptedRequestCouldNotBe'), 'error');
          }
        }
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || t('homeUiFailedToAcceptProposal'), 'error');
      }
    } catch (err: any) {
      showToast(err.message || t('homeUiErrorAcceptingProposal'), 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const [clarifyDrafts, setClarifyDrafts] = useState<Record<string, string>>({});

  const handleClarifyProposal = async (proposalId: string, sessionId?: string) => {
    const answer = (clarifyDrafts[proposalId] || '').trim();
    if (!answer || actionLoading === proposalId) return;
    setActionLoading(proposalId);
    try {
      const res = await fetch(apiUrl(`/api/personal/proposals/${encodeURIComponent(proposalId)}/clarify`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer, actor: 'user', session_id: sessionId || currentSessionId }),
      });
      const data = await res.json().catch(() => ({} as any));
      if (!res.ok) {
        showToast(data.detail || t('homeUiErrorClarifyingProposal'), 'error');
        return;
      }
      setClarifyDrafts(prev => ({ ...prev, [proposalId]: '' }));
      setMessages(prev => {
        const marked = prev.map(msg => msg.metadata?.proposal_id === proposalId
          ? { ...msg, metadata: { ...msg.metadata, status: 'superseded' } }
          : msg);
        return data.message ? [...marked, data.message] : marked;
      });
      fetchOverview();
    } catch (err: any) {
      showToast(err.message || t('homeUiErrorClarifyingProposal'), 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRejectProposal = async (proposalId: string) => {
    if (actionLoading === proposalId) return;
    setActionLoading(proposalId);
    try {
      // The decision must outlive this screen: tell the backend, otherwise the proposal is still pending after a reload.
      const res = await fetch(apiUrl(`/api/personal/proposals/${encodeURIComponent(proposalId)}/revoke`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'rejected by user', actor: 'user' }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || t('homeUiErrorRejectingProposal'), 'error');
        return;
      }
      fetchOverview();
      setMessages(prev => prev.map(msg => {
        if (msg.metadata?.proposal_id === proposalId) {
          return {
            ...msg,
            metadata: { ...msg.metadata, status: 'rejected' },
            steps: msg.steps.map(s => s.details?.proposal_id === proposalId ? { ...s, status: 'failed', title: t('homeUiProposalDeclined') } : s),
          };
        }
        return msg;
      }));
      showToast(t('homeUiProposalDeclined2'), 'info');
    } finally {
      setActionLoading(null);
    }
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', minHeight: '100%' }}>
      <TopHeader
        title="Personal AI Office"
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
              <RefreshCw size={14} /> {t('connRefresh')}
            </button>
          </div>
        }
      />
      <div style={{ padding: '32px 28px 64px 28px', maxWidth: '1080px', margin: '0 auto', width: '100%', boxSizing: 'border-box' }}>
        {/* Top Hero Banner & Status */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                {t('homeUiWhatDoYouNeedToday')}
              </h1>
              <span className="badge badge-primary" style={{ fontSize: '12px', padding: '2px 8px' }}>
                {workspaceName}
              </span>
              {overview.pending_approvals?.length > 0 ? (
                <span className="badge" style={{ backgroundColor: '#f59e0b20', color: '#f59e0b', border: '1px solid #f59e0b50', fontSize: '11px' }}>
                  {overview.pending_approvals.length} {t('homeUiNeedsApproval')}
                </span>
              ) : overview.background_tasks?.some((t: any) => t.status === 'running') ? (
                <span className="badge" style={{ backgroundColor: 'hsl(var(--primary)/0.15)', color: 'hsl(var(--primary))', fontSize: '11px' }}>
                  {t('homeUiWorkInProgress')}
                </span>
              ) : (
                <span className="badge" style={{ backgroundColor: '#10b98115', color: '#10b981', border: '1px solid #10b98130', fontSize: '11px' }}>
                  {t('homeUiReadyToHelp')}
                </span>
              )}
            </div>
            <p style={{ margin: '6px 0 0', fontSize: '14px', color: 'hsl(var(--muted-fg))' }}>
              {t('homeUiDescribeYourGoalOrAskAether')}
            </p>
          </div>
        </div>

        {/* 1. HERO COLLABORATOR PROMPT BOX (TOP PROMINENT INTERACTION) */}
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
                placeholder={isListening ? t('homeUiListeningSpeakClearly') : t('homeUiWhatWouldYouLikeAetherTo')}
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '12px', paddingTop: '10px', borderTop: '1px solid hsl(var(--border)/0.5)', flexWrap: 'wrap', gap: '8px' }}>
                {/* Suggestion Chips */}
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => handleSendPrompt(t('homeUiAetherGiveMeAStatusUpdate'))}
                    style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '12px', backgroundColor: 'hsl(var(--primary)/0.1)', color: 'hsl(var(--primary))', fontWeight: 600 }}
                  >
                    <Sparkles size={12} style={{ marginRight: '4px' }} /> {t('homeUiAetherHandleIt')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => {
                      if (onNewTask) onNewTask();
                      else handleSendPrompt(t('homeUiNewTask'));
                    }}
                    style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '12px', backgroundColor: 'hsl(var(--muted)/0.5)' }}
                  >
                    <Plus size={12} style={{ marginRight: '4px' }} /> {t('homeUiNewTask')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => handleSendPrompt(t('homeUiCheckMyCalendarAppointmentsForTomorrow'))}
                    style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '12px', backgroundColor: 'hsl(var(--muted)/0.5)' }}
                  >
                    <Calendar size={12} style={{ marginRight: '4px' }} /> {t('homeUiCheckSchedule')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => handleSendPrompt(t('homeUiCreateADocumentWithTheProject'))}
                    style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '12px', backgroundColor: 'hsl(var(--muted)/0.5)' }}
                  >
                    <FileText size={12} style={{ marginRight: '4px' }} /> {t('homeUiCreateDocument')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => handleSendPrompt(t('homeUiDelegateToTheTeamAnalyzeThe'))}
                    style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '12px', backgroundColor: 'hsl(var(--muted)/0.5)' }}
                  >
                    <Users size={12} style={{ marginRight: '4px' }} /> {t('homeUiDelegateToTeam')}
                  </button>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', maxWidth: '100%' }}>
                  {/* Push-to-Talk Microphone Button */}
                  <button
                    type="button"
                    data-testid="voice-mic-btn"
                    onClick={toggleListening}
                    title={isListening ? t('homeUiStopListening') : t('homeUiVoiceInputClickToSpeak')}
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
                    <span style={{ fontSize: '12px' }}>{isListening ? t('homeUiListening') : t('homeUiVoice')}</span>
                  </button>

                  <button
                    data-testid="companion-submit-btn"
                    className="btn btn-primary"
                    disabled={!promptInput.trim() || isSubmitting}
                    onClick={() => handleSendPrompt(promptInput)}
                    style={{ padding: '6px 16px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                  >
                    {isSubmitting ? t('homeUiProcessing') : t('homeUiTakeCareOfIt')}
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
                      {msg.role === 'user' ? t('homeUiYou') : 'Aether'}
                    </span>
                    <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                      {msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                    </span>
                  </div>

                  {msg.role === 'assistant' && (
                    <button
                      type="button"
                      onClick={() => handleSpeakText(msg.id, msg.content)}
                      title={isSpeaking && speakingMessageId === msg.id ? t('homeUiStopAudio') : t('homeUiReadAloud')}
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
                        ) : (st.status === 'pending_approval' || st.status === 'waiting_approval') ? (
                          <AlertTriangle size={14} color="#f59e0b" />
                        ) : (
                          <Clock size={14} color="hsl(var(--primary))" />
                        )}
                        <span style={{ fontWeight: 500, color: (st.status === 'pending_approval' || st.status === 'waiting_approval') ? '#f59e0b' : 'hsl(var(--fg))' }}>
                          {translateStepTitle(st.title, t)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                <div style={{ fontSize: '14px', lineHeight: 1.6, color: 'hsl(var(--fg))', whiteSpace: 'pre-wrap' }}>
                  {msg.content}
                </div>
                {msg.role === 'assistant' && msg.metadata?.model && (
                  <div data-testid="answer-model" style={{ marginTop: '6px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                    {msg.metadata.provider ? `${msg.metadata.provider} · ` : ''}{msg.metadata.model}
                  </div>
                )}

                {/* Pending Approval Action Card in Message */}
                {msg.action_execution_id && msg.steps.some(s => s.status === 'pending_approval' || s.status === 'waiting_approval') && (
                  <div style={{ marginTop: '14px', padding: '12px 16px', borderRadius: '10px', backgroundColor: '#f59e0b10', border: '1px solid #f59e0b40', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Shield size={16} color="#f59e0b" />
                      <span style={{ fontSize: '13px', fontWeight: 600, color: '#f59e0b' }}>{t('homeUiConfirmationRequired')}</span>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        className="btn btn-ghost"
                        disabled={actionLoading === msg.action_execution_id}
                        onClick={() => handleRejectAction(msg.action_execution_id!)}
                        style={{
                          fontSize: '12px',
                          padding: '4px 10px',
                          color: 'hsl(var(--destructive))',
                          opacity: actionLoading === msg.action_execution_id ? 0.6 : 1,
                        }}
                      >
                        <X size={13} style={{ marginRight: '4px' }} /> {t('reject')}
                      </button>
                      <button
                        className="btn btn-primary"
                        disabled={actionLoading === msg.action_execution_id}
                        onClick={() => handleApproveAction(msg.action_execution_id!)}
                        style={{
                          fontSize: '12px',
                          padding: '4px 14px',
                          backgroundColor: '#10b981',
                          borderColor: '#10b981',
                          opacity: actionLoading === msg.action_execution_id ? 0.6 : 1,
                        }}
                      >
                        {actionLoading === msg.action_execution_id ? (
                          <Loader2 size={13} className="animate-spin" style={{ marginRight: '4px' }} />
                        ) : (
                          <Check size={13} style={{ marginRight: '4px' }} />
                        )}
                        {actionLoading === msg.action_execution_id ? t('homeUiApproving') : t('approve')}
                      </button>
                    </div>
                  </div>
                )}

                {/* Proposal waiting for the user's answer: the answer resumes the same request */}
                {msg.metadata?.proposal_id && msg.metadata?.status === 'proposal_pending' && msg.metadata?.proposal?.status === 'needs_clarification' && (
                  <div data-testid="proposal-clarification" style={{ marginTop: '14px', padding: '12px 16px', borderRadius: '10px', backgroundColor: '#f59e0b10', border: '1px solid #f59e0b40' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                      <Shield size={16} color="#f59e0b" />
                      <span style={{ fontSize: '13px', fontWeight: 600, color: '#f59e0b' }}>{t('homeUiClarificationNeeded')}</span>
                    </div>
                    <ul style={{ margin: '0 0 10px 18px', fontSize: '13px', color: 'hsl(var(--fg))' }}>
                      {(msg.metadata.proposal.clarification_requirements || []).map((c: any, i: number) => (
                        <li key={i}>{c.question || c.context_key}</li>
                      ))}
                    </ul>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <input
                        className="input"
                        style={{ flex: 1, fontSize: '13px' }}
                        placeholder={t('homeUiClarificationPlaceholder')}
                        value={clarifyDrafts[msg.metadata.proposal_id] || ''}
                        onChange={(e) => setClarifyDrafts(prev => ({ ...prev, [msg.metadata!.proposal_id]: e.target.value }))}
                        onKeyDown={(e) => { if (e.key === 'Enter') handleClarifyProposal(msg.metadata!.proposal_id, msg.session_id); }}
                      />
                      <button
                        className="btn btn-ghost"
                        disabled={actionLoading === msg.metadata.proposal_id}
                        onClick={() => handleRejectProposal(msg.metadata!.proposal_id)}
                        style={{ fontSize: '12px', padding: '4px 10px', color: 'hsl(var(--destructive))' }}
                      >
                        <X size={13} style={{ marginRight: '4px' }} /> {t('reject')}
                      </button>
                      <button
                        className="btn btn-primary"
                        disabled={actionLoading === msg.metadata.proposal_id || !(clarifyDrafts[msg.metadata.proposal_id] || '').trim()}
                        onClick={() => handleClarifyProposal(msg.metadata!.proposal_id, msg.session_id)}
                        style={{ fontSize: '12px', padding: '4px 14px' }}
                      >
                        {t('homeUiClarificationSend')}
                      </button>
                    </div>
                  </div>
                )}

                {/* Pending Proposal Acceptance Card in Message */}
                {msg.metadata?.proposal_id && msg.metadata?.proposal?.status !== 'needs_clarification' && (msg.metadata?.status === 'proposal_pending' || msg.steps.some(s => s.status === 'waiting_acceptance')) && (
                  <div style={{ marginTop: '14px', padding: '12px 16px', borderRadius: '10px', backgroundColor: '#f59e0b10', border: '1px solid #f59e0b40', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Shield size={16} color="#f59e0b" />
                      <span style={{ fontSize: '13px', fontWeight: 600, color: '#f59e0b' }}>{t('homeUiConfirmationRequired')}</span>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        className="btn btn-ghost"
                        disabled={actionLoading === msg.metadata!.proposal_id}
                        onClick={() => handleRejectProposal(msg.metadata!.proposal_id)}
                        style={{
                          fontSize: '12px',
                          padding: '4px 10px',
                          color: 'hsl(var(--destructive))',
                          opacity: actionLoading === msg.metadata!.proposal_id ? 0.6 : 1,
                        }}
                      >
                        <X size={13} style={{ marginRight: '4px' }} /> {t('reject')}
                      </button>
                      <button
                        className="btn btn-primary"
                        disabled={actionLoading === msg.metadata!.proposal_id}
                        onClick={() => handleApproveProposal(msg.metadata!.proposal_id)}
                        style={{
                          fontSize: '12px',
                          padding: '4px 14px',
                          backgroundColor: '#10b981',
                          borderColor: '#10b981',
                          opacity: actionLoading === msg.metadata!.proposal_id ? 0.6 : 1,
                        }}
                      >
                        {actionLoading === msg.metadata!.proposal_id ? (
                          <Loader2 size={13} className="animate-spin" style={{ marginRight: '4px' }} />
                        ) : (
                          <Check size={13} style={{ marginRight: '4px' }} />
                        )}
                        {actionLoading === msg.metadata!.proposal_id ? t('homeUiApproving') : t('approve')}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* 2. IN ATTESA DI APPROVAZIONE (SE PRESENTI) */}
        {overview.pending_approvals && overview.pending_approvals.length > 0 && (
          <div data-testid="needs-attention-section" style={{ marginBottom: '28px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Shield size={18} color="#f59e0b" />
                <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                  In attesa di approvazione ({overview.pending_approvals.length})
                </h2>
              </div>
              <span style={{ fontSize: '12px', color: '#f59e0b', fontWeight: 500 }}>
                {t('homeUiOperationsPausedWaitingForYourConfirmation')}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {overview.pending_approvals.map((appr: any) => {
                const isTargeted = initialApprovalId === appr.execution_id;
                const isLoading = actionLoading === appr.execution_id;
                return (
                  <div
                    key={appr.execution_id}
                    id={`approval-card-${appr.execution_id}`}
                    className="card"
                    style={{
                      padding: '16px 20px',
                      borderRadius: '12px',
                      border: isTargeted ? '2px solid #f59e0b' : '1px solid #f59e0b50',
                      boxShadow: isTargeted ? '0 0 16px rgba(245, 158, 11, 0.3)' : '0 2px 8px rgba(0,0,0,0.04)',
                      backgroundColor: isTargeted ? '#f59e0b14' : '#f59e0b08',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      transition: 'all 0.3s ease',
                    }}
                  >
                    <div style={{ flex: 1, marginRight: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '10px', fontWeight: 700, padding: '2px 7px', borderRadius: '4px', backgroundColor: '#f59e0b20', color: '#f59e0b', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          {t('homeUiConfirmationRequired')}
                        </span>
                        <span style={{ fontWeight: 600, fontSize: '14.5px' }}>{appr.human_summary || appr.action_name}</span>
                      </div>
                      {appr.action_id === 'email.send' && (
                        <div style={{ fontSize: '12.5px', color: 'hsl(var(--fg)/0.85)', marginTop: '6px', padding: '8px 12px', backgroundColor: 'hsl(var(--muted)/0.3)', borderRadius: '6px' }}>
                          <div><strong>A:</strong> {appr.input_data?.to}</div>
                          <div><strong>{t('homeUiSubjectLabel')}</strong> {appr.input_data?.subject}</div>
                          {appr.input_data?.body && <div style={{ marginTop: '4px', whiteSpace: 'pre-wrap', color: 'hsl(var(--muted-fg))' }}>{appr.input_data.body}</div>}
                        </div>
                      )}
                      {appr.action_id === 'github.create_issue' && (
                        <div style={{ fontSize: '12.5px', color: 'hsl(var(--fg)/0.85)', marginTop: '6px', padding: '8px 12px', backgroundColor: 'hsl(var(--muted)/0.3)', borderRadius: '6px' }}>
                          <div><strong>Repository:</strong> {appr.input_data?.owner ? `${appr.input_data.owner}/${appr.input_data.repository}` : (appr.input_data?.repository || 'repository')}</div>
                          <div><strong>{t('homeUiTitleLabel')}</strong> {appr.input_data?.title}</div>
                          {appr.input_data?.body && <div style={{ marginTop: '4px', whiteSpace: 'pre-wrap', color: 'hsl(var(--muted-fg))' }}>{appr.input_data.body}</div>}
                        </div>
                      )}
                      {appr.action_id === 'slack.send_message' && (
                        <div style={{ fontSize: '12.5px', color: 'hsl(var(--fg)/0.85)', marginTop: '6px', padding: '8px 12px', backgroundColor: 'hsl(var(--muted)/0.3)', borderRadius: '6px' }}>
                          <div><strong>{t('homeUiChannelLabel')}</strong> {appr.input_data?.channel || '#general'}</div>
                          {appr.input_data?.text && <div style={{ marginTop: '4px', whiteSpace: 'pre-wrap', color: 'hsl(var(--muted-fg))' }}>{appr.input_data.text}</div>}
                        </div>
                      )}
                      {appr.action_id === 'calendar.create_event' && (
                        <div style={{ fontSize: '12.5px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                          {appr.input_data?.start_time ? `${t('homeUiTimeLabel')} ${appr.input_data.start_time}` : ''} {appr.input_data?.location ? `• ${t('homeUiLocationLabel')} ${appr.input_data.location}` : ''}
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <button
                        className="btn btn-ghost"
                        disabled={isLoading}
                        onClick={() => handleRejectAction(appr.execution_id)}
                        style={{ fontSize: '12px', padding: '6px 12px', color: 'hsl(var(--destructive))', opacity: isLoading ? 0.6 : 1 }}
                      >
                        {t('reject')}
                      </button>
                      <button
                        className="btn btn-primary"
                        disabled={isLoading}
                        onClick={() => handleApproveAction(appr.execution_id)}
                        style={{
                          fontSize: '12px',
                          padding: '6px 16px',
                          backgroundColor: '#10b981',
                          borderColor: '#10b981',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          opacity: isLoading ? 0.6 : 1,
                        }}
                      >
                        {isLoading && <Loader2 size={13} className="animate-spin" />}
                        {isLoading ? t('homeUiApproving') : t('approve')}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 3. LAVORI IN CORSO */}
        {((overview.background_tasks && overview.background_tasks.length > 0) || (overview.active_works && overview.active_works.length > 0)) && (
          <div data-testid="background-tasks-section" style={{ marginBottom: '28px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Clock size={16} className="text-primary" />
                <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                  {t('homeWorkInProgress')} ({(overview.background_tasks?.length || 0) + (overview.active_works?.length || 0)})
                </h2>
              </div>
              <button
                className="btn btn-ghost"
                onClick={() => navigate('missions')}
                style={{ fontSize: '12px', padding: '2px 8px', color: 'hsl(var(--primary))' }}
              >
                {t('homeUiViewAllJobs')}
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {overview.background_tasks?.map((task: any) => (
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
                      <span style={{ fontWeight: 600, fontSize: '14px' }}>{task.title || t('homeUiBackgroundOperation')}</span>
                      <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                        {task.current_step || task.status}
                      </div>
                    </div>
                    <span
                      className={`badge ${task.status === 'completed' ? 'badge-success' : task.status === 'running' ? 'badge-primary' : 'badge-warning'}`}
                      style={{ fontSize: '11px', textTransform: 'capitalize' }}
                    >
                      {task.status === 'completed' ? t('homeUiCompleted') : task.status === 'running' ? t('homeUiRunning') : task.status}
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
                        <ExternalLink size={12} /> {t('homeViewDocument')}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 4. RISULTATI E DOCUMENTI RECENTI */}
        {overview.recent_deliverables && overview.recent_deliverables.length > 0 && (
          <div style={{ marginBottom: '28px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FileText size={16} className="text-primary" />
                <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                  Risultati e documenti recenti ({overview.recent_deliverables.length})
                </h2>
              </div>
              <button
                className="btn btn-ghost"
                onClick={() => navigate('results')}
                style={{ fontSize: '12px', padding: '2px 8px', color: 'hsl(var(--primary))' }}
              >
                {t('homeUiOpenInResults')}
              </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(280px, 100%), 1fr))', gap: '12px' }}>
              {overview.recent_deliverables.map((deliv: any) => (
                <div
                  key={deliv.id || deliv.file_path}
                  className="card"
                  onClick={() => navigate('results')}
                  style={{
                    padding: '14px 16px',
                    borderRadius: '10px',
                    border: '1px solid hsl(var(--border))',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                    transition: 'border-color 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <FileText size={15} color="hsl(var(--primary))" />
                      <span style={{ fontSize: '13.5px', fontWeight: 600 }}>{deliv.title || deliv.name}</span>
                    </div>
                    <span className="badge" style={{ fontSize: '10px', textTransform: 'uppercase' }}>
                      {deliv.file_type || 'documento'}
                    </span>
                  </div>
                  {deliv.summary && (
                    <p style={{ margin: 0, fontSize: '12px', color: 'hsl(var(--muted-fg))', lineHeight: 1.4 }}>
                      {deliv.summary}
                    </p>
                  )}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                    <span>{deliv.created_at ? new Date(deliv.created_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}</span>
                    <span style={{ color: 'hsl(var(--primary))', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                      {t('syViewResult')} <ArrowRight size={10} />
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 5. HUB SHORTCUTS: Lavori, Connessioni, Automazioni, Attività */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: '16px', marginBottom: '28px' }}>
          {/* Lavori */}
          <div
            className="card"
            style={{ padding: '18px', borderRadius: '12px', cursor: 'pointer' }}
            onClick={() => navigate('missions')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '14.5px' }}>
                <Users size={17} color="hsl(var(--primary))" /> {t('homeCardWorkTitle')}
              </div>
              <ArrowRight size={15} color="hsl(var(--muted-fg))" />
            </div>
            <div style={{ fontSize: '12.5px', color: 'hsl(var(--muted-fg))' }}>
              {overview.active_works?.length > 0 ? (
                <span><strong>{overview.active_works.length}</strong> {t('homeUiActiveMissions')}</span>
              ) : (
                <span>{t('homeUiOngoingProjectsAndSupervisedTasks')}</span>
              )}
            </div>
          </div>

          {/* Servizi Collegati */}
          <div
            className="card"
            style={{ padding: '18px', borderRadius: '12px', cursor: 'pointer' }}
            onClick={() => navigate('connections')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '14.5px' }}>
                <Calendar size={17} color="#4285F4" /> {t('homeCardServicesTitle')}
              </div>
              <ArrowRight size={15} color="hsl(var(--muted-fg))" />
            </div>
            <div style={{ fontSize: '12.5px', color: 'hsl(var(--muted-fg))' }}>
              <span><strong>{overview.connected_apps_count || 0}</strong> {t('homeUiAppsVerified')}</span>
            </div>
          </div>

          {/* Automazioni */}
          <div
            className="card"
            style={{ padding: '18px', borderRadius: '12px', cursor: 'pointer' }}
            onClick={() => navigate('automations')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '14.5px' }}>
                <Clock size={17} color="#8b5cf6" /> Automazioni
              </div>
              <ArrowRight size={15} color="hsl(var(--muted-fg))" />
            </div>
            <div style={{ fontSize: '12.5px', color: 'hsl(var(--muted-fg))' }}>
              <span>{t('homeUiAutomaticSchedulesAndRecurringTasks')}</span>
            </div>
          </div>

          {/* Cronologia Attività */}
          <div
            className="card"
            style={{ padding: '18px', borderRadius: '12px', cursor: 'pointer' }}
            onClick={() => navigate('activity')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '14.5px' }}>
                <Activity size={17} color="#10b981" /> {t('homeCardHistoryTitle')}
              </div>
              <ArrowRight size={15} color="hsl(var(--muted-fg))" />
            </div>
            <div style={{ fontSize: '12.5px', color: 'hsl(var(--muted-fg))' }}>
              <span>{t('homeUiTransparentLogOfAllExecutedActions')}</span>
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
