import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, Loader2, Mic, Play, Square } from 'lucide-react';
import { apiUrl } from '../api';
import { FirstRunModel } from '../FirstRunModel';
import { createListener, forgetVoiceStatus, speakText, stopSpeech, voiceStatus, type NaturalVoice, type Listener } from '../voice/voiceIO';
import type { TranslationKey } from '../i18n';

type T = (key: TranslationKey, params?: Record<string, string | number>) => string;
type Step = 'name' | 'voice' | 'city' | 'model' | 'calendar' | 'first';

export const ONBOARDED_KEY = 'aether_onboarded';
export function onboarded(): boolean {
  // someone who already met Aether before the welcome existed is not walked through it again (Settings can replay it)
  try { return !!localStorage.getItem(ONBOARDED_KEY) || !!localStorage.getItem('aether_met'); } catch { return true; }
}
export function replayWelcome() {
  try { localStorage.removeItem(ONBOARDED_KEY); localStorage.removeItem('aether_met'); localStorage.setItem('aether_home_view', 'presence'); } catch { /* storage unavailable */ }
}
function markOnboarded() {
  try { localStorage.setItem(ONBOARDED_KEY, '1'); localStorage.setItem('aether_met', '1'); localStorage.setItem('aether_brief_day', new Date().toISOString().slice(0, 10)); } catch { /* storage unavailable */ }
}

/**
 * The first minute with Aether, under the orb and spoken by it: your name, its voice (downloaded while you answer), your city
 * (and the weather there at once), the model if none is set, the calendar, then the first real thing to remember, which
 * becomes the first confirmation card. Every step can be skipped; nothing leaves the Mac except the city name to Open-Meteo.
 */
