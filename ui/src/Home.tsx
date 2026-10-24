import { useState, useEffect, useContext, useRef } from 'react';
import { CalendarDays, CircleDot, FileText, Loader2, Mail, Sparkles } from 'lucide-react';
import { AssistantMessage, Composer, ConfirmCard, Thinking, UserMessage } from './chat/ChatParts';
import './home.css';
import './chat/chat.css';
import { apiUrl } from './api';
import { speak, speakVoiceAnswersEnabled } from './voiceOut';
import { Presence } from './presence/Presence';
import { Rewind } from './presence/Rewind';
import { Promises } from './presence/Promises';
import { useTranslation } from './i18n';
import { ToastContext } from './toast';
import { AutoArchitectModal } from './AutoArchitectModal';
import { FirstRunModel } from './FirstRunModel';
import { Today } from './Today';
import { NotificationCenter } from './NotificationCenter';
import { submitApprovalDecision, approvalToastKind, approvalIsFinished, approvalIsInProgress } from './canonicalNotification';

interface HomeProps {
  navigate: (view: string, params?: any) => void;
  workspaceName: string;
  initialApprovalId?: string | null;
  onNewTask?: () => void;
  onSelectConversation?: (id: string) => void;
  conversations?: any[];
  /** The chat to show (null = a new one), chosen in the sidebar; reported back when a new chat gets its id. */
  sessionId?: string | null;
  onSessionChange?: (id: string | null) => void;
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
  sessionId = null,
  onSessionChange,
}: HomeProps) {
  const [promptInput, setPromptInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<PersonalMsg[]>([]);
  const [sessionTitle, setSessionTitle] = useState('');
  const [undoStates, setUndoStates] = useState<Record<string, 'busy' | 'done'>>({});
  const scrollRef = useRef<HTMLDivElement>(null);
  // Presence (the orb, the default) or the transcript of the same conversation (the classic chat)
  const [view, setViewState] = useState<'presence' | 'transcript'>(() => {
    try { return localStorage.getItem('aether_home_view') === 'transcript' ? 'transcript' : 'presence'; } catch { return 'presence'; }
  });
  const setView = (v: 'presence' | 'transcript') => { setViewState(v); try { localStorage.setItem('aether_home_view', v); } catch { /* storage unavailable */ } };
  const [rewindOpen, setRewindOpen] = useState(false);
  const [promisesOpen, setPromisesOpen] = useState(false);
  const [autonomyAnswers, setAutonomyAnswers] = useState<Record<string, 'yes' | 'no'>>({});
  const voiceTurnRef = useRef(false);   // the current question was spoken: the answer is spoken back
  const holdRef = useRef(false);        // Space is held down to talk
  const sendAfterVoiceRef = useRef(false);
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
  const { t, language } = useTranslation();

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

  // The sidebar chooses the chat: load its history, or start empty for a new one.
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      setCurrentSessionId(null);
      setSessionTitle('');
      return;
    }
    if (sessionId === currentSessionId) return;
    let cancelled = false;
    fetch(apiUrl(`/api/personal/sessions/${encodeURIComponent(sessionId)}`))
      .then(res => (res.ok ? res.json() : null))
      .then(data => {
        if (cancelled || !data) return;
        setCurrentSessionId(sessionId);
        setViewState('transcript');  // an older chat opened from the sidebar reads best as a transcript
        setSessionTitle(data.title || '');
        setMessages(Array.isArray(data.messages) ? data.messages.map((m: any) => ({ ...m, steps: m.steps || [] })) : []);
        setUndoStates({});
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Follow the conversation: the newest message (or "thinking") stays in view.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: messages.length > 2 ? 'smooth' : 'auto' });
  }, [messages.length, isSubmitting]);

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
      rec.lang = language === 'it' ? 'it-IT' : 'en-US'; // dictation in the interface language

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
  }, [language]);

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
    setIsSpeaking(true);
    setSpeakingMessageId(msgId);
    speak(text, language, () => {
      setIsSpeaking(false);
      setSpeakingMessageId(null);
    });
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
          language,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.session_id && data.session_id !== currentSessionId) {
          setSessionTitle(text.slice(0, 60));
          onSessionChange?.(data.session_id);
        }
        setCurrentSessionId(data.session_id);
        setMessages(prev => [...prev, { ...data, steps: data.steps || [] }]);
        fetchOverview();
        if (voiceTurnRef.current && speakVoiceAnswersEnabled() && data.content) {
          setIsSpeaking(true);
          setSpeakingMessageId(data.id);
          speak(data.content, language, () => { setIsSpeaking(false); setSpeakingMessageId(null); });
        }
      } else {
        const errData = await res.json().catch(() => ({}));
        const errMsg = errData.detail || t('homeUiErrorProcessingRequest');
        showToast(errMsg, 'error');
        setMessages(prev => [...prev, {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `${t('chRequestFailed')} ${errMsg}`,
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
        content: `${t('chNetworkFailed')} ${errMsg}`,
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
      voiceTurnRef.current = false;
    }
  };

  // Hold Space (outside a text field) to talk to the orb; release to send what was heard.
  useEffect(() => {
    if (view !== 'presence') return;
    const typing = (el: EventTarget | null) => {
      const n = el as HTMLElement | null;
      return !!n && (n.tagName === 'INPUT' || n.tagName === 'TEXTAREA' || n.tagName === 'SELECT' || n.isContentEditable);
    };
    const down = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.repeat || typing(e.target) || holdRef.current || isSubmitting) return;
      e.preventDefault();
      if (!recognitionRef.current) { showToast(t('homeUiSpeechRecognitionNotSupportedInThis'), 'warning'); return; }
      holdRef.current = true;
      setPromptInput('');
      try { recognitionRef.current.start(); setIsListening(true); } catch { holdRef.current = false; }
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || !holdRef.current) return;
      e.preventDefault();
      holdRef.current = false;
      sendAfterVoiceRef.current = true;
      try { recognitionRef.current?.stop(); } catch { /* already stopped */ }
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, isSubmitting]);

  useEffect(() => {
    if (isListening || !sendAfterVoiceRef.current) return;
    sendAfterVoiceRef.current = false;
    if (promptInput.trim()) {
      voiceTurnRef.current = true;
      void handleSendPrompt(promptInput);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isListening]);

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
          language,
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

  const handleUndo = async (msg: PersonalMsg) => {
    const exId = msg.metadata?.undo_execution_id;
    if (!exId || undoStates[msg.id]) return;
    setUndoStates(prev => ({ ...prev, [msg.id]: 'busy' }));
    try {
      const res = await fetch(apiUrl(`/api/undo/${encodeURIComponent(exId)}`), { method: 'POST' });
      if (res.ok) {
        setUndoStates(prev => ({ ...prev, [msg.id]: 'done' }));
        showToast(t('chUndoneToast'), 'success');
        fetchOverview();
      } else {
        const err = await res.json().catch(() => ({}));
        const code = err?.detail?.code;
        setUndoStates(prev => { const n = { ...prev }; delete n[msg.id]; return n; });
        showToast(code === 'changed_since' ? t('chUndoChanged') : code === 'already_undone' ? t('chUndoAlready') : t('chUndoFailed'), 'error');
      }
    } catch {
      setUndoStates(prev => { const n = { ...prev }; delete n[msg.id]; return n; });
      showToast(t('chUndoFailed'), 'error');
    }
  };

  // The personal space is created by the runtime at launch; until it is there App shows the calm "getting ready" notice.
  if (!workspaceName) return null;

  const hasChat = messages.length > 0;
  const needsAnswer = (msg: PersonalMsg) => msg.steps.some(s => s.status === 'pending_approval' || s.status === 'waiting_approval');
  const answerAutonomy = async (msg: PersonalMsg, allow: boolean) => {
    const offer = msg.metadata?.autonomy_offer;
    if (!offer) return;
    setAutonomyAnswers(prev => ({ ...prev, [msg.id]: allow ? 'yes' : 'no' }));
    const res = await fetch(apiUrl('/api/autonomy'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: offer.key, allow }) }).catch(() => null);
    if (res?.ok) showToast(allow ? t('auGrantedToast', { label: offer.label }) : t('auDeclinedToast'), 'success');
    else { setAutonomyAnswers(prev => { const n = { ...prev }; delete n[msg.id]; return n; }); showToast(t('chUndoFailed'), 'error'); }
  };
  const renderCards = (msg: PersonalMsg) => (
    <>
      {msg.metadata?.autonomy_offer && !autonomyAnswers[msg.id] && (
        <ConfirmCard testId="autonomy-offer" title={t('auOfferTitle', { count: msg.metadata.autonomy_offer.count, label: msg.metadata.autonomy_offer.label })} busy={false}
          onConfirm={() => answerAutonomy(msg, true)} onDecline={() => answerAutonomy(msg, false)}
          confirmLabel={t('auOfferYes')} declineLabel={t('auOfferNo')}>
          <p className="ch-confirm-note">{t('auOfferNote')}</p>
        </ConfirmCard>
      )}
      {msg.action_execution_id && needsAnswer(msg) && (
        <ConfirmCard title={t('homeUiConfirmationRequired')} busy={actionLoading === msg.action_execution_id}
          onConfirm={() => handleApproveAction(msg.action_execution_id!)} onDecline={() => handleRejectAction(msg.action_execution_id!)}
          confirmLabel={actionLoading === msg.action_execution_id ? t('homeUiApproving') : t('approve')} declineLabel={t('reject')} />
      )}
      {msg.metadata?.proposal_id && msg.metadata?.status === 'proposal_pending' && msg.metadata?.proposal?.status === 'needs_clarification' && (
        <ConfirmCard testId="proposal-clarification" title={t('homeUiClarificationNeeded')} busy={actionLoading === msg.metadata.proposal_id}
          onConfirm={() => handleClarifyProposal(msg.metadata!.proposal_id, msg.session_id)} onDecline={() => handleRejectProposal(msg.metadata!.proposal_id)}
          confirmLabel={t('homeUiClarificationSend')} declineLabel={t('reject')}>
          <ul>{(msg.metadata.proposal.clarification_requirements || []).map((c: any, i: number) => <li key={i}>{c.question || c.context_key}</li>)}</ul>
          <input placeholder={t('homeUiClarificationPlaceholder')} aria-label={t('homeUiClarificationPlaceholder')} value={clarifyDrafts[msg.metadata.proposal_id] || ''}
            onChange={e => setClarifyDrafts(prev => ({ ...prev, [msg.metadata!.proposal_id]: e.target.value }))}
            onKeyDown={e => { if (e.key === 'Enter') handleClarifyProposal(msg.metadata!.proposal_id, msg.session_id); }} />
        </ConfirmCard>
      )}
      {msg.metadata?.proposal_id && msg.metadata?.proposal?.status !== 'needs_clarification' && (msg.metadata?.status === 'proposal_pending' || msg.steps.some(s => s.status === 'waiting_acceptance')) && (
        <ConfirmCard title={t('homeUiConfirmationRequired')} busy={actionLoading === msg.metadata.proposal_id}
          onConfirm={() => handleApproveProposal(msg.metadata!.proposal_id)} onDecline={() => handleRejectProposal(msg.metadata!.proposal_id)}
          confirmLabel={actionLoading === msg.metadata.proposal_id ? t('homeUiApproving') : t('approve')} declineLabel={t('reject')} />
      )}
    </>
  );
  const lastAi = [...messages].reverse().find(m => m.role === 'assistant');
  const needsYou = !!lastAi && (needsAnswer(lastAi) || (lastAi.metadata?.status === 'proposal_pending'));
  const composer = (
    <Composer
      value={promptInput}
      onChange={setPromptInput}
      onSend={() => handleSendPrompt(promptInput)}
      onMic={toggleListening}
      listening={isListening}
      busy={isSubmitting}
      placeholder={isListening ? t('homeUiListeningSpeakClearly') : t('chPlaceholder')}
      t={t}
      autoFocus
    />
  );

  if (view === 'presence') {
    return (
      <div className="ch-shell" data-view="presence">
        <Presence
          t={t}
          language={language}
          messages={messages}
          busy={isSubmitting}
          listening={isListening}
          speaking={isSpeaking}
          input={promptInput}
          composer={composer}
          actions={lastAi ? renderCards(lastAi) : null}
          needsYou={needsYou}
          undoState={lastAi ? (undoStates[lastAi.id] || 'idle') : 'idle'}
          onUndo={lastAi ? () => handleUndo(lastAi) : undefined}
          onSpeak={() => lastAi && handleSpeakText(lastAi.id, lastAi.content)}
          onOpenTranscript={() => setView('transcript')}
          onOpenRewind={() => setRewindOpen(true)}
          onOpenPromises={() => setPromisesOpen(true)}
          onAsk={p => handleSendPrompt(p)}
          notifications={<NotificationCenter workspaceName={workspaceName} onNavigate={navigate} />}
        />
        {rewindOpen && <Rewind t={t} language={language} onClose={() => setRewindOpen(false)} />}
        {promisesOpen && <Promises t={t} language={language} onClose={() => setPromisesOpen(false)} />}
        {isAutoArchitectOpen && (
          <AutoArchitectModal isOpen={isAutoArchitectOpen} onClose={() => setIsAutoArchitectOpen(false)} onSuccess={() => fetchOverview()} />
        )}
      </div>
    );
  }

  return (
    <div className="ch-shell">
      <header className="ch-top" data-testid="top-header">
        <span className="ch-top-left">
          <button type="button" className="ch-presence-btn" onClick={() => setView('presence')} data-testid="open-presence"><CircleDot size={15} />{t('prPresence')}</button>
          {hasChat && <h2 className="ch-top-title">{sessionTitle || t('chUntitled')}</h2>}
        </span>
        <NotificationCenter workspaceName={workspaceName} onNavigate={navigate} />
      </header>

      <div className="ch-scroll" ref={scrollRef}>
        {!hasChat ? (
          <div className="ch-empty">
            <div className="ch-hello">
              <div className="ch-orb" aria-hidden />
              <h1 className="ch-greeting">{t('homeUiWhatDoYouNeedToday')}</h1>
              {overview.pending_approvals?.length > 0 && (
                <button type="button" className="ch-quiet" onClick={() => document.getElementById('ch-approvals')?.scrollIntoView({ behavior: 'smooth' })} data-testid="home-approvals-hint">
                  {overview.pending_approvals.length} {t('homeUiNeedsApproval')}
                </button>
              )}
            </div>

            <FirstRunModel />
            {composer}

            <div className="ch-suggest">
              <button type="button" onClick={() => handleSendPrompt(t('homeUiCheckMyCalendarAppointmentsForTomorrow'))}><CalendarDays size={15} />{t('homeUiCheckSchedule')}</button>
              <button type="button" onClick={() => handleSendPrompt(t('chSuggestMailPrompt'))}><Mail size={15} />{t('chSuggestMail')}</button>
              <button type="button" onClick={() => handleSendPrompt(t('homeUiCreateADocumentWithTheProject'))}><FileText size={15} />{t('homeUiCreateDocument')}</button>
              <button type="button" onClick={() => handleSendPrompt(t('homeUiAetherGiveMeAStatusUpdate'))}><Sparkles size={15} />{t('homeUiAetherHandleIt')}</button>
            </div>

            <Today navigate={navigate} />

            {overview.pending_approvals && overview.pending_approvals.length > 0 && (
              <section className="ch-section" id="ch-approvals" data-testid="needs-attention-section">
                <h2>{t('chWaitingForYou', { count: overview.pending_approvals.length })}</h2>
                <div className="ch-list">
                  {overview.pending_approvals.map((appr: any) => {
                    const isLoading = actionLoading === appr.execution_id;
                    const details = appr.action_id === 'email.send' ? `${appr.input_data?.to || ''} · ${appr.input_data?.subject || ''}`
                      : appr.action_id === 'slack.send_message' ? `${appr.input_data?.channel || '#general'} · ${appr.input_data?.text || ''}`
                      : appr.action_id === 'github.create_issue' ? `${appr.input_data?.owner ? `${appr.input_data.owner}/` : ''}${appr.input_data?.repository || ''} · ${appr.input_data?.title || ''}`
                      : appr.input_data?.when || appr.input_data?.start_time || '';
                    return (
                      <div key={appr.execution_id} id={`approval-card-${appr.execution_id}`} className="ch-item" data-targeted={initialApprovalId === appr.execution_id ? 'true' : undefined}>
                        <span className="ch-item-main"><b>{appr.human_summary || appr.action_name}</b>{details && <small>{details}</small>}</span>
                        <span className="ch-item-actions">
                          <button type="button" className="ch-btn ghost" disabled={isLoading} onClick={() => handleRejectAction(appr.execution_id)}>{t('reject')}</button>
                          <button type="button" className="ch-btn primary" disabled={isLoading} onClick={() => handleApproveAction(appr.execution_id)}>
                            {isLoading && <Loader2 size={14} className="ch-spin" />}{isLoading ? t('homeUiApproving') : t('approve')}
                          </button>
                        </span>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {((overview.background_tasks?.length || 0) + (overview.active_works?.length || 0)) > 0 && (
              <section className="ch-section" data-testid="background-tasks-section">
                <h2>{t('homeWorkInProgress')} <button type="button" className="ch-link" onClick={() => navigate('missions')}>{t('homeUiViewAllJobs')}</button></h2>
                <div className="ch-list">
                  {overview.background_tasks?.map((task: any) => (
                    <div key={task.id} className="ch-item" data-testid="background-task-card">
                      <span className="ch-item-main">
                        <b>{task.title || t('homeUiBackgroundOperation')}</b>
                        <small>{task.status === 'completed' ? t('homeUiCompleted') : task.status === 'running' ? (task.current_step || t('homeUiRunning')) : task.status}</small>
                        <span className="ch-bar"><i style={{ width: `${task.progress_pct || (task.status === 'completed' ? 100 : 25)}%` }} /></span>
                      </span>
                      {task.deliverable_path && <button type="button" className="ch-link" onClick={() => navigate('missions')}>{t('homeViewDocument')}</button>}
                    </div>
                  ))}
                  {overview.active_works?.map((w: any) => (
                    <div key={w.id || w.title} className="ch-item">
                      <span className="ch-item-main"><b>{w.title || w.goal}</b><small>{w.status}</small></span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {overview.recent_deliverables && overview.recent_deliverables.length > 0 && (
              <section className="ch-section">
                <h2>{t('chRecentDocs')} <button type="button" className="ch-link" onClick={() => navigate('results')}>{t('homeUiOpenInResults')}</button></h2>
                <div className="ch-list">
                  {overview.recent_deliverables.slice(0, 5).map((d: any) => (
                    <button type="button" key={d.id || d.file_path} className="ch-item" style={{ background: 'none', border: 0, font: 'inherit', textAlign: 'left', cursor: 'pointer', color: 'inherit' }} onClick={() => navigate('results')}>
                      <FileText size={16} color="hsl(var(--muted-fg))" />
                      <span className="ch-item-main"><b>{d.title || d.name}</b>{d.summary && <small>{d.summary}</small>}</span>
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>
        ) : (
          <div className="ch-column" data-testid="companion-messages-container">
            {messages.map(msg => msg.role === 'user' ? <UserMessage key={msg.id} msg={msg} /> : (
              <AssistantMessage
                key={msg.id}
                msg={msg}
                t={t}
                notify={showToast}
                speaking={isSpeaking && speakingMessageId === msg.id}
                onSpeak={() => handleSpeakText(msg.id, msg.content)}
                onUndo={() => handleUndo(msg)}
                undoState={undoStates[msg.id] || 'idle'}
              >
                {renderCards(msg)}
              </AssistantMessage>
            ))}
            {isSubmitting && <Thinking t={t} />}
          </div>
        )}
      </div>

      {hasChat && (
        <div className="ch-dock">
          <div className="ch-dock-inner">
            {composer}
            <p className="ch-note">{t('chNote')}</p>
          </div>
        </div>
      )}

      {isAutoArchitectOpen && (
        <AutoArchitectModal isOpen={isAutoArchitectOpen} onClose={() => setIsAutoArchitectOpen(false)} onSuccess={() => fetchOverview()} />
      )}
    </div>
  );
}
