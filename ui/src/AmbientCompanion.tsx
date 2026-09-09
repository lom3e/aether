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
  Eye,
  MessageSquare,
  Info,
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
  progress_percent?: number | null;
  current_step?: string;
  started_at?: string;
  deliverable_path?: string;
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

  // Progressive UI Modes
  const [showVisualNotice, setShowVisualNotice] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);

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
      const res = await fetch(
        apiUrl(`/api/personal/overview?workspace_id=${encodeURIComponent(activeWorkspace)}`)
      );
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
      const res = await fetch(
        apiUrl(`/api/notifications?workspace_id=${encodeURIComponent(activeWorkspace)}&limit=5`)
      );
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
                        progress_percent: data.progress_pct,
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
                  progress_percent: data.progress_pct,
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
      rec.lang = "it-IT,en-US";

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

  // 6. Action Layer Approvals (Human-friendly non-technical confirmation)
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

  // Keyboard shortcuts (Escape to dismiss, Cmd+O for Workspace, Cmd+M for Voice)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        handleDismiss();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "o") {
        e.preventDefault();
        handleOpenFullWorkspace();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "m") {
        e.preventDefault();
        toggleVoiceListening();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPromptInput("");
        setLatestResponse(null);
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    inputRef.current?.focus();
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleDismiss, handleOpenFullWorkspace, toggleVoiceListening]);

  const activeRunningTasks = backgroundTasks.filter(
    t => t.status === "running" || t.status === "pending"
  );
  const completedTaskWithDeliverable = backgroundTasks.find(
    t => t.status === "completed" && t.deliverable_path
  );

  return (
    <div
      data-testid="ambient-companion-surface"
      style={{
        display: "flex",
        flexDirection: "column",
        width: "100vw",
        height: "100vh",
        backgroundColor: "rgba(15, 23, 42, 0.90)",
        backdropFilter: "blur(28px) saturate(190%)",
        WebkitBackdropFilter: "blur(28px) saturate(190%)",
        color: "hsl(var(--fg))",
        boxSizing: "border-box",
        overflow: "hidden",
        border: "1px solid rgba(255, 255, 255, 0.12)",
        borderRadius: "18px",
        boxShadow: "0 20px 50px rgba(0, 0, 0, 0.65), 0 0 40px rgba(56, 189, 248, 0.12)",
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      }}
    >
      {/* 1. Sleek Ambient HUD Header */}
      <header
        data-tauri-drag-region
        style={{
          height: "44px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 14px",
          borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
          backgroundColor: "rgba(255, 255, 255, 0.03)",
          cursor: "grab",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px", pointerEvents: "none" }}>
          {/* Pulsing Jarvis Orb */}
          <div
            style={{
              width: "10px",
              height: "10px",
              borderRadius: "50%",
              backgroundColor: isListening
                ? "#ef4444"
                : activeRunningTasks.length > 0
                ? "#f59e0b"
                : "#38bdf8",
              boxShadow: isListening
                ? "0 0 12px #ef4444"
                : activeRunningTasks.length > 0
                ? "0 0 12px #f59e0b"
                : "0 0 10px rgba(56, 189, 248, 0.8)",
              animation: isListening || activeRunningTasks.length > 0 ? "pulse 1.4s infinite" : "none",
            }}
          />
          <span style={{ fontSize: "13px", fontWeight: 700, letterSpacing: "-0.01em", color: "#f8fafc" }}>
            Aether
          </span>
          <span
            style={{
              fontSize: "10px",
              fontWeight: 500,
              padding: "2px 6px",
              borderRadius: "10px",
              backgroundColor: "rgba(255, 255, 255, 0.08)",
              color: "rgba(255, 255, 255, 0.6)",
              letterSpacing: "0.02em",
            }}
          >
            {isListening ? "Listening" : activeRunningTasks.length > 0 ? "Active" : "Ambient"}
          </span>
          {activeWorkspace && (
            <span
              style={{
                fontSize: "11px",
                color: "rgba(255, 255, 255, 0.45)",
                maxWidth: "110px",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              · {activeWorkspace}
            </span>
          )}
          {unreadCount > 0 && (
            <span
              title={`${unreadCount} notification${unreadCount > 1 ? "s" : ""}`}
              style={{
                fontSize: "10px",
                padding: "2px 6px",
                borderRadius: "10px",
                backgroundColor: "rgba(56, 189, 248, 0.15)",
                color: "#38bdf8",
                display: "inline-flex",
                alignItems: "center",
                gap: "3px",
              }}
            >
              <Bell size={10} />
              <span>{unreadCount}</span>
            </span>
          )}
        </div>

        {/* Quick Transition Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "default" }}>
          <button
            onClick={handleOpenFullWorkspace}
            title="Open Full Workspace (Cmd+O)"
            data-testid="companion-open-workspace-btn"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
              padding: "3px 8px",
              fontSize: "11px",
              fontWeight: 500,
              borderRadius: "6px",
              border: "1px solid rgba(255, 255, 255, 0.12)",
              backgroundColor: "rgba(255, 255, 255, 0.06)",
              color: "#e2e8f0",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            <ExternalLink size={11} />
            <span>Workspace</span>
          </button>
          <button
            onClick={handleDismiss}
            title="Dismiss (Esc)"
            data-testid="companion-dismiss-btn"
            style={{
              padding: "4px 6px",
              borderRadius: "6px",
              border: "none",
              background: "transparent",
              color: "rgba(255, 255, 255, 0.5)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <X size={14} />
          </button>
        </div>
      </header>

      {/* 2. Top-Anchored Jarvis Command Bar */}
      <div
        style={{
          padding: "10px 14px",
          borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
          backgroundColor: "rgba(0, 0, 0, 0.15)",
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          gap: "8px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            backgroundColor: "rgba(255, 255, 255, 0.06)",
            border: isListening
              ? "1px solid rgba(239, 68, 68, 0.6)"
              : "1px solid rgba(255, 255, 255, 0.14)",
            borderRadius: "12px",
            padding: "6px 10px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
            transition: "border 0.2s ease",
          }}
        >
          <Sparkles size={14} color="#38bdf8" style={{ flexShrink: 0, opacity: 0.9 }} />
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
            placeholder={isListening ? "Listening to your voice..." : "Ask Aether, execute actions, or dispatch workforce..."}
            disabled={isSubmitting}
            style={{
              flex: 1,
              border: "none",
              outline: "none",
              background: "transparent",
              color: "#f8fafc",
              fontSize: "13px",
              padding: "4px 2px",
            }}
          />

          {/* Voice Mic Button */}
          <button
            onClick={toggleVoiceListening}
            title={isListening ? "Listening... click to stop (Cmd+M)" : "Voice input (Cmd+M)"}
            data-testid="companion-voice-btn"
            style={{
              padding: "5px",
              borderRadius: "6px",
              border: "none",
              backgroundColor: isListening ? "rgba(239, 68, 68, 0.25)" : "transparent",
              color: isListening ? "#ef4444" : "rgba(255, 255, 255, 0.6)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
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
              padding: "5px 8px",
              borderRadius: "6px",
              border: "none",
              backgroundColor: promptInput.trim() ? "hsl(var(--primary))" : "rgba(255, 255, 255, 0.08)",
              color: promptInput.trim() ? "hsl(var(--primary-fg))" : "rgba(255, 255, 255, 0.4)",
              cursor: promptInput.trim() && !isSubmitting ? "pointer" : "default",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: isSubmitting ? 0.6 : 1,
              transition: "all 0.15s ease",
            }}
          >
            {isSubmitting ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Send size={13} />
            )}
          </button>
        </div>

        {/* Quick Ambient Modalities Bar: [Chat] [Voice] [Visual] [Suggestions] */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: "2px" }}>
          <div style={{ display: "flex", gap: "6px" }}>
            <button
              onClick={() => {
                inputRef.current?.focus();
              }}
              title="Chat mode"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
                fontSize: "11px",
                fontWeight: 500,
                padding: "3px 8px",
                borderRadius: "6px",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                backgroundColor: "rgba(255, 255, 255, 0.04)",
                color: "rgba(255, 255, 255, 0.75)",
                cursor: "pointer",
              }}
            >
              <MessageSquare size={11} />
              <span>Chat</span>
            </button>

            <button
              onClick={toggleVoiceListening}
              title="Voice Push-To-Talk"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
                fontSize: "11px",
                fontWeight: 500,
                padding: "3px 8px",
                borderRadius: "6px",
                border: isListening ? "1px solid rgba(239, 68, 68, 0.4)" : "1px solid rgba(255, 255, 255, 0.08)",
                backgroundColor: isListening ? "rgba(239, 68, 68, 0.15)" : "rgba(255, 255, 255, 0.04)",
                color: isListening ? "#ef4444" : "rgba(255, 255, 255, 0.75)",
                cursor: "pointer",
              }}
            >
              <Mic size={11} />
              <span>Voice</span>
            </button>

            {/* Truthful Visual Capability Button */}
            <button
              onClick={() => setShowVisualNotice(prev => !prev)}
              title="Visual Intelligence state"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
                fontSize: "11px",
                fontWeight: 500,
                padding: "3px 8px",
                borderRadius: "6px",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                backgroundColor: "rgba(255, 255, 255, 0.04)",
                color: "rgba(255, 255, 255, 0.5)",
                cursor: "pointer",
              }}
            >
              <Eye size={11} />
              <span>Visual</span>
              <span style={{ fontSize: "9px", opacity: 0.6 }}>(Upcoming)</span>
            </button>
          </div>

          <button
            onClick={() => setShowSuggestions(prev => !prev)}
            title="Toggle prompt suggestions"
            style={{
              fontSize: "11px",
              padding: "2px 6px",
              borderRadius: "4px",
              border: "none",
              backgroundColor: "transparent",
              color: "rgba(255, 255, 255, 0.4)",
              cursor: "pointer",
            }}
          >
            {showSuggestions ? "Hide suggestions" : "Suggestions"}
          </button>
        </div>

        {/* Suggestion Chips */}
        {showSuggestions && !latestResponse && !promptInput && (
          <div style={{ display: "flex", gap: "6px", overflowX: "auto", paddingBottom: "2px" }}>
            <button
              onClick={() => {
                setPromptInput("ciao come stai?");
                inputRef.current?.focus();
              }}
              style={{
                fontSize: "11px",
                padding: "3px 8px",
                borderRadius: "6px",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                backgroundColor: "rgba(255, 255, 255, 0.03)",
                color: "rgba(255, 255, 255, 0.7)",
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              💬 "ciao come stai?"
            </button>
            <button
              onClick={() => {
                setPromptInput("Analisi di mercato per CarShine");
                inputRef.current?.focus();
              }}
              style={{
                fontSize: "11px",
                padding: "3px 8px",
                borderRadius: "6px",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                backgroundColor: "rgba(255, 255, 255, 0.03)",
                color: "rgba(255, 255, 255, 0.7)",
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              🚀 CarShine Research
            </button>
            <button
              onClick={() => {
                setPromptInput("Schedule a meeting with ");
                inputRef.current?.focus();
              }}
              style={{
                fontSize: "11px",
                padding: "3px 8px",
                borderRadius: "6px",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                backgroundColor: "rgba(255, 255, 255, 0.03)",
                color: "rgba(255, 255, 255, 0.7)",
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              📅 Schedule Meeting
            </button>
            <button
              onClick={() => {
                setPromptInput("Create a document called ");
                inputRef.current?.focus();
              }}
              style={{
                fontSize: "11px",
                padding: "3px 8px",
                borderRadius: "6px",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                backgroundColor: "rgba(255, 255, 255, 0.03)",
                color: "rgba(255, 255, 255, 0.7)",
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              📝 Create Doc
            </button>
          </div>
        )}
      </div>

      {/* Visual Intelligence Truthful Banner (if triggered) */}
      {showVisualNotice && (
        <div
          style={{
            margin: "8px 14px 0",
            padding: "8px 12px",
            borderRadius: "8px",
            backgroundColor: "rgba(56, 189, 248, 0.1)",
            border: "1px solid rgba(56, 189, 248, 0.25)",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: "8px",
          }}
        >
          <div style={{ display: "flex", gap: "8px", alignItems: "flex-start" }}>
            <Info size={14} color="#38bdf8" style={{ marginTop: "2px", flexShrink: 0 }} />
            <span style={{ fontSize: "11px", color: "#e0f2fe", lineHeight: 1.4 }}>
              <strong>Visual Intelligence</strong>: In arrivo nel prossimo aggiornamento desktop. La cattura dello schermo e della webcam è attualmente disattivata per tutelare la tua privacy.
            </span>
          </div>
          <button
            onClick={() => setShowVisualNotice(false)}
            style={{
              background: "transparent",
              border: "none",
              color: "rgba(255, 255, 255, 0.5)",
              cursor: "pointer",
              padding: "2px",
            }}
          >
            <X size={13} />
          </button>
        </div>
      )}

      {/* 3. Main Interactive Body */}
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
        {/* Human-Centric Safety Approvals (Only visible when pending) */}
        {pendingApprovals.length > 0 && (
          <div
            data-testid="companion-approvals-card"
            style={{
              padding: "12px 14px",
              borderRadius: "12px",
              border: "1px solid rgba(245, 158, 11, 0.4)",
              backgroundColor: "rgba(245, 158, 11, 0.08)",
              display: "flex",
              flexDirection: "column",
              gap: "10px",
              boxShadow: "0 4px 14px rgba(0,0,0,0.25)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Shield size={16} color="#f59e0b" />
              <span style={{ fontSize: "12px", fontWeight: 600, color: "#fbbf24" }}>
                Approval Required
              </span>
            </div>

            {pendingApprovals.map(approval => {
              const approvalId = approval.execution_id || approval.id || "";
              const friendlyAction =
                approval.action_name || approval.title || "external action";
              const targetDetail =
                approval.input_data?.title ||
                approval.params?.title ||
                approval.description ||
                "";

              return (
                <div
                  key={approvalId}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "6px",
                    backgroundColor: "rgba(0, 0, 0, 0.25)",
                    padding: "10px",
                    borderRadius: "8px",
                    border: "1px solid rgba(255, 255, 255, 0.08)",
                  }}
                >
                  <div style={{ fontSize: "13px", fontWeight: 500, color: "#f8fafc" }}>
                    Aether wants to {friendlyAction.toLowerCase()}{targetDetail ? `: "${targetDetail}"` : "."}
                  </div>
                  <div style={{ fontSize: "11px", color: "rgba(255, 255, 255, 0.55)" }}>
                    This will safely update your calendar or external account. Review and confirm to proceed.
                  </div>

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
                        backgroundColor: "#38bdf8",
                        color: "#0f172a",
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
                        border: "1px solid rgba(255, 255, 255, 0.12)",
                        backgroundColor: "rgba(255, 255, 255, 0.05)",
                        color: "rgba(255, 255, 255, 0.75)",
                        cursor: "pointer",
                      }}
                    >
                      Not now
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Active Conversational Transcript */}
        {(lastUserPrompt || latestResponse) && (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {/* User Message Bubble */}
            {lastUserPrompt && (
              <div
                style={{
                  alignSelf: "flex-end",
                  maxWidth: "85%",
                  padding: "8px 12px",
                  borderRadius: "12px 12px 2px 12px",
                  backgroundColor: "rgba(56, 189, 248, 0.15)",
                  border: "1px solid rgba(56, 189, 248, 0.3)",
                  color: "#f0f9ff",
                  fontSize: "13px",
                  lineHeight: 1.4,
                }}
              >
                {lastUserPrompt}
              </div>
            )}

            {/* Assistant Response Card */}
            {latestResponse && (
              <div
                style={{
                  alignSelf: "flex-start",
                  width: "100%",
                  padding: "12px",
                  borderRadius: "12px 12px 12px 2px",
                  backgroundColor: "rgba(255, 255, 255, 0.04)",
                  border: "1px solid rgba(255, 255, 255, 0.08)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <Sparkles size={13} color="#38bdf8" />
                    <span style={{ fontSize: "11px", fontWeight: 600, color: "rgba(255, 255, 255, 0.7)" }}>
                      Aether
                    </span>
                  </div>
                  <button
                    onClick={() => speakText(latestResponse.content)}
                    title={isSpeaking ? "Stop speaking" : "Listen to response"}
                    style={{
                      padding: "3px",
                      background: "transparent",
                      border: "none",
                      color: isSpeaking ? "#38bdf8" : "rgba(255, 255, 255, 0.5)",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                    }}
                  >
                    {isSpeaking ? <VolumeX size={13} /> : <Volume2 size={13} />}
                  </button>
                </div>

                <div
                  style={{
                    fontSize: "13px",
                    lineHeight: 1.5,
                    color: "#f8fafc",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {latestResponse.content}
                </div>

                {/* Steps detail (if any) */}
                {latestResponse.steps && latestResponse.steps.length > 0 && (
                  <div
                    style={{
                      marginTop: "6px",
                      paddingTop: "6px",
                      borderTop: "1px solid rgba(255, 255, 255, 0.06)",
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "6px",
                    }}
                  >
                    {latestResponse.steps.map(s => (
                      <span
                        key={s.id}
                        style={{
                          fontSize: "10px",
                          padding: "2px 6px",
                          borderRadius: "4px",
                          backgroundColor: "rgba(255, 255, 255, 0.06)",
                          color: "rgba(255, 255, 255, 0.6)",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                        }}
                      >
                        {s.status === "completed" ? (
                          <CheckCircle2 size={10} color="#22c55e" />
                        ) : (
                          <Clock size={10} color="#f59e0b" />
                        )}
                        <span>{s.title}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Unread Notifications (discreet banner) */}
        {unreadNotifications.length > 0 && !lastUserPrompt && !latestResponse && pendingApprovals.length === 0 && (
          <div
            data-testid="companion-notifications-card"
            style={{
              padding: "8px 12px",
              borderRadius: "10px",
              backgroundColor: "rgba(255, 255, 255, 0.04)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <Bell size={12} color="#38bdf8" style={{ flexShrink: 0 }} />
            <span
              style={{
                fontSize: "11px",
                color: "rgba(255, 255, 255, 0.8)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {unreadNotifications[0].title}: {unreadNotifications[0].message}
            </span>
          </div>
        )}

        {/* Resting / Idle State when no prompt has been submitted */}
        {!lastUserPrompt && !latestResponse && (
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              gap: "12px",
              padding: "20px 10px",
              opacity: 0.85,
            }}
          >
            <div
              style={{
                width: "48px",
                height: "48px",
                borderRadius: "50%",
                background: "radial-gradient(circle, rgba(56,189,248,0.25) 0%, rgba(56,189,248,0) 70%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "0 0 25px rgba(56,189,248,0.3)",
              }}
            >
              <Sparkles size={22} color="#38bdf8" />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <span style={{ fontSize: "14px", fontWeight: 600, color: "#f8fafc" }}>
                Aether Ambient Presence
              </span>
              <span style={{ fontSize: "12px", color: "rgba(255, 255, 255, 0.5)", maxWidth: "260px" }}>
                Evocato vicino al tuo cursore. Chiedi, dialoga o assegna compiti operativi alla workforce.
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 4. Minimal Floating Background Work & Deliverable Indicator */}
      {(activeRunningTasks.length > 0 || completedTaskWithDeliverable) && (
        <div
          data-testid="companion-active-work"
          style={{
            padding: "8px 14px",
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
            backgroundColor: "rgba(0, 0, 0, 0.35)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexShrink: 0,
          }}
        >
          {activeRunningTasks.length > 0 ? (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flex: 1, minWidth: 0 }}>
              <Loader2 size={13} className="animate-spin text-primary" color="#38bdf8" />
              <div style={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ fontSize: "11px", fontWeight: 600, color: "#e2e8f0" }}>
                    {activeRunningTasks[0].title}
                  </span>
                  {typeof (activeRunningTasks[0].progress_pct ?? activeRunningTasks[0].progress_percent) === "number" && (
                    <span style={{ fontSize: "10px", fontWeight: 600, color: "#38bdf8" }}>
                      {Math.round((activeRunningTasks[0].progress_pct ?? activeRunningTasks[0].progress_percent) || 0)}%
                    </span>
                  )}
                </div>
                {activeRunningTasks[0].current_step && (
                  <span
                    style={{
                      fontSize: "10px",
                      color: "rgba(255, 255, 255, 0.5)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {activeRunningTasks[0].current_step}
                  </span>
                )}
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "6px", flex: 1 }}>
              <CheckCircle2 size={13} color="#22c55e" />
              <span style={{ fontSize: "11px", fontWeight: 500, color: "#86efac" }}>
                Deliverable completato ({completedTaskWithDeliverable?.title})
              </span>
            </div>
          )}

          <button
            onClick={handleOpenFullWorkspace}
            style={{
              fontSize: "10px",
              padding: "3px 7px",
              borderRadius: "5px",
              border: "1px solid rgba(255, 255, 255, 0.1)",
              backgroundColor: "rgba(255, 255, 255, 0.06)",
              color: "#38bdf8",
              cursor: "pointer",
              marginLeft: "10px",
              whiteSpace: "nowrap",
            }}
          >
            Open in Aether ↗
          </button>
        </div>
      )}
    </div>
  );
}
