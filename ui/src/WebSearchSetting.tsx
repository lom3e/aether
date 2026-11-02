import { useEffect, useState } from 'react';
import { apiUrl } from './api';
import { openExternalUrl } from './desktop';
import { useTranslation } from './i18n';

const SERVICES: Record<string, { name: string; keyUrl: string }> = {
  brave: { name: 'Brave Search', keyUrl: 'https://api-dashboard.search.brave.com/' },
  tavily: { name: 'Tavily', keyUrl: 'https://app.tavily.com/' },
};

/** Settings → Model: which service answers web questions when the model cannot search by itself (the user's own free key). */
export function WebSearchSetting() {
  const { t } = useTranslation();
  const [current, setCurrent] = useState('');
  const [service, setService] = useState('brave');
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(apiUrl('/api/web-search')).then(r => (r.ok ? r.json() : null)).then(d => { if (d?.configured) { setCurrent(d.provider); setService(d.provider); } }).catch(() => undefined);
  }, []);

  const name = SERVICES[service]?.name || service;
  const save = async () => {
    if (!key.trim() || busy) return;
    setBusy(true);
    setError('');
    try {
      const res = await fetch(apiUrl('/api/web-search'), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: service, api_key: key.trim() }) });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) {
        const code = d?.detail?.code;
        setError(t(code === 'invalid_key' ? 'wsInvalidKey' : code === 'rate_limited' ? 'wsRateLimited' : 'wsUnreachable', { name }));
        return;
      }
      setKey('');
      setCurrent(service);
    } finally { setBusy(false); }
  };
  const remove = async () => {
    await fetch(apiUrl('/api/web-search'), { method: 'DELETE' }).catch(() => undefined);
    setCurrent('');
  };

  return (
    <div className="card" style={{ padding: '24px' }} data-testid="web-search-setting">
      <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>{t('wsTitle')}</h3>
      <p className="text-muted" style={{ fontSize: '13px', lineHeight: 1.5, marginBottom: '14px' }}>{t('wsExplain')}</p>
      {current ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', fontSize: '14px' }}>
          <span data-testid="web-search-on">{t('wsOn', { name: SERVICES[current]?.name || current })}</span>
          <button type="button" className="btn btn-secondary" onClick={() => void remove()}>{t('wsRemove')}</button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(140px, 180px) 1fr', gap: '10px' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span className="form-label" style={{ margin: 0 }}>{t('wsProvider')}</span>
              <select className="form-select" value={service} onChange={e => { setService(e.target.value); setError(''); }} data-testid="web-search-service">
                {Object.entries(SERVICES).map(([id, s]) => <option key={id} value={id}>{s.name}</option>)}
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span className="form-label" style={{ margin: 0 }}>{t('wsKey')}</span>
              <input type="password" className="form-input" value={key} autoComplete="off" spellCheck={false} name="web-search-key"
                onChange={e => setKey(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void save(); }} data-testid="web-search-key" />
            </label>
          </div>
          {error && <p role="alert" style={{ margin: 0, fontSize: '13px', color: 'hsl(var(--destructive))' }}>{error}</p>}
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <button type="button" className="btn btn-primary" disabled={busy || !key.trim()} onClick={() => void save()} data-testid="web-search-save">
              {busy ? t('testing') : t('wsSave')}
            </button>
            <button type="button" className="link-btn" onClick={() => void openExternalUrl(SERVICES[service].keyUrl)}
              style={{ border: 0, background: 'none', padding: 0, cursor: 'pointer', font: 'inherit', fontSize: '13px', color: 'hsl(var(--primary))', textDecoration: 'underline', textUnderlineOffset: '3px' }}>
              {t('wsGetKey')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
