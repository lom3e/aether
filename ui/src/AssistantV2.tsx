import { classifyCodingResult, runStillActive, testOutcome } from './codingStatus';
import { classifyRestoreResponse, forgetStaleSession } from './sessionRestore';
import { useState, useEffect, useRef, useCallback, useContext } from 'react';
import {
  Sparkles, Send, Mic, MicOff, CheckCircle2, AlertTriangle, X,
  Briefcase, Link2, Users, FileText, Settings, ArrowRight,
  Layers, ChevronRight, Code2, Terminal, Check, ShieldCheck,
  RotateCw, Download, LogIn, Square, ChevronDown, Copy,
  FolderGit2, FileCode, Plus, Trash2, Minimize2, Maximize2, MessageSquare
} from 'lucide-react';
import { AetherOrb } from './orb/AetherOrb';
import type { OrbState, QualityProfileKey } from './orb/OrbEngine';
import { apiUrl } from './api';
import { ToastContext } from './toast';
import { submitApprovalDecision, approvalToastKind } from './canonicalNotification';
import { MarkdownRenderer } from './MarkdownRenderer';
import './assistant-v2.css';

interface AssistantV2Props {
  workspaceName: string;
  navigate: (view: string, params?: any) => void;
  onSwitchToV1: () => void;
  onOpenWorkspaceModal?: () => void;
}

interface StepItem {
  id: string;
  title: string;
  status: string;
  category: string;
  details?: any;
}

interface ThoughtBubbleItem {
  id: string;
  text: string;
  slot: 'top-left' | 'top-right' | 'mid-left' | 'mid-right';
  tier: 'info' | 'attention' | 'done';
  onClick?: () => void;
}

