import { useEffect, useRef, useState } from 'react';
import { Crosshair, ExternalLink, Mic, Minus, Plus, Send, Square, X } from 'lucide-react';
import { MarkdownRenderer } from '../MarkdownRenderer';
import type { CompanionRuntime } from './useCompanionRuntime';
import { STATUS_COLORS, STATUS_LABEL_KEYS } from './status';
import { startNativeDrag } from './windowControl';
import { useDictation } from './useDictation';
import { showMainWindow } from '../desktop';
import type { TranslationKey } from '../i18n';

interface Props {
  runtime: CompanionRuntime;
  language: string;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
  follow: boolean;
  onToggleFollow: () => void;
  onCollapse: () => void;
  onHide: () => void;
  notify: (message: string, kind: 'success' | 'error' | 'info' | 'warning') => void;
}

export function CompanionPanel({ runtime, language, t, follow, onToggleFollow, onCollapse, onHide, notify }: Props) {
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const { messages, approvals, tasks, problem, submitting, status } = runtime;
  const dictation = useDictation(language, setText, runtime.setListening);
  const color = STATUS_COLORS[status];

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, submitting, approvals.length]);

  // Auto-grow the input up to its CSS max-height.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [text]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCollapse();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCollapse]);

  const submit = (value?: string) => {
    const v = (value ?? text).trim();
    if (!v || submitting) return;
    if (dictation.supported) dictation.stop();
    setText('');
    runtime.send(v, language);
  };

  const problemText = (() => {
    if (!problem) return null;
    if (problem.kind === 'unreachable') return t('cmpRuntimeUnreachable');
    if (problem.kind === 'no_workspace') return t('cmpNoWorkspace');
    if (problem.message === 'NO_PROVIDER') return t('cmpNoProviderHint');
    return `${t('cmpRequestFailed')} ${problem.message}`;
  })();
  const problemIsProvider = problem?.kind === 'request' && problem.message === 'NO_PROVIDER';

  const dragFromHeader = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('button')) return;
    if (e.button === 0) startNativeDrag();
  };

  return (
    <div className="cmp-shell">
      <section className="cmp-panel" data-testid="companion-panel" data-status={status} style={{ ['--cmp-ring' as any]: color }} aria-label="Aether Companion">
        <header className="cmp-head" onMouseDown={dragFromHeader} title={t('cmpDragHint')}>
          <span className="cmp-dot" data-testid="companion-status-dot" data-busy={status === 'processing' || status === 'listening'} />
          <span className="cmp-title">Aether</span>
          <span className="cmp-status" data-testid="companion-status-label" role="status" aria-live="polite">{t(STATUS_LABEL_KEYS[status])}</span>
          <span className="cmp-spacer" />
          <button className="cmp-iconbtn" aria-pressed={follow} onClick={onToggleFollow} title={`${follow ? t('cmpFollowOn') : t('cmpFollowOff')} — ${t('cmpFollowHint')}`} data-testid="companion-follow-toggle">
            <Crosshair size={15} />
          </button>
          <button className="cmp-iconbtn" onClick={runtime.newConversation} title={t('cmpNewConversation')} data-testid="companion-new"><Plus size={16} /></button>
          <button className="cmp-iconbtn" onClick={() => showMainWindow()} title={t('cmpOpenWorkspace')} data-testid="companion-open-main"><ExternalLink size={15} /></button>
          <button className="cmp-iconbtn" onClick={onCollapse} title={t('cmpCollapse')} data-testid="companion-collapse"><Minus size={16} /></button>
          <button className="cmp-iconbtn" onClick={onHide} title={t('cmpHide')} data-testid="companion-hide"><X size={16} /></button>
        </header>

        <div className="cmp-body" ref={bodyRef} data-testid="companion-messages">
          {messages.length === 0 && !submitting && (
            <div className="cmp-empty">
              <h3>{t('cmpEmptyTitle')}</h3>
              <p>{t('cmpEmptyHint')}</p>
              <button className="cmp-chip" onClick={() => submit(t('cmpSuggestion1'))}>{t('cmpSuggestion1')}</button>
              <button className="cmp-chip" onClick={() => submit(t('cmpSuggestion2'))}>{t('cmpSuggestion2')}</button>
            </div>
          )}
          {messages.map(m => (
            <div key={m.id} className={`cmp-msg ${m.role}${m.errorCode ? ' error' : ''}`} data-testid={`companion-msg-${m.role}`}>
              {m.role === 'assistant' ? <MarkdownRenderer content={m.content} /> : m.content}
            </div>
          ))}
          {submitting && (
            <div className="cmp-thinking" data-testid="companion-thinking" aria-label={t('cmpThinking')}>
              <i /><i /><i />
            </div>
          )}
        </div>

        {approvals.length > 0 && (
          <div className="cmp-section" data-testid="companion-approvals">
            <h4>{t('cmpApprovalsTitle')}</h4>
            {approvals.slice(0, 3).map(a => {
              const id = (a.execution_id || a.id || '').trim();
              const busy = runtime.decidingId === id;
              return (
                <div className="cmp-card approval" key={id}>
                  <b>{a.title || a.action_name || t('cmpApprovalFallbackTitle')}</b>
                  {a.description && <div className="desc">{a.description}</div>}
                  <div className="cmp-row">
                    <button className="cmp-btn" disabled={busy} onClick={async () => { const r = await runtime.decide(a, 'reject', t('cmpRejectedReason')); notify(r.message, r.kind); }}>{t('cmpReject')}</button>
                    <button className="cmp-btn primary" disabled={busy} data-testid="companion-approve" onClick={async () => { const r = await runtime.decide(a, 'approve', ''); notify(r.message, r.kind); }}>{t('cmpApprove')}</button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {tasks.length > 0 && (
          <div className="cmp-section" data-testid="companion-tasks">
            <h4>{t('cmpRunningTitle')}</h4>
            {tasks.slice(0, 3).map(task => {
              const pct = task.progress_pct ?? task.progress_percent;
              return (
                <div className="cmp-card" key={task.id}>
                  <b>{task.title}</b>
                  {task.current_step && <div className="desc" style={{ margin: '3px 0 0' }}>{task.current_step}</div>}
                  {typeof pct === 'number' && <div className="cmp-bar"><i style={{ width: `${Math.max(2, Math.min(100, pct))}%` }} /></div>}
                </div>
              );
            })}
          </div>
        )}

        {problemText && (
          <div className="cmp-banner" role="alert" data-testid="companion-problem">
            <span>{problemText}</span>
            {problemIsProvider ? (
              <button className="cmp-btn" onClick={() => showMainWindow()}>{t('cmpOpenWorkspace')}</button>
            ) : problem?.kind === 'no_workspace' ? (
              <button className="cmp-btn" onClick={() => showMainWindow()}>{t('cmpOpenWorkspace')}</button>
            ) : (
              <button className="cmp-btn" onClick={() => runtime.retryLast(language)}>{t('cmpRetry')}</button>
            )}
          </div>
        )}

        <footer className="cmp-foot">
          <div className="cmp-input-wrap">
            <textarea
              ref={inputRef}
              className="cmp-input"
              data-testid="companion-input"
              rows={1}
              value={text}
              placeholder={t('cmpPlaceholder')}
              onChange={e => setText(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            {dictation.supported && (
              <button className="cmp-iconbtn" aria-pressed={status === 'listening'} onClick={() => (status === 'listening' ? dictation.stop() : dictation.start())} title={status === 'listening' ? t('cmpMicStop') : t('cmpMicStart')} data-testid="companion-mic">
                {status === 'listening' ? <Square size={14} /> : <Mic size={15} />}
              </button>
            )}
            <button className="cmp-send" data-testid="companion-send" disabled={!text.trim() || submitting} onClick={() => submit()} title={t('cmpSend')}>
              <Send size={15} />
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
