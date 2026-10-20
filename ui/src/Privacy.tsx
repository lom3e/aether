import { useCallback, useContext, useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { apiUrl } from './api';
import { ToastContext } from './toast';
import { useTranslation } from './i18n';
import { TopHeader } from './TopHeader';
import './privacy.css';

type Tab = 'out' | 'knows' | 'undo';

interface LedgerEntry { id: string; ts: number; provider: string; model?: string | null; local: boolean; purpose?: string | null; chars: number; images: number; redactions: Record<string, number>; unmasked: boolean; status: string }
interface Summary { requests: number; cloud_requests: number; local_requests: number; images_sent: number; redactions_total: number; providers: string[] }
interface Mem { id: string; category: string; summary?: string; content: string; provenance?: { source_entity?: string } }
interface ScreenNote { id: string; title?: string; created_at: number; expires_at: number }
interface UndoItem { execution_id: string; title: string; created_at: number | string; reversible: boolean; reason: string; undone: boolean; kind?: string }

const when = (ts: number | string) => new Date(typeof ts === 'number' ? ts * 1000 : ts).toLocaleString();

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(apiUrl(path));
    return res.ok ? ((await res.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function Privacy() {
  const { t } = useTranslation();
  const toast = useContext(ToastContext);
  const [tab, setTab] = useState<Tab>('out');
  const [summary, setSummary] = useState<Summary | null>(null);
  const [redact, setRedact] = useState(true);
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [mems, setMems] = useState<Mem[]>([]);
  const [notes, setNotes] = useState<ScreenNote[]>([]);
  const [undo, setUndo] = useState<UndoItem[]>([]);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);

  const load = useCallback(async () => {
    const [s, l, m, n, u] = await Promise.all([
      getJson<{ summary: Summary; settings: { redact: boolean } } | null>('/api/privacy/summary?days=7', null),
      getJson<{ entries: LedgerEntry[] }>('/api/privacy/ledger?limit=50', { entries: [] }),
      getJson<Mem[]>('/api/memories?status=active&limit=200', []),
      getJson<{ items: ScreenNote[] }>('/api/screen-memory', { items: [] }),
      getJson<{ items: UndoItem[] }>('/api/undo', { items: [] }),
    ]);
    if (s) { setSummary(s.summary); setRedact(!!s.settings?.redact); }
    setEntries(l.entries); setMems(Array.isArray(m) ? m : []); setNotes(n.items); setUndo(u.items);
  }, []);
  useEffect(() => { void load(); }, [load]);

  const toggleRedact = async () => {
    const next = !redact;
    setRedact(next);
    await fetch(apiUrl('/api/privacy/settings'), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ redact: next }) });
  };
  const forgetMem = async (id: string) => {
    const res = await fetch(apiUrl(`/api/memories/${encodeURIComponent(id)}?hard=true`), { method: 'DELETE' });
    if (res.ok) { setMems(prev => prev.filter(x => x.id !== id)); toast(t('pvForgot'), 'success'); }
  };
  const saveEdit = async () => {
    if (!editing || !editing.text.trim()) return;
    const text = editing.text.trim();
    const res = await fetch(apiUrl(`/api/memories/${encodeURIComponent(editing.id)}`), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ summary: text, content: text }) });
    if (res.ok) {
      setMems(prev => prev.map(x => (x.id === editing.id ? { ...x, summary: text, content: text } : x)));
      setEditing(null);
      toast(t('pvEdited'), 'success');
    } else {
      toast(t('pvEditFailed'), 'error');
    }
  };
  const forgetNote = async (id: string) => {
    const res = await fetch(apiUrl(`/api/screen-memory/${encodeURIComponent(id)}`), { method: 'DELETE' });
    if (res.ok) { setNotes(prev => prev.filter(x => x.id !== id)); toast(t('pvForgot'), 'success'); }
  };
  const doUndo = async (id: string) => {
    const res = await fetch(apiUrl(`/api/undo/${encodeURIComponent(id)}`), { method: 'POST' });
    toast(res.ok ? t('pvUndone') : t('pvUndoFailed'), res.ok ? 'success' : 'error');
    void load();
  };

  const groups = mems.reduce<Record<string, Mem[]>>((acc, m) => { (acc[m.category] ||= []).push(m); return acc; }, {});
  const reasonText = (r: string) => (r === 'changed_since' ? t('pvReasonChanged') : r === 'already_undone' ? t('pvReasonDone') : t('pvReasonNoUndo'));

  return (
    <div className="pv-page" data-testid="privacy-view">
      <TopHeader title={t('pvTitle')} subtitle={t('pvSub')} icon={ShieldCheck} />
      <div className="pv-body">
        <div className="pv-tabs" role="tablist">
          {(['out', 'knows', 'undo'] as Tab[]).map(k => (
            <button key={k} role="tab" aria-selected={tab === k} data-testid={`privacy-tab-${k}`} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>
              {k === 'out' ? t('pvTabOut') : k === 'knows' ? t('pvTabKnows') : t('pvTabUndo')}
            </button>
          ))}
        </div>

        {tab === 'out' && (
          <section data-testid="privacy-out">
            <p className="pv-lead">
              {summary && summary.cloud_requests > 0
                ? t('pvLeadCloud').replace('{n}', String(summary.cloud_requests)).replace('{m}', String(summary.redactions_total))
                : t('pvLeadNone')}
            </p>
            <label className="pv-switch">
              <input type="checkbox" checked={redact} onChange={toggleRedact} data-testid="privacy-redact-toggle" />
              <span><strong>{t('pvRedactLabel')}</strong><small>{t('pvRedactHint')}</small></span>
            </label>
            {entries.length === 0 ? <p className="pv-empty">{t('pvLedgerEmpty')}</p> : (
              <ul className="pv-list">
                {entries.map(e => (
                  <li key={e.id}>
                    <span className={`pv-dot ${e.local ? 'local' : 'cloud'}`} aria-hidden />
                    <span className="pv-main">{e.provider}{e.model ? ` · ${e.model}` : ''}<small>{e.local ? t('pvLocalTag') : t('pvCloudTag')}{e.images ? ` · ${e.images} ${t('pvImages')}` : ''}{Object.keys(e.redactions).length ? ` · ${Object.values(e.redactions).reduce((a, b) => a + b, 0)} ${t('pvMasked')}` : ''}</small></span>
                    <time>{when(e.ts)}</time>
                  </li>
                ))}
              </ul>
            )}
            <p className="pv-limits">{t('pvLimits')}</p>
          </section>
        )}

        {tab === 'knows' && (
          <section data-testid="privacy-knows">
            {notes.length > 0 && (
              <div className="pv-group">
                <h3>{t('pvScreenNotes')}</h3>
                <ul className="pv-list">
                  {notes.map(n => (
                    <li key={n.id}><span className="pv-main">{n.title || n.id}<small>{t('pvExpires')} {when(n.expires_at)}</small></span>
                      <button className="pv-link" data-testid={`forget-note-${n.id}`} onClick={() => forgetNote(n.id)}>{t('pvForget')}</button></li>
                  ))}
                </ul>
              </div>
            )}
            {Object.keys(groups).length === 0 && notes.length === 0 && <p className="pv-empty">{t('pvKnowsEmpty')}</p>}
            {Object.entries(groups).map(([cat, list]) => (
              <div className="pv-group" key={cat}>
                <h3>{cat} <span>{list.length}</span></h3>
                <ul className="pv-list">
                  {list.map(m => (
                    <li key={m.id}>
                      {editing?.id === m.id ? (
                        <span className="pv-main">
                          <textarea className="pv-edit" rows={2} autoFocus value={editing.text} onChange={e => setEditing({ id: m.id, text: e.target.value })} data-testid="privacy-edit-input" />
                          <button className="pv-link" onClick={saveEdit} data-testid="privacy-edit-save">{t('pvSave')}</button>
                          <button className="pv-link" onClick={() => setEditing(null)}>{t('pvCancel')}</button>
                        </span>
                      ) : (
                        <>
                          <span className="pv-main">{m.summary || m.content.slice(0, 120)}{m.provenance?.source_entity && <small>{t('pvSource')}: {m.provenance.source_entity}</small>}</span>
                          <button className="pv-link" onClick={() => setEditing({ id: m.id, text: m.summary || m.content })} data-testid={`privacy-edit-${m.id}`}>{t('pvEdit')}</button>
                          <button className="pv-link" onClick={() => forgetMem(m.id)}>{t('pvForget')}</button>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        )}

        {tab === 'undo' && (
          <section data-testid="privacy-undo">
            {undo.length === 0 ? <p className="pv-empty">{t('pvUndoEmpty')}</p> : (
              <ul className="pv-list">
                {undo.map(u => (
                  <li key={u.execution_id}>
                    <span className="pv-main">{u.title}<small>{when(u.created_at)}{!u.reversible ? ` · ${reasonText(u.reason)}` : ''}</small></span>
                    {u.reversible && <button className="pv-link" data-testid={`undo-${u.execution_id}`} onClick={() => doUndo(u.execution_id)}>{t('pvUndoBtn')}</button>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
