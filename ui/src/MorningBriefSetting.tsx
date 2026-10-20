import { useEffect, useState } from 'react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';

/** Settings → General: the optional morning brief (off by default). One notification a day, at the time chosen, only if there is something to say. */
export function MorningBriefSetting() {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(false);
  const [time, setTime] = useState('08:30');

  useEffect(() => {
    fetch(apiUrl('/api/life/settings')).then(r => (r.ok ? r.json() : null)).then(d => { if (d) { setEnabled(!!d.brief_enabled); setTime(d.brief_time || '08:30'); } }).catch(() => undefined);
  }, []);

  const save = (next: { brief_enabled?: boolean; brief_time?: string }) =>
    fetch(apiUrl('/api/life/settings'), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(next) }).catch(() => undefined);

  return (
    <div className="card" style={{ padding: '24px' }} data-testid="morning-brief-setting">
      <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>{t('briefTitle')}</h3>
      <p className="text-muted" style={{ fontSize: '13px', marginBottom: '14px' }}>{t('briefDesc')}</p>
      <label style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '14px', cursor: 'pointer' }}>
        <input type="checkbox" checked={enabled} onChange={e => { setEnabled(e.target.checked); void save({ brief_enabled: e.target.checked }); }} data-testid="brief-toggle" />
        {t('briefToggle')}
      </label>
      {enabled && (
        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '14px', marginTop: '12px' }}>
          {t('briefAt')}
          <input type="time" value={time} onChange={e => setTime(e.target.value)} onBlur={() => void save({ brief_time: time })} data-testid="brief-time" style={{ font: 'inherit', padding: '6px 10px', borderRadius: '8px', border: 0, background: 'hsl(var(--muted) / .6)', color: 'hsl(var(--fg))' }} />
        </label>
      )}
    </div>
  );
}
