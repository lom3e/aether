import { useEffect, useRef, useState } from 'react';
import { Bell, Camera, ChevronDown, ChevronRight, Copy, ExternalLink, Eye, MoreHorizontal, Mic, Paperclip, Plus, Send, Square, X } from 'lucide-react';
import { AetherOrb } from '../orb/AetherOrb';
import { MarkdownRenderer } from '../MarkdownRenderer';
import { contextIsEmpty, type AttachedFile, type CompanionRuntime, type DesktopContext, type NotificationsSummary } from './useCompanionRuntime';
import { STATUS_COLORS, STATUS_LABEL_KEYS, orbStateFor } from './status';
import { onSummon, resizeNativePanel, startNativeDrag } from './windowControl';
import { takeSummonCapture } from './vision/captureBridge';
import { shieldCapture, type ShieldedImage } from './vision/shield';
import { useDictation } from './useDictation';
import { showMainWindow } from '../desktop';
import type { TranslationKey } from '../i18n';
import { ScreenAssist } from './vision/ScreenAssist';
import { AnnotatedImage } from './vision/AnnotatedImage';
import { Receipts } from './Receipts';
import { SecondOpinion } from './SecondOpinion';
import { speak, speakVoiceAnswersEnabled, stopSpeaking } from '../voiceOut';

interface Props {
  runtime: CompanionRuntime;
  language: string;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
  onHide: () => void;
  notify: (message: string, kind: 'success' | 'error' | 'info' | 'warning') => void;
}