export function Welcome({ t, language, onFinish, onOpenConnections, onSpeaking }: {
  t: T; language: string; onFinish: (firstThing?: string) => void; onOpenConnections: () => void; onSpeaking: (on: boolean) => void;
}) {
  const [steps, setSteps] = useState<Step[]>(['name', 'voice', 'city', 'model', 'calendar', 'first']);
  const [i, setI] = useState(0);
  const [name, setName] = useState('');
  const [city, setCity] = useState('');
  const [first, setFirst] = useState('');
  const [said, setSaid] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [natural, setNatural] = useState<NaturalVoice | null>(null);
  const [voice, setVoice] = useState('');
  const [preview, setPreview] = useState('');
  const [listening, setListening] = useState(false);
  const listener = useRef<Listener | null>(null);
  const voiceReady = natural?.state === 'ready';
  const step = steps[i];
  const it = language === 'it';

  // the natural voice starts downloading at once, so it is ready by the time the user picks it
  useEffect(() => {
    let alive = true;
    void (async () => {
      const st = await voiceStatus(language, true);
      if (!alive) return;
      const n = st?.tts.neural || null;
      setNatural(n);
      if (n?.state === 'missing') await fetch(apiUrl('/api/voice/natural/download'), { method: 'POST' }).catch(() => undefined);
      const res = await fetch(apiUrl('/api/settings/provider')).then(r => (r.ok ? r.json() : null)).catch(() => null);
      const c = res?.configured || {};
      const hasModel = !!res?.provider || !!(c.openai || c.anthropic || c.gemini || c.groq);
      if (alive) setSteps(s => s.filter(x => !(x === 'model' && hasModel) && !(x === 'voice' && (!n || n.state === 'unavailable'))));
    })();
    return () => { alive = false; listener.current?.abort(); stopSpeech(); };
  }, [language]);

  useEffect(() => {
    if (natural?.state !== 'downloading') return;
    const id = window.setInterval(async () => {
      forgetVoiceStatus();
      const st = await voiceStatus(language, true);
      setNatural(st?.tts.neural || null);
    }, 900);
    return () => window.clearInterval(id);
  }, [natural?.state, language]);

  // each step is said aloud once the natural voice is there (never with the robotic system voice)
  const say = async (text: string, opts?: { voice?: string }) => {
    if (!voiceReady && !opts?.voice) return;
    onSpeaking(true);
    await speakText(text, language, opts?.voice ? { voice: opts.voice, engine: 'neural' } : { engine: 'neural' }).catch(() => false);
    onSpeaking(false);
  };
  const question: Record<Step, string> = {
    name: t('wlNameQ'), voice: t('wlVoiceQ'), city: t('wlCityQ'), model: t('wlModelQ'), calendar: t('wlCalendarQ'), first: t('wlFirstQ'),
  };
  useEffect(() => {
    setError('');
    if (step && step !== 'name' && step !== 'voice') void say(`${said ? said + ' ' : ''}${question[step]}`);
    setSaid('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const next = () => {
    listener.current?.abort();
    if (i + 1 >= steps.length) { markOnboarded(); onFinish(); return; }
    setI(i + 1);
  };
  const skipAll = () => { listener.current?.abort(); stopSpeech(); markOnboarded(); onFinish(); };

  const saveName = async () => {
    const n = name.trim();
    if (n) await fetch(apiUrl('/api/profile'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: n, language }) }).catch(() => undefined);
    setSaid(n ? t('wlNiceToMeet', { name: n.split(' ')[0] }) : '');
    next();
  };
  const pickVoice = async (id: string) => {
    setVoice(id);
    await fetch(apiUrl('/api/voice/settings'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tts: 'neural', neural_voice: id }) }).catch(() => undefined);
    forgetVoiceStatus();
  };
  const previewVoice = async (id: string, label: string) => {
    if (preview) { stopSpeech(); setPreview(''); return; }
    setPreview(id);
    const who = name.trim().split(' ')[0];
    await say(t('wlVoiceSample', { voice: label, name: who ? `, ${who}` : '' }), { voice: id });
    setPreview('');
  };
  const saveCity = async () => {
    const c = city.trim();
    if (!c) { next(); return; }
    setBusy(true);
    try {
      const res = await fetch(apiUrl('/api/profile'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ city: c, language }) });
      if (res.status === 422) { setError(t('wlCityUnknown', { city: c })); return; }
      const d = res.ok ? await res.json() : null;
      setSaid(d?.weather || '');
      next();
    } finally { setBusy(false); }
  };
  const finishWith = () => {
    const thing = first.trim();
    listener.current?.abort();
    markOnboarded();
    onFinish(thing ? (it ? `Ricordami ${thing.replace(/^ricordami\s+/i, '')}` : `Remind me to ${thing.replace(/^remind me\s+/i, '').replace(/^to\s+/i, '')}`) : undefined);
  };

  // talk instead of typing: Whisper (or the Mac's dictation) fills the field; a pause ends the answer
  const listen = (set: (v: string) => void) => {
    if (listening) { listener.current?.stop(); return; }
    stopSpeech();
    listener.current?.abort();
    listener.current = createListener(language, {
      onText: v => set(v.replace(/[.!?]+$/, '')),
      onListening: on => setListening(on),
      onError: code => { if (code === 'mic_denied') setError(t('voMicDenied')); },
    });
    void listener.current.start({ autoStop: true });
  };
  const mic = (set: (v: string) => void) => (
    <button type="button" className={`wl-mic${listening ? ' on' : ''}`} onClick={() => listen(set)} aria-label={listening ? t('wlStopTalking') : t('wlTalk')} data-testid="welcome-mic">
      {listening ? <Square size={14} /> : <Mic size={16} />}
    </button>
  );

  if (!step) return null;
  const pct = natural ? Math.round((natural.download.done / Math.max(1, natural.download.total)) * 100) : 0;
  return (
    <section className="wl" data-testid="welcome" data-step={step} aria-labelledby="wl-q">
      <ol className="wl-dots" aria-label={t('wlProgress', { n: i + 1, total: steps.length })}>
        {steps.map((s, k) => <li key={s} className={k < i ? 'done' : k === i ? 'now' : ''} />)}
      </ol>
      {step === 'name' && <p className="wl-hello">{t('wlHello')}</p>}
      <h1 id="wl-q" className="wl-q">{question[step]}</h1>

      {step === 'name' && (
        <form className="wl-row" onSubmit={e => { e.preventDefault(); void saveName(); }}>
          <input className="wl-input" autoFocus value={name} onChange={e => setName(e.target.value)} placeholder={t('wlNamePh')} aria-label={t('wlNameQ')} maxLength={60} autoComplete="given-name" data-testid="welcome-name" />
          {mic(setName)}
          <button className="wl-go" type="submit" aria-label={t('wlNext')} data-testid="welcome-next"><ArrowRight size={18} /></button>
        </form>
      )}

      {step === 'voice' && (
        <div className="wl-voices">
          {natural?.state === 'downloading' && (
            <p className="wl-note" data-testid="welcome-voice-progress"><Loader2 size={14} className="pr-spin" /> {t('wlVoicePreparing', { pct })}</p>
          )}
          <div className="wl-voice-row">
            {(natural?.voices || []).map(v => (
              <div key={v.id} className={`wl-voice${voice === v.id ? ' picked' : ''}`}>
                <button type="button" className="wl-voice-pick" onClick={() => void pickVoice(v.id)} aria-pressed={voice === v.id} disabled={!voiceReady} data-testid={`welcome-voice-${v.id}`}>
                  {voice === v.id && <Check size={15} />}<b>{v.name}</b>
                </button>
                <button type="button" className="wl-play" onClick={() => void previewVoice(v.id, v.name)} disabled={!voiceReady} aria-label={t('wlListen', { voice: v.name })}>
                  {preview === v.id ? <Square size={13} /> : <Play size={13} />}
                </button>
              </div>
            ))}
          </div>
          {natural?.state === 'missing' && natural.download.error && <p className="wl-note" role="alert">{t('voNatError')}</p>}
          <div className="wl-actions">
            <button type="button" className="wl-primary" onClick={next} disabled={!voice && voiceReady} data-testid="welcome-next">{voice || !voiceReady ? t('wlNext') : t('wlPickOne')}</button>
          </div>
        </div>
      )}

      {step === 'city' && (
        <form className="wl-row" onSubmit={e => { e.preventDefault(); void saveCity(); }}>
          <input className="wl-input" autoFocus value={city} onChange={e => setCity(e.target.value)} placeholder={t('wlCityPh')} aria-label={t('wlCityQ')} maxLength={80} autoComplete="address-level2" data-testid="welcome-city" />
          {mic(setCity)}
          <button className="wl-go" type="submit" disabled={busy} aria-label={t('wlNext')} data-testid="welcome-next">{busy ? <Loader2 size={18} className="pr-spin" /> : <ArrowRight size={18} />}</button>
        </form>
      )}

      {step === 'model' && <div className="wl-model"><FirstRunModel onDone={next} /></div>}

      {step === 'calendar' && (
        <div className="wl-actions">
          <button type="button" className="wl-primary" onClick={() => { markOnboarded(); onOpenConnections(); }} data-testid="welcome-connect">{t('wlConnect')}</button>
          <button type="button" className="wl-ghost" onClick={next} data-testid="welcome-later">{t('wlLater')}</button>
        </div>
      )}

      {step === 'first' && (
        <form className="wl-row" onSubmit={e => { e.preventDefault(); finishWith(); }}>
          <input className="wl-input" autoFocus value={first} onChange={e => setFirst(e.target.value)} placeholder={t('wlFirstPh')} aria-label={t('wlFirstQ')} maxLength={300} data-testid="welcome-first" />
          {mic(setFirst)}
          <button className="wl-go" type="submit" aria-label={t('wlNext')} data-testid="welcome-next"><ArrowRight size={18} /></button>
        </form>
      )}

      {error && <p className="wl-error" role="alert">{error}</p>}
      <p className="wl-sub">{t(`wlSub_${step}` as TranslationKey)}</p>
      <div className="wl-foot">
        {step !== 'calendar' && <button type="button" className="wl-link" onClick={step === 'first' ? () => { markOnboarded(); onFinish(); } : next} data-testid="welcome-skip">{t('wlSkip')}</button>}
        <button type="button" className="wl-link" onClick={skipAll} data-testid="welcome-skip-all">{t('wlSkipAll')}</button>
      </div>
    </section>
  );
}
