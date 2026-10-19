/**
 * The "look at my screen" flow, one explicit step at a time:
 *   choose (what to capture) -> capturing (native, the Companion hides) -> review (preview + marks + question)
 *   -> sending -> back to the conversation (the answer is a normal message of the shared session).
 * Nothing is captured before the user presses a capture button and nothing is sent before they press Send. The image
 * exists only in this component's state: closing it discards it.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Camera, Crop, Monitor, Square, ArrowUpRight, Highlighter, EyeOff, Undo2, X } from 'lucide-react';
import type { CompanionRuntime, VisionStatus } from '../useCompanionRuntime';
import type { TranslationKey } from '../../i18n';
import { showMainWindow } from '../../desktop';
import {
  getCaptureStatus, openCaptureSettings, requestCapturePermission, takeCapture,
  type CaptureMode, type CaptureResult, type CaptureStatus,
} from './captureBridge';
import { flattenToDataUrl, stripDataUrl, type Shape, type Tool } from './annotations';
import { AnnotationEditor } from './AnnotatedImage';

type T = (key: TranslationKey, params?: Record<string, string | number>) => string;
type Phase = 'choose' | 'capturing' | 'review' | 'sending' | 'error';

interface Captured {
  url: string;
  base64: string;
  mediaType: string;
  width: number;
  height: number;
}

interface Props {
  runtime: CompanionRuntime;
  language: string;
  t: T;
  onClose: () => void;
  notify: (message: string, kind: 'success' | 'error' | 'info' | 'warning') => void;
}

export function visionUnavailableKey(reason: string): TranslationKey {
  switch (reason) {
    case 'no_provider': return 'cmpVisionNoProvider';
    case 'provider_unusable': return 'cmpVisionProviderBroken';
    case 'no_model': return 'cmpVisionNoModel';
    default: return 'cmpVisionNoVision';
  }
}

export function visionFailureKey(reason: string): TranslationKey {
  switch (reason) {
    case 'timeout': return 'cmpVisionErrTimeout';
    case 'auth': return 'cmpVisionErrAuth';
    case 'rate_limit': return 'cmpVisionErrRate';
    case 'connection': return 'cmpVisionErrConnection';
    case 'model_not_found': return 'cmpVisionErrModel';
    case 'empty_response': return 'cmpVisionErrEmpty';
    default: return 'cmpVisionErrGeneric';
  }
}

const TOOLS: { id: Tool; icon: typeof Square; key: TranslationKey }[] = [
  { id: 'box', icon: Square, key: 'cmpVisionToolBox' },
  { id: 'highlight', icon: Highlighter, key: 'cmpVisionToolHighlight' },
  { id: 'arrow', icon: ArrowUpRight, key: 'cmpVisionToolArrow' },
  { id: 'blur', icon: EyeOff, key: 'cmpVisionToolBlur' },
];

export function ScreenAssist({ runtime, language, t, onClose, notify }: Props) {
  const [phase, setPhase] = useState<Phase>('choose');
  const [capture, setCapture] = useState<CaptureStatus | null>(null);
  const [vision, setVision] = useState<VisionStatus | null>(null);
  const [visionChecked, setVisionChecked] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [permissionHelp, setPermissionHelp] = useState(false);
  const [image, setImage] = useState<Captured | null>(null);
  const [tool, setTool] = useState<Tool>('box');
  const [marks, setMarks] = useState<Shape[]>([]);
  const [prompt, setPrompt] = useState('');
  const [annotate, setAnnotate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remembering, setRemembering] = useState(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const refreshStatus = useCallback(async () => {
    const [c, v] = await Promise.all([getCaptureStatus(), runtime.fetchVisionStatus()]);
    if (!alive.current) return;
    setCapture(c);
    setVision(v);
    setVisionChecked(true);
    if (c.permission === 'granted') setPermissionHelp(false);
  }, [runtime]);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && phase !== 'sending' && phase !== 'capturing') {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [phase, onClose]);

  const canAnalyse = !!vision?.supported;
  const platformOk = !!capture?.supported;
  const permission = capture?.permission;

  const startCapture = async (mode: CaptureMode) => {
    setNote(null);
    setError(null);
    let perm = permission;
    if (perm === 'denied') {
      // The system prompt only appears the first time; afterwards the user has to enable it in System Settings.
      const after = await requestCapturePermission();
      if (!alive.current) return;
      setCapture(after);
      perm = after.permission;
      if (perm !== 'granted') {
        setPermissionHelp(true);
        return;
      }
    }
    setPhase('capturing');
    const r: CaptureResult = await takeCapture(mode);
    if (!alive.current) return;
    if (r.ok) {
      setImage({ url: `data:${r.mediaType};base64,${r.imageBase64}`, base64: r.imageBase64, mediaType: r.mediaType, width: r.width, height: r.height });
      setMarks([]);
      setPhase('review');
      return;
    }
    setPhase('choose');
    if (r.error === 'permission_denied') {
      setCapture(c => (c ? { ...c, permission: 'denied' } : c));
      setPermissionHelp(true);
    } else if (r.error === 'cancelled') {
      setNote(t('cmpVisionCancelled'));
    } else if (r.error === 'too_large') {
      setNote(t('cmpVisionTooLarge'));
    } else if (r.error === 'unsupported') {
      setCapture({ platform: 'other', supported: false, permission: 'unsupported' });
    } else {
      setNote(t('cmpVisionCaptureFailed', { detail: r.detail }));
    }
  };

  const remember = async (ttlDays: 7 | 30) => {
    if (!image || remembering) return;
    setRemembering(true);
    let b64 = image.base64;
    let mediaType = image.mediaType;
    try {
      if (marks.length > 0) {
        b64 = stripDataUrl(await flattenToDataUrl(image.url, marks));
        mediaType = 'image/png';
      }
      const r = await runtime.rememberImage({ imageBase64: b64, mediaType, ttlDays, language });
      if (!alive.current) return;
      if (r === 'ok') {
        notify(t('cmpRememberDone', { days: ttlDays }), 'success');
        onClose();
      } else {
        notify(t(r === 'unavailable' ? 'cmpRememberUnavailable' : 'cmpRememberFailed'), 'error');
      }
    } catch {
      if (alive.current) notify(t('cmpRememberFailed'), 'error');
    } finally {
      if (alive.current) setRemembering(false);
    }
  };

  const send = async () => {
    if (!image) return;
    setPhase('sending');
    setError(null);
    let url = image.url;
    let b64 = image.base64;
    let mediaType = image.mediaType;
    if (marks.length > 0) {
      try {
        url = await flattenToDataUrl(image.url, marks);
        b64 = stripDataUrl(url);
        mediaType = 'image/png';
      } catch {
        // Never send the image without the marks the user thinks they are sending.
        if (alive.current) {
          setError(t('cmpVisionErrGeneric'));
          setPhase('error');
        }
        return;
      }
    }
    const question = prompt.trim() || t('cmpVisionDefaultQuestion');
    const r = await runtime.askAboutImage({ prompt: question, imageBase64: b64, mediaType, displayUrl: url, width: image.width, height: image.height, language, annotate });
    if (!alive.current) return;
    if (r.status === 'ok') {
      if (annotate && r.shapes.length === 0) notify(t('cmpVisionNoMarks'), 'info');
      else if (r.rejected > 0) notify(t('cmpVisionMarksRejected', { count: r.rejected }), 'info');
      onClose();
      return;
    }
    if (r.status === 'unavailable') {
      setVision(v => ({ supported: false, reason: r.reason, provider: r.provider || v?.provider || '', model: r.model || v?.model || '' }));
      setError(t(visionUnavailableKey(r.reason), { model: r.model }));
    } else if (r.status === 'invalid_image') {
      setError(t('cmpVisionErrInvalid', { reason: r.reason }));
    } else if (r.status === 'unreachable') {
      setError(t('cmpRuntimeUnreachable'));
    } else if (r.status === 'no_workspace') {
      setError(t('cmpNoWorkspace'));
    } else {
      setError(`${t(visionFailureKey(r.reason))}${r.detail && r.reason === 'provider_error' ? ` ${r.detail}` : ''}`);
    }
    setPhase('error');
  };

  const sentTo = vision?.provider ? `${vision.provider}${vision.model ? ` · ${vision.model}` : ''}` : '';

  return (
    <div className="cmp-vision" data-testid="companion-vision" role="dialog" aria-label={t('cmpVisionTitle')}>
      <header className="cmp-vision-head">
        <Camera size={15} />
        <b>{t('cmpVisionTitle')}</b>
        <span className="cmp-spacer" />
        <button className="cmp-iconbtn" onClick={onClose} disabled={phase === 'sending' || phase === 'capturing'} aria-label={t('cmpVisionDiscard')} data-testid="vision-close"><X size={16} /></button>
      </header>

      <div className="cmp-vision-body">
        {phase === 'choose' && (
          <>
            <p className="cmp-vision-intro">{t('cmpVisionIntro')}</p>
            {note && <div className="cmp-notice" role="status" data-testid="vision-note">{note}</div>}
            {visionChecked && !canAnalyse && (
              <div className="cmp-card warn" data-testid="vision-unavailable">
                <p>{t(visionUnavailableKey(vision?.reason || 'no_provider'), { model: vision?.model || '' })}</p>
                <div className="cmp-row">
                  <button className="cmp-btn" onClick={() => showMainWindow()}>{t('cmpOpenWorkspace')}</button>
                  <button className="cmp-btn" onClick={refreshStatus} data-testid="vision-recheck">{t('cmpVisionRecheck')}</button>
                </div>
              </div>
            )}
            {capture && !platformOk && <div className="cmp-card warn" data-testid="vision-platform"><p>{t('cmpVisionUnsupportedPlatform')}</p></div>}
            {(permissionHelp || permission === 'denied') && platformOk && (
              <div className="cmp-card warn" data-testid="vision-permission">
                <b>{t('cmpVisionPermTitle')}</b>
                <p>{t('cmpVisionPermBody')}</p>
                <div className="cmp-row">
                  <button className="cmp-btn" onClick={async () => { const s = await requestCapturePermission(); setCapture(s); if (s.permission !== 'granted') setPermissionHelp(true); }} data-testid="vision-request-permission">{t('cmpVisionAskPerm')}</button>
                  <button className="cmp-btn primary" onClick={() => openCaptureSettings()} data-testid="vision-open-settings">{t('cmpVisionOpenSettings')}</button>
                </div>
                <button className="cmp-btn" style={{ marginTop: 8, width: '100%' }} onClick={refreshStatus}>{t('cmpVisionRecheck')}</button>
              </div>
            )}
            <button className="cmp-choice" disabled={!canAnalyse || !platformOk} onClick={() => startCapture('screen')} data-testid="vision-capture-screen">
              <Monitor size={18} /> <span><b>{t('cmpVisionScreen')}</b><em>{t('cmpVisionScreenHint')}</em></span>
            </button>
            <button className="cmp-choice" disabled={!canAnalyse || !platformOk} onClick={() => startCapture('region')} data-testid="vision-capture-region">
              <Crop size={18} /> <span><b>{t('cmpVisionRegion')}</b><em>{t('cmpVisionRegionHint')}</em></span>
            </button>
          </>
        )}

        {phase === 'capturing' && <div className="cmp-vision-wait" data-testid="vision-capturing">{t('cmpVisionCapturing')}</div>}

        {(phase === 'review' || phase === 'sending' || phase === 'error') && image && (
          <>
            <h4 className="cmp-vision-sub">{t('cmpVisionPreviewTitle')}</h4>
            <AnnotationEditor imageUrl={image.url} alt={t('cmpVisionImageAlt')} width={image.width} height={image.height} tool={tool} shapes={marks} onAdd={s => setMarks(m => [...m, s])} />
            <div className="cmp-tools" role="toolbar" aria-label={t('cmpVisionMarksHint')}>
              {TOOLS.map(({ id, icon: Icon, key }) => (
                <button key={id} className="cmp-iconbtn" aria-pressed={tool === id} title={t(key)} onClick={() => setTool(id)} data-testid={`vision-tool-${id}`}><Icon size={15} /></button>
              ))}
              <button className="cmp-iconbtn" title={t('cmpVisionUndo')} disabled={marks.length === 0} onClick={() => setMarks(m => m.slice(0, -1))} data-testid="vision-undo"><Undo2 size={15} /></button>
              <button className="cmp-btn tiny" disabled={marks.length === 0} onClick={() => setMarks([])} data-testid="vision-clear">{t('cmpVisionClear')}</button>
              <span className="cmp-spacer" />
              <span className="cmp-vision-count" data-testid="vision-mark-count">{marks.length > 0 ? t('cmpVisionMarkCount', { count: marks.length }) : ''}</span>
            </div>
            <p className="cmp-vision-hint">{t('cmpVisionMarksHint')}</p>
            <textarea className="cmp-vision-prompt" data-testid="vision-prompt" rows={2} value={prompt} placeholder={t('cmpVisionPromptPlaceholder')} onChange={e => setPrompt(e.target.value)} disabled={phase === 'sending'} />
            <label className="cmp-vision-check">
              <input type="checkbox" checked={annotate} onChange={e => setAnnotate(e.target.checked)} disabled={phase === 'sending'} data-testid="vision-annotate" />
              <span>{t('cmpVisionAnnotate')}</span>
            </label>
            <div className="cmp-vision-remember" data-testid="vision-remember">
              <span>{t('cmpRememberLabel')}</span>
              {([7, 30] as const).map(d => (
                <button key={d} className="cmp-btn tiny" onClick={() => remember(d)} disabled={phase === 'sending' || remembering || !canAnalyse} data-testid={`vision-remember-${d}`}>{t('cmpRememberDays', { days: d })}</button>
              ))}
            </div>
            {sentTo && <p className="cmp-vision-hint" data-testid="vision-sent-to">{t('cmpVisionSentTo', { target: sentTo })}</p>}
            {phase === 'error' && error && <div className="cmp-banner" role="alert" data-testid="vision-error"><span>{error}</span></div>}
          </>
        )}
      </div>

      {(phase === 'review' || phase === 'sending' || phase === 'error') && (
        <footer className="cmp-vision-foot">
          <button className="cmp-btn" onClick={onClose} disabled={phase === 'sending'} data-testid="vision-discard">{t('cmpVisionDiscard')}</button>
          <button className="cmp-btn" onClick={() => { setImage(null); setMarks([]); setPhase('choose'); refreshStatus(); }} disabled={phase === 'sending'} data-testid="vision-retake">{t('cmpVisionRetake')}</button>
          <button className="cmp-btn primary" onClick={send} disabled={phase === 'sending' || !canAnalyse} data-testid="vision-send">{phase === 'sending' ? t('cmpVisionSending') : t('cmpVisionSend')}</button>
        </footer>
      )}
    </div>
  );
}
