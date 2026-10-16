import { useEffect, useRef, useState } from 'react';
import { Bell, Camera, ChevronDown, ChevronRight, Copy, Crosshair, ExternalLink, Eye, Mic, Minus, Paperclip, Plus, Send, Square, X } from 'lucide-react';
import { MarkdownRenderer } from '../MarkdownRenderer';
import { contextIsEmpty, type AttachedFile, type CompanionRuntime, type DesktopContext, type NotificationsSummary } from './useCompanionRuntime';
import { STATUS_COLORS, STATUS_LABEL_KEYS } from './status';
import { startNativeDrag } from './windowControl';
import { useDictation } from './useDictation';
import { showMainWindow } from '../desktop';
import type { TranslationKey } from '../i18n';
import { ScreenAssist } from './vision/ScreenAssist';
import { AnnotatedImage } from './vision/AnnotatedImage';

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
  const [attachments, setAttachments] = useState<AttachedFile[]>([]);
  const [context, setContext] = useState<DesktopContext | null>(null);
  const [notice, setNotice] = useState<{ kind: 'info' | 'warning'; text: string } | null>(null);
  const [notifications, setNotifications] = useState<NotificationsSummary | null>(null);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [visionOpen, setVisionOpen] = useState(false);
  const [busyTool, setBusyTool] = useState<'context' | 'attach' | 'notifications' | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const { messages, approvals, tasks, missions, results, problem, submitting, status } = runtime;
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
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'o') {
        e.preventDefault();
        showMainWindow();
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        runtime.newConversation();
        setText('');
        setAttachments([]);
        setContext(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCollapse, runtime]);

  const submit = (value?: string) => {
    const v = (value ?? text).trim();
    if (!v || submitting) return;
    if (dictation.supported) dictation.stop();
    setText('');
    runtime.send(v, language);
  };

  const addToInput = (snippet: string) => setText(prev => (prev ? `${prev}\n\n${snippet}` : snippet));

  const doCaptureContext = async () => {
    setBusyTool('context');
    setNotice(null);
    const c = await runtime.captureContext();
    setBusyTool(null);
    if (!c || contextIsEmpty(c)) {
      setContext(null);
      setNotice({ kind: 'warning', text: t('cmpContextUnavailable') });
      return;
    }
    setContext(c);
  };

  const doAttach = async (files: FileList | File[]) => {
    const list = Array.from(files).slice(0, 3);
    if (list.length === 0) return;
    setBusyTool('attach');
    setNotice(null);
    for (const f of list) {
      try {
        const a = await runtime.attachFile(f);
        setAttachments(prev => [...prev, a]);
        setText(prev => (prev.trim() ? prev : t('cmpReviewFile', { name: a.filename })));
      } catch (e: any) {
        const code = String(e?.message || e);
        setNotice({ kind: 'warning', text: code === 'too_large' ? t('cmpFileTooLarge', { name: f.name }) : t('cmpFileFailed', { name: f.name }) });
      }
    }
    setBusyTool(null);
    inputRef.current?.focus();
  };

  const doNotifications = async () => {
    setBusyTool('notifications');
    setNotice(null);
    const n = await runtime.checkNotifications();
    setBusyTool(null);
    if (!n) {
      setNotice({ kind: 'warning', text: t('cmpNotificationsFailed') });
      return;
    }
    setNotifications(n);
  };

  const copyPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path);
      notify(t('cmpPathCopied'), 'info');
    } catch {
      notify(path, 'info');
    }
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
      <section
        className="cmp-panel"
        data-testid="companion-panel"
        data-status={status}
        style={{ ['--cmp-ring' as any]: color }}
        aria-label="Aether Companion"
        onDragOver={e => {
          if (Array.from(e.dataTransfer?.types || []).includes('Files')) {
            e.preventDefault();
            setDragging(true);
          }
        }}
        onDragLeave={e => {
          if (e.currentTarget === e.target) setDragging(false);
        }}
        onDrop={e => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer?.files?.length) doAttach(e.dataTransfer.files);
        }}
      >
        {dragging && <div className="cmp-drop" data-testid="companion-drop-overlay">{t('cmpDropHere')}</div>}
        <header className="cmp-head" onMouseDown={dragFromHeader} title={t('cmpDragHint')}>
          <span className="cmp-dot" data-testid="companion-status-dot" data-busy={status === 'processing' || status === 'listening'} />
          <span className="cmp-title">Aether</span>
          <span className="cmp-status" data-testid="companion-status-label" role="status" aria-live="polite">{t(STATUS_LABEL_KEYS[status])}</span>
          <span className="cmp-spacer" />
          <button className="cmp-iconbtn" onClick={doNotifications} disabled={busyTool === 'notifications'} title={t('cmpNotifications')} data-testid="companion-notifications"><Bell size={15} /></button>
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
              <button className="cmp-chip" onClick={doNotifications} data-testid="companion-chip-notifications">{t('cmpNotifications')}</button>
            </div>
          )}
          {messages.map(m => (
            <div key={m.id} className={`cmp-msg ${m.role}${m.errorCode ? ' error' : ''}`} data-testid={`companion-msg-${m.role}`}>
              {m.vision && (
                <div className="cmp-msg-vision" data-testid="companion-msg-vision">
                  <AnnotatedImage imageUrl={m.vision.imageUrl} alt={t('cmpVisionImageAlt')} shapes={m.vision.shapes} width={m.vision.width} height={m.vision.height} testId="companion-msg-image" />
                  {m.vision.shapes.some(s => s.source === 'model') && <div className="cmp-vision-hint" data-testid="companion-model-marks">{t('cmpVisionModelMarks')}</div>}
                </div>
              )}
              {m.role === 'assistant' ? <MarkdownRenderer content={m.content} /> : m.content}
              {m.proposal && (
                <div className="cmp-proposal" data-testid="companion-proposal">
                  <b>{t('cmpProposalTitle')}</b>
                  {m.proposal.title && <div className="desc">{m.proposal.title}</div>}
                  <button className="cmp-btn" onClick={() => showMainWindow()}>{t('cmpReviewInAether')}</button>
                </div>
              )}
            </div>
          ))}
          {submitting && (
            <div className="cmp-thinking" data-testid="companion-thinking" aria-label={t('cmpThinking')}>
              <i /><i /><i />
            </div>
          )}
        </div>

        <div className="cmp-activity" data-testid="companion-activity">
        {approvals.length > 0 && (
          <div className="cmp-section" data-testid="companion-approvals">
            <h4>{t('cmpApprovalsTitle')}</h4>
            {approvals.slice(0, 3).map(a => {
              const id = (a.execution_id || a.id || '').trim();
              const busy = runtime.decidingId === id;
              return (
                <div className="cmp-card approval" key={id}>
                  <b>{a.human_summary || a.title || a.action_name || t('cmpApprovalFallbackTitle')}</b>
                  {!a.human_summary && a.description && <div className="desc">{a.description}</div>}
                  <div className="cmp-row">
                    <button className="cmp-btn" disabled={busy} onClick={async () => { const r = await runtime.decide(a, 'reject', t('cmpRejectedReason')); notify(r.message, r.kind); }}>{t('cmpReject')}</button>
                    <button className="cmp-btn primary" disabled={busy} data-testid="companion-approve" onClick={async () => { const r = await runtime.decide(a, 'approve', ''); notify(r.message, r.kind); }}>{t('cmpApprove')}</button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {(tasks.length > 0 || missions.length > 0) && (
          <div className="cmp-section" data-testid="companion-tasks">
            <h4>{t('cmpRunningTitle')}</h4>
            {missions.slice(0, 2).map(m => (
              <div className="cmp-card" key={`m-${m.id}`} data-testid="companion-mission">
                <b>{m.title}</b>
                <div className="desc" style={{ margin: '3px 0 0' }}>{[m.status, m.current_stage].filter(Boolean).join(' · ')}</div>
                {typeof m.progress === 'number' && m.progress > 0 && <div className="cmp-bar"><i style={{ width: `${Math.max(2, Math.min(100, m.progress))}%` }} /></div>}
              </div>
            ))}
            {tasks.slice(0, 2).map(task => {
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

        {results.length > 0 && (
          <div className="cmp-section" data-testid="companion-results">
            <button className="cmp-fold" onClick={() => setResultsOpen(o => !o)} aria-expanded={resultsOpen} data-testid="companion-results-toggle">
              {resultsOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              <h4>{t('cmpResultsTitle', { count: results.length })}</h4>
            </button>
            {resultsOpen && results.slice(0, 4).map(r => (
              <div className="cmp-card" key={r.id || r.file_path} data-testid="companion-result">
                <b>{r.title}</b>
                <div className="desc" style={{ margin: '3px 0 6px' }}>{[r.source, r.file_size_bytes > 0 ? `${Math.max(1, Math.round(r.file_size_bytes / 1024))} KB` : ''].filter(Boolean).join(' · ')}</div>
                <div className="cmp-row">
                  <button className="cmp-btn" onClick={() => copyPath(r.file_path)}><Copy size={12} style={{ verticalAlign: '-2px' }} /> {t('cmpCopyPath')}</button>
                  <button className="cmp-btn" onClick={() => showMainWindow()}>{t('cmpOpenWorkspace')}</button>
                </div>
              </div>
            ))}
          </div>
        )}

        {notifications && (
          <div className="cmp-section" data-testid="companion-notifications-card">
            <div className="cmp-row" style={{ alignItems: 'center' }}>
              <h4 style={{ flex: 1 }}>{notifications.unread > 0 ? t('cmpNotificationsUnread', { count: notifications.unread }) : t('cmpNotificationsNone')}</h4>
              <button className="cmp-iconbtn" onClick={() => setNotifications(null)} aria-label="close"><X size={14} /></button>
            </div>
            {notifications.items.slice(0, 3).map(n => (
              <div className="cmp-card" key={n.id}><b>{n.title}</b>{n.message && <div className="desc" style={{ margin: '3px 0 0' }}>{n.message}</div>}</div>
            ))}
          </div>
        )}
        </div>

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

        {(attachments.length > 0 || context || notice) && (
          <div className="cmp-chips" data-testid="companion-chips">
            {notice && <div className={`cmp-notice ${notice.kind}`} role="status" data-testid="companion-notice">{notice.text}<button className="cmp-iconbtn" onClick={() => setNotice(null)} aria-label="close"><X size={13} /></button></div>}
            {attachments.map((a, i) => (
              <div className="cmp-chip-file" key={`${a.filename}-${i}`} data-testid="companion-attachment" title={a.path}>
                <Paperclip size={12} /> <span>{a.filename}</span> <em>{Math.max(1, Math.round(a.size / 1024))} KB</em>
                <button className="cmp-iconbtn" onClick={() => setAttachments(prev => prev.filter((_, j) => j !== i))} aria-label="remove"><X size={12} /></button>
              </div>
            ))}
            {context && (
              <div className="cmp-card" data-testid="companion-context">
                <b>{context.app_name}{context.window_title ? ` — ${context.window_title}` : ''}</b>
                {/aether/i.test(context.app_name) && <div className="desc" style={{ margin: '3px 0 0' }}>{t('cmpContextIsAether')}</div>}
                {context.clipboard_text && <div className="desc" style={{ margin: '3px 0 6px', whiteSpace: 'pre-wrap' }}>{context.clipboard_text.slice(0, 160)}{context.clipboard_text.length > 160 ? '…' : ''}</div>}
                <div className="cmp-row">
                  <button className="cmp-btn primary" data-testid="companion-context-add" onClick={() => { addToInput(`Context [${context.app_name}${context.window_title ? ` - ${context.window_title}` : ''}]:\n${context.clipboard_text || ''}`.trim()); setContext(null); inputRef.current?.focus(); }}>{t('cmpAddToMessage')}</button>
                  <button className="cmp-btn" onClick={() => setContext(null)}>{t('cmpDismiss')}</button>
                </div>
              </div>
            )}
          </div>
        )}

        {visionOpen && <ScreenAssist runtime={runtime} language={language} t={t} onClose={() => { setVisionOpen(false); inputRef.current?.focus(); }} notify={notify} />}
        <footer className="cmp-foot">
          <input ref={fileRef} type="file" multiple hidden data-testid="companion-file-input" onChange={e => { if (e.target.files) doAttach(e.target.files); e.target.value = ''; }} />
          <div className="cmp-input-wrap">
            <button className="cmp-iconbtn" onClick={() => fileRef.current?.click()} disabled={busyTool === 'attach'} title={t('cmpAttach')} data-testid="companion-attach"><Paperclip size={15} /></button>
            <button className="cmp-iconbtn" onClick={() => setVisionOpen(true)} disabled={submitting} title={t('cmpVisionOpen')} data-testid="companion-vision-open"><Camera size={15} /></button>
            <button className="cmp-iconbtn" onClick={doCaptureContext} disabled={busyTool === 'context'} title={t('cmpCaptureContext')} data-testid="companion-capture-context"><Eye size={15} /></button>
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
