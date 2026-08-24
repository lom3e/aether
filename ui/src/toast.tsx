import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
  duration: number;
}

export type ShowToastFunction = (
  message: string,
  type?: ToastType,
  duration?: number
) => void;

export const ToastContext = createContext<ShowToastFunction>((_msg, _type, _dur) => {});

export function useToast(): ShowToastFunction {
  return useContext(ToastContext);
}

interface SingleToastProps {
  toast: ToastItem;
  onDismiss: (id: string) => void;
}

function SingleToast({ toast, onDismiss }: SingleToastProps) {
  const [isPaused, setIsPaused] = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  const startTimeRef = useRef<number>(Date.now());
  const remainingRef = useRef<number>(toast.duration);
  const timerRef = useRef<any>(null);

  const handleDismiss = useCallback(() => {
    setIsExiting(true);
    setTimeout(() => {
      onDismiss(toast.id);
    }, 200);
  }, [onDismiss, toast.id]);

  useEffect(() => {
    if (isPaused) {
      clearTimeout(timerRef.current);
      remainingRef.current -= Date.now() - startTimeRef.current;
    } else {
      startTimeRef.current = Date.now();
      timerRef.current = setTimeout(() => {
        handleDismiss();
      }, Math.max(remainingRef.current, 0));
    }
    return () => clearTimeout(timerRef.current);
  }, [isPaused, handleDismiss]);

  const getIcon = () => {
    switch (toast.type) {
      case 'success':
        return <CheckCircle2 size={16} className="toast-icon-success" />;
      case 'error':
        return <AlertCircle size={16} className="toast-icon-error" />;
      case 'warning':
        return <AlertTriangle size={16} className="toast-icon-warning" />;
      case 'info':
      default:
        return <Info size={16} className="toast-icon-info" />;
    }
  };

  const isAlert = toast.type === 'error' || toast.type === 'warning';

  return (
    <div
      role={isAlert ? 'alert' : 'status'}
      aria-live={isAlert ? 'assertive' : 'polite'}
      className={`aether-toast aether-toast-${toast.type} ${isExiting ? 'aether-toast-exit' : ''}`}
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      data-testid={`toast-${toast.type}`}
    >
      <div className="aether-toast-content">
        <span className="aether-toast-icon">{getIcon()}</span>
        <span className="aether-toast-message">{toast.message}</span>
        <button
          className="aether-toast-close"
          onClick={handleDismiss}
          aria-label="Close notification"
        >
          <X size={14} />
        </button>
      </div>
      <div className="aether-toast-progress-track">
        <div
          className="aether-toast-progress-bar"
          style={{
            animationDuration: `${toast.duration}ms`,
            animationPlayState: isPaused ? 'paused' : 'running',
          }}
        />
      </div>
    </div>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback((
    message: string,
    type: ToastType = 'info',
    duration: number = 3800
  ) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setToasts((prev) => {
      const next = [...prev, { id, message, type, duration }];
      return next.slice(-5);
    });
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      <div className="aether-toast-container" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <SingleToast key={toast.id} toast={toast} onDismiss={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}
