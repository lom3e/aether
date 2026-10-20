/**
 * Connects the Companion to Aether Core. There is no assistant logic here: the same endpoints, the same session
 * (shared with the main Assistant through ACTIVE_SESSION_KEY), the same approval router as the rest of the app.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiUrl, getSessionToken } from '../api';
import { ACTIVE_SESSION_KEY, classifyRestoreResponse, forgetStaleSession } from '../sessionRestore';
import { approvalToastKind, submitApprovalDecision } from '../canonicalNotification';
import { deriveCompanionStatus, type CompanionStatus } from './status';
import { sanitizeModelShapes, type Shape } from './vision/annotations';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  /** Set when the runtime itself reported a failure for this reply (e.g. NO_PROVIDER). */
  errorCode?: string;
  /** A proposal the runtime attached to this reply. Accepting it is done in the main app (same session). */
  proposal?: { id: string; title: string; objective: string };
  /** Receipts: what the runtime really injected into this answer, and what left the computer for it. */
  sources?: AnswerSource[];
  egress?: EgressSummary;
  /** A screenshot the user chose to share, kept in memory for this window only (never persisted), with any marks drawn on it. */
  vision?: { imageUrl: string; width: number; height: number; shapes: Shape[]; provider?: string; model?: string };
}

/** Whether the provider the runtime would use can take an image (nothing is sent to find out). */
export interface VisionStatus {
  supported: boolean;
  reason: string;
  provider: string;
  model: string;
}

export interface VisionRequest {
  prompt: string;
  imageBase64: string;
  mediaType: string;
  /** What to show in the conversation (the same pixels that were sent). */
  displayUrl: string;
  width: number;
  height: number;
  language: string;
  annotate: boolean;
}

export type VisionAnswer =
  | { status: 'ok'; provider: string; model: string; shapes: Shape[]; rejected: number }
  | { status: 'unavailable' | 'failed' | 'invalid_image' | 'unreachable' | 'no_workspace'; reason: string; detail: string; provider: string; model: string };

export interface AnswerSource {
  tag?: string;
  kind: string;
  ref: string;
  title?: string;
  source?: string;
  trust?: string;
  /** A memory record the user can remove from here (its id is the real memory id). */
  forgettable?: boolean;
}

export interface EgressSummary {
  ids?: string[];
  requests: number;
  local_only: boolean;
  providers: string[];
  models?: string[];
  images: number;
  redactions: Record<string, number>;
  redactions_total: number;
  unmasked?: boolean;
}

/** Receipts carried by a reply's metadata (both optional: background answers and older messages have none). */
export function receiptsOf(metadata: any): { sources?: AnswerSource[]; egress?: EgressSummary } {
  const sources = Array.isArray(metadata?.sources) && metadata.sources.length ? (metadata.sources as AnswerSource[]) : undefined;
  const egress = metadata?.egress && typeof metadata.egress === 'object' ? (metadata.egress as EgressSummary) : undefined;
  return { sources, egress };
}

export interface PendingApproval {
  id?: string;
  execution_id?: string;
  human_summary?: string;
  action_name?: string;
  title?: string;
  description?: string;
  impact_level?: string;
  created_at?: string;
}

export interface RunningTask {
  id: string;
  title: string;
  status: string;
  progress_pct?: number | null;
  progress_percent?: number | null;
  current_step?: string;
}

export interface ActiveMission {
  id: string;
  title: string;
  status: string;
  current_stage?: string | null;
  progress?: number | null;
}

export interface ResultItem {
  id: string;
  title: string;
  source: string;
  file_path: string;
  file_type: string;
  file_size_bytes: number;
}

/** What the runtime could read from the desktop, exactly as returned (nothing is inferred). */
export interface DesktopContext {
  app_name: string;
  window_title: string;
  clipboard_text: string;
  timestamp: string;
}

export interface AttachedFile {
  filename: string;
  size: number;
  path: string;
}

export interface NotificationsSummary {
  unread: number;
  items: { id: string; title: string; message: string }[];
}

export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

/** The runtime lists an unreadable desktop as the default "Desktop" with nothing else. */
export function contextIsEmpty(c: DesktopContext): boolean {
  return (!c.app_name || c.app_name === 'Desktop') && !c.window_title && !c.clipboard_text;
}

