import { useState } from 'react';
import { useTranslation } from './i18n';
import { canSpeak, setSpeakVoiceAnswers, speak, speakVoiceAnswersEnabled } from './voiceOut';

/** Settings → General: spoken answers when you ask by voice (system voices, offline). */
export function VoiceSetting() {
  const { t, language } = useTranslation();
  const [on, setOn] = useState(speakVoiceAnswersEnabled());
  return (
    <div className="card" style={{ padding: '24px' }} data-testid="voice-setting">
      <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>{t('voiceTitle')}</h3>
      <p className="text-muted" style={{ fontSize: '13px', marginBottom: '14px' }}>{t('voiceDesc')}</p>
      <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', fontSize: '14px', cursor: 'pointer' }}>
        {t('voiceToggle')}
        <input type="checkbox" role="switch" className="ui-switch" checked={on} onChange={e => { setOn(e.target.checked); setSpeakVoiceAnswers(e.target.checked); }} data-testid="voice-toggle" disabled={!canSpeak()} />
      </label>
      {canSpeak() && (
        <button className="btn btn-ghost" style={{ marginTop: '12px', fontSize: '13px' }} onClick={() => speak(t('voiceSample'), language)} data-testid="voice-try">{t('voiceTry')}</button>
      )}
    </div>
  );
}
