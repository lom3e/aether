import { useState, useEffect, useRef, useCallback, useContext } from "react";
import {
  Sparkles,
  Send,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  ExternalLink,
  X,
  Check,
  Clock,
  CheckCircle2,
  Shield,
  Loader2,
  Bell,
} from "lucide-react";
import { apiUrl, getSessionToken } from "./api";
import { hideCompanion, showMainWindow } from "./desktop";
import { ToastContext } from "./toast";

interface AmbientCompanionProps {
  workspaceName?: string;
  onOpenWorkspace?: () => void;
}

interface StepItem {
  id: string;
  title: string;
  status: string;
  category: string;
  details?: any;
}

interface AssistantResponse {
  id: string;
  role: string;
  content: string;
  tier: string;
  steps: StepItem[];
  action_execution_id?: string;
  mission_id?: string;
  created_at: string;
}

interface PendingApproval {
  id?: string;
  execution_id?: string;
  action_id?: string;
  action_name?: string;
  action_type?: string;
  title?: string;
  description?: string;
  impact_level?: string;
  params?: Record<string, any>;
  input_data?: Record<string, any>;
  created_at: string;
}

interface BackgroundTask {
  id: string;
  title: string;
  status: string;
  progress_pct?: number | null;
  current_step?: string;
  started_at?: string;
}

interface NotificationItem {
  id: string;
  title: string;
  message: string;
  priority: string;
  status: string;
  created_at: string;
}

