import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowUp, Check, ChevronRight, Copy, Loader2, Mic, Square, Undo2, Volume2, VolumeX, X } from 'lucide-react';
import { MarkdownRenderer } from '../MarkdownRenderer';
import { translateStepTitle } from '../stepTitles';
import { Receipts } from '../companion/Receipts';
import { receiptsOf, type ChatMessage } from '../companion/useCompanionRuntime';
import type { TranslationKey } from '../i18n';

type T = (key: TranslationKey, params?: Record<string, string | number>) => string;

export interface ChatStep { id: string; title: string; status: string; category: string; details?: any }
export interface ChatMsg {
  id: string;
  role: string;
  content: string;
  tier?: string;
  steps: ChatStep[];
  action_execution_id?: string;
  session_id?: string;
  metadata?: Record<string, any>;
  created_at: string;
}

/** The composer: grows with the text, Enter sends, Shift+Enter is a new line. */
export function Composer({ value, onChange, onSend, onMic, listening, busy, placeholder, t, autoFocus }: {
  value: string; onChange: (v: string) => void; onSend: () => void; onMic: () => void; listening: boolean; busy: boolean;
  placeholder: string; t: T; autoFocus?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value]);
  useEffect(() => { if (autoFocus) ref.current?.focus(); }, [autoFocus]);
  return (
    <div className="ch-composer" data-listening={listening ? 'true' : 'false'}>
      <textarea
        ref={ref}
        data-testid="companion-input-field"
        rows={1}
        placeholder={placeholder}
        value={value}
        aria-label={placeholder}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            onSend();
          }
        }}
      />
      <div className="ch-composer-tools">
        <button type="button" data-testid="voice-mic-btn" className={`ch-icon ${listening ? 'on' : ''}`} onClick={onMic}
          title={listening ? t('homeUiStopListening') : t('homeUiVoiceInputClickToSpeak')} aria-label={listening ? t('homeUiStopListening') : t('homeUiVoiceInputClickToSpeak')}>
          {listening ? <Square size={14} /> : <Mic size={17} />}
        </button>
        <button type="button" data-testid="companion-submit-btn" className="ch-send" disabled={!value.trim() || busy} onClick={onSend}
          aria-label={busy ? t('homeUiProcessing') : t('homeUiTakeCareOfIt')} title={busy ? t('homeUiProcessing') : t('homeUiTakeCareOfIt')}>
          {busy ? <Loader2 size={16} className="ch-spin" /> : <ArrowUp size={18} strokeWidth={2.4} />}
        </button>
      </div>
    </div>
  );
}

function Steps({ steps, t }: { steps: ChatStep[]; t: T }) {
  const [open, setOpen] = useState(false);
  const shown = steps;
  if (!shown.length) return null;
  const running = shown.find(s => s.status === 'running');
  const lastFailed = [...shown].reverse().find(s => s.status === 'failed');
  const failed = !!lastFailed;
  // The summary says what matters: what is happening now, or what went wrong (e.g. "Proposal declined"), else how many steps
  const label = running ? translateStepTitle(running.title, t) : lastFailed ? translateStepTitle(lastFailed.title, t) : t('chStepsDone', { count: shown.length });
  return (
    <div className={`ch-steps ${open ? 'open' : ''}`}>
      <button type="button" className="ch-steps-head" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        {running ? <Loader2 size={13} className="ch-spin" /> : failed ? <X size={13} className="ch-bad" /> : <Check size={13} className="ch-ok" />}
        <span>{label}</span>
        <ChevronRight size={13} className="ch-chev" />
      </button>
      {open && (
        <ol className="ch-steps-list">
          {shown.map(s => (
            <li key={s.id} data-status={s.status}>{translateStepTitle(s.title, t)}</li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** A confirmation before Aether changes something: plain question, two buttons. */
export function ConfirmCard({ title, busy, onConfirm, onDecline, confirmLabel, declineLabel, children, testId }: {
  title: string; busy: boolean; onConfirm: () => void; onDecline: () => void; confirmLabel: string; declineLabel: string; children?: ReactNode; testId?: string;
}) {
  return (
    <div className="ch-confirm" data-testid={testId}>
      <div className="ch-confirm-title">{title}</div>
      {children}
      <div className="ch-confirm-actions">
        <button type="button" className="ch-btn ghost" disabled={busy} onClick={onDecline}>{declineLabel}</button>
        <button type="button" className="ch-btn primary" disabled={busy} onClick={onConfirm}>
          {busy && <Loader2 size={14} className="ch-spin" />}{confirmLabel}
        </button>
      </div>
    </div>
  );
}

export function UserMessage({ msg }: { msg: ChatMsg }) {
  return (
    <div className="ch-row user" data-role="user">
      <div className="ch-bubble">{msg.content}</div>
    </div>
  );
}

export function AssistantMessage({ msg, t, speaking, onSpeak, onUndo, undoState, notify, children }: {
  msg: ChatMsg; t: T; speaking: boolean; onSpeak: () => void; onUndo?: () => void; undoState?: 'idle' | 'busy' | 'done';
  notify: (message: string, kind: 'success' | 'error' | 'info' | 'warning') => void; children?: ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const receiptMsg = { id: msg.id, role: 'assistant', content: msg.content, createdAt: msg.created_at, ...receiptsOf(msg.metadata) } as unknown as ChatMessage;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard not available */ }
  };
  return (
    <div className="ch-row ai" data-role="assistant">
      <div className="ch-avatar" aria-hidden><span /></div>
      <div className="ch-body">
        {msg.steps?.length > 0 && <Steps steps={msg.steps} t={t} />}
        <div className="ch-md"><MarkdownRenderer content={msg.content} /></div>
        {children}
        {msg.metadata?.undo_execution_id && onUndo && (
          <button type="button" className="ch-undo" disabled={undoState !== 'idle'} onClick={onUndo} data-testid="chat-undo">
            {undoState === 'busy' ? <Loader2 size={13} className="ch-spin" /> : <Undo2 size={13} />}
            {undoState === 'done' ? t('chUndone') : t('chUndo')}
          </button>
        )}
        <Receipts message={receiptMsg} t={t} notify={notify} />
        <div className="ch-actions">
          <button type="button" className="ch-icon sm" onClick={copy} title={copied ? t('chCopied') : t('chCopy')} aria-label={copied ? t('chCopied') : t('chCopy')}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button type="button" className="ch-icon sm" onClick={onSpeak} title={speaking ? t('homeUiStopAudio') : t('homeUiReadAloud')} aria-label={speaking ? t('homeUiStopAudio') : t('homeUiReadAloud')}>
            {speaking ? <VolumeX size={14} /> : <Volume2 size={14} />}
          </button>
          {msg.metadata?.model && (
            <span className="ch-model" data-testid="answer-model">{msg.metadata.provider ? `${msg.metadata.provider} · ` : ''}{msg.metadata.model}</span>
          )}
        </div>
      </div>
    </div>
  );
}

export function Thinking({ t }: { t: T }) {
  return (
    <div className="ch-row ai" aria-live="polite">
      <div className="ch-avatar thinking" aria-hidden><span /></div>
      <div className="ch-body"><span className="ch-thinking">{t('chThinking')}</span></div>
    </div>
  );
}
