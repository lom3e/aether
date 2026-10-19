import { useEffect, useState } from 'react';
import { apiUrl } from '../api';
import type { TranslationKey } from '../i18n';

type T = (key: TranslationKey, params?: Record<string, string | number>) => string;

interface Opinion { provider: string; model?: string | null; status: string; content?: string; reason?: string }
interface Result { status: string; opinions?: Opinion[]; agreement?: { level: string; differing_numbers: string[] } }

let availability: Promise<boolean> | null = null;
const canAskSecondOpinion = () => (availability ||= fetch(apiUrl('/api/personal/second-opinion/providers')).then(r => (r.ok ? r.json() : { available: false })).then(d => !!d.available).catch(() => false));

/** "Ask other models": the same question to the other configured providers, with an honest comparison. Shown only when >= 2 are configured. */
export function SecondOpinion({ question, language, t }: { question: string; language: string; t: T }) {
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  useEffect(() => { let live = true; canAskSecondOpinion().then(v => live && setOk(v)); return () => { live = false; }; }, []);
  if (!ok || !question.trim()) return null;

  const ask = async () => {
    setBusy(true);
    try {
      const res = await fetch(apiUrl('/api/personal/second-opinion'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, language }) });
      setResult(res.ok ? await res.json() : { status: 'failed' });
    } catch {
      setResult({ status: 'failed' });
    } finally {
      setBusy(false);
    }
  };

  const level = result?.agreement?.level;
  return (
    <div className="cmp-second" data-testid="companion-second-opinion">
      {!result && <button className="cmp-receipts-toggle" disabled={busy} onClick={ask} data-testid="companion-second-opinion-btn">{busy ? t('cmpSecondBusy') : t('cmpSecondAsk')}</button>}
      {result && result.status !== 'ok' && <span className="cmp-vision-hint">{t('cmpSecondFailed')}</span>}
      {result?.status === 'ok' && (
        <div className="cmp-receipts-body">
          {level && level !== 'single' && (
            <div className={`cmp-second-level ${level}`} data-testid="companion-second-level">
              {t(level === 'agree' ? 'cmpSecondAgree' : level === 'partial' ? 'cmpSecondPartial' : 'cmpSecondDiffer')}
              {result.agreement?.differing_numbers.length ? ` · ${t('cmpSecondNumbers', { list: result.agreement.differing_numbers.join(', ') })}` : ''}
            </div>
          )}
          {result.opinions?.map(o => (
            <div key={o.provider} className="cmp-second-op">
              <b>{o.provider}{o.model ? ` · ${o.model}` : ''}</b>
              <div>{o.status === 'ok' ? o.content : t('cmpSecondProviderFailed')}</div>
            </div>
          ))}
          <div className="cmp-vision-hint">{t('cmpSecondNote')}</div>
        </div>
      )}
    </div>
  );
}
