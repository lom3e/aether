/**
 * Connects the Companion to Aether Core. There is no assistant logic here: the same endpoints, the same session
 * (shared with the main Assistant through ACTIVE_SESSION_KEY), the same approval router as the rest of the app.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiUrl, getSessionToken } from '../api';
import { ACTIVE_SESSION_KEY, classifyRestoreResponse, forgetStaleSession } from '../sessionRestore';
import { approvalToastKind, submitApprovalDecision } from '../canonicalNotification';
import { deriveCompanionStatus, type CompanionStatus } from './status';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  /** Set when the runtime itself reported a failure for this reply (e.g. NO_PROVIDER). */
  errorCode?: string;
}

export interface PendingApproval {
  id?: string;
  execution_id?: string;
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
  problem: RuntimeProblem;
  submitting: boolean;
  status: CompanionStatus;
  decidingId: string | null;
  send: (text: string, language: string) => Promise<void>;
  retryLast: (language: string) => Promise<void>;
  decide: (approval: PendingApproval, decision: 'approve' | 'reject', reason: string) => Promise<{ message: string; kind: 'success' | 'error' | 'info' | 'warning' }>;
  newConversation: () => void;
  refresh: () => Promise<void>;
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
        // A task that was running and is not any more has finished (the runtime told us so by dropping it).
        const now = new Set(running.map(t => t.id));
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
    async (text: string, language: string) => {
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
          body: JSON.stringify({ prompt, session_id: sessionId, workspace_id: ws, language }),
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
          { id: data.id || `a-${Date.now()}`, role: 'assistant', content: data.content || '', createdAt: data.created_at || new Date().toISOString(), errorCode },
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

  const status = deriveCompanionStatus({
    listening,
    submitting,
    pendingApprovals: approvals.length,
    runningTasks: tasks.length,
    hasError: problem !== null,
    justCompleted,
  });

  return {
    workspace, messages, approvals, tasks, problem, submitting, status, decidingId,
    send, retryLast, decide, newConversation, refresh,
    dismissProblem: () => setProblem(null),
    setListening,
  };
}
