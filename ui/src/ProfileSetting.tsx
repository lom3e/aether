import { useEffect, useState } from 'react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { replayWelcome } from './presence/Welcome';

/** Settings → General: what Aether calls you and where you live (greeting, mail signature, weather), and the welcome again. */
export function ProfileSetting({ onReplay }: { onReplay?: () => void }) {
  const { t, language } = useTranslation();
  const [name, setName] = useState('');
  const [city, setCity] = useState('');
  const [saved, setSaved] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(apiUrl('/api/profile')).then(r => (r.ok ? r.json() : null)).then(d => { if (d) { setName(d.name || ''); setCity(d.city || ''); } }).catch(() => undefined);
  }, []);

  const save = async () => {
    setError(''); setSaved('');
    const res = await fetch(apiUrl('/api/profile'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, city, language }) }).catch(() => null);
    if (!res) { setError(t('lifeSaveFailed')); return; }
    if (res.status === 422) { setError(t('wlCityUnknown', { city })); return; }
    const d = await res.json().catch(() => ({}));
    if (d.city) setCity(d.city);
    setSaved(d.weather || t('profSaved'));
  };

  return (
    <div className="card" style={{ padding: '24px' }} data-testid="profile-setting">
      <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>{t('profTitle')}</h3>
      <p className="text-muted" style={{ fontSize: '13px', marginBottom: '14px' }}>{t('profDesc')}</p>
      <form style={{ display: 'grid', gap: '12px' }} onSubmit={e => { e.preventDefault(); void save(); }}>
        <label style={{ display: 'grid', gap: '6px', fontSize: '14px' }}>
          <span>{t('wlNamePh')}</span>
          <input className="input" value={name} onChange={e => setName(e.target.value)} maxLength={60} autoComplete="given-name" data-testid="profile-name" />
        </label>
        <label style={{ display: 'grid', gap: '6px', fontSize: '14px' }}>
          <span>{t('wlCityPh')}</span>
          <input className="input" value={city} onChange={e => setCity(e.target.value)} maxLength={80} autoComplete="address-level2" data-testid="profile-city" />
        </label>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <button className="btn btn-primary" type="submit" data-testid="profile-save">{t('profSave')}</button>
          <button className="btn btn-ghost" type="button" onClick={() => { replayWelcome(); onReplay?.(); }} data-testid="profile-replay">{t('profReplay')}</button>
          {saved && <small className="text-muted" aria-live="polite">{saved}</small>}
          {error && <small role="alert" style={{ color: 'hsl(var(--danger, 0 70% 50%))' }}>{error}</small>}
        </div>
      </form>
    </div>
  );
}