export function AmbientCompanion({
  workspaceName: propWorkspaceName,
  onOpenWorkspace,
}: AmbientCompanionProps) {
  const [activeWorkspace, setActiveWorkspace] = useState<string>(propWorkspaceName || "");
  const [promptInput, setPromptInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [latestResponse, setLatestResponse] = useState<AssistantResponse | null>(null);
  const [lastUserPrompt, setLastUserPrompt] = useState<string | null>(null);

  // Real backend states
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([]);
  const [backgroundTasks, setBackgroundTasks] = useState<BackgroundTask[]>([]);
  const [unreadNotifications, setUnreadNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);

  // Voice State
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const recognitionRef = useRef<any>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const showToast = useContext(ToastContext);

  // 1. Resolve workspace if not provided via props
  const fetchWorkspace = useCallback(async () => {
    try {
      const res = await fetch(apiUrl("/api/workspace"));
      if (res.ok) {
        const data = await res.json();
        if (data && data.name) {
          setActiveWorkspace(data.name);
        }
      }
    } catch (err) {
      console.warn("Could not resolve workspace in companion:", err);
    }
  }, []);

  useEffect(() => {
    if (!propWorkspaceName) {
      fetchWorkspace();
    } else {
      setActiveWorkspace(propWorkspaceName);
    }
  }, [propWorkspaceName, fetchWorkspace]);

  // 2. Fetch Overview & Pending State from single source of truth
  const fetchOverview = useCallback(async () => {
    if (!activeWorkspace) return;
    try {
      const res = await fetch(apiUrl(`/api/personal/overview?workspace_id=${encodeURIComponent(activeWorkspace)}`));
      if (res.ok) {
        const data = await res.json();
        if (data) {
          if (Array.isArray(data.pending_approvals)) {
            setPendingApprovals(data.pending_approvals);
          }
          if (Array.isArray(data.background_tasks)) {
            setBackgroundTasks(data.background_tasks);
          }
          if (typeof data.unread_notifications === "number") {
            setUnreadCount(data.unread_notifications);
          }
        }
      }
    } catch (err) {
      console.warn("Failed to fetch companion overview:", err);
    }
  }, [activeWorkspace]);

  const fetchUnreadNotifications = useCallback(async () => {
    if (!activeWorkspace) return;
    try {
      const res = await fetch(apiUrl(`/api/notifications?workspace_id=${encodeURIComponent(activeWorkspace)}&limit=5`));
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          const unread = data.filter((n: any) => n.status === "unread");
          setUnreadNotifications(unread.slice(0, 3));
          setUnreadCount(unread.length);
        }
      }
    } catch (err) {
      console.warn("Failed to fetch unread notifications:", err);
    }
  }, [activeWorkspace]);

  useEffect(() => {
    if (activeWorkspace) {
      fetchOverview();
      fetchUnreadNotifications();
    }
  }, [activeWorkspace, fetchOverview, fetchUnreadNotifications]);

  // Refresh on focus / visibility change (reopening the window)
  useEffect(() => {
    const handleVisibility = () => {
      if (!document.hidden && activeWorkspace) {
        fetchOverview();
        fetchUnreadNotifications();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("focus", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", handleVisibility);
    };
  }, [activeWorkspace, fetchOverview, fetchUnreadNotifications]);

  // 3. Real-Time SSE Hub integration (tasks, steps, approvals, notifications)
  useEffect(() => {
    if (!activeWorkspace) return;

    let eventSource: EventSource | null = null;
    try {
      const token = getSessionToken() || "";
      const tokenParam = token ? `&token=${encodeURIComponent(token)}` : "";
      eventSource = new EventSource(
        apiUrl(`/api/personal/events?workspace_id=${encodeURIComponent(activeWorkspace)}${tokenParam}`)
      );

      eventSource.addEventListener("step_update", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (data && data.step) {
            setLatestResponse(prev => {
              if (!prev) return prev;
              const exists = prev.steps.some(s => s.id === data.step.id);
              const updatedSteps = exists
                ? prev.steps.map(s => (s.id === data.step.id ? data.step : s))
                : [...prev.steps, data.step];
              return { ...prev, steps: updatedSteps };
            });
          }
        } catch {
          // Ignore parse errors
        }
      });

      eventSource.addEventListener("task_progress", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          if (data && data.task_id) {
            setBackgroundTasks(prev => {
              const exists = prev.some(t => t.id === data.task_id);
              if (exists) {
                return prev.map(t =>
                  t.id === data.task_id
                    ? {
                        ...t,
                        progress_pct: data.progress_pct,
                        current_step: data.step_title,
                        status: data.status || t.status,
                      }
                    : t
                );
              }
              return [
                {
                  id: data.task_id,
                  title: data.step_title || "Running task",
                  status: data.status || "running",
                  progress_pct: data.progress_pct,
                  current_step: data.step_title,
                },
                ...prev,
              ];
            });
          }
        } catch {
          // Ignore parse errors
        }
      });

      eventSource.addEventListener("task_completed", () => {
        fetchOverview();
      });

      eventSource.addEventListener("notification", () => {
        fetchOverview();
        fetchUnreadNotifications();
      });
    } catch (err) {
      console.warn("Companion SSE error:", err);
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [activeWorkspace, fetchOverview, fetchUnreadNotifications]);

  // 4. Voice Input (Web Speech API)
  useEffect(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      const rec = new SpeechRecognition();
      rec.continuous = false;
      rec.interimResults = true;
      rec.lang = "en-US";

      rec.onresult = (event: any) => {
        let transcript = "";
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

  const toggleVoiceListening = () => {
    if (!recognitionRef.current) {
      showToast("Speech recognition is not supported in this environment.", "warning");
      return;
    }
    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
      } catch (err) {
        console.error("Failed to start speech recognition:", err);
      }
    }
  };

  const speakText = (text: string) => {
    if (!("speechSynthesis" in window)) {
      showToast("Text-to-speech not supported.", "warning");
      return;
    }
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    setIsSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  // 5. Submit natural-language request to Personal Agent
  const handleSendPrompt = async () => {
    const text = promptInput.trim();
    if (!text || isSubmitting) return;

    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
    }

    setIsSubmitting(true);
    setLastUserPrompt(text);
    setPromptInput("");

    try {
      const res = await fetch(apiUrl("/api/personal/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: text,
          session_id: sessionId,
          workspace_id: activeWorkspace || undefined,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setSessionId(data.session_id);
        setLatestResponse(data);
        fetchOverview();
        fetchUnreadNotifications();
      } else {
        showToast("Error communicating with Aether.", "error");
      }
    } catch (err) {
      console.error("Companion request error:", err);
      showToast("Network error contacting Aether Core.", "error");
    } finally {
      setIsSubmitting(false);
    }
  };

  // 6. Action Layer Approvals
  const handleApproveAction = async (executionId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/actions/executions/${executionId}/approve`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approver: "user" }),
      });
      if (res.ok) {
        showToast("Action approved and executing.", "success");
        setPendingApprovals(prev => prev.filter(a => (a.execution_id || a.id) !== executionId));
        fetchOverview();
      } else {
        showToast("Failed to approve action.", "error");
      }
    } catch {
      showToast("Network error while approving action.", "error");
    }
  };

  const handleRejectAction = async (executionId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/actions/executions/${executionId}/reject`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Declined by user via Companion" }),
      });
      if (res.ok) {
        showToast("Action declined.", "info");
        setPendingApprovals(prev => prev.filter(a => (a.execution_id || a.id) !== executionId));
        fetchOverview();
      } else {
        showToast("Failed to decline action.", "error");
      }
    } catch {
      showToast("Network error while declining action.", "error");
    }
  };

  const handleMarkNotificationRead = async (id: string) => {
    try {
      const res = await fetch(
        apiUrl(`/api/notifications/${id}/read?workspace_id=${encodeURIComponent(activeWorkspace)}`),
        { method: "POST" }
      );
      if (res.ok) {
        setUnreadNotifications(prev => prev.filter(n => n.id !== id));
        setUnreadCount(prev => Math.max(0, prev - 1));
      }
    } catch {
      // Ignore
    }
  };

  // 7. Surface Transitions
  const handleOpenFullWorkspace = () => {
    if (onOpenWorkspace) {
      onOpenWorkspace();
    } else {
      showMainWindow();
    }
  };

  const handleDismiss = () => {
    hideCompanion();
  };

  // Keyboard dismiss (Escape) & focus
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        handleDismiss();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    inputRef.current?.focus();
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const activeRunningTasks = backgroundTasks.filter(
    t => t.status === "running" || t.status === "pending"
  );

  return (
    <div
      data-testid="ambient-companion-surface"
      style={{
        display: "flex",
        flexDirection: "column",
        width: "100vw",
        height: "100vh",
        backgroundColor: "hsl(var(--bg))",
        color: "hsl(var(--fg))",
        boxSizing: "border-box",
        overflow: "hidden",
        border: "1px solid hsl(var(--border))",
        borderRadius: "12px",
        boxShadow: "0 20px 40px rgba(0,0,0,0.24)",
        userSelect: "none",
      }}
    >
      {/* 1. Frameless Ambient Header with Drag Region */}
      <header
        data-tauri-drag-region
        style={{
          height: "46px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 14px",
          borderBottom: "1px solid hsl(var(--border))",
          backgroundColor: "hsl(var(--card))",
          cursor: "grab",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px", pointerEvents: "none" }}>
          <div
            style={{
              width: "22px",
              height: "22px",
              borderRadius: "6px",
              backgroundColor: "hsl(var(--primary)/0.15)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Sparkles size={13} className="text-primary" />
          </div>
          <span style={{ fontSize: "13px", fontWeight: 600, letterSpacing: "-0.01em" }}>Aether</span>
          <span
            style={{
              fontSize: "10px",
              fontWeight: 500,
              padding: "2px 6px",
              borderRadius: "4px",
              backgroundColor: "hsl(var(--muted))",
              color: "hsl(var(--muted-fg))",
            }}
          >
            Companion
          </span>
          {activeWorkspace && (
            <span
              style={{
                fontSize: "11px",
                color: "hsl(var(--muted-fg))",
                maxWidth: "120px",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              · {activeWorkspace}
            </span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "4px", cursor: "default" }}>
          <button
            onClick={handleOpenFullWorkspace}
            title="Open Full Workspace"
            data-testid="companion-open-workspace-btn"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              padding: "4px 8px",
              fontSize: "11px",
              fontWeight: 500,
              borderRadius: "6px",
              border: "1px solid hsl(var(--border))",
              backgroundColor: "hsl(var(--bg))",
              color: "hsl(var(--fg))",
              cursor: "pointer",
              transition: "background 0.15s",
            }}
          >
            <ExternalLink size={12} />
            <span>Workspace</span>
          </button>
          <button
            onClick={handleDismiss}
            title="Dismiss (Esc)"
            data-testid="companion-dismiss-btn"
            style={{
              padding: "5px",
              borderRadius: "6px",
              border: "none",
              background: "transparent",
              color: "hsl(var(--muted-fg))",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <X size={15} />
          </button>
        </div>
      </header>

      {/* 2. Scrollable Body */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "14px",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        }}
      >
        {/* Pending Approvals Widget (High Priority) */}
        {pendingApprovals.length > 0 && (
          <div
            data-testid="companion-approvals-card"
            style={{
              padding: "12px 14px",
              borderRadius: "10px",
              border: "1px solid hsl(38 92% 50% / 0.35)",
              backgroundColor: "hsl(38 92% 50% / 0.08)",
              display: "flex",
              flexDirection: "column",
              gap: "10px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Shield size={16} color="hsl(38 92% 50%)" />
              <span style={{ fontSize: "12px", fontWeight: 600, color: "hsl(38 92% 40%)" }}>
                Action requires your approval
              </span>
            </div>

            {pendingApprovals.map(approval => {
              const approvalId = approval.execution_id || approval.id || '';
              const approvalTitle = approval.action_name || approval.title || approval.action_type || "Action Execution";
              return (
                <div
                  key={approvalId}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "6px",
                    backgroundColor: "hsl(var(--card))",
                    padding: "10px",
                    borderRadius: "8px",
                    border: "1px solid hsl(var(--border))",
                  }}
                >
                  <div style={{ fontSize: "13px", fontWeight: 500 }}>
                    {approvalTitle}
                  </div>
                  {approval.description && (
                    <div style={{ fontSize: "11px", color: "hsl(var(--muted-fg))" }}>
                      {approval.description}
                    </div>
                  )}
                  <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                    <button
                      onClick={() => handleApproveAction(approvalId)}
                      data-testid={`approve-btn-${approvalId}`}
                      style={{
                        flex: 1,
                        padding: "6px 12px",
                        fontSize: "12px",
                        fontWeight: 600,
                        borderRadius: "6px",
                        border: "none",
                        backgroundColor: "hsl(var(--primary))",
                        color: "hsl(var(--primary-fg))",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: "4px",
                      }}
                    >
                      <Check size={13} />
                      <span>Approve</span>
                    </button>
                    <button
                      onClick={() => handleRejectAction(approvalId)}
                      data-testid={`reject-btn-${approvalId}`}
                      style={{
                        padding: "6px 12px",
                        fontSize: "12px",
                        fontWeight: 500,
                        borderRadius: "6px",
                        border: "1px solid hsl(var(--border))",
                        backgroundColor: "hsl(var(--card))",
                        color: "hsl(var(--muted-fg))",
                        cursor: "pointer",
                      }}
                    >
                      Reject
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Active Work / Background Tasks */}
        {activeRunningTasks.length > 0 && (
          <div
            data-testid="companion-active-work"
            style={{
              padding: "12px 14px",
              borderRadius: "10px",
              border: "1px solid hsl(var(--border))",
              backgroundColor: "hsl(var(--card))",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <Loader2 size={13} className="animate-spin text-primary" />
                <span style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", color: "hsl(var(--muted-fg))" }}>
                  Active Work
                </span>
              </div>
              <span style={{ fontSize: "11px", color: "hsl(var(--muted-fg))" }}>
                {activeRunningTasks.length} task{activeRunningTasks.length > 1 ? "s" : ""} running
              </span>
            </div>

            {activeRunningTasks.map(task => (
              <div
                key={task.id}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "4px",
                  padding: "8px",
                  backgroundColor: "hsl(var(--bg))",
                  borderRadius: "6px",
                  border: "1px solid hsl(var(--border)/0.6)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "12px", fontWeight: 500 }}>{task.title}</span>
                  {typeof task.progress_pct === "number" && (
                    <span style={{ fontSize: "11px", fontWeight: 600, color: "hsl(var(--primary))" }}>
                      {Math.round(task.progress_pct)}%
                    </span>
                  )}
                </div>
                {task.current_step && (
                  <span style={{ fontSize: "11px", color: "hsl(var(--muted-fg))" }}>
                    {task.current_step}
                  </span>
                )}
                {typeof task.progress_pct === "number" && (
                  <div
                    style={{
                      height: "4px",
                      borderRadius: "2px",
                      backgroundColor: "hsl(var(--muted))",
                      overflow: "hidden",
                      marginTop: "4px",
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        width: `${Math.min(100, Math.max(0, task.progress_pct))}%`,
                        backgroundColor: "hsl(var(--primary))",
                        transition: "width 0.3s ease",
                      }}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Unread Notifications (Compact) */}
        {unreadNotifications.length > 0 && (
          <div
            data-testid="companion-notifications-card"
            style={{
              padding: "10px 12px",
              borderRadius: "10px",
              border: "1px solid hsl(var(--border))",
              backgroundColor: "hsl(var(--card))",
              display: "flex",
              flexDirection: "column",
              gap: "6px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <Bell size={13} className="text-primary" />
                <span style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", color: "hsl(var(--muted-fg))" }}>
                  Notifications ({unreadCount})
                </span>
              </div>
            </div>

            {unreadNotifications.map(item => (
              <div
                key={item.id}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "space-between",
                  gap: "8px",
                  padding: "6px 8px",
                  borderRadius: "6px",
                  backgroundColor: "hsl(var(--bg))",
                }}
              >
                <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                  <span style={{ fontSize: "12px", fontWeight: 500 }}>{item.title}</span>
                  <span
                    style={{
                      fontSize: "11px",
                      color: "hsl(var(--muted-fg))",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {item.message}
                  </span>
                </div>
                <button
                  onClick={() => handleMarkNotificationRead(item.id)}
                  title="Mark as read"
                  style={{
                    padding: "3px",
                    borderRadius: "4px",
                    border: "none",
                    background: "transparent",
                    color: "hsl(var(--muted-fg))",
                    cursor: "pointer",
                  }}
                >
                  <Check size={13} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Previous Interaction / Active Session Result */}
        {latestResponse && (
          <div
            data-testid="companion-response-box"
            style={{
              padding: "12px 14px",
              borderRadius: "10px",
              border: "1px solid hsl(var(--border))",
              backgroundColor: "hsl(var(--card))",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            {lastUserPrompt && (
              <div
                style={{
                  fontSize: "11px",
                  color: "hsl(var(--muted-fg))",
                  borderBottom: "1px solid hsl(var(--border)/0.5)",
                  paddingBottom: "6px",
                }}
              >
                You: <span style={{ color: "hsl(var(--fg))" }}>{lastUserPrompt}</span>
              </div>
            )}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div
                style={{
                  fontSize: "13px",
                  lineHeight: "1.5",
                  color: "hsl(var(--fg))",
                  whiteSpace: "pre-wrap",
                }}
              >
                {latestResponse.content}
              </div>
              <button
                onClick={() => speakText(latestResponse.content)}
                title={isSpeaking ? "Stop speaking" : "Read aloud"}
                style={{
                  padding: "4px",
                  borderRadius: "4px",
                  border: "none",
                  background: "transparent",
                  color: isSpeaking ? "hsl(var(--primary))" : "hsl(var(--muted-fg))",
                  cursor: "pointer",
                }}
              >
                {isSpeaking ? <VolumeX size={14} /> : <Volume2 size={14} />}
              </button>
            </div>

            {/* Steps pills */}
            {latestResponse.steps && latestResponse.steps.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginTop: "4px" }}>
                {latestResponse.steps.map(step => (
                  <div
                    key={step.id}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "4px",
                      fontSize: "10px",
                      padding: "2px 8px",
                      borderRadius: "12px",
                      backgroundColor:
                        step.status === "completed"
                          ? "hsl(var(--primary)/0.12)"
                          : step.status === "failed"
                          ? "hsl(0 84% 60% / 0.12)"
                          : "hsl(var(--muted))",
                      color:
                        step.status === "completed"
                          ? "hsl(var(--primary))"
                          : step.status === "failed"
                          ? "hsl(0 84% 60%)"
                          : "hsl(var(--muted-fg))",
                    }}
                  >
                    {step.status === "completed" ? (
                      <CheckCircle2 size={10} />
                    ) : step.status === "pending_approval" ? (
                      <Shield size={10} />
                    ) : (
                      <Clock size={10} />
                    )}
                    <span>{step.title}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Empty state when no previous prompt and no active tasks */}
        {!latestResponse && activeRunningTasks.length === 0 && pendingApprovals.length === 0 && (
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              padding: "24px 12px",
              color: "hsl(var(--muted-fg))",
            }}
          >
            <div
              style={{
                width: "40px",
                height: "40px",
                borderRadius: "12px",
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: "10px",
              }}
            >
              <Sparkles size={20} className="text-primary" />
            </div>
            <div style={{ fontSize: "13px", fontWeight: 500, color: "hsl(var(--fg))" }}>
              Aether Ambient Companion
            </div>
            <div style={{ fontSize: "11px", marginTop: "4px", maxWidth: "240px", lineHeight: 1.4 }}>
              Type any instruction or click the mic. Press Esc to hide or Alt+Space anytime.
            </div>
          </div>
        )}
      </div>

      {/* 3. Dominant Natural-Language Input Bar */}
      <div
        style={{
          padding: "12px 14px",
          borderTop: "1px solid hsl(var(--border))",
          backgroundColor: "hsl(var(--card))",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            backgroundColor: "hsl(var(--bg))",
            border: "1px solid hsl(var(--border))",
            borderRadius: "10px",
            padding: "6px 10px",
            boxShadow: "0 2px 6px rgba(0,0,0,0.04)",
          }}
        >
          <input
            ref={inputRef}
            type="text"
            data-testid="companion-chat-input"
            value={promptInput}
            onChange={e => setPromptInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSendPrompt();
              }
            }}
            placeholder="How can I help you?"
            disabled={isSubmitting}
            style={{
              flex: 1,
              border: "none",
              outline: "none",
              background: "transparent",
              color: "hsl(var(--fg))",
              fontSize: "13px",
              padding: "4px 2px",
            }}
          />

          {/* Voice Mic Button */}
          <button
            onClick={toggleVoiceListening}
            title={isListening ? "Listening... click to stop" : "Voice input"}
            data-testid="companion-voice-btn"
            style={{
              padding: "6px",
              borderRadius: "6px",
              border: "none",
              backgroundColor: isListening ? "hsl(0 84% 60% / 0.15)" : "transparent",
              color: isListening ? "hsl(0 84% 60%)" : "hsl(var(--muted-fg))",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              animation: isListening ? "pulse 1.5s infinite" : "none",
            }}
          >
            {isListening ? <MicOff size={15} /> : <Mic size={15} />}
          </button>

          {/* Send Button */}
          <button
            onClick={handleSendPrompt}
            disabled={!promptInput.trim() || isSubmitting}
            data-testid="companion-send-btn"
            style={{
              padding: "6px",
              borderRadius: "6px",
              border: "none",
              backgroundColor: promptInput.trim() ? "hsl(var(--primary))" : "hsl(var(--muted))",
              color: promptInput.trim() ? "hsl(var(--primary-fg))" : "hsl(var(--muted-fg))",
              cursor: promptInput.trim() && !isSubmitting ? "pointer" : "default",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: isSubmitting ? 0.6 : 1,
            }}
          >
            {isSubmitting ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