/** Proposal metadata -> what the panel shows; ignores replies without a proposal. */
export function proposalOf(metadata: any): ChatMessage['proposal'] | undefined {
  const p = metadata?.proposal;
  const id = metadata?.proposal_id || p?.id;
  if (!id) return undefined;
  return { id: String(id), title: String(p?.title || p?.objective || ''), objective: String(p?.objective || p?.title || '') };
}

export type RuntimeProblem =
  | { kind: 'unreachable' }
  | { kind: 'no_workspace' }
  | { kind: 'request'; message: string }
  | null;

const COMPLETED_PULSE_MS = 4000;
const POLL_VISIBLE_MS = 4000;

export interface CompanionRuntime {
  workspace: string | null;
  messages: ChatMessage[];
  approvals: PendingApproval[];
  tasks: RunningTask[];
  missions: ActiveMission[];
  results: ResultItem[];
  problem: RuntimeProblem;
  submitting: boolean;
  status: CompanionStatus;
  decidingId: string | null;
  /** `hiddenContext` is sent to the model with the message but not shown as part of it (e.g. text read from the screen). */
  send: (text: string, language: string, hiddenContext?: string) => Promise<void>;
  retryLast: (language: string) => Promise<void>;
  decide: (approval: PendingApproval, decision: 'approve' | 'reject', reason: string) => Promise<{ message: string; kind: 'success' | 'error' | 'info' | 'warning' }>;
  newConversation: () => void;
  refresh: () => Promise<void>;
  captureContext: () => Promise<DesktopContext | null>;
  attachFile: (file: File) => Promise<AttachedFile>;
  checkNotifications: () => Promise<NotificationsSummary | null>;
  fetchVisionStatus: () => Promise<VisionStatus | null>;
  askAboutImage: (req: VisionRequest) => Promise<VisionAnswer>;
  rememberImage: (req: { imageBase64: string; mediaType: string; ttlDays: 7 | 30; language: string }) => Promise<'ok' | 'unavailable' | 'failed'>;
  dismissProblem: () => void;
  setListening: (v: boolean) => void;
}