export function AssistantV2({
  workspaceName,
  navigate,
  onSwitchToV1,
}: AssistantV2Props) {
  // Orb State
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const [audioLevel, setAudioLevel] = useState<number>(0);
  const [quality] = useState<QualityProfileKey>('auto');

  // Conversation & Input
  const [promptInput, setPromptInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);
  const [lastUserMessage, setLastUserMessage] = useState<string>('');
  const [lastAssistantMessage, setLastAssistantMessage] = useState<string>('');

  // Voice Interaction
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  // Field / Contextual Workspace State
  interface CodingResultData {
    provider_id?: string;
    status?: string;
    summary?: string;
    diff?: string;
    modified_files?: string[];
    test_output?: string;
    test_passed?: boolean;
    external_task_id?: string;
    execution_id?: string;
    project_path?: string;
    verification_passed?: boolean;
    verification_details?: {
      reason?: string;
      acceptance_passed?: boolean;
      files_passed?: boolean;
      tests_passed?: boolean;
      symbols_passed?: boolean;
    };
    interaction_prompt?: string;
    interaction_options?: string[];
    awaiting?: string | null;
    run_terminal?: boolean;
    verified?: boolean;
    deliverable_ready?: boolean;
  }

  const [activeWorkContext, setActiveWorkContext] = useState<{
    title: string;
    description: string;
    steps: StepItem[];
    actionExecutionId?: string;
    missionId?: string;
    proposalId?: string;
    proposal?: any;
    hasDeliverables?: boolean;
    status: 'working' | 'needs-you' | 'done';
    codingResult?: CodingResultData;
    actionArgs?: any;
    designatedProviderId?: string;
  } | null>(null);

  // Proposal & Approval Decisions State
  const [isAcceptingProposal, setIsAcceptingProposal] = useState(false);
  const [proposalDecisions, setProposalDecisions] = useState<Record<string, 'accepted' | 'rejected'>>({});
  const [isDecidingApproval, setIsDecidingApproval] = useState(false);
  const [executionDecisions, setExecutionDecisions] = useState<Record<string, 'approved' | 'rejected'>>({});

  // Chat History & Sessions
  const [sessions, setSessions] = useState<Array<{ id: string; title: string; updated_at: string }>>([]);
  const [isMinimizedCard, setIsMinimizedCard] = useState(false);
  const [interactionReplyText, setInteractionReplyText] = useState('');
  const [isSubmittingInteraction, setIsSubmittingInteraction] = useState(false);

  // Pending Approvals & Overview
  const [pendingApprovals, setPendingApprovals] = useState<any[]>([]);
  const [isManualDrawerOpen, setIsManualDrawerOpen] = useState(false);

  // Thought Bubbles
  const [bubbles, setBubbles] = useState<ThoughtBubbleItem[]>([]);

  const showToast = useContext(ToastContext);

  // External Coding Agent Providers State
  interface SetupOperationItem {
    id: string;
    provider_id: string;
    operation_type: string;
    status: string;
    progress: number;
    message: string;
    logs: string[];
    started_at: string;
    completed_at?: string | null;
    error?: string | null;
  }

  interface CodingProviderItem {
    id: string;
    name: string;
    description: string;
    installation_state?: string;
    authentication_state?: string;
    operational_state?: string;
    auth_method?: string | null;
    installed: boolean;
    authenticated: boolean;
    available: boolean;
    is_preferred: boolean;
    binary_path?: string | null;
    version?: string | null;
    version_requirement?: string | null;
    diagnostic: string;
    missing_prerequisites: string[];
    capabilities: any;
    next_action?: string;
    error_code?: string | null;
    active_setup_operation?: SetupOperationItem | null;
  }

  const [codingProviders, setCodingProviders] = useState<CodingProviderItem[]>([]);
  const [preferredProviderId, setPreferredProviderId] = useState<string>('antigravity');
  const [isCodingModalOpen, setIsCodingModalOpen] = useState(false);
  const [isUpdatingPreference, setIsUpdatingPreference] = useState(false);
  const [designatedProviderOverride, setDesignatedProviderOverride] = useState<string | null>(null);

  // Lifecycle Modals & Active Operation State
  const [installConfirmTarget, setInstallConfirmTarget] = useState<CodingProviderItem | null>(null);
  const [isInstalling, setIsInstalling] = useState(false);
  const [authInstructionsModal, setAuthInstructionsModal] = useState<{ provider: CodingProviderItem; instructions: string[] } | null>(null);
  const [expandedLogs, setExpandedLogs] = useState<Record<string, boolean>>({});

  const fetchCodingProviders = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/coding/providers'));
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.providers)) {
          setCodingProviders(data.providers);
        }
        if (data.preferred_provider_id) {
          setPreferredProviderId(data.preferred_provider_id);
        }
      }
    } catch (err) {
      console.debug('Failed to fetch coding providers:', err);
    }
  }, []);

  const handleSelectPreferredProvider = async (providerId: string) => {
    if (isUpdatingPreference) return;
    setIsUpdatingPreference(true);
    try {
      const res = await fetch(apiUrl('/api/coding/preferences'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preferred_provider_id: providerId }),
      });
      if (res.ok) {
        const data = await res.json();
        setPreferredProviderId(data.preferred_provider_id);
        if (Array.isArray(data.providers)) {
          setCodingProviders(data.providers);
        }
        const provName = data.providers?.find((p: any) => p.id === providerId)?.name || providerId;
        showToast(`Coding agent predefinito impostato su: ${provName}`, 'success');
      } else {
        const err = await res.json();
        showToast(err.detail || 'Impossibile aggiornare la preferenza.', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Errore di connessione.', 'error');
    } finally {
      setIsUpdatingPreference(false);
    }
  };

  const handleDiagnoseProvider = async (providerId: string) => {
    try {
      showToast('Verifica diagnostica avviata...', 'info');
      const res = await fetch(apiUrl(`/api/coding/providers/${providerId}/diagnose`), { method: 'POST' });
      if (res.ok) {
        await fetchCodingProviders();
        showToast('Diagnostica completata.', 'success');
      } else {
        const err = await res.json();
        showToast(err.detail || 'Errore durante la diagnostica.', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Errore di connessione.', 'error');
    }
  };

  const handleConfirmInstall = async () => {
    if (!installConfirmTarget || isInstalling) return;
    setIsInstalling(true);
    try {
      const res = await fetch(apiUrl(`/api/coding/providers/${installConfirmTarget.id}/install`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed: true }),
      });
      if (res.ok) {
        showToast(`Installazione di ${installConfirmTarget.name} avviata in background.`, 'info');
        setInstallConfirmTarget(null);
        await fetchCodingProviders();
      } else {
        const err = await res.json();
        showToast(err.detail || 'Errore durante l\'avvio dell\'installazione.', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Errore di connessione.', 'error');
    } finally {
      setIsInstalling(false);
    }
  };

  const handleAuthenticateProvider = async (provider: CodingProviderItem) => {
    try {
      const res = await fetch(apiUrl(`/api/coding/providers/${provider.id}/authenticate`), { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.instructions) && data.instructions.length > 0) {
          setAuthInstructionsModal({ provider, instructions: data.instructions });
        } else {
          showToast(`Verifica autenticazione per ${provider.name} completata.`, 'info');
        }
        await fetchCodingProviders();
      } else {
        const err = await res.json();
        showToast(err.detail || 'Errore durante l\'avvio dell\'autenticazione.', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Errore di connessione.', 'error');
    }
  };

  const handleCancelOperation = async (operationId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/coding/setup-operations/${operationId}/cancel`), { method: 'POST' });
      if (res.ok) {
        showToast('Richiesta di annullamento inviata.', 'info');
        await fetchCodingProviders();
      }
    } catch (err: any) {
      showToast(err.message || 'Errore annullamento.', 'error');
    }
  };

  // Poll active setup operation if any provider has one running
  useEffect(() => {
    const hasRunningOp = codingProviders.some(
      p => p.active_setup_operation?.status === 'running' || p.active_setup_operation?.status === 'pending'
    );
    if (!hasRunningOp) return;

    const interval = setInterval(() => {
      fetchCodingProviders();
    }, 2000);

    return () => clearInterval(interval);
  }, [codingProviders, fetchCodingProviders]);

  // 1. Fetch Real Overview from Backend
  const fetchOverview = useCallback(() => {
    if (!workspaceName) return;
    fetch(apiUrl(`/api/personal/overview?workspace_id=${encodeURIComponent(workspaceName)}`))
      .then(res => res.json())
      .then(data => {
        if (data && typeof data === 'object') {
          if (Array.isArray(data.coding_providers) && data.coding_providers.length > 0) {
            setCodingProviders(data.coding_providers);
          }
          if (data.preferred_coding_provider) {
            setPreferredProviderId(data.preferred_coding_provider);
          }
          if (Array.isArray(data.pending_approvals)) {
            setPendingApprovals(data.pending_approvals);
            if (data.pending_approvals.length > 0) {
              setOrbState('needs-you');
              const topApp = data.pending_approvals[0];
              setActiveWorkContext(prev => ({
                title: topApp.action_name || 'Autorizzazione Richiesta',
                description: topApp.target || 'Operazione sul sistema',
                steps: prev?.steps || [],
                actionExecutionId: topApp.execution_id || topApp.id,
                status: 'needs-you',
              }));
              addBubble({
                id: `app-${topApp.id}`,
                text: `Decisione richiesta: ${topApp.action_name || 'Azione da confermare'}`,
                slot: 'top-right',
                tier: 'attention',
              });
            }
          }
        }
      })
      .catch(console.error);
  }, [workspaceName]);

  const fetchSessions = useCallback(async () => {
    if (!workspaceName) return;
    try {
      const res = await fetch(apiUrl(`/api/personal/sessions?workspace_id=${encodeURIComponent(workspaceName)}&limit=30`));
      if (res.ok) {
        const data = await res.json();
        setSessions(data || []);
      }
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    }
  }, [workspaceName]);

  const restoreSession = useCallback(async (sid: string) => {
    try {
      const res = await fetch(apiUrl(`/api/personal/sessions/${encodeURIComponent(sid)}`));
      if (!isMountedRef.current) return;
      const outcome = classifyRestoreResponse(res.status);
      if (outcome === 'stale') {
        // The stored id points to a session that no longer exists: forget it and start from a clean, coherent state.
        // (Other failures keep the id: they do not prove the session is gone.)
        forgetStaleSession(localStorage, sid);
        setSessionId(null);
        setLastUserMessage('');
        setLastAssistantMessage('');
        setActiveWorkContext(null);
        setOrbState('idle');
        return;
      }
      if (outcome === 'restored') {
        const data = await res.json();
        if (!isMountedRef.current) return;
        setSessionId(sid);
        localStorage.setItem('aether_active_session_id', sid);
        const msgs = data.messages || [];
        if (msgs.length > 0) {
          const userMsgs = msgs.filter((m: any) => m.role === 'user');
          const asstMsgs = msgs.filter((m: any) => m.role === 'assistant');
          if (userMsgs.length > 0) setLastUserMessage(userMsgs[userMsgs.length - 1].content);
          if (asstMsgs.length > 0) {
            const lastAsst = asstMsgs[asstMsgs.length - 1];
            setLastAssistantMessage(lastAsst.content);
            if (lastAsst.metadata?.coding_result) {
              const cr = lastAsst.metadata.coding_result;
              setActiveWorkContext({
                title: 'Attività Coding Delegata',
                description: cr.summary || lastAsst.content,
                steps: lastAsst.steps || [],
                status: classifyCodingResult(cr).workStatus,
                codingResult: cr,
                hasDeliverables: Boolean(cr.modified_files?.length),
              });
              setOrbState(classifyCodingResult(cr).kind === 'completed' ? 'done' : 'idle');
            }
          }
        }
      }
    } catch (e) {
      console.error('Failed to restore session:', e);
    }
  }, []);

  const handleSelectSession = (targetSessionId: string) => {
    restoreSession(targetSessionId);
    setIsManualDrawerOpen(false);
    showToast('Sessione chat caricata.', 'info');
  };

  const handleNewSession = () => {
    const freshId = `session-${Date.now()}`;
    setSessionId(freshId);
    localStorage.setItem('aether_active_session_id', freshId);
    setLastUserMessage('');
    setLastAssistantMessage('');
    setActiveWorkContext(null);
    setOrbState('idle');
    setIsManualDrawerOpen(false);
    fetchSessions();
    showToast('Nuova conversazione avviata.', 'success');
  };

  const handleDeleteSession = async (targetSessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await fetch(apiUrl(`/api/personal/sessions/${encodeURIComponent(targetSessionId)}`), {
        method: 'DELETE',
      });
      if (res.ok) {
        showToast('Conversazione eliminata.', 'info');
        if (sessionId === targetSessionId) {
          handleNewSession();
        } else {
          fetchSessions();
        }
      }
    } catch (err) {
      showToast('Errore eliminazione sessione.', 'error');
    }
  };

  const handleInteractCoding = async (messageToSend?: string) => {
    const msg = (messageToSend || interactionReplyText).trim();
    const execId = activeWorkContext?.actionExecutionId || activeWorkContext?.codingResult?.execution_id;
    if (!msg || !execId || isSubmittingInteraction) return;

    setIsSubmittingInteraction(true);
    try {
      const res = await fetch(apiUrl('/api/personal/coding/interact'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          execution_id: execId,
          message: msg,
        }),
      });

      if (res.ok) {
        setInteractionReplyText('');
        showToast('Risposta inviata ad Antigravity. Esecuzione ripresa...', 'success');
        setOrbState('working');
        fetchOverview();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Errore durante l\'invio della risposta.', 'error');
      }
    } catch (e) {
      showToast('Impossibile comunicare con l\'agente.', 'error');
    } finally {
      setIsSubmittingInteraction(false);
    }
  };

  useEffect(() => {
    fetchOverview();
    fetchCodingProviders();
    fetchSessions();
    const storedSid = localStorage.getItem('aether_active_session_id');
    if (storedSid) {
      restoreSession(storedSid);
    }
  }, [fetchOverview, fetchCodingProviders, fetchSessions, restoreSession]);

  // 2. Real-Time SSE Stream for Steps and Progress
  useEffect(() => {
    if (!workspaceName || typeof EventSource === 'undefined') return;

    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource(apiUrl(`/api/personal/events?workspace_id=${encodeURIComponent(workspaceName)}`));

      eventSource.addEventListener('step_update', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (data && data.step) {
            setActiveWorkContext(prev => {
              if (!prev) return null;
              const exists = prev.steps.some(s => s.id === data.step.id);
              const nextSteps = exists
                ? prev.steps.map(s => s.id === data.step.id ? data.step : s)
                : [...prev.steps, data.step];
              return { ...prev, steps: nextSteps };
            });

            // Mostra bubble solo per passaggi operativi rilevanti (azioni, deleghe, proposte), non per log cognitivi interni
            if (data.step.category === 'action' || data.step.category === 'delegation' || data.step.category === 'proposal') {
              addBubble({
                id: `step-${data.step.id}`,
                text: data.step.title,
                slot: 'top-left',
                tier: 'info',
              });
            }
          }
        } catch {
          // Ignore parse errors
        }
      });

      eventSource.addEventListener('task_completed', () => {
        setOrbState('done');
        fetchOverview();
        setTimeout(() => {
          setOrbState('idle');
        }, 3200);
      });

      eventSource.addEventListener('notification', () => {
        fetchOverview();
      });
    } catch (err) {
      console.debug('EventSource connection error:', err);
    }

    return () => {
      if (eventSource) eventSource.close();
    };
  }, [workspaceName, fetchOverview]);

  // 3. Web Speech Recognition for Real Voice Input
  useEffect(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      const rec = new SpeechRecognition();
      rec.continuous = false;
      rec.interimResults = true;
      rec.lang = 'it-IT';

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
        setOrbState('idle');
      };

      rec.onend = () => {
        setIsListening(false);
        setOrbState('idle');
      };

      recognitionRef.current = rec;
    }
  }, []);

  // Audio level metering for Living Orb responsiveness during voice
  useEffect(() => {
    if (!isListening) {
      setAudioLevel(0);
      return;
    }
    const interval = setInterval(() => {
      setAudioLevel(0.12 + Math.random() * 0.4);
    }, 100);
    return () => clearInterval(interval);
  }, [isListening]);

  const toggleVoiceListening = () => {
    if (!recognitionRef.current) {
      showToast('Riconoscimento vocale non supportato in questo browser.', 'warning');
      return;
    }
    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
      setOrbState('idle');
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
        setOrbState('listening');
        showToast('In ascolto... Parla pure con Aether.', 'info');
      } catch (e) {
        console.error(e);
      }
    }
  };

  // Helper to add Thought Bubble with automatic clean expiration
  const addBubble = (bubble: ThoughtBubbleItem) => {
    setBubbles(prev => {
      const filtered = prev.filter(b => b.slot !== bubble.slot);
      return [...filtered, bubble];
    });

    if (bubble.tier !== 'attention') {
      setTimeout(() => {
        setBubbles(prev => prev.filter(b => b.id !== bubble.id));
      }, 5000);
    }
  };

  // 4. Submit Real Prompt to Aether Core
  const handleSendPrompt = async (textToSend?: string) => {
    const text = (textToSend || promptInput).trim();
    if (!text || isSubmitting) return;

    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
    }

    setIsSubmitting(true);
    setOrbState('working');
    setLastUserMessage(text);
    setPromptInput('');

    try {
      const res = await fetch(apiUrl('/api/personal/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: text,
          session_id: sessionId,
          workspace_id: workspaceName,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setSessionId(data.session_id);
        if (data.session_id) {
          localStorage.setItem('aether_active_session_id', data.session_id);
          fetchSessions();
        }
        setLastAssistantMessage(data.content || '');

        // Progressive Disclosure (Principi 1, 2, 6):
        // Mostra il contesto operativo SOLO per vero lavoro operativo (proposte, approvazioni, missioni, azioni mutanti).
        // Conversazioni semplici, cortesie o risposte informative restano pulite nello stream conversazionale.
        const isProposal = Boolean(data.metadata?.proposal || data.metadata?.proposal_id);
        const prop = data.metadata?.proposal;
        const proposalStatus = prop?.status || data.metadata?.status;
        const codingRes = data.metadata?.coding_result;
        const codingStat = data.metadata?.coding_status;
        const isActionOrMission = Boolean(
          data.action_execution_id ||
          data.mission_id ||
          data.tier === 'delegate' ||
          data.tier === 'mission' ||
          data.tier === 'act' ||
          data.tier === 'do' ||
          codingRes ||
          codingStat
        );
        const hasRealOperationalWork = isProposal || isActionOrMission;

        if (hasRealOperationalWork) {
          let cardTitle = 'Attività in corso';
          let cardStatus: 'working' | 'needs-you' | 'done' = 'done';

          if (codingRes) {
            const pres = classifyCodingResult(codingRes);
            cardTitle = pres.title;
            cardStatus = pres.workStatus;
          } else if (isProposal) {
            const cleanTitle = prop?.title || 'Proposta operativa da confermare';
            cardTitle = `Proposta: ${cleanTitle}`;
            cardStatus = 'needs-you';
          } else if (data.action_execution_id) {
            cardTitle = 'Richiesta di approvazione';
            cardStatus = 'needs-you';
          } else if (data.tier === 'mission' || data.tier === 'delegate' || data.mission_id) {
            cardTitle = 'Missione operativa';
            cardStatus = data.status === 'completed' ? 'done' : 'working';
          } else if (data.tier === 'do') {
            cardTitle = 'Operazione completata';
            cardStatus = 'done';
          }

          const operationalSteps = (data.steps || []).filter((s: any) =>
            s.category === 'action' || s.category === 'delegation' || s.category === 'proposal'
          );

          const descText = isProposal && prop?.objective
            ? prop.objective
            : (codingRes?.summary || (data.content ? data.content.replace(/^#+\s+.*?\n+/g, '').slice(0, 140) + '...' : 'Attività operativa in carico ad Aether'));

          setActiveWorkContext({
            title: cardTitle,
            description: descText,
            steps: operationalSteps.length > 0 ? operationalSteps : (data.steps || []),
            actionExecutionId: data.action_execution_id,
            missionId: data.mission_id,
            proposalId: data.metadata?.proposal_id,
            proposal: prop,
            hasDeliverables: Boolean(data.mission_id || prop?.expected_deliverables?.length || codingRes?.modified_files?.length),
            status: cardStatus,
            codingResult: codingRes,
            actionArgs: data.metadata?.action_args,
            designatedProviderId: data.metadata?.designated_provider_id,
          });
        } else {
          setActiveWorkContext(null);
        }

        if (data.action_execution_id || (isProposal && proposalStatus !== 'accepted')) {
          setOrbState('needs-you');
        } else {
          setOrbState('done');
          setTimeout(() => {
            setOrbState('idle');
          }, 3000);
        }

        fetchOverview();
      } else {
        const errData = await res.json().catch(() => ({}));
        const errMsg = errData.detail || 'Impossibile completare la richiesta.';
        showToast(errMsg, 'error');
        setLastAssistantMessage(`⚠️ Non è stato possibile completare la richiesta: ${errMsg}`);
        setOrbState('idle');
      }
    } catch (err: any) {
      console.error('Chat error:', err);
      showToast('Errore di connessione con il runtime di Aether.', 'error');
      setOrbState('idle');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 5. Phase 1 — Proposal Acceptance
  const handleAcceptProposal = async (proposalId: string, version?: number) => {
    if (!proposalId || isAcceptingProposal) return;
    setIsAcceptingProposal(true);
    try {
      const res = await fetch(apiUrl(`/api/personal/proposals/${encodeURIComponent(proposalId)}/accept`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_version: version,
          actor: 'user',
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Impossibile confermare la proposta.', 'error');
        setIsAcceptingProposal(false);
        return;
      }

      const acceptData = await res.json();
      setProposalDecisions(prev => ({ ...prev, [proposalId]: 'accepted' }));
      showToast('Piano confermato. Aether avvia la richiesta operativa...', 'success');
      setOrbState('working');

      addBubble({
        id: `prop-accepted-${proposalId}`,
        text: 'Piano confermato • Avvio in corso',
        slot: 'top-left',
        tier: 'done',
      });

      // Pass task-scoped provider override without overwriting global user preferences
      const providerForTask = designatedProviderOverride || undefined;

      // Submit prompt with ExecutionAuthority to trigger the execution gate
      const promptToRun = lastUserMessage || activeWorkContext?.description || 'Esegui il piano confermato';
      const chatRes = await fetch(apiUrl('/api/personal/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: promptToRun,
          session_id: sessionId,
          workspace_id: workspaceName,
          authority: acceptData.authority,
          provider_id: providerForTask,
        }),
      });

      if (chatRes.ok) {
        const chatData = await chatRes.json();
        setSessionId(chatData.session_id);
        if (chatData.session_id) {
          localStorage.setItem('aether_active_session_id', chatData.session_id);
          fetchSessions();
        }
        setLastAssistantMessage(chatData.content || '');

        if (chatData.action_execution_id) {
          // Entered Phase 2: HITL Execution Gate
          setOrbState('needs-you');
          setActiveWorkContext({
            title: 'Autorizzazione Esecuzione Coding Agent',
            description: chatData.content ? chatData.content.slice(0, 160) + '...' : 'Richiesta di autorizzazione per modifiche al progetto.',
            steps: (chatData.steps || []).filter((s: any) => s.category === 'action' || s.category === 'delegation'),
            actionExecutionId: chatData.action_execution_id,
            status: 'needs-you',
          });
          fetchOverview();
        } else if (chatData.metadata?.coding_result) {
          // Completed directly or waiting for interaction
          const cr = chatData.metadata.coding_result;
          const pres = classifyCodingResult(cr);
          setOrbState(pres.kind === 'completed' ? 'done' : pres.workStatus === 'needs-you' ? 'needs-you' : 'idle');
          setActiveWorkContext({
            title: pres.title,
            description: cr.summary || chatData.content || pres.label,
            steps: chatData.steps || [],
            status: pres.workStatus,
            codingResult: cr,
            hasDeliverables: Boolean(cr.modified_files?.length),
          });
        }
      } else {
        const errData = await chatRes.json().catch(() => ({}));
        showToast(errData.detail || 'Errore durante l\'avvio operativo.', 'error');
        setOrbState('idle');
      }
    } catch (err: any) {
      showToast(err.message || 'Errore durante la conferma della proposta.', 'error');
      setOrbState('idle');
    } finally {
      setIsAcceptingProposal(false);
    }
  };

  const handleRejectProposal = async (proposalId: string) => {
    // The decision is stored by the backend, otherwise the proposal would still be pending after a reload.
    try {
      const res = await fetch(apiUrl(`/api/personal/proposals/${encodeURIComponent(proposalId)}/revoke`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'rejected by user', actor: 'user' }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Impossibile rifiutare la proposta.', 'error');
        return;
      }
    } catch {
      showToast('Impossibile rifiutare la proposta.', 'error');
      return;
    }
    setProposalDecisions(prev => ({ ...prev, [proposalId]: 'rejected' }));
    showToast('Proposta rifiutata.', 'info');
    setTimeout(() => {
      setActiveWorkContext(null);
      setOrbState('idle');
    }, 1200);
  };

  const [clarifyDraft, setClarifyDraft] = useState('');
  const [isClarifying, setIsClarifying] = useState(false);

  // The user answers the open question of a proposal: the request is resumed with a new proposal to approve.
  const handleClarifyProposal = async (proposalId: string) => {
    const answer = clarifyDraft.trim();
    if (!proposalId || !answer || isClarifying) return;
    setIsClarifying(true);
    try {
      const res = await fetch(apiUrl(`/api/personal/proposals/${encodeURIComponent(proposalId)}/clarify`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer, actor: 'user', session_id: sessionId }),
      });
      const data = await res.json().catch(() => ({} as any));
      if (!res.ok) {
        showToast(data.detail || 'Impossibile inviare il chiarimento.', 'error');
        return;
      }
      const next = data.proposal;
      setClarifyDraft('');
      setLastUserMessage(next?.objective || answer);   // what gets executed on approval includes the answer
      setActiveWorkContext(prev => prev ? {
        ...prev,
        description: next?.objective || prev.description,
        proposalId: next?.id,
        proposal: next,
        steps: (next?.proposed_steps || []).map((st: any) => ({ id: st.id, title: st.title, status: 'pending', category: 'proposal' })),
        status: 'needs-you',
      } : prev);
      showToast(next?.status === 'needs_clarification'
        ? 'Serve ancora un chiarimento.' : 'Piano aggiornato: puoi approvarlo.', 'info');
    } catch (err: any) {
      showToast(err?.message || 'Impossibile inviare il chiarimento.', 'error');
    } finally {
      setIsClarifying(false);
    }
  };

  // 6. Polling for Execution Results & Evidence
  const pollExecutionResults = useCallback((executionId: string, maxAttempts = 30) => {
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const res = await fetch(apiUrl(`/api/actions/executions/${encodeURIComponent(executionId)}`));
        if (res.ok) {
          const exec = await res.json();
          if (exec.status === 'succeeded' || exec.status === 'completed') {
            // The action record succeeds when the request is accepted: look at the RUN to know where it really is.
            const out = exec.output_data || {};
            const pres = classifyCodingResult(out);
            setActiveWorkContext(prev => ({
              title: pres.title,
              description: out.summary || pres.label,
              steps: prev?.steps || [],
              actionExecutionId: executionId,
              status: pres.workStatus,
              codingResult: out,
              hasDeliverables: Boolean(out.modified_files?.length),
            }));
            if (!runStillActive(out)) {
              clearInterval(interval);
              setOrbState(pres.kind === 'completed' ? 'done' : pres.workStatus === 'needs-you' ? 'needs-you' : 'idle');
              fetchOverview();
              setTimeout(() => setOrbState('idle'), 3500);
            }
          } else if (exec.status === 'failed' || exec.status === 'cancelled') {
            clearInterval(interval);
            showToast(exec.error_message || 'Esecuzione non riuscita.', 'error');
            setOrbState('idle');
            fetchOverview();
          }
        }
      } catch (e) {
        console.debug('Polling execution error:', e);
      }
      if (attempts >= maxAttempts) {
        clearInterval(interval);
      }
    }, 1500);
  }, [fetchOverview, showToast]);

  // 7. Phase 2 — Real Approval Decision Submission
  const handleApproveAction = async (targetId: string) => {
    if (isDecidingApproval) return;
    setIsDecidingApproval(true);
    setExecutionDecisions(prev => ({ ...prev, [targetId]: 'approved' }));

    try {
      const res = await submitApprovalDecision({
        target_type: 'action_execution',
        target_id: targetId,
        decision: 'approve',
        approver: 'user',
        workspaceName,
      });

      if (res.success) {
        showToast(res.message || 'Approvazione registrata.', approvalToastKind(res, 'approve'));
        setPendingApprovals(prev => prev.filter(a => (a.execution_id || a.id) !== targetId));
        setOrbState('working');

        addBubble({
          id: `app-done-${targetId}`,
          text: 'Decisione confermata • Esecuzione in corso',
          slot: 'top-left',
          tier: 'done',
        });

        const entity = res.entity;
        if (entity && (entity.status === 'succeeded' || entity.status === 'completed') && entity.output_data) {
          const out = entity.output_data;
          const pres = classifyCodingResult(out);
          setActiveWorkContext(prev => ({
            title: pres.title,
            description: out.summary || pres.label,
            steps: prev?.steps || [],
            actionExecutionId: targetId,
            status: pres.workStatus,
            codingResult: out,
            hasDeliverables: Boolean(out.modified_files?.length),
          }));
          setOrbState(pres.kind === 'completed' ? 'done' : pres.workStatus === 'needs-you' ? 'needs-you' : 'idle');
          setTimeout(() => setOrbState('idle'), 3500);
          if (runStillActive(out)) pollExecutionResults(targetId);
        } else {
          pollExecutionResults(targetId);
        }
      } else {
        showToast(res.message, 'error');
        setExecutionDecisions(prev => {
          const next = { ...prev };
          delete next[targetId];
          return next;
        });
      }
    } catch (err: any) {
      showToast(err.message || 'Errore durante la conferma.', 'error');
      setExecutionDecisions(prev => {
        const next = { ...prev };
        delete next[targetId];
        return next;
      });
    } finally {
      setIsDecidingApproval(false);
    }
  };

  const handleRejectAction = async (targetId: string) => {
    if (isDecidingApproval) return;
    setIsDecidingApproval(true);
    setExecutionDecisions(prev => ({ ...prev, [targetId]: 'rejected' }));

    try {
      const res = await submitApprovalDecision({
        target_type: 'action_execution',
        target_id: targetId,
        decision: 'reject',
        reason: 'Rifiutato dall\'utente',
        workspaceName,
      });

      if (res.success) {
        showToast('Operazione annullata.', 'info');
        setPendingApprovals(prev => prev.filter(a => (a.execution_id || a.id) !== targetId));
        setTimeout(() => {
          setActiveWorkContext(null);
          setOrbState('idle');
          fetchOverview();
        }, 1200);
      } else {
        showToast(res.message, 'error');
        setExecutionDecisions(prev => {
          const next = { ...prev };
          delete next[targetId];
          return next;
        });
      }
    } catch (err: any) {
      showToast(err.message || 'Errore durante l\'annullamento.', 'error');
      setExecutionDecisions(prev => {
        const next = { ...prev };
        delete next[targetId];
        return next;
      });
    } finally {
      setIsDecidingApproval(false);
    }
  };

  const isFieldVisible = !!activeWorkContext || pendingApprovals.length > 0;

  const codingPres = classifyCodingResult(activeWorkContext?.codingResult);

  return (
    <div className="aether-v2-container">
      {/* Dynamic Atmospheric Glow */}
      <div className={`aether-v2-ambient-glow glow-${orbState}`} />

      {/* Minimalist Top Header */}
      <header className="aether-v2-header">
        <div className="header-brand">
          <div className="brand-dot" />
          <span className="brand-title">Aether</span>
          <span className="brand-tag">Assistant V2</span>
        </div>

        <div className="header-center-status">
          <span className={`status-dot-indicator status-dot-${orbState}`} />
          <span>
            {orbState === 'idle' && 'Disponibile'}
            {orbState === 'listening' && 'In ascolto'}
            {orbState === 'speaking' && 'In risposta'}
            {orbState === 'working' && 'In attività'}
            {orbState === 'needs-you' && 'Decisione richiesta'}
            {orbState === 'done' && 'Completato'}
          </span>
        </div>

        <div className="header-actions">
          {/* External Coding Agent Quick Selector Pill */}
          <button
            className="v2-action-btn coding-agent-header-btn"
            onClick={() => {
              fetchCodingProviders();
              setIsCodingModalOpen(true);
            }}
            title="Gestisci e seleziona coding agent esterni (Google Antigravity, Claude Code, OpenAI Codex)"
          >
            <Code2 size={13} color="#a78bfa" />
            <span>Coding: {codingProviders.find(p => p.id === preferredProviderId)?.name || 'Antigravity'}</span>
            <span
              className={`coding-status-dot ${
                codingProviders.find(p => p.id === preferredProviderId)?.available
                  ? 'dot-ready'
                  : codingProviders.find(p => p.id === preferredProviderId)?.installed
                  ? 'dot-warning'
                  : 'dot-offline'
              }`}
            />
          </button>

          {/* V1 Classic Switch Button */}
          <button
            className="v2-action-btn v2-switch-btn"
            onClick={onSwitchToV1}
            title="Passa all'interfaccia completa con dashboard, sidebar e missioni"
          >
            <Layers size={13} />
            <span>Interfaccia V1 Classica</span>
          </button>

          {/* Manual Mode / Spazio & Strumenti */}
          <button
            className="v2-action-btn"
            onClick={() => setIsManualDrawerOpen(true)}
            title="Accesso manuale a lavori, servizi, automazioni e impostazioni"
          >
            <Briefcase size={13} />
            <span>Spazio & Strumenti</span>
          </button>
        </div>
      </header>

      {/* Main Interactive Stage */}
      <main className="aether-v2-stage">
        {/* Living 3D Point Sphere */}
        <div className={`orb-stage-wrapper ${isFieldVisible ? 'orb-stage-elevated' : ''}`}>
          <AetherOrb
            state={orbState}
            audioLevel={audioLevel}
            quality={quality}
            size={640}
            onClick={() => {
              // Micro-reaction feedback
              if (orbState === 'idle') {
                showToast('Aether è presente e pronto ad aiutarti.', 'info');
              }
            }}
          />
        </div>

        {/* Thought Bubbles (Protected Perimeter Orbit) */}
        <div className="thought-bubbles-container">
          {bubbles.map(b => (
            <div
              key={b.id}
              className={`production-bubble bubble-slot-${b.slot} ${b.tier === 'attention' ? 'bubble-attention' : ''}`}
              onClick={b.onClick}
            >
              <Sparkles size={13} color="#c4b5fd" />
              <span>{b.text}</span>
            </div>
          ))}
        </div>

        {/* Aether Field Contextual Workspace (Non-overlapping Bottom Surface) */}
        <div className={`aether-field-container ${isFieldVisible ? 'field-visible' : ''}`}>
          {pendingApprovals.length > 0 ? (
            // FASE 2: APPROVAL SURFACE (Autorizzazione Esecuzione HITL Gate)
            <div className="field-card approval-card-highlight">
              <div className="field-header">
                <div className="field-title-group">
                  <div className="field-icon-badge" style={{ background: 'rgba(245,158,11,0.15)', borderColor: 'rgba(245,158,11,0.4)', color: '#fbbf24' }}>
                    <AlertTriangle size={16} />
                  </div>
                  <div>
                    <h3 className="field-title">
                      {pendingApprovals[0].title || 'Autorizzazione richiesta per procedere'}
                    </h3>
                    <p className="field-desc">
                      {pendingApprovals[0].human_summary || pendingApprovals[0].summary || pendingApprovals[0].action_name || 'Aether richiede la tua conferma prima di applicare questa operazione.'}
                    </p>
                  </div>
                </div>
                <div className="phase-tag-badge phase-badge-execution">
                  Fase 2 • Autorizzazione Esecuzione
                </div>
              </div>

              <div className="field-body">
                {executionDecisions[pendingApprovals[0].execution_id || pendingApprovals[0].id] === 'approved' ? (
                  <div className="card-decision-banner decision-banner-approved">
                    <CheckCircle2 size={14} />
                    <span>Autorizzazione concessa • Esecuzione delegata in corso...</span>
                  </div>
                ) : executionDecisions[pendingApprovals[0].execution_id || pendingApprovals[0].id] === 'rejected' ? (
                  <div className="card-decision-banner decision-banner-rejected">
                    <X size={14} />
                    <span>Operazione annullata dall'utente</span>
                  </div>
                ) : (
                  <>
                    {/* 4 Pilastri di Decisione (Principio 4) */}
                    <div className="approval-narrative-card">
                      <div className="narrative-point">
                        <span className="narrative-label">Perché serve il tuo consenso</span>
                        <span className="narrative-val">
                          {pendingApprovals[0].reason || 'Questa operazione apporta modifiche permanenti al progetto tramite un agente di coding esterno o modifica servizi autorizzati.'}
                        </span>
                      </div>
                      <div className="narrative-point">
                        <span className="narrative-label">Cosa accadrà</span>
                        <span className="narrative-val">
                          {pendingApprovals[0].consequences || 'L\'operazione verrà eseguita subito in sicurezza: i file modificati, il diff verificabile e l\'esito dei test verranno raccolti automaticamente.'}
                        </span>
                      </div>
                      <div className="narrative-recommendation">
                        <Sparkles size={14} color="#fbbf24" style={{ flexShrink: 0, marginTop: 1 }} />
                        <span>
                          <strong>Raccomandazione di Aether:</strong> {pendingApprovals[0].recommendation || 'Le verifiche preliminari sono state superate. Puoi autorizzare con tranquillità.'}
                        </span>
                      </div>
                    </div>

                    {/* Dedicated Coding Agent Designation & Readiness Gate */}
                    {pendingApprovals[0].action_id === 'coding.delegate' && (() => {
                      const provId = pendingApprovals[0].input_data?.provider_id || pendingApprovals[0].designated_provider_id || preferredProviderId;
                      const prov = codingProviders.find(p => p.id === provId);
                      const isReady = prov?.available ?? true;
                      return (
                        <>
                          <div className="designated-agent-banner">
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <Code2 size={14} color="#a78bfa" />
                              <span style={{ color: '#e2e8f0', fontWeight: 600 }}>Agente designato per l'esecuzione:</span>
                              <span style={{ color: '#c4b5fd' }}>{prov?.name || (provId === 'antigravity' ? 'Google Antigravity' : provId)}</span>
                            </div>
                            {prov && (
                              <span className={prov.available ? 'status-badge-ready' : 'status-badge-warning'}>
                                <span className={`coding-status-dot ${prov.available ? 'dot-ready' : 'dot-warning'}`} />
                                {prov.available ? 'Pronto & Verificato' : 'Non pronto'}
                              </span>
                            )}
                          </div>
                          {!isReady && prov && (
                            <div className="unready-agent-warning">
                              <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
                              <div>
                                <strong>Blocco sicurezza (Fail-closed):</strong> {prov.diagnostic}.
                                {prov.missing_prerequisites?.length > 0 && (
                                  <div style={{ marginTop: '4px' }}>
                                    Prerequisiti mancanti: {prov.missing_prerequisites.join(', ')}
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </>
                      );
                    })()}

                    {/* Livello 4 — Dettagli tecnici completi su richiesta */}
                    <details className="technical-details-toggle">
                      <summary>Dettagli tecnici & parametri di esecuzione</summary>
                      <div className="technical-details-content">
                        <div>Azione: <code>{pendingApprovals[0].action_id || pendingApprovals[0].action_name || 'coding.delegate'}</code></div>
                        <div>Target: <code>{pendingApprovals[0].target || pendingApprovals[0].input_data?.project_path || 'Sistema locale'}</code></div>
                        <div>Livello di rischio: <code>{pendingApprovals[0].risk_level || 'Tier ACT (HITL)'}</code></div>
                        <div>ID Esecuzione: <code>{pendingApprovals[0].execution_id || pendingApprovals[0].id}</code></div>
                      </div>
                    </details>

                    <div className="approval-actions">
                      <button
                        className="btn-cancel-soft"
                        disabled={isDecidingApproval}
                        onClick={() => handleRejectAction(pendingApprovals[0].execution_id || pendingApprovals[0].id)}
                      >
                        Rifiuta o modifica
                      </button>
                      <button
                        className="btn-approve-amber"
                        disabled={
                          isDecidingApproval ||
                          (pendingApprovals[0].action_id === 'coding.delegate' &&
                            codingProviders.find(p => p.id === (pendingApprovals[0].input_data?.provider_id || preferredProviderId))?.available === false)
                        }
                        onClick={() => handleApproveAction(pendingApprovals[0].execution_id || pendingApprovals[0].id)}
                      >
                        <CheckCircle2 size={14} />
                        {isDecidingApproval ? 'Esecuzione in corso...' : 'Approva ed Esegui (Consigliato)'}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          ) : activeWorkContext?.codingResult ? (
            // FASE 3: VERIFIABLE CODING RESULTS SURFACE (Evidenza Diff + Test Automatici)
            <div className="field-card">
              <div className="field-header">
                <div className="field-title-group">
                  <div className="field-icon-badge" style={codingPres.verified
                    ? { background: 'rgba(16,185,129,0.15)', borderColor: 'rgba(16,185,129,0.4)', color: '#34d399' }
                    : { background: 'rgba(148,163,184,0.12)', borderColor: 'rgba(148,163,184,0.35)', color: '#94a3b8' }}>
                    {codingPres.verified ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                  </div>
                  <div>
                    <h3 className="field-title">{activeWorkContext.title}</h3>
                    <p className="field-desc">{activeWorkContext.description}</p>
                  </div>
                </div>
                <div className="phase-tag-badge phase-badge-results">
                  {codingPres.verified ? 'Fase 3 • Risultato Verificato' : `Fase 3 • ${codingPres.label}`}
                </div>
              </div>

              <div className="field-body">
                <div className="coding-results-box">
                  <div className="coding-meta-row">
                    <div className="coding-provider-badge">
                      <Sparkles size={12} />
                      <span>{activeWorkContext.codingResult.provider_id === 'antigravity' ? 'Google Antigravity' : (activeWorkContext.codingResult.provider_id === 'claude_code' ? 'Claude Code' : 'Coding Agent')}</span>
                    </div>
                    <div className={`coding-status-pill ${codingPres.pillClass}`} data-coding-kind={codingPres.kind}>
                      {codingPres.label}
                    </div>
                  </div>

                  {activeWorkContext.codingResult.summary && (
                    <p style={{ fontSize: '13px', lineHeight: 1.5, color: '#e2e8f0', margin: 0 }}>
                      {activeWorkContext.codingResult.summary}
                    </p>
                  )}

                  {Array.isArray(activeWorkContext.codingResult.modified_files) && activeWorkContext.codingResult.modified_files.length > 0 && (
                    <div>
                      <div style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', marginBottom: '4px' }}>
                        File Modificati ({activeWorkContext.codingResult.modified_files.length}):
                      </div>
                      <div className="modified-files-list">
                        {activeWorkContext.codingResult.modified_files.map((f: string) => (
                          <span key={f} className="file-badge-pill">{f}</span>
                        ))}
                      </div>
                    </div>
                  )}

                  {activeWorkContext.codingResult.diff && (
                    <details className="diff-viewer-toggle" open>
                      <summary>
                        <ChevronRight size={13} />
                        <span>Diff Git Verificabile ({activeWorkContext.codingResult.diff.split('\n').length} righe)</span>
                      </summary>
                      <pre className="diff-code-pre">{activeWorkContext.codingResult.diff}</pre>
                    </details>
                  )}

                  {activeWorkContext.codingResult.test_output && (
                    <div style={{ marginTop: '4px' }}>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: testOutcome(activeWorkContext.codingResult.test_passed) === 'passed' ? '#34d399' : testOutcome(activeWorkContext.codingResult.test_passed) === 'failed' ? '#f87171' : '#94a3b8', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {testOutcome(activeWorkContext.codingResult.test_passed) === 'passed' ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                        <span>Evidenza Test Automatici {testOutcome(activeWorkContext.codingResult.test_passed) === 'passed' ? '(Superati)' : testOutcome(activeWorkContext.codingResult.test_passed) === 'failed' ? '(Falliti)' : '(Esito non dichiarato)'}</span>
                      </div>
                      <pre className="test-output-box">{activeWorkContext.codingResult.test_output}</pre>
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
                  <button
                    className="v2-action-btn"
                    onClick={() => navigate('results')}
                    style={{ background: 'rgba(16,185,129,0.18)', borderColor: 'rgba(16,185,129,0.4)', color: '#34d399', fontWeight: 600 }}
                  >
                    <span>Visualizza Risultati & Consegne</span>
                    <ArrowRight size={13} />
                  </button>
                </div>
              </div>
            </div>
          ) : activeWorkContext?.proposal ? (
            // FASE 1: PROPOSAL CONFIRMATION SURFACE (Accettazione del Piano)
            <div className="field-card proposal-card-highlight">
              <div className="field-header">
                <div className="field-title-group">
                  <div className="field-icon-badge" style={{ background: 'rgba(140,92,246,0.15)', borderColor: 'rgba(140,92,246,0.4)', color: '#c4b5fd' }}>
                    <Sparkles size={16} />
                  </div>
                  <div>
                    <h3 className="field-title">{activeWorkContext.title}</h3>
                    <p className="field-desc">{activeWorkContext.description}</p>
                  </div>
                </div>
                <div className="phase-tag-badge phase-badge-proposal">
                  Fase 1 • Conferma del Piano
                </div>
              </div>

              <div className="field-body">
                {proposalDecisions[activeWorkContext.proposalId || activeWorkContext.proposal?.id] === 'accepted' ? (
                  <div className="card-decision-banner decision-banner-accepted">
                    <CheckCircle2 size={14} />
                    <span>Piano confermato • Avvio in corso...</span>
                  </div>
                ) : proposalDecisions[activeWorkContext.proposalId || activeWorkContext.proposal?.id] === 'rejected' ? (
                  <div className="card-decision-banner decision-banner-rejected">
                    <X size={14} />
                    <span>Proposta rifiutata dall'utente</span>
                  </div>
                ) : (
                  <>
                    <div className="approval-narrative-card" style={{ background: 'rgba(140,92,246,0.04)', borderColor: 'rgba(140,92,246,0.2)' }}>
                      <div className="narrative-point">
                        <span className="narrative-label" style={{ color: '#c4b5fd' }}>Perché serve la tua conferma</span>
                        <span className="narrative-val">
                          Aether ha formulato un piano operativo e richiede la tua conferma sul perimetro e sugli obiettivi prima di predisporre l'agente di coding esterno.
                        </span>
                      </div>
                      <div className="narrative-point">
                        <span className="narrative-label" style={{ color: '#c4b5fd' }}>Cosa accadrà</span>
                        <span className="narrative-val">
                          Una volta confermato il piano, Aether richiederà l'autorizzazione di esecuzione specifica (Fase 2) prima di applicare qualsiasi modifica concreta al codice.
                        </span>
                      </div>
                      {activeWorkContext.proposal?.status === 'needs_clarification' ? (
                        <div className="narrative-recommendation" style={{ background: 'rgba(245,158,11,0.08)', borderLeftColor: '#fbbf24', color: '#fef3c7' }}>
                          <AlertTriangle size={14} color="#fbbf24" style={{ flexShrink: 0, marginTop: 1 }} />
                          <span>
                            <strong>Stato di verifica:</strong> Sono necessari chiarimenti prima di procedere con l'approvazione del piano.
                          </span>
                        </div>
                      ) : (
                        <div className="narrative-recommendation" style={{ background: 'rgba(140,92,246,0.08)', borderLeftColor: '#a78bfa', color: '#ede9fe' }}>
                          <Sparkles size={14} color="#c4b5fd" style={{ flexShrink: 0, marginTop: 1 }} />
                          <span>
                            <strong>Raccomandazione di Aether:</strong> Piano verificato e strutturato. Puoi confermare per procedere alla fase di autorizzazione dell'esecuzione.
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Proposal Target Scope: Project & Target Files */}
                    {(() => {
                      const projPath = activeWorkContext.actionArgs?.project_path || activeWorkContext.proposal?.action_args?.project_path;
                      const targetFiles = activeWorkContext.actionArgs?.context_files || activeWorkContext.proposal?.action_args?.context_files || [];
                      if (!projPath && (!targetFiles || targetFiles.length === 0)) return null;
                      return (
                        <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', padding: '10px 14px', marginTop: '10px' }}>
                          {projPath && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: targetFiles.length > 0 ? '8px' : 0 }}>
                              <FolderGit2 size={14} color="#a78bfa" />
                              <span style={{ color: '#94a3b8', fontSize: '12px' }}>Progetto target:</span>
                              <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 8px', borderRadius: '4px', color: '#e2e8f0', fontFamily: 'monospace', fontSize: '12px', userSelect: 'all' }}>{projPath}</code>
                            </div>
                          )}
                          {targetFiles.length > 0 && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                              <FileCode size={14} color="#38bdf8" />
                              <span style={{ color: '#94a3b8', fontSize: '12px' }}>File interessati:</span>
                              {targetFiles.map((f: string, i: number) => (
                                <code key={i} style={{ background: 'rgba(56,189,248,0.1)', border: '1px solid rgba(56,189,248,0.2)', padding: '2px 8px', borderRadius: '4px', color: '#7dd3fc', fontFamily: 'monospace', fontSize: '12px' }}>{f}</code>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    {/* Proposed Steps List */}
                    {(() => {
                      const stepsList = activeWorkContext.proposal?.proposed_steps || activeWorkContext.proposal?.tasks || [];
                      if (!stepsList || stepsList.length === 0) return null;
                      return (
                        <div className="steps-list" style={{ marginTop: '10px' }}>
                          {stepsList.map((t: any, idx: number) => (
                            <div key={t.id || idx} className="step-row">
                              <span>{t.title || t.description}</span>
                              <span className="step-done" style={{ color: '#c4b5fd' }}>In piano</span>
                            </div>
                          ))}
                        </div>
                      );
                    })()}

                    {/* Designated Provider Selector in Phase 1 */}
                    <div className="designated-agent-selector">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Code2 size={14} color="#c4b5fd" />
                        <span style={{ color: '#e2e8f0', fontWeight: 500 }}>Coding Agent Designato:</span>
                      </div>
                      <select
                        className="agent-selector-select"
                        value={designatedProviderOverride || preferredProviderId}
                        onChange={(e) => setDesignatedProviderOverride(e.target.value)}
                      >
                        {codingProviders.map(p => (
                          <option key={p.id} value={p.id}>
                            {p.name} {p.available ? '(Pronto)' : '(Non pronto)'}
                          </option>
                        ))}
                      </select>
                    </div>

                    {activeWorkContext.proposal?.status === 'needs_clarification' ? (
                      <div className="clarification-warning-box" style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: '8px', padding: '12px', marginTop: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fbbf24', fontWeight: 600, fontSize: '0.85rem' }}>
                          <AlertTriangle size={15} />
                          <span>La proposta richiede chiarimenti prima dell'accettazione</span>
                        </div>
                        {activeWorkContext.proposal?.clarification_requirements?.length > 0 && (
                          <ul style={{ margin: '8px 0 0 16px', color: '#fef3c7', fontSize: '0.8rem', lineHeight: '1.4' }}>
                            {activeWorkContext.proposal.clarification_requirements.map((c: any, i: number) => (
                              <li key={i}>{c.question || c.context_key}</li>
                            ))}
                          </ul>
                        )}
                        <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
                          <input
                            data-testid="clarification-input"
                            value={clarifyDraft}
                            onChange={(e) => setClarifyDraft(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') handleClarifyProposal(activeWorkContext.proposalId || activeWorkContext.proposal?.id); }}
                            placeholder="Rispondi qui: Aether aggiorna il piano…"
                            style={{ flex: 1, background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: '6px', padding: '6px 10px', color: '#f8fafc', fontSize: '0.8rem' }}
                          />
                          <button
                            className="btn-cancel-soft"
                            onClick={() => handleRejectProposal(activeWorkContext.proposalId || activeWorkContext.proposal?.id)}
                          >
                            Rifiuta
                          </button>
                          <button
                            className="btn-approve-purple"
                            disabled={isClarifying || !clarifyDraft.trim()}
                            onClick={() => handleClarifyProposal(activeWorkContext.proposalId || activeWorkContext.proposal?.id)}
                          >
                            {isClarifying ? 'Invio…' : 'Invia risposta'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="approval-actions">
                        <button
                          className="btn-cancel-soft"
                          disabled={isAcceptingProposal}
                          onClick={() => handleRejectProposal(activeWorkContext.proposalId || activeWorkContext.proposal?.id)}
                        >
                          Rifiuta Proposta
                        </button>
                        <button
                          className="btn-approve-purple"
                          disabled={isAcceptingProposal}
                          onClick={() => handleAcceptProposal(activeWorkContext.proposalId || activeWorkContext.proposal?.id, activeWorkContext.proposal?.version)}
                        >
                          <CheckCircle2 size={14} />
                          {isAcceptingProposal ? 'Conferma in corso...' : 'Conferma Piano (Consigliato)'}
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ) : isMinimizedCard && activeWorkContext ? (
            <div className="field-minimized-pill" onClick={() => setIsMinimizedCard(false)} title="Clicca per espandere la scheda">
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: activeWorkContext.status === 'done' ? '#34d399' : activeWorkContext.status === 'needs-you' ? '#fbbf24' : '#818cf8',
                }}
              />
              <span>{activeWorkContext.title}</span>
              <Maximize2 size={12} style={{ opacity: 0.7 }} />
            </div>
          ) : activeWorkContext ? (
            // ACTIVE WORK STREAM & RESULTS (Principi 2 e 6: I risultati contano più dei processi)
            <div className="field-card">
              <div className="field-header">
                <div className="field-title-group">
                  <div className="field-icon-badge" style={activeWorkContext.status === 'done' ? { background: 'rgba(16,185,129,0.15)', borderColor: 'rgba(16,185,129,0.4)', color: '#34d399' } : {}}>
                    {activeWorkContext.status === 'done' ? <CheckCircle2 size={16} /> : <FileText size={16} />}
                  </div>
                  <div style={{ overflow: 'hidden' }}>
                    <h3 className="field-title">{activeWorkContext.title}</h3>
                    <p className="field-desc">
                      {activeWorkContext.codingResult?.provider_id
                        ? (activeWorkContext.codingResult.provider_id === 'antigravity' ? 'Google Antigravity' : activeWorkContext.codingResult.provider_id)
                        : (activeWorkContext.description ? activeWorkContext.description.slice(0, 70) : 'Attività in corso')}
                    </p>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <button
                    className="v2-action-btn"
                    style={{ padding: '4px 8px', fontSize: '11px' }}
                    onClick={() => setIsMinimizedCard(true)}
                    title="Riduci a pillola"
                  >
                    <Minimize2 size={12} />
                    <span>Riduci</span>
                  </button>
                  <button
                    className="v2-action-btn"
                    style={{ padding: '4px 8px', fontSize: '11px' }}
                    onClick={() => setActiveWorkContext(null)}
                    title="Chiudi Scheda"
                  >
                    <X size={12} />
                  </button>
                </div>
              </div>

              <div className="field-body">
                {/* Interaction Routing Prompt (Phase 3: Two-way Agent Interaction) */}
                {activeWorkContext.codingResult?.status === 'waiting_for_interaction' && (
                  <div className="agent-interaction-box">
                    <div className="agent-interaction-header">
                      <Terminal size={15} />
                      <span>Intervento Richiesto dal Coding Agent ({activeWorkContext.codingResult.provider_id || 'Antigravity'})</span>
                    </div>
                    <div className="agent-interaction-prompt">
                      <MarkdownRenderer
                        content={
                          activeWorkContext.codingResult.interaction_prompt ||
                          activeWorkContext.description ||
                          'L\'agente richiede chiarimenti o autorizzazioni per proseguire.'
                        }
                      />
                    </div>
                    {activeWorkContext.codingResult.interaction_options && activeWorkContext.codingResult.interaction_options.length > 0 && (
                      <div className="agent-interaction-options">
                        {activeWorkContext.codingResult.interaction_options.map((opt, oIdx) => (
                          <button
                            key={oIdx}
                            className="agent-interaction-option-btn"
                            onClick={() => handleInteractCoding(opt)}
                          >
                            {opt}
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="agent-interaction-reply-dock">
                      <input
                        type="text"
                        className="agent-interaction-input"
                        placeholder="Rispondi all'agente o fornisci indicazioni..."
                        value={interactionReplyText}
                        onChange={(e) => setInteractionReplyText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            handleInteractCoding();
                          }
                        }}
                      />
                      <button
                        className="agent-interaction-submit-btn"
                        disabled={isSubmittingInteraction}
                        onClick={() => handleInteractCoding()}
                      >
                        <Send size={12} />
                        <span>{isSubmittingInteraction ? 'Invio...' : 'Rispondi'}</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* Se è una proposta che richiede chiarimento (Principio 4: Chiarimento se materiale) */}
                {activeWorkContext.proposal && activeWorkContext.proposal.status === 'needs_clarification' && (
                  <div className="outcome-highlight-box" style={{ borderColor: 'rgba(245,158,11,0.3)', background: 'rgba(245,158,11,0.06)' }}>
                    <div className="outcome-title" style={{ color: '#fbbf24' }}>
                      <AlertTriangle size={16} />
                      <span>Chiarimento necessario per procedere</span>
                    </div>
                    <p className="outcome-summary" style={{ color: '#e2e8f0' }}>
                      {activeWorkContext.proposal.clarification_requirements?.[0]?.question ||
                        'Aether ha preparato il piano operativo, ma serve un chiarimento sui riferimenti del progetto prima di procedere in sicurezza.'}
                    </p>
                  </div>
                )}

                {/* Se il lavoro è completato, mostra in evidenza il risultato formattato e verificato (Principio 6) */}
                {activeWorkContext.status === 'done' && !activeWorkContext.proposal && (
                  <div className="outcome-highlight-box">
                    <div className="outcome-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <CheckCircle2 size={16} color="#34d399" />
                        <span>Risultato completato & verificato</span>
                      </div>
                      {activeWorkContext.codingResult?.verification_passed !== undefined && (
                        <span
                          className="phase-tag-badge"
                          style={{
                            background: activeWorkContext.codingResult.verification_passed ? 'rgba(16,185,129,0.18)' : 'rgba(239,68,68,0.18)',
                            borderColor: activeWorkContext.codingResult.verification_passed ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)',
                            color: activeWorkContext.codingResult.verification_passed ? '#34d399' : '#f87171',
                          }}
                        >
                          {activeWorkContext.codingResult.verification_passed ? '✓ Gate Verificato' : '⚠ Revisione Richiesta'}
                        </span>
                      )}
                    </div>

                    {/* Render summary cleanly ONCE with MarkdownRenderer */}
                    <div className="outcome-summary" style={{ marginTop: '8px' }}>
                      <MarkdownRenderer
                        content={
                          activeWorkContext.codingResult?.summary ||
                          activeWorkContext.description ||
                          "Aether si è occupato dell'attività. Verifiche completate."
                        }
                      />
                    </div>

                    {/* Modified Files Pills */}
                    {activeWorkContext.codingResult?.modified_files && activeWorkContext.codingResult.modified_files.length > 0 && (
                      <div style={{ marginTop: '8px' }}>
                        <div style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', marginBottom: '4px' }}>
                          File Modificati ({activeWorkContext.codingResult.modified_files.length}):
                        </div>
                        <div className="modified-files-list">
                          {activeWorkContext.codingResult.modified_files.map((mf, mIdx) => (
                            <span key={mIdx} className="file-badge-pill">
                              {mf}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Diff Viewer */}
                    {activeWorkContext.codingResult?.diff && (
                      <details className="diff-viewer-toggle" style={{ marginTop: '8px' }}>
                        <summary>
                          <Code2 size={13} />
                          <span>Visualizza Diff Modifiche ({activeWorkContext.codingResult.diff.split('\n').length} righe)</span>
                        </summary>
                        <pre className="diff-code-pre">{activeWorkContext.codingResult.diff}</pre>
                      </details>
                    )}

                    {/* Test Output */}
                    {activeWorkContext.codingResult?.test_output && (
                      <details className="diff-viewer-toggle" style={{ marginTop: '6px' }}>
                        <summary>
                          <Terminal size={13} />
                          <span>Evidenza Test ({activeWorkContext.codingResult.test_passed ? 'Superati' : 'Output'})</span>
                        </summary>
                        <pre className="test-output-box">{activeWorkContext.codingResult.test_output}</pre>
                      </details>
                    )}

                    {activeWorkContext.hasDeliverables && (
                      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '10px' }}>
                        <button
                          className="v2-action-btn"
                          onClick={() => navigate('results')}
                          style={{ background: 'rgba(16,185,129,0.18)', borderColor: 'rgba(16,185,129,0.4)', color: '#34d399', fontWeight: 600 }}
                        >
                          <span>Visualizza Risultati & Consegne</span>
                          <ArrowRight size={13} />
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Livello 4: I singoli step tecnici sono visibili ma compatti (o collassati se conclusi) */}
                {activeWorkContext.steps && activeWorkContext.steps.length > 0 && (
                  activeWorkContext.status === 'done' ? (
                    <details className="technical-details-toggle" style={{ marginTop: '4px' }}>
                      <summary>Vedi i passaggi eseguiti da Aether ({activeWorkContext.steps.length} passaggi completati)</summary>
                      <div className="steps-list" style={{ marginTop: '8px' }}>
                        {activeWorkContext.steps.map(step => (
                          <div key={step.id} className="step-row">
                            <span>{step.title}</span>
                            <span className="step-done">✓ Completato</span>
                          </div>
                        ))}
                      </div>
                    </details>
                  ) : (
                    <div className="steps-list">
                      {activeWorkContext.steps.map(step => (
                        <div key={step.id} className="step-row">
                          <span>{step.title}</span>
                          <span className={step.status === 'completed' ? 'step-done' : 'step-running'}>
                            {step.status === 'completed' ? '✓ Completato' : 'In corso...'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )
                )}
              </div>
            </div>
          ) : null}
        </div>
      </main>

      {/* Assistant-First Dialogue & Input Dock */}
      <section className={`v2-conversation-dock ${isFieldVisible ? 'dock-hidden' : ''}`} aria-label="Aether Dialogue">
        {/* Dialogue Toast Stream */}
        {lastUserMessage && !lastAssistantMessage && (
          <div className="v2-dialogue-toast" style={{ borderColor: 'rgba(255,255,255,0.08)', color: '#94a3b8' }}>
            <span>“{lastUserMessage}”</span>
          </div>
        )}
        {lastAssistantMessage && (
          <div className="v2-dialogue-toast">
            <Sparkles size={14} color="#c4b5fd" style={{ flexShrink: 0, marginTop: '3px' }} />
            <div className="v2-dialogue-text">
              <MarkdownRenderer content={lastAssistantMessage} />
            </div>
          </div>
        )}

        {/* Suggestion Chips — Esprimono obiettivi umani, non comandi a una macchina */}
        {!lastAssistantMessage && (
          <div className="v2-chips-row">
            <button
              className="v2-chip-btn"
              onClick={() => handleSendPrompt("Organizzami la giornata.")}
            >
              “Organizzami la giornata.”
            </button>
            <button
              className="v2-chip-btn"
              onClick={() => handleSendPrompt("Sistema questo progetto.")}
            >
              “Sistema questo progetto.”
            </button>
            <button
              className="v2-chip-btn"
              onClick={() => handleSendPrompt("Occupati di questo cliente.")}
            >
              “Occupati di questo cliente.”
            </button>
            <button
              className="v2-chip-btn"
              onClick={() => handleSendPrompt("Preparami qualcosa da pubblicare.")}
            >
              “Preparami qualcosa da pubblicare.”
            </button>
            <button
              className="v2-chip-btn"
              onClick={() => handleSendPrompt("Ricordami di fare questa cosa domani.")}
            >
              “Ricordami di fare questa cosa domani.”
            </button>
          </div>
        )}

        {/* Input Bar */}
        <div className="v2-input-dock">
          <input
            type="text"
            className="v2-text-input"
            placeholder={isListening ? "In ascolto... Parla pure con Aether" : "Tu dimmi cosa vuoi ottenere. Aether si occupa del resto..."}
            value={promptInput}
            onChange={(e) => setPromptInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleSendPrompt();
              }
            }}
          />

          <button
            className={`v2-mic-btn ${isListening ? 'v2-mic-active' : ''}`}
            onClick={toggleVoiceListening}
            title={isListening ? "Disattiva ascolto" : "Attiva ascolto vocale"}
          >
            {isListening ? <MicOff size={16} /> : <Mic size={16} />}
          </button>

          <button
            className="v2-send-btn"
            disabled={!promptInput.trim() || isSubmitting}
            onClick={() => handleSendPrompt()}
            title="Invia ad Aether"
          >
            <Send size={15} />
          </button>
        </div>
      </section>

      {/* Manual Mode Slide-over Drawer */}
      {isManualDrawerOpen && (
        <div className="manual-drawer-backdrop" onClick={() => setIsManualDrawerOpen(false)}>
          <aside className="manual-drawer-panel" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <h2 className="drawer-title">Spazio & Strumenti</h2>
              <button className="v2-action-btn" onClick={() => setIsManualDrawerOpen(false)} style={{ padding: '4px 8px' }}>
                <X size={14} />
              </button>
            </div>

            <p style={{ fontSize: '12px', color: '#94a3b8', lineHeight: 1.5 }}>
              Aether gestisce il lavoro autonomamente, ma puoi sempre accedere alla cronologia e agli strumenti:
            </p>

            {/* Cronologia Chat Section (Precision 5: isolamento conversazioni e workspace) */}
            <div className="drawer-section-title">
              <span>Cronologia Chat</span>
              <button className="btn-new-chat" onClick={handleNewSession} title="Avvia nuova conversazione">
                <Plus size={11} />
                <span>Nuova Chat</span>
              </button>
            </div>

            <div className="drawer-session-list">
              {sessions.length === 0 ? (
                <div style={{ fontSize: '11px', color: '#64748b', padding: '6px 8px' }}>
                  Nessuna conversazione precedente.
                </div>
              ) : (
                sessions.map(s => (
                  <div
                    key={s.id}
                    className={`drawer-session-item ${sessionId === s.id ? 'drawer-session-active' : ''}`}
                    onClick={() => handleSelectSession(s.id)}
                    title={s.title}
                  >
                    <MessageSquare size={13} style={{ flexShrink: 0, opacity: 0.7, marginRight: '6px' }} />
                    <span className="session-item-title">{s.title}</span>
                    <button
                      className="btn-delete-session"
                      onClick={(e) => handleDeleteSession(s.id, e)}
                      title="Elimina conversazione"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))
              )}
            </div>

            <nav className="drawer-nav-list">
              <button className="drawer-nav-item" onClick={() => { setIsManualDrawerOpen(false); navigate('missions'); }}>
                <Briefcase size={16} color="#c4b5fd" />
                <span>Missioni & Lavori</span>
                <ChevronRight size={14} style={{ marginLeft: 'auto', opacity: 0.5 }} />
              </button>

              <button className="drawer-nav-item" onClick={() => { setIsManualDrawerOpen(false); navigate('results'); }}>
                <FileText size={16} color="#34d399" />
                <span>Risultati & Consegne</span>
                <ChevronRight size={14} style={{ marginLeft: 'auto', opacity: 0.5 }} />
              </button>

              <button className="drawer-nav-item" onClick={() => { setIsManualDrawerOpen(false); navigate('connections'); }}>
                <Link2 size={16} color="#38bdf8" />
                <span>Servizi & Connessioni</span>
                <ChevronRight size={14} style={{ marginLeft: 'auto', opacity: 0.5 }} />
              </button>

              <button className="drawer-nav-item" onClick={() => { setIsManualDrawerOpen(false); navigate('workforce'); }}>
                <Users size={16} color="#f472b6" />
                <span>Collaboratori & Agenti</span>
                <ChevronRight size={14} style={{ marginLeft: 'auto', opacity: 0.5 }} />
              </button>

              <button
                className="drawer-nav-item"
                onClick={() => {
                  setIsManualDrawerOpen(false);
                  fetchCodingProviders();
                  setIsCodingModalOpen(true);
                }}
              >
                <Terminal size={16} color="#a78bfa" />
                <span>Coding Agents Esterni</span>
                <ChevronRight size={14} style={{ marginLeft: 'auto', opacity: 0.5 }} />
              </button>

              <button className="drawer-nav-item" onClick={() => { setIsManualDrawerOpen(false); navigate('settings'); }}>
                <Settings size={16} color="#94a3b8" />
                <span>Impostazioni & Profilo</span>
                <ChevronRight size={14} style={{ marginLeft: 'auto', opacity: 0.5 }} />
              </button>
            </nav>

            <div style={{ marginTop: 'auto', paddingTop: '16px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <button
                className="v2-action-btn v2-switch-btn"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => {
                  setIsManualDrawerOpen(false);
                  onSwitchToV1();
                }}
              >
                <Layers size={14} />
                <span>Torna all'Interfaccia V1 Classica</span>
              </button>
            </div>
          </aside>
        </div>
      )}

      {/* Coding Agent Provider Manager Modal */}
      {isCodingModalOpen && (
        <div className="coding-modal-backdrop" onClick={() => setIsCodingModalOpen(false)}>
          <div className="coding-modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="coding-modal-header">
              <div className="coding-modal-title-group">
                <Terminal size={18} color="#c4b5fd" />
                <div>
                  <h2 className="coding-modal-title">Coding Agent Provider Manager</h2>
                  <p className="coding-modal-subtitle">
                    Orchestrazione e selezione dei coding agent autonomi esterni
                  </p>
                </div>
              </div>
              <button
                className="v2-action-btn"
                onClick={() => setIsCodingModalOpen(false)}
                style={{ padding: '4px 8px' }}
              >
                <X size={14} />
              </button>
            </div>

            <div className="coding-banner-notice">
              <ShieldCheck size={16} color="#a78bfa" style={{ flexShrink: 0, marginTop: 1 }} />
              <span>
                Aether delega compiti di sviluppo agli agenti installati e autorizzati sul tuo sistema. Nessun fallback silenzioso: il modello AI interno non scrive mai codice al posto dei coding agent e rispetta rigorosamente i confini di sicurezza.
              </span>
            </div>

            <div className="coding-providers-list">
              {codingProviders.map(p => {
                const isCurrentPref = p.id === preferredProviderId;
                const activeOp = p.active_setup_operation;
                const isOpRunning = activeOp && (activeOp.status === 'running' || activeOp.status === 'pending');

                return (
                  <div
                    key={p.id}
                    className={`coding-provider-card ${isCurrentPref ? 'card-preferred' : ''}`}
                  >
                    <div className="provider-card-header">
                      <div className="provider-card-title-group">
                        <Code2 size={16} color={p.available ? '#34d399' : '#a78bfa'} />
                        <span className="provider-card-title">{p.name}</span>
                        {isCurrentPref && (
                          <span className="badge-preferred-pill">Predefinito</span>
                        )}
                      </div>

                      {/* 3D State Indicators */}
                      <div className="badge-3d-row">
                        {/* 1. Installation Badge */}
                        <span className={`badge-3d-pill ${p.installed ? 'installed' : 'not-installed'}`}>
                          {p.installed ? 'Installato' : 'Non installato'}
                        </span>

                        {/* 2. Authentication Badge */}
                        <span className={`badge-3d-pill ${p.authenticated ? 'authenticated' : (p.authentication_state === 'interactive_login_required' ? 'auth-required' : 'not-installed')}`}>
                          {p.authenticated ? 'Autenticato' : (p.authentication_state === 'interactive_login_required' ? 'Login richiesto' : (p.authentication_state === 'credentials_detected_unverified' ? 'Credenziali non verif.' : 'Non autenticato'))}
                        </span>

                        {/* 3. Operational State Badge */}
                        <span className={`badge-3d-pill ${p.available ? 'operational-ready' : 'operational-blocked'}`}>
                          <span className={`coding-status-dot ${p.available ? 'dot-ready' : 'dot-warning'}`} />
                          {p.available ? 'Pronto' : (p.operational_state?.replace(/_/g, ' ') || 'Non pronto')}
                        </span>
                      </div>
                    </div>

                    <p className="provider-card-desc">{p.description}</p>

                    <div className="provider-info-row">
                      {p.binary_path && (
                        <div>Eseguibile: <code>{p.binary_path}</code></div>
                      )}
                      {p.version && (
                        <div>Versione: <code>{p.version}</code></div>
                      )}
                      {p.auth_method && (
                        <div>Metodo Auth: <code>{p.auth_method}</code></div>
                      )}
                      <div>Diagnostica: <span style={{ color: p.available ? '#34d399' : '#fbbf24' }}>{p.diagnostic}</span></div>
                    </div>

                    {/* Observable Setup Operation In Progress */}
                    {activeOp && (
                      <div className="setup-op-card">
                        <div className="setup-op-header">
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <RotateCw size={12} className={isOpRunning ? 'spin-icon' : ''} color="#a78bfa" />
                            <span style={{ fontWeight: 600, color: '#e2e8f0', textTransform: 'capitalize' }}>
                              Operazione {activeOp.operation_type}: {activeOp.status} ({activeOp.progress.toFixed(0)}%)
                            </span>
                          </div>
                          {isOpRunning && (
                            <button
                              className="btn-lifecycle-action danger"
                              style={{ padding: '2px 8px', fontSize: '10px' }}
                              onClick={() => handleCancelOperation(activeOp.id)}
                            >
                              <Square size={10} />
                              <span>Annulla</span>
                            </button>
                          )}
                        </div>

                        <div className="setup-op-progress-bar">
                          <div
                            className="setup-op-progress-fill"
                            style={{ width: `${Math.max(5, Math.min(100, activeOp.progress))}%` }}
                          />
                        </div>

                        <div style={{ fontSize: '11px', color: '#cbd5e1' }}>
                          {activeOp.message || 'Elaborazione in corso...'}
                        </div>

                        {Array.isArray(activeOp.logs) && activeOp.logs.length > 0 && (
                          <div>
                            <button
                              type="button"
                              onClick={() => setExpandedLogs(prev => ({ ...prev, [activeOp.id]: !prev[activeOp.id] }))}
                              style={{
                                background: 'transparent',
                                border: 'none',
                                color: '#94a3b8',
                                fontSize: '11px',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px',
                                padding: 0,
                                marginTop: '4px'
                              }}
                            >
                              <ChevronDown size={12} style={{ transform: expandedLogs[activeOp.id] ? 'rotate(180deg)' : 'none', transition: 'transform 150ms' }} />
                              <span>Log operazione ({activeOp.logs.length} eventi)</span>
                            </button>
                            {expandedLogs[activeOp.id] && (
                              <div className="setup-op-logs-box" style={{ marginTop: '6px' }}>
                                {activeOp.logs.join('\n')}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {Array.isArray(p.missing_prerequisites) && p.missing_prerequisites.length > 0 && (
                      <div className="prereq-alert-box">
                        <div className="prereq-alert-title">
                          <AlertTriangle size={13} />
                          <span>Prerequisiti richiesti:</span>
                        </div>
                        {p.missing_prerequisites.map((prereq, idx) => (
                          <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            <span>{prereq}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Contextual Lifecycle Actions Row */}
                    <div className="provider-actions-row">
                      {!p.installed && (
                        <button
                          className="btn-lifecycle-action primary"
                          onClick={() => setInstallConfirmTarget(p)}
                          disabled={Boolean(isOpRunning)}
                        >
                          <Download size={12} />
                          <span>Installa {p.name}</span>
                        </button>
                      )}

                      {!p.authenticated && (
                        <button
                          className="btn-lifecycle-action warning"
                          onClick={() => handleAuthenticateProvider(p)}
                          disabled={Boolean(isOpRunning)}
                        >
                          <LogIn size={12} />
                          <span>Accedi / Istruzioni</span>
                        </button>
                      )}

                      <button
                        className="btn-lifecycle-action"
                        onClick={() => handleDiagnoseProvider(p.id)}
                        disabled={Boolean(isOpRunning)}
                      >
                        <RotateCw size={12} />
                        <span>Verifica</span>
                      </button>

                      <div style={{ marginLeft: 'auto' }}>
                        <button
                          className={`btn-set-preferred ${isCurrentPref ? 'is-current' : ''}`}
                          disabled={isCurrentPref || isUpdatingPreference}
                          onClick={() => handleSelectPreferredProvider(p.id)}
                        >
                          {isCurrentPref ? (
                            <>
                              <Check size={13} />
                              <span>Predefinito</span>
                            </>
                          ) : (
                            <span>Imposta Predefinito</span>
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Dialog for Installation */}
      {installConfirmTarget && (
        <div className="lifecycle-dialog-backdrop" onClick={() => !isInstalling && setInstallConfirmTarget(null)}>
          <div className="lifecycle-dialog-panel" onClick={(e) => e.stopPropagation()}>
            <h3 className="lifecycle-dialog-title">
              <Download size={18} color="#a78bfa" />
              <span>Conferma Installazione: {installConfirmTarget.name}</span>
            </h3>

            <p className="lifecycle-dialog-desc">
              Aether eseguirà l'installazione del CLI ufficiale di <strong>{installConfirmTarget.name}</strong> nel tuo sistema.
              Questa operazione richiede Node.js/npm e scaricherà il pacchetto CLI ufficiale in modalità verificata.
            </p>

            <div className="prereq-alert-box" style={{ background: 'rgba(140,92,246,0.06)', borderColor: 'rgba(140,92,246,0.25)' }}>
              <div className="prereq-alert-title" style={{ color: '#c4b5fd' }}>
                <ShieldCheck size={14} />
                <span>Garanzie e Controlli del Runtime</span>
              </div>
              <span style={{ color: '#e2e8f0', fontSize: '12px' }}>
                Nessuna modifica non autorizzata: al termine dell'installazione Aether verificherà che l'eseguibile sia integro, dotato di permessi adeguati e responsivo prima di dichiararlo operativo.
              </span>
            </div>

            <div className="lifecycle-dialog-actions">
              <button
                className="btn-lifecycle-action"
                onClick={() => setInstallConfirmTarget(null)}
                disabled={isInstalling}
              >
                Annulla
              </button>
              <button
                className="btn-lifecycle-action primary"
                onClick={handleConfirmInstall}
                disabled={isInstalling}
              >
                {isInstalling ? (
                  <>
                    <RotateCw size={12} className="spin-icon" />
                    <span>Avvio in corso...</span>
                  </>
                ) : (
                  <>
                    <Check size={12} />
                    <span>Conferma e Installa</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Authentication & Terminal Instructions Dialog */}
      {authInstructionsModal && (
        <div className="lifecycle-dialog-backdrop" onClick={() => setAuthInstructionsModal(null)}>
          <div className="lifecycle-dialog-panel" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h3 className="lifecycle-dialog-title">
                <LogIn size={18} color="#60a5fa" />
                <span>Autenticazione: {authInstructionsModal.provider.name}</span>
              </h3>
              <button
                className="v2-action-btn"
                onClick={() => setAuthInstructionsModal(null)}
                style={{ padding: '2px 6px' }}
              >
                <X size={14} />
              </button>
            </div>

            <p className="lifecycle-dialog-desc">
              Per motivi di sicurezza e per proteggere le tue credenziali, l'autenticazione per questo agente richiede una procedura interattiva:
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {authInstructionsModal.instructions.map((step, idx) => (
                <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '12px', color: '#cbd5e1' }}>
                  <span style={{ background: 'rgba(255,255,255,0.08)', borderRadius: '50%', width: '18px', height: '18px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', flexShrink: 0 }}>
                    {idx + 1}
                  </span>
                  <span>{step}</span>
                </div>
              ))}
            </div>

            {authInstructionsModal.provider.id === 'claude_code' && (
              <div style={{ marginTop: '6px' }}>
                <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '4px' }}>Comando da eseguire nel terminale:</div>
                <div className="prereq-alert-command" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>claude login</span>
                  <button
                    type="button"
                    style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
                    onClick={() => {
                      navigator.clipboard.writeText('claude login');
                      showToast('Comando copiato negli appunti!', 'success');
                    }}
                  >
                    <Copy size={13} />
                  </button>
                </div>
              </div>
            )}

            {authInstructionsModal.provider.id === 'codex' && (
              <div style={{ marginTop: '6px' }}>
                <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '4px' }}>Comando da eseguire nel terminale:</div>
                <div className="prereq-alert-command" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>codex login</span>
                  <button
                    type="button"
                    style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
                    onClick={() => {
                      navigator.clipboard.writeText('codex login');
                      showToast('Comando copiato negli appunti!', 'success');
                    }}
                  >
                    <Copy size={13} />
                  </button>
                </div>
              </div>
            )}

            <div className="lifecycle-dialog-actions" style={{ marginTop: '12px' }}>
              <button
                className="btn-lifecycle-action primary"
                onClick={() => {
                  handleDiagnoseProvider(authInstructionsModal.provider.id);
                  setAuthInstructionsModal(null);
                }}
              >
                <Check size={12} />
                <span>Ho completato l'accesso (Verifica)</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
