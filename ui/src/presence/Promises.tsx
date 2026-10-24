import { useContext, useEffect, useState } from 'react';
import { HandHeart, Loader2, X } from 'lucide-react';
import { apiUrl } from '../api';
import { ToastContext } from '../toast';
import { fmtDue, lifeApi } from '../lifeApi';
import type { TranslationKey } from '../i18n';

type T = (key: TranslationKey, params?: Record<string, string | number>) => string;
interface Promise_ { kind: 'i_promised' | 'they_asked'; title: string; who: string; due_at: number | null; message_id: string; subject: string; contact: string | null }

/** Promise keeper: what you promised and what was asked of you in recent mail. Nothing is saved until you pick it. */
export function Promises({ t, language, onClose }: { t: T; language: string; onClose: () => void }) {
  const toast = useContext(ToastContext);
  const [state, setState] = useState<{ status: string; items: Promise_[]; scanned?: number } | null>(null);
  const [done, setDone] = useState<Record<string, 'saved' | 'skipped'>>({});

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
    try {
      let contactId: string | null = null;
      if (p.who) {
        const all = await lifeApi.contacts();
        contactId = all.find(c => c.name.toLowerCase() === (p.contact || p.who).toLowerCase())?.id
          || (await lifeApi.addContact({ name: p.contact || p.who, kind: 'client' })).id;
      }
      await lifeApi.addJob({ title: p.title, contact_id: contactId, due_at: p.due_at, source: 'promise_keeper' });
      setDone(prev => ({ ...prev, [p.message_id + p.title]: 'saved' }));
      toast(t('pkSaved'), 'success');
    } catch { toast(t('lifeSaveFailed'), 'error'); }
  };

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
          {state?.status === 'ok' && state.items.length === 0 && <p className="rw-empty">{t('pkNone', { count: state.scanned || 0 })}</p>}
          {state?.status === 'ok' && state.items.length > 0 && (
            <ol className="pk-list">
              {state.items.map(p => {
                const k = p.message_id + p.title;
                return (
                  <li key={k} className={done[k] ? 'handled' : ''} data-testid="promise-item">
                    <span className="rw-main">
                      <small>{p.kind === 'i_promised' ? t('pkYouPromised', { who: p.who || '—' }) : t('pkTheyAsked', { who: p.who || '—' })}{p.due_at ? ` · ${fmtDue(p.due_at, language)}` : ''}</small>
                      <b>{p.title}</b>
                      <em className="pk-src">{p.subject}</em>
                    </span>
                    <span className="rw-actions">
                      {done[k] === 'saved' ? <em className="pk-ok">{t('pkSavedShort')}</em> : done[k] === 'skipped' ? null : (
                        <>
                          <button type="button" className="rw-btn" onClick={() => save(p)} data-testid="promise-save">{t('pkSave')}</button>
                          <button type="button" className="rw-btn ghost" onClick={() => setDone(prev => ({ ...prev, [k]: 'skipped' }))}>{t('pkSkip')}</button>
                        </>
                      )}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </section>
    </div>
  );
}