export function CompanionPanel({ runtime, language, t, onHide, notify }: Props) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<AttachedFile[]>([]);
  const [context, setContext] = useState<DesktopContext | null>(null);
  const [notice, setNotice] = useState<{ kind: 'info' | 'warning'; text: string } | null>(null);
  const [notifications, setNotifications] = useState<NotificationsSummary | null>(null);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [visionOpen, setVisionOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  // What Aether saw when it was summoned: held in memory for the next message only, then dropped.
  const [sight, setSight] = useState<ShieldedImage | null>(null);
  const sightRef = useRef<ShieldedImage | null>(null);
  const textRef = useRef('');
  const [busyTool, setBusyTool] = useState<'context' | 'attach' | 'notifications' | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const { messages, approvals, tasks, missions, results, problem, submitting, status } = runtime;
  const dictation = useDictation(language, setText, runtime.setListening);
  const color = STATUS_COLORS[status];
  sightRef.current = sight;
  textRef.current = text;
  // Asked by voice → answered by voice: remember that the next answer belongs to a spoken question.
  const voiceTurnRef = useRef<{ after: number } | null>(null);
  useEffect(() => {
    const turn = voiceTurnRef.current;
    if (!turn || messages.length <= turn.after) return;
    const last = messages[messages.length - 1];
    if (last.role !== 'assistant' || !last.content) return;
    voiceTurnRef.current = null;
    if (speakVoiceAnswersEnabled()) speak(last.content, language);
  }, [messages, language]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // The Bar is as tall as its content (one input row when empty) up to the native maximum; overlays ask for more room.
  useEffect(() => {
    const el = panelRef.current;
    if (!el) return;
    let last = 0;
    const report = () => {
      let natural = 0;
      Array.from(el.children).forEach(c => {
        const h = c as HTMLElement;
        natural += h.classList.contains('cmp-body') ? h.scrollHeight : h.offsetHeight;
      });
      const wanted = Math.ceil(Math.max(natural, visionOpen ? 600 : 0, menuOpen ? 330 : 0, dragging ? 200 : 0));
      if (Math.abs(wanted - last) > 1) {
        last = wanted;
        resizeNativePanel(wanted);
      }
    };
    const ro = new ResizeObserver(report);
    ro.observe(el);
    Array.from(el.children).forEach(c => ro.observe(c));
    const mo = new MutationObserver(report);
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    report();
    return () => {
      ro.disconnect();
      mo.disconnect();
    };
  }, [visionOpen, menuOpen, dragging]);

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
        if (menuOpen) setMenuOpen(false);
        else onHide();
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
  }, [onHide, runtime, menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('.cmp-menu, [data-testid="companion-menu"]')) setMenuOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [menuOpen]);

  const submit = (value?: string) => {
    const v = (value ?? text).trim();
    if (!v || submitting) return;
    if (dictation.supported) dictation.stop();
    setText('');
    const seen = sightRef.current;
    if (!seen) {
      runtime.send(v, language);
      return;
    }
    setSight(null); // one-shot: the next message does not carry the old screen
    void (async () => {
      const vs = await runtime.fetchVisionStatus();
      // "ricordami di rispondere a questa", "segna questo": something to keep, not a question about the picture. The text the
      // local OCR read goes with the request, so Aether can name it ("Rispondere a Mario: preventivo") and ask to save it.
      const keep = /\b(ricord\w*|segna\w*|annota\w*|aggiung\w*|salva\w*|promemoria|remind\w*|save|note|add)\b/i.test(v);
      if (vs?.supported && !(keep && seen.text)) {
        await runtime.askAboutImage({ prompt: v, imageBase64: seen.base64, mediaType: seen.mediaType, displayUrl: seen.url, width: seen.width, height: seen.height, language, annotate: false });
      } else {
        // The model cannot see images: give it the text the local OCR read instead (it is masked like any outgoing text).
        runtime.send(v, language, seen.text ? `${t('cmpSightTextHeader')}\n${seen.text}` : undefined);
      }
    })();
  };
  const submitRef = useRef(submit);
  submitRef.current = submit;
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  // Hold the shortcut and talk: the native side read the screen first, then the Bar came up and told us.
  useEffect(() => {
    return onSummon(phase => {
      if (phase === 'press') {
        stopSpeaking(); // a new question interrupts the previous spoken answer
        setSight(null);
        takeSummonCapture().then(cap => (cap ? shieldCapture(cap) : null)).then(img => { if (img) setSight(img); });
        if (dictation.supported) dictation.start();
      } else if (phase === 'release') {
        if (dictation.supported) dictation.stop();
        window.setTimeout(() => {
          if (!textRef.current.trim()) return;
          voiceTurnRef.current = { after: messagesRef.current.length };
          submitRef.current(textRef.current);
        }, 450);
      } else if (phase === 'tap') {
        if (dictation.supported) dictation.stop();
        inputRef.current?.focus();
      } else if (phase === 'cancel') {
        if (dictation.supported) dictation.stop();
        setSight(null);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dictation.supported]);

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
        ref={panelRef}
        className="cmp-panel"
        data-testid="companion-panel"
        data-status={status}
        data-overlay={visionOpen ? 'true' : undefined}
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
          <span className="cmp-head-orb" data-testid="companion-panel-orb" data-status={status} aria-hidden>
            <AetherOrb state={orbStateFor(status)} size={30} quality="low" interactive={false} compact followVoice />
          </span>
          <span className="cmp-title">Aether</span>
          <span className="cmp-status" data-testid="companion-status-label" role="status" aria-live="polite">{t(STATUS_LABEL_KEYS[status])}</span>
          <span className="cmp-spacer" />
          <button className="cmp-iconbtn" onClick={() => setMenuOpen(o => !o)} aria-haspopup="menu" aria-expanded={menuOpen} aria-label={t('cmpMenu')} title={t('cmpMenu')} data-testid="companion-menu"><MoreHorizontal size={17} /></button>
          {menuOpen && (
            <div className="cmp-menu" role="menu" data-testid="companion-menu-list">
              <button role="menuitem" onClick={() => { setMenuOpen(false); doNotifications(); }} disabled={busyTool === 'notifications'} data-testid="companion-notifications"><Bell size={15} />{t('cmpNotifications')}</button>
              <button role="menuitem" onClick={() => { setMenuOpen(false); runtime.newConversation(); }} data-testid="companion-new"><Plus size={15} />{t('cmpNewConversation')}</button>
              <button role="menuitem" onClick={() => { setMenuOpen(false); showMainWindow(); }} data-testid="companion-open-main"><ExternalLink size={15} />{t('cmpOpenWorkspace')}</button>
              <hr />
              <button role="menuitem" onClick={() => { setMenuOpen(false); onHide(); }} data-testid="companion-hide"><X size={15} />{t('cmpHide')}</button>
            </div>
          )}
        </header>

        <div className="cmp-body" ref={bodyRef} data-testid="companion-messages">
          {messages.length === 0 && !submitting && (
            <div className="cmp-empty">
              <div className="cmp-empty-orb" aria-hidden="true">
                <AetherOrb state={orbStateFor(status)} size={112} quality="medium" interactive={false} compact />
              </div>
              <h3>{t('cmpEmptyTitle')}</h3>
              <button className="cmp-chip" onClick={() => submit(t('cmpSuggestion1'))}>{t('cmpSuggestion1')}</button>
              <button className="cmp-chip" onClick={() => submit(t('cmpSuggestion2'))}>{t('cmpSuggestion2')}</button>
              <button className="cmp-chip" onClick={doNotifications} data-testid="companion-chip-notifications">{t('cmpNotifications')}</button>
            </div>
          )}
          {messages.map((m, mi) => (
            <div key={m.id} className={`cmp-msg ${m.role}${m.errorCode ? ' error' : ''}`} data-testid={`companion-msg-${m.role}`}>
              {m.vision && (
                <div className="cmp-msg-vision" data-testid="companion-msg-vision">
                  <AnnotatedImage imageUrl={m.vision.imageUrl} alt={t('cmpVisionImageAlt')} shapes={m.vision.shapes} width={m.vision.width} height={m.vision.height} testId="companion-msg-image" />
                  {m.vision.shapes.some(s => s.source === 'model') && <div className="cmp-vision-hint" data-testid="companion-model-marks">{t('cmpVisionModelMarks')}</div>}
                </div>
              )}
              {m.role === 'assistant' ? <MarkdownRenderer content={m.content} /> : m.content}
              {m.role === 'assistant' && !m.errorCode && <Receipts message={m} t={t} notify={notify} />}
              {m.role === 'assistant' && !m.errorCode && !m.vision && <SecondOpinion question={[...messages.slice(0, mi)].reverse().find(x => x.role === 'user')?.content || ''} language={language} t={t} />}
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

        {sight && (
          <div className="cmp-sight" data-testid="companion-sight" data-state={sight.ran ? (sight.hidden ? 'hidden' : 'clean') : 'unchecked'}>
            <Eye size={13} aria-hidden="true" />
            <span>{!sight.ran ? t('cmpSightUnchecked') : sight.hidden > 0 ? t('cmpSightHidden', { count: sight.hidden }) : t('cmpSightSeeing')}</span>
            <button className="cmp-link" onClick={() => setSight(null)} data-testid="companion-sight-drop">{t('cmpSightDrop')}</button>
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
