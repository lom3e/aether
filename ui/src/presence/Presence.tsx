import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AlarmClock, BookOpen, CalendarDays, Check, Copy, HandHeart, History, Loader2, MessageSquareText, ShieldAlert, Timer, Undo2, Volume2, VolumeX } from 'lucide-react';
import { AetherOrb } from '../orb/AetherOrb';
import type { OrbState } from '../orb/OrbEngine';
import { MarkdownRenderer } from '../MarkdownRenderer';
import { FirstRunModel } from '../FirstRunModel';
import { fmtTime, fmtWhen, lifeApi, type TodayData } from '../lifeApi';
import type { TranslationKey } from '../i18n';
import './presence.css';

type T = (key: TranslationKey, params?: Record<string, string | number>) => string;

export interface PresenceMsg { id: string; role: string; content: string; metadata?: Record<string, any>; created_at: string }

/**
 * Aether as a presence, not a chat window: the orb in the middle of the screen breathes, listens, thinks and speaks;
 * what it says runs under it as a subtitle; a confirmation, an Undo or a list appears right below; the day sits around
 * it (next appointment, what is overdue, what waits for you). The whole conversation is one click away (transcript).
 */
export function Presence({
  t, language, messages, busy, listening, transcribing, speaking, input, composer, actions, undoState, needsYou,
  onUndo, onSpeak, onOpenTranscript, onOpenRewind, onOpenPromises, onAsk, notifications, brief, briefBusy, onBriefAnswer, welcome,
  focus, onFocusStart, onFocusStop,
}: {
  t: T; language: string; messages: PresenceMsg[]; busy: boolean; listening: boolean; transcribing?: boolean; speaking: boolean; input: string;
  composer: ReactNode; actions?: ReactNode; undoState?: 'idle' | 'busy' | 'done'; needsYou: boolean;
  onUndo?: () => void; onSpeak: () => void; onOpenTranscript: () => void; onOpenRewind: () => void; onOpenPromises: () => void; onAsk: (prompt: string) => void;
  notifications: ReactNode;
  brief?: { body: string; offer: { type: string } | null } | null; briefBusy?: boolean; onBriefAnswer?: (answer: 'yes' | 'no') => void;
  welcome?: ReactNode;
  /** Concentrazione: on while `focus` is set (seconds left and how far along), started and ended from here or by voice */
  focus?: { remaining: number; progress: number } | null; onFocusStart?: (minutes: number) => void; onFocusStop?: () => void;
}) {
  const [focusMenu, setFocusMenu] = useState(false);
  const [today, setToday] = useState<TodayData | null>(null);
  const [copied, setCopied] = useState(false);
  const [justDone, setJustDone] = useState(false);
  // the orb leaves room for what it says: smaller on narrow or short windows
  const sizeFor = () => Math.max(170, Math.min(window.innerWidth < 640 ? 240 : 340, Math.round(window.innerHeight * 0.36)));
  const [orbSize, setOrbSize] = useState(sizeFor);

  // the stage is dark: the sidebar follows it while the presence is on screen
  useEffect(() => {
    document.documentElement.dataset.stage = 'presence';
    const resize = () => setOrbSize(sizeFor());
    window.addEventListener('resize', resize);
    return () => { delete document.documentElement.dataset.stage; window.removeEventListener('resize', resize); };
  }, []);

  useEffect(() => {
    let alive = true;
    const load = () => lifeApi.today(language).then(d => { if (alive) setToday(d); }).catch(() => undefined);
    void load();
    const timer = window.setInterval(load, 5 * 60 * 1000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [language, messages.length]);

  const lastUser = [...messages].reverse().find(m => m.role === 'user');
  const lastAi = [...messages].reverse().find(m => m.role === 'assistant');
  const answerIsCurrent = !!lastAi && (!lastUser || lastAi.created_at >= lastUser.created_at);

  // a finished turn flashes "done" for a moment, then the orb rests again
  useEffect(() => {
    if (busy || !answerIsCurrent) return;
    setJustDone(true);
    const id = window.setTimeout(() => setJustDone(false), 1600);
    return () => window.clearTimeout(id);
  }, [busy, answerIsCurrent, lastAi?.id]);

  // close the focus menu with Escape or a click elsewhere
  useEffect(() => {
    if (!focusMenu) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent && e.key !== 'Escape') return;
      if (e instanceof MouseEvent && (e.target as HTMLElement)?.closest?.('.pr-focus-menu, [data-testid="presence-focus"]')) return;
      setFocusMenu(false);
    };
    window.addEventListener('keydown', close);
    window.addEventListener('mousedown', close);
    return () => { window.removeEventListener('keydown', close); window.removeEventListener('mousedown', close); };
  }, [focusMenu]);

  const orbState: OrbState = listening ? 'listening' : busy ? 'working' : speaking ? 'speaking' : needsYou ? 'needs-you' : justDone ? 'done' : 'idle';

  const greeting = useMemo(() => {
    const h = new Date().getHours();
    return t(h < 5 ? 'prGreetEvening' : h < 13 ? 'prGreetMorning' : h < 18 ? 'prGreetAfternoon' : 'prGreetEvening');
  }, [t]);

  const nextEvent = today?.events?.find(e => e.all_day || e.start * 1000 >= Date.now() - 15 * 60 * 1000);
  const overdue = [...(today?.jobs?.overdue || []), ...(today?.reminders?.overdue || [])];
  const dueToday = [...(today?.jobs?.today || []), ...(today?.reminders?.today || [])];
  const waiting = today?.pending_approvals || 0;
  // nothing for today: the next thing in the coming days, so the home always says what comes next
  const next = overdue.length || dueToday.length ? null : [...(today?.jobs?.upcoming || []), ...(today?.reminders?.upcoming || [])]
    .filter(x => x.due_at).sort((a, b) => (a.due_at || 0) - (b.due_at || 0))[0];

  const copy = async () => {
    if (!lastAi) return;
    try { await navigator.clipboard.writeText(lastAi.content); setCopied(true); window.setTimeout(() => setCopied(false), 1400); } catch { /* not available */ }
  };

  let caption: ReactNode;
  if (welcome) caption = welcome;
  else if (listening) caption = <p className="pr-live" aria-live="polite">{input || (transcribing ? t('voTranscribing') : t('prListening'))}</p>;
  else if (busy) caption = <><p className="pr-said">«{lastUser?.content}»</p><p className="pr-thinking" aria-live="polite">{t('prThinking')}</p></>;
  else if (brief) caption = (
    <div className="pr-brief" data-testid="presence-brief">
      <h1 className="pr-greeting">{greeting}</h1>
      <p className="pr-brief-text" aria-live="polite">{brief.body}</p>
      {brief.offer && onBriefAnswer && (
        <div className="pr-brief-actions">
          <button type="button" className="pr-undo" disabled={briefBusy} onClick={() => onBriefAnswer('yes')} data-testid="brief-yes">
            {briefBusy ? <Loader2 size={14} className="pr-spin" /> : <Check size={14} />}{t('brYes')}
          </button>
          <button type="button" className="pr-undo ghost" disabled={briefBusy} onClick={() => onBriefAnswer('no')} data-testid="brief-no">{t('brNo')}</button>
          <small>{t('brSayIt')}</small>
        </div>
      )}
    </div>
  );
  else if (answerIsCurrent && lastAi) caption = (
    <div className="pr-answer" data-testid="presence-answer">
      {lastUser && <p className="pr-said">«{lastUser.content}»</p>}
      <div className="pr-md"><MarkdownRenderer content={lastAi.content} /></div>
      {actions}
      <div className="pr-tools">
        {lastAi.metadata?.undo_execution_id && onUndo && (
          <button type="button" className="pr-undo" disabled={undoState !== 'idle'} onClick={onUndo} data-testid="presence-undo">
            {undoState === 'busy' ? <Loader2 size={14} className="pr-spin" /> : <Undo2 size={14} />}{undoState === 'done' ? t('chUndone') : t('chUndo')}
          </button>
        )}
        <button type="button" className="pr-icon" onClick={onSpeak} aria-label={speaking ? t('homeUiStopAudio') : t('homeUiReadAloud')} title={speaking ? t('homeUiStopAudio') : t('homeUiReadAloud')}>
          {speaking ? <VolumeX size={15} /> : <Volume2 size={15} />}
        </button>
        <button type="button" className="pr-icon" onClick={copy} aria-label={copied ? t('chCopied') : t('chCopy')} title={copied ? t('chCopied') : t('chCopy')}>
          {copied ? <Check size={15} /> : <Copy size={15} />}
        </button>
      </div>
    </div>
  );
  else caption = <><h1 className="pr-greeting">{greeting}</h1><p className="pr-sub">{t('prHowCanIHelp')}</p><div className="pr-firstrun"><FirstRunModel /></div></>;

  return (
    <div className="pr-stage" data-testid="presence" data-state={orbState} data-focus={focus ? 'on' : undefined}>
      <div className="pr-sky" aria-hidden />
      <header className="pr-top" data-testid="top-header">
        <div className="pr-top-left">
          <button type="button" className="pr-chip" onClick={onOpenTranscript} data-testid="presence-open-transcript"><MessageSquareText size={15} /><span className="pr-chip-label">{t('prTranscript')}</span></button>
          <button type="button" className="pr-chip" onClick={onOpenRewind} data-testid="presence-open-rewind"><History size={15} /><span className="pr-chip-label">{t('rwTitle')}</span></button>
          {onFocusStart && !focus && (
            <div className="pr-focus-wrap">
              <button type="button" className="pr-chip" onClick={() => setFocusMenu(v => !v)} aria-expanded={focusMenu} aria-controls="pr-focus-menu" data-testid="presence-focus">
                <Timer size={15} /><span className="pr-chip-label">{t('fcTitle')}</span>
              </button>
              {focusMenu && (
                <div className="pr-focus-menu" id="pr-focus-menu" role="group" aria-label={t('fcTitle')}>
                  <p>{t('fcExplain')}</p>
                  <div>
                    {[25, 50, 90].map(m => (
                      <button key={m} type="button" autoFocus={m === 50} onClick={() => { setFocusMenu(false); onFocusStart(m); }} data-testid={`focus-${m}`}>
                        {t('fcMinutes', { count: m })}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        {notifications}
      </header>

      <div className="pr-center">
        <div className="pr-orbit">
          {!busy && !listening && !welcome && !focus && (
            <aside className="pr-day" aria-label={t('lifeToday')} data-testid="presence-day">
              {nextEvent && (
                <button type="button" className="pr-card" onClick={() => onAsk(t('prAskAgenda'))}>
                  <CalendarDays size={15} /><span><small>{nextEvent.all_day ? t('prAllDay') : fmtTime(nextEvent.start, language)}</small>{nextEvent.title}</span>
                </button>
              )}
              {overdue.length > 0 && (
                <button type="button" className="pr-card warn" onClick={() => onAsk(t('prAskOverdue'))}>
                  <AlarmClock size={15} /><span><small>{t('prOverdue', { count: overdue.length })}</small>{'title' in overdue[0] ? overdue[0].title : overdue[0].text}</span>
                </button>
              )}
              {overdue.length === 0 && dueToday.length > 0 && (
                <button type="button" className="pr-card" onClick={() => onAsk(t('prAskOverdue'))}>
                  <AlarmClock size={15} /><span><small>{t('prDueToday', { count: dueToday.length })}</small>{'title' in dueToday[0] ? dueToday[0].title : dueToday[0].text}</span>
                </button>
              )}
              {next && (
                <button type="button" className="pr-card" onClick={() => onAsk(t('prAskWeek'))} data-testid="presence-next">
                  <AlarmClock size={15} /><span><small>{t('prNext')} · {fmtWhen(next.due_at || 0, language)}</small>{'title' in next ? next.title : next.text}</span>
                </button>
              )}
              <button type="button" className="pr-card ghost" onClick={() => onAsk(t('dyAsk'))} data-testid="presence-diary">
                <BookOpen size={15} /><span><small>{t('dyTitle')}</small>{t('dyCta')}</span>
              </button>
              <button type="button" className="pr-card ghost" onClick={onOpenPromises} data-testid="presence-open-promises">
                <HandHeart size={15} /><span><small>{t('pkTitle')}</small>{t('pkCta')}</span>
              </button>
              {waiting > 0 && (
                <button type="button" className="pr-card accent" onClick={onOpenTranscript}>
                  <ShieldAlert size={15} /><span><small>{t('prWaiting')}</small>{t('prWaitingCount', { count: waiting })}</span>
                </button>
              )}
            </aside>
          )}
          <div className="pr-orb" style={{ width: orbSize, height: orbSize, ['--orb' as string]: `${orbSize}px` }}>
            <AetherOrb state={orbState} size={orbSize} quality="auto" interactive={false} compact={orbSize < 300} followVoice />
            {focus && (
              <svg className="pr-focus-ring" viewBox="0 0 100 100" aria-hidden>
                <circle cx="50" cy="50" r="48" pathLength={100} className="track" />
                <circle cx="50" cy="50" r="48" pathLength={100} className="done" strokeDasharray={`${Math.max(0.5, focus.progress * 100)} 100`} />
              </svg>
            )}
          </div>
        </div>
        {focus && !listening && !busy && (
          <div className="pr-focus-status" data-testid="focus-status">
            <span><Timer size={14} />{t('fcLeft', { time: fmtLeft(focus.remaining) })}</span>
            {onFocusStop && <button type="button" className="pr-undo ghost" onClick={onFocusStop} data-testid="focus-stop">{t('fcStop')}</button>}
          </div>
        )}
        <div className="pr-caption">{caption}</div>
      </div>

      {!welcome && (
        <footer className="pr-bottom">
          {composer}
          <p className="pr-hint">{t('prHoldSpace')}</p>
        </footer>
      )}
    </div>
  );
}

function fmtLeft(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
}
