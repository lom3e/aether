import { useEffect, useState } from 'react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { setSpeakVoiceAnswers, speakVoiceAnswersEnabled } from './voiceOut';
import { forgetVoiceStatus, speakText, voiceStatus, type VoiceStatus } from './voice/voiceIO';
import { greetAloudEnabled, setGreetAloud } from './voice/greet';

/** Settings → General: how Aether hears you (Whisper or the Mac's dictation) and which voice answers you. */
export function VoiceSetting() {
  const { t, language } = useTranslation();
  const [on, setOn] = useState(speakVoiceAnswersEnabled());
  const [greet, setGreet] = useState(greetAloudEnabled());
  const [st, setSt] = useState<VoiceStatus | null>(null);
  const [trying, setTrying] = useState(false);

  useEffect(() => { void voiceStatus(language, true).then(setSt); }, [language]);

  const save = async (patch: Record<string, string>) => {
    const res = await fetch(apiUrl('/api/voice/settings'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) });
    forgetVoiceStatus();
    if (res.ok) setSt(await voiceStatus(language, true));
  };

  const voiceValue = st ? (st.tts.engine === 'openai' ? `openai:${st.settings.openai_voice}` : `system:${st.tts.voice}`) : '';
  const pickVoice = (v: string) => {
    const [engine, ...rest] = v.split(':');
    const name = rest.join(':');
    void save(engine === 'openai' ? { tts: 'openai', openai_voice: name } : { tts: 'system', system_voice: name });
  };
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

          <label style={{ display: 'grid', gap: '6px', fontSize: '14px' }}>
            <span>{t('voSpeakLabel')}</span>
            <span style={{ display: 'flex', gap: '8px' }}>
              <select className="input" style={{ flex: 1 }} value={voiceValue} onChange={e => pickVoice(e.target.value)} data-testid="voice-tts">
                {st.tts.voices.map(v => <option key={v.name} value={`system:${v.name}`}>{v.name} · {quality(v.quality)}</option>)}
                {st.tts.available.includes('openai') && st.tts.openai_voices.map(v => <option key={v} value={`openai:${v}`}>OpenAI · {v} · {t('voQualityCloud')}</option>)}
              </select>
              <button className="btn btn-ghost" type="button" onClick={() => void tryVoice()} disabled={trying} data-testid="voice-try">{t('voiceTry')}</button>
            </span>
            <small className="text-muted">{st.tts.engine === 'openai' ? t('voSpeakCloudNote') : t('voSpeakLocalNote')}</small>
          </label>

          {st.tts.needs_better_voice && (
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
