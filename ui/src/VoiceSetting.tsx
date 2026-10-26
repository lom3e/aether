import { useEffect, useRef, useState } from 'react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { setSpeakVoiceAnswers, speakVoiceAnswersEnabled } from './voiceOut';
import { bargeInEnabled, forgetVoiceStatus, setBargeIn, speakText, voiceStatus, type VoiceStatus } from './voice/voiceIO';
import { greetAloudEnabled, setGreetAloud } from './voice/greet';

/** Settings → General: how Aether hears you (Whisper or the Mac's dictation) and which voice answers you. */
export function VoiceSetting() {
  const { t, language } = useTranslation();
  const [on, setOn] = useState(speakVoiceAnswersEnabled());
  const [greet, setGreet] = useState(greetAloudEnabled());
  const [barge, setBarge] = useState(bargeInEnabled());
  const [st, setSt] = useState<VoiceStatus | null>(null);
  const [trying, setTrying] = useState(false);
  const poll = useRef<number | null>(null);

  useEffect(() => { void voiceStatus(language, true).then(setSt); }, [language]);

  // while the natural voice downloads, the status is polled for the progress bar
  const natural = st?.tts.neural;
  useEffect(() => {
    if (natural?.state !== 'downloading') return;
    poll.current = window.setInterval(() => { forgetVoiceStatus(); void voiceStatus(language, true).then(setSt); }, 800);
    return () => { if (poll.current) window.clearInterval(poll.current); };
  }, [natural?.state, language]);

  const naturalAction = async (path: string, method = 'POST') => {
    await fetch(apiUrl(path), { method }).catch(() => undefined);
    forgetVoiceStatus();
    setSt(await voiceStatus(language, true));
  };

  const save = async (patch: Record<string, string>) => {
    const res = await fetch(apiUrl('/api/voice/settings'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) });
    forgetVoiceStatus();
    if (res.ok) setSt(await voiceStatus(language, true));
  };

  const voiceValue = st ? `${st.tts.engine === 'device' ? 'system' : st.tts.engine}:${st.tts.engine === 'openai' ? st.settings.openai_voice : st.tts.voice}` : '';
  const pickVoice = (v: string) => {
    const [engine, ...rest] = v.split(':');
    const name = rest.join(':');
    void save(engine === 'openai' ? { tts: 'openai', openai_voice: name } : engine === 'neural' ? { tts: 'neural', neural_voice: name } : { tts: 'system', system_voice: name });
  };
  const pct = natural ? Math.min(100, Math.round((natural.download.done / Math.max(1, natural.download.total)) * 100)) : 0;
  const tryVoice = async () => {
    setTrying(true);
    await speakText(t('voiceSample'), language);
    setTrying(false);
  };
  const quality = (q: string) => (q === 'premium' ? t('voQualityPremium') : q === 'enhanced' ? t('voQualityEnhanced') : t('voQualityBasic'));

  return (
    <div className="card" style={{ padding: '24px' }} data-testid="voice-setting">
      <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>{t('voiceTitle')}</h3>
      <p className="text-muted" style={{ fontSize: '13px', marginBottom: '14px' }}>{t('voiceDesc')}</p>
      <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', fontSize: '14px', cursor: 'pointer' }}>
        {t('voiceToggle')}
        <input type="checkbox" role="switch" className="ui-switch" checked={on} onChange={e => { setOn(e.target.checked); setSpeakVoiceAnswers(e.target.checked); }} data-testid="voice-toggle" />
      </label>
      <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', fontSize: '14px', cursor: 'pointer', marginTop: '12px' }}>
        {t('voBargeToggle')}
        <input type="checkbox" role="switch" className="ui-switch" checked={barge} onChange={e => { setBarge(e.target.checked); setBargeIn(e.target.checked); }} data-testid="voice-barge" />
      </label>
      <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', fontSize: '14px', cursor: 'pointer', marginTop: '12px' }}>
        {t('voGreetToggle')}
        <input type="checkbox" role="switch" className="ui-switch" checked={greet} onChange={e => { setGreet(e.target.checked); setGreetAloud(e.target.checked); }} data-testid="voice-greet" />
      </label>

      {st && (
        <div style={{ display: 'grid', gap: '14px', marginTop: '18px' }}>
          <label style={{ display: 'grid', gap: '6px', fontSize: '14px' }}>
            <span>{t('voHearLabel')}</span>
            <select className="input" value={st.settings.stt} onChange={e => void save({ stt: e.target.value })} data-testid="voice-stt">
              <option value="auto">{t('voHearAuto')}</option>
              {st.stt.available.includes('groq') && <option value="groq">{t('voHearGroq')}</option>}
              {st.stt.available.includes('openai') && <option value="openai">{t('voHearOpenai')}</option>}
              <option value="device">{t('voHearDevice')}</option>
            </select>
            <small className="text-muted" data-testid="voice-stt-note">
              {st.stt.engine === 'device' ? t('voHearDeviceNote') : t('voHearCloudNote', { provider: st.stt.engine === 'groq' ? 'Groq' : 'OpenAI' })}
            </small>
          </label>

          {(natural?.state === 'ready' || st.tts.voices.length > 0 || st.tts.available.includes('openai')) && <label style={{ display: 'grid', gap: '6px', fontSize: '14px' }}>
            <span>{t('voSpeakLabel')}</span>
            <span style={{ display: 'flex', gap: '8px' }}>
              <select className="input" style={{ flex: 1 }} value={voiceValue} onChange={e => pickVoice(e.target.value)} data-testid="voice-tts">
                {natural?.state === 'ready' && natural.voices.map(v => <option key={v.id} value={`neural:${v.id}`}>{v.name} · {t('voQualityNatural')}</option>)}
                {st.tts.voices.map(v => <option key={v.name} value={`system:${v.name}`}>{v.name} · {quality(v.quality)}</option>)}
                {st.tts.available.includes('openai') && st.tts.openai_voices.map(v => <option key={v} value={`openai:${v}`}>OpenAI · {v} · {t('voQualityCloud')}</option>)}
              </select>
              <button className="btn btn-ghost" type="button" onClick={() => void tryVoice()} disabled={trying} data-testid="voice-try">{t('voiceTry')}</button>
            </span>
            <small className="text-muted">{st.tts.engine === 'openai' ? t('voSpeakCloudNote') : st.tts.engine === 'neural' ? t('voSpeakNaturalNote') : t('voSpeakLocalNote')}</small>
          </label>}

          {natural && (natural.state === 'missing' || natural.state === 'downloading') && (
            <div role="note" data-testid="voice-natural" style={{ fontSize: '13px', lineHeight: 1.5, padding: '12px 14px', borderRadius: '12px', background: 'var(--surface-2, rgba(127,127,127,.08))' }}>
              <b style={{ display: 'block', marginBottom: '4px' }}>{t('voNatTitle')}</b>
              {t('voNatDesc', { mb: String(natural.size_mb) })}
              {natural.state === 'downloading' ? (
                <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <progress max={100} value={pct} aria-label={t('voNatDownloading', { pct: String(pct) })} style={{ flex: 1 }} data-testid="voice-natural-progress" />
                  <span aria-hidden="true" style={{ fontVariantNumeric: 'tabular-nums', minWidth: '4ch' }}>{pct}%</span>
                  <button className="btn btn-ghost" type="button" onClick={() => void naturalAction('/api/voice/natural/cancel')} data-testid="voice-natural-cancel">{t('voNatCancel')}</button>
                </div>
              ) : (
                <div style={{ marginTop: '10px' }}>
                  {natural.download.error && natural.download.error !== 'cancelled' && <p role="alert" style={{ margin: '0 0 8px' }}>{t('voNatError')}</p>}
                  <button className="btn btn-primary" type="button" onClick={() => void naturalAction('/api/voice/natural/download')} data-testid="voice-natural-download">{t('voNatDownload')}</button>
                </div>
              )}
            </div>
          )}
          {natural?.state === 'ready' && (
            <button className="btn btn-ghost" type="button" style={{ justifySelf: 'start', fontSize: '13px' }} onClick={() => void naturalAction('/api/voice/natural', 'DELETE')} data-testid="voice-natural-remove">{t('voNatRemove')}</button>
          )}

          {st.tts.needs_better_voice && (!natural || natural.state === 'unavailable') && (
            <div className="vo-tip" role="note" data-testid="voice-better" style={{ fontSize: '13px', lineHeight: 1.5, padding: '12px 14px', borderRadius: '12px', background: 'var(--surface-2, rgba(127,127,127,.08))' }}>
              <b style={{ display: 'block', marginBottom: '4px' }}>{t('voBetterTitle')}</b>
              {t('voBetterSteps')}
              <div style={{ marginTop: '10px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <button className="btn btn-ghost" type="button" onClick={() => void fetch(apiUrl('/api/voice/open-system-voices'), { method: 'POST' })} data-testid="voice-open-settings">{t('voBetterOpen')}</button>
                <button className="btn btn-ghost" type="button" onClick={() => { forgetVoiceStatus(); void voiceStatus(language, true).then(setSt); }}>{t('voBetterRecheck')}</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
