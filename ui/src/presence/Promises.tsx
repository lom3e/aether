import { useContext, useEffect, useState } from 'react';
import { HandHeart, Loader2, X } from 'lucide-react';
import { apiUrl } from '../api';
import { ToastContext } from '../toast';
import { fmtDue } from '../lifeApi';
import type { TranslationKey } from '../i18n';

type T = (key: TranslationKey, params?: Record<string, string | number>) => string;
interface Promise_ { id?: string; status?: string; kind: 'i_promised' | 'they_asked' | 'they_promised' | 'fulfilled'; title: string; who: string; due_at: number | null; message_id: string; subject: string; contact?: string | null; job_id?: string }

/** Promise keeper: what you promised, what was asked of you, what others promised you, and what a mail you sent already
 * closed. Nothing is saved or marked done until you pick it. The daily check can be turned on from here. */
export function Promises({ t, language, onClose }: { t: T; language: string; onClose: () => void }) {
  const toast = useContext(ToastContext);
  const [state, setState] = useState<{ status: string; items: Promise_[]; fulfilled?: Promise_[]; scanned?: number } | null>(null);
  const [done, setDone] = useState<Record<string, 'saved' | 'skipped' | 'closed'>>({});
  const [watch, setWatch] = useState<boolean | null>(null);

  useEffect(() => {
    fetch(apiUrl('/api/life/promises?status=new')).then(r => (r.ok ? r.json() : null)).then(d => { if (d) setWatch(!!d.watch); }).catch(() => undefined);
  }, []);

  const offer = (body: Record<string, unknown>) =>
    fetch(apiUrl('/api/presence/offer'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, language }) });

  useEffect(() => {
    let alive = true;
    fetch(apiUrl('/api/life/promises/scan'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ language }) })
      .then(r => (r.ok ? r.json() : { status: 'failed', items: [] }))
      .then(d => { if (alive) setState(d); })
      .catch(() => { if (alive) setState({ status: 'failed', items: [] }); });
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', esc);
    return () => { alive = false; window.removeEventListener('keydown', esc); };
  }, [language, onClose]);

  const save = async (p: Promise_) => {
    const k = p.message_id + p.title;
    const res = p.id ? await offer({ offer: { type: p.kind === 'fulfilled' ? 'job_done' : 'track', promise_id: p.id }, answer: 'yes' }).catch(() => null) : null;
    if (!res?.ok) { toast(t('lifeSaveFailed'), 'error'); return; }
    setDone(prev => ({ ...prev, [k]: p.kind === 'fulfilled' ? 'closed' : 'saved' }));
    toast(p.kind === 'fulfilled' ? t('pkClosed') : t('pkSaved'), 'success');
  };
  const skip = (p: Promise_) => {
    setDone(prev => ({ ...prev, [p.message_id + p.title]: 'skipped' }));
    if (p.id) void offer({ offer: { type: p.kind === 'fulfilled' ? 'job_done' : 'track', promise_id: p.id }, answer: 'no' }).catch(() => undefined);
  };
  const toggleWatch = async () => {
    const res = await offer({ offer: { type: 'watch_on' }, answer: 'yes' }).catch(() => null);
    if (res?.ok) setWatch(true);
  };
  const label = (p: Promise_) => {
    const who = p.who || '—';
    if (p.kind === 'i_promised') return t('pkYouPromised', { who });
    if (p.kind === 'they_promised') return t('pkTheyPromised', { who });
    if (p.kind === 'fulfilled') return t('pkLooksDone');
    return t('pkTheyAsked', { who });
  };
  const all = [...(state?.fulfilled || []), ...(state?.items || [])];

  return (
    <div className="rw-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <section className="rw-panel" role="dialog" aria-modal="true" aria-labelledby="pk-title" data-testid="promises">
        <header className="rw-head">
          <div>
            <h2 id="pk-title"><HandHeart size={18} />{t('pkTitle')}</h2>
            <p>{t('pkSub')}</p>
          </div>
          <button type="button" className="rw-close" onClick={onClose} aria-label={t('close')}><X size={18} /></button>
        </header>
        <div className="rw-body">
          {!state && <p className="rw-empty"><Loader2 size={15} className="pr-spin" /> {t('pkReading')}</p>}
          {state?.status === 'no_gmail' && <p className="rw-empty">{t('pkNoGmail')}</p>}
          {state?.status === 'unavailable' && <p className="rw-empty">{t('pkNoModel')}</p>}
          {state?.status === 'failed' && <p className="rw-empty">{t('pkFailed')}</p>}
          {state?.status === 'ok' && all.length === 0 && <p className="rw-empty">{t('pkNone', { count: state.scanned || 0 })}</p>}
          {state?.status === 'ok' && all.length > 0 && (
            <ol className="pk-list">
              {all.map(p => {
                const k = p.message_id + p.title;
                return (
                  <li key={k} className={done[k] ? 'handled' : ''} data-testid="promise-item">
                    <span className="rw-main">
                      <small>{label(p)}{p.due_at ? ` · ${fmtDue(p.due_at, language)}` : ''}</small>
                      <b>{p.title}</b>
                      <em className="pk-src">{p.subject}</em>
                    </span>
                    <span className="rw-actions">
                      {done[k] === 'saved' || p.status === 'tracked' ? <em className="pk-ok">{t('pkSavedShort')}</em>
                        : done[k] === 'closed' || p.status === 'done' ? <em className="pk-ok">{t('pkClosedShort')}</em>
                        : done[k] === 'skipped' || p.status === 'ignored' ? null : (
                        <>
                          <button type="button" className="rw-btn" onClick={() => save(p)} data-testid="promise-save">{p.kind === 'fulfilled' ? t('pkMarkDone') : t('pkSave')}</button>
                          <button type="button" className="rw-btn ghost" onClick={() => skip(p)}>{t('pkSkip')}</button>
                        </>
                      )}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
          {watch === false && (
            <p className="pk-watch" data-testid="promise-watch">
              {t('pkWatchOffer')} <button type="button" className="rw-btn" onClick={() => void toggleWatch()} data-testid="promise-watch-on">{t('pkWatchOn')}</button>
            </p>
          )}
          {watch === true && <p className="pk-watch muted">{t('pkWatchActive')}</p>}
        </div>
      </section>
    </div>
  );
}