export function useCompanionRuntime(): CompanionRuntime {
  const [workspace, setWorkspace] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(ACTIVE_SESSION_KEY);
    } catch {
      return null;
    }
  });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [tasks, setTasks] = useState<RunningTask[]>([]);
  const [missions, setMissions] = useState<ActiveMission[]>([]);
  const [results, setResults] = useState<ResultItem[]>([]);
  const [problem, setProblem] = useState<RuntimeProblem>(null);
  const [submitting, setSubmitting] = useState(false);
  const [listening, setListening] = useState(false);
  const [justCompleted, setJustCompleted] = useState(false);
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const lastPrompt = useRef<string | null>(null);
  const completedTimer = useRef<number | null>(null);
  const prevRunning = useRef<Set<string>>(new Set());
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (completedTimer.current) window.clearTimeout(completedTimer.current);
    };
  }, []);

  const pulseCompleted = useCallback(() => {
    setJustCompleted(true);
    if (completedTimer.current) window.clearTimeout(completedTimer.current);
    completedTimer.current = window.setTimeout(() => mounted.current && setJustCompleted(false), COMPLETED_PULSE_MS);
  }, []);

  const resolveWorkspace = useCallback(async (): Promise<string | null> => {
    try {
      const res = await fetch(apiUrl('/api/workspace'));
      if (!res.ok) {
        setProblem(res.status === 503 || res.status === 404 ? { kind: 'no_workspace' } : { kind: 'unreachable' });
        return null;
      }
      const data = await res.json();
      if (data && data.name) {
        setWorkspace(data.name);
        setProblem(p => (p && (p.kind === 'unreachable' || p.kind === 'no_workspace') ? null : p));
        return data.name as string;
      }
      setProblem({ kind: 'no_workspace' });
      return null;
    } catch {
      setProblem({ kind: 'unreachable' });
      return null;
    }
  }, []);

  const fetchOverview = useCallback(
    async (ws: string | null) => {
      if (!ws) return;
      try {
        const res = await fetch(apiUrl(`/api/personal/overview?workspace_id=${encodeURIComponent(ws)}`));
        if (!res.ok || !mounted.current) return;
        const data = await res.json();
        setApprovals(Array.isArray(data?.pending_approvals) ? data.pending_approvals : []);
        const running: RunningTask[] = (Array.isArray(data?.background_tasks) ? data.background_tasks : []).filter(
          (t: RunningTask) => t.status === 'running' || t.status === 'pending',
        );
        setTasks(running);
        const works: ActiveMission[] = (Array.isArray(data?.active_works) ? data.active_works : [])
          .filter((m: any) => ['running', 'in_progress', 'pending'].includes(m.status))
          .map((m: any) => ({ id: m.id || m.mission_id, title: m.title || m.objective || '', status: m.status, current_stage: m.current_stage, progress: m.progress }));
        setMissions(works);
        setResults(Array.isArray(data?.recent_deliverables) ? data.recent_deliverables : []);
        // A task or mission that was running and is not any more has finished (the runtime dropped it from the list).
        const now = new Set([...running.map(t => t.id), ...works.filter(m => m.status !== 'pending').map(m => m.id)]);
        let finished = false;
        prevRunning.current.forEach(id => {
          if (!now.has(id)) finished = true;
        });
        prevRunning.current = now;
        if (finished) pulseCompleted();
      } catch {
        /* a failed poll is not an error the user can act on; the next poll or request reports reachability */
      }
    },
    [pulseCompleted],
  );

  const refresh = useCallback(async () => {
    const ws = workspace || (await resolveWorkspace());
    await fetchOverview(ws);
  }, [workspace, resolveWorkspace, fetchOverview]);

  // Resolve the workspace, and keep trying while there is none (or the runtime was unreachable): the Companion must
  // recover by itself when the user opens a workspace in the main app or the runtime comes back.
  useEffect(() => {
    resolveWorkspace();
    if (workspace) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') resolveWorkspace();
    }, POLL_VISIBLE_MS);
    const onFocus = () => resolveWorkspace();
    window.addEventListener('focus', onFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', onFocus);
    };
  }, [workspace, resolveWorkspace]);

  // Restore the shared session so the Companion continues the conversation of the main Assistant.
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(apiUrl(`/api/personal/sessions/${encodeURIComponent(sessionId)}`));
        const outcome = classifyRestoreResponse(res.status);
        if (cancelled) return;
        if (outcome === 'stale') {
          forgetStaleSession(localStorage, sessionId);
          setSessionId(null);
          return;
        }
        if (outcome === 'restored') {
          const data = await res.json();
          if (cancelled) return;
          const restored: ChatMessage[] = (data.messages || [])
            .filter((m: any) => m.role === 'user' || m.role === 'assistant')
            .map((m: any, i: number) => ({
              id: m.id || `restored-${i}`,
              role: m.role,
              content: m.content || '',
              createdAt: m.created_at || '',
              errorCode: m.metadata?.error_code,
              proposal: proposalOf(m.metadata),
              ...receiptsOf(m.metadata),
            }));
          setMessages(restored);
        }
      } catch {
        /* keep the id: a network failure does not prove the session is gone */
      }
    })();
    // Only on first mount / when a different stored id is adopted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll while the window is visible; refresh on focus / visibility, and on server-sent events.
  useEffect(() => {
    if (!workspace) return;
    fetchOverview(workspace);
    const tick = () => {
      if (document.visibilityState === 'visible') fetchOverview(workspace);
    };
    const timer = window.setInterval(tick, POLL_VISIBLE_MS);
    const onFocus = () => {
      fetchOverview(workspace);
    };
    document.addEventListener('visibilitychange', tick);
    window.addEventListener('focus', onFocus);
    let es: EventSource | null = null;
    try {
      const token = getSessionToken();
      es = new EventSource(
        apiUrl(`/api/personal/events?workspace_id=${encodeURIComponent(workspace)}${token ? `&token=${encodeURIComponent(token)}` : ''}`),
      );
      const refreshOnEvent = () => fetchOverview(workspace);
      ['task_progress', 'task_completed', 'notification'].forEach(n => es!.addEventListener(n, refreshOnEvent));
    } catch {
      /* polling alone is enough */
    }
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', tick);
      window.removeEventListener('focus', onFocus);
      es?.close();
    };
  }, [workspace, fetchOverview]);

  const send = useCallback(
    async (text: string, language: string, hiddenContext?: string) => {
      const prompt = text.trim();
      if (!prompt || submitting) return;
      lastPrompt.current = prompt;
      const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: 'user', content: prompt, createdAt: new Date().toISOString() };
      setMessages(m => [...m, userMsg]);
      setProblem(null);
      setSubmitting(true);
      try {
        const ws = workspace || (await resolveWorkspace());
        if (!ws) {
          setSubmitting(false);
          return; // resolveWorkspace already recorded why
        }
        const res = await fetch(apiUrl('/api/personal/chat'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: hiddenContext ? `${prompt}\n\n${hiddenContext}` : prompt, session_id: sessionId, workspace_id: ws, language }),
        });
        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try {
            const body = await res.json();
            if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
          } catch {
            /* keep the status line */
          }
          setProblem({ kind: 'request', message: detail });
          return;
        }
        const data = await res.json();
        if (data.session_id && data.session_id !== sessionId) {
          setSessionId(data.session_id);
          try {
            localStorage.setItem(ACTIVE_SESSION_KEY, data.session_id);
          } catch {
            /* storage unavailable: the session still works for this window */
          }
        }
        const errorCode: string | undefined = data.metadata?.error_code;
        setMessages(m => [
          ...m,
          { id: data.id || `a-${Date.now()}`, role: 'assistant', content: data.content || '', createdAt: data.created_at || new Date().toISOString(), errorCode, proposal: proposalOf(data.metadata), ...receiptsOf(data.metadata) },
        ]);
        if (errorCode) {
          setProblem({ kind: 'request', message: errorCode });
        } else {
          pulseCompleted();
        }
        fetchOverview(ws);
      } catch {
        setProblem({ kind: 'unreachable' });
      } finally {
        if (mounted.current) setSubmitting(false);
      }
    },
    [workspace, sessionId, submitting, resolveWorkspace, fetchOverview, pulseCompleted],
  );

  const retryLast = useCallback(
    async (language: string) => {
      if (lastPrompt.current) await send(lastPrompt.current, language);
    },
    [send],
  );

  const decide = useCallback(
    async (approval: PendingApproval, decision: 'approve' | 'reject', reason: string) => {
      const id = (approval.execution_id || approval.id || '').trim();
      setDecidingId(id);
      try {
        const res = await submitApprovalDecision({
          target_type: 'action_execution',
          target_id: id,
          decision,
          approver: 'user',
          reason: decision === 'reject' ? reason : undefined,
          workspaceName: workspace || undefined,
        });
        if (res.success) {
          setApprovals(prev => prev.filter(a => (a.execution_id || a.id) !== id));
          await fetchOverview(workspace);
        }
        return { message: res.message, kind: res.success ? (decision === 'approve' ? approvalToastKind(res, 'approve') : ('info' as const)) : ('error' as const) };
      } catch (e: any) {
        return { message: e?.message || String(e), kind: 'error' as const };
      } finally {
        if (mounted.current) setDecidingId(null);
      }
    },
    [workspace, fetchOverview],
  );

  const newConversation = useCallback(() => {
    try {
      localStorage.removeItem(ACTIVE_SESSION_KEY);
    } catch {
      /* ignore */
    }
    setSessionId(null);
    setMessages([]);
    setProblem(null);
    lastPrompt.current = null;
  }, []);

  const captureContext = useCallback(async (): Promise<DesktopContext | null> => {
    try {
      const res = await fetch(apiUrl('/api/personal/companion/context'), { method: 'POST' });
      if (!res.ok) return null;
      return (await res.json()) as DesktopContext;
    } catch {
      return null;
    }
  }, []);

  const attachFile = useCallback(
    async (file: File): Promise<AttachedFile> => {
      if (file.size > MAX_ATTACHMENT_BYTES) throw new Error('too_large');
      const ws = workspace || (await resolveWorkspace());
      if (!ws) throw new Error('no_workspace');
      const base64: string = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
        reader.onerror = () => reject(new Error('read_failed'));
        reader.readAsDataURL(file);
      });
      const res = await fetch(apiUrl('/api/personal/companion/drop'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, content_base64: base64, session_id: sessionId, workspace_id: ws }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      return { filename: d.file_name || file.name, size: d.file_size ?? file.size, path: d.file_path || '' };
    },
    [workspace, sessionId, resolveWorkspace],
  );

  const fetchVisionStatus = useCallback(async (): Promise<VisionStatus | null> => {
    try {
      const res = await fetch(apiUrl('/api/personal/companion/vision/status'));
      if (!res.ok) return null;
      const d = await res.json();
      return { supported: !!d.supported, reason: String(d.reason || ''), provider: String(d.provider || ''), model: String(d.model || '') };
    } catch {
      return null;
    }
  }, []);

  const rememberImage = useCallback(
    async (req: { imageBase64: string; mediaType: string; ttlDays: 7 | 30; language: string }): Promise<'ok' | 'unavailable' | 'failed'> => {
      try {
        const ws = workspace || (await resolveWorkspace());
        if (!ws) return 'failed';
        const res = await fetch(apiUrl('/api/personal/companion/vision/remember'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_base64: req.imageBase64, media_type: req.mediaType, ttl_days: req.ttlDays, language: req.language, workspace_id: ws }),
        });
        if (!res.ok) return 'failed';
        const d = await res.json();
        return d.status === 'ok' ? 'ok' : d.status === 'unavailable' ? 'unavailable' : 'failed';
      } catch {
        return 'failed';
      }
    },
    [workspace, resolveWorkspace],
  );

  const askAboutImage = useCallback(
    async (req: VisionRequest): Promise<VisionAnswer> => {
      const fail = (status: 'unavailable' | 'failed' | 'invalid_image' | 'unreachable' | 'no_workspace', reason = '', detail = '', provider = '', model = ''): VisionAnswer => ({ status, reason, detail, provider, model });
      setSubmitting(true);
      try {
        const ws = workspace || (await resolveWorkspace());
        if (!ws) return fail('no_workspace');
        const res = await fetch(apiUrl('/api/personal/companion/vision'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            image_base64: req.imageBase64, media_type: req.mediaType, prompt: req.prompt, session_id: sessionId,
            workspace_id: ws, language: req.language, annotate: req.annotate,
          }),
        });
        if (res.status === 422) {
          const body = await res.json().catch(() => null);
          return fail('invalid_image', String(body?.detail?.code || 'invalid_image'));
        }
        if (!res.ok) return fail('failed', 'provider_error', `HTTP ${res.status}`);
        const d = await res.json();
        if (d.status !== 'ok' || !d.message) {
          return fail(d.status === 'unavailable' ? 'unavailable' : 'failed', String(d.reason || ''), String(d.detail || ''), String(d.provider || ''), String(d.model || ''));
        }
        const sid = d.message.session_id;
        if (sid && sid !== sessionId) {
          setSessionId(sid);
          try {
            localStorage.setItem(ACTIVE_SESSION_KEY, sid);
          } catch {
            /* the session still works for this window */
          }
        }
        const shapes = sanitizeModelShapes(d.annotations);
        const now = new Date().toISOString();
        const vision = { imageUrl: req.displayUrl, width: req.width, height: req.height, provider: String(d.provider || ''), model: String(d.model || '') };
        setMessages(m => [
          ...m,
          { id: `u-${Date.now()}`, role: 'user', content: req.prompt, createdAt: now, vision: { ...vision, shapes: [] } },
          { id: d.message.id || `a-${Date.now()}`, role: 'assistant', content: d.message.content || '', createdAt: d.message.created_at || now, vision: shapes.length ? { ...vision, shapes } : undefined, ...receiptsOf(d.message.metadata) },
        ]);
        pulseCompleted();
        fetchOverview(ws);
        return { status: 'ok', provider: vision.provider, model: vision.model, shapes, rejected: Array.isArray(d.annotations_rejected) ? d.annotations_rejected.length : 0 };
      } catch {
        return fail('unreachable');
      } finally {
        if (mounted.current) setSubmitting(false);
      }
    },
    [workspace, sessionId, resolveWorkspace, fetchOverview, pulseCompleted],
  );

  const checkNotifications = useCallback(async (): Promise<NotificationsSummary | null> => {
    const ws = workspace || (await resolveWorkspace());
    if (!ws) return null;
    try {
      const res = await fetch(apiUrl('/api/personal/companion/quick-action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action_id: 'check_notifications', workspace_id: ws }),
      });
      if (!res.ok) return null;
      const d = await res.json();
      return { unread: Number(d.unread_count) || 0, items: (d.notifications || []).map((n: any) => ({ id: n.id, title: n.title, message: n.message })) };
    } catch {
      return null;
    }
  }, [workspace, resolveWorkspace]);

  const status = deriveCompanionStatus({
    listening,
    submitting,
    pendingApprovals: approvals.length,
    runningTasks: tasks.length + missions.filter(m => m.status === 'running' || m.status === 'in_progress').length,
    hasError: problem !== null,
    justCompleted,
  });

  return {
    workspace, messages, approvals, tasks, missions, results, problem, submitting, status, decidingId,
    send, retryLast, decide, newConversation, refresh, captureContext, attachFile, checkNotifications, fetchVisionStatus, askAboutImage, rememberImage,
    dismissProblem: () => setProblem(null),
    setListening,
  };
}
