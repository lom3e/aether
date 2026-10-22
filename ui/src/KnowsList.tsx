import { useCallback, useContext, useEffect, useState } from 'react';
import { apiUrl } from './api';
import { ToastContext } from './toast';
import { useTranslation, type TranslationKey } from './i18n';
import './privacy.css';

// "What Aether knows about you": the same list in Memory (where you also add things) and in Privacy (where you review it).
interface Mem { id: string; category: string; summary?: string; content: string; provenance?: { source_entity?: string } }
interface ScreenNote { id: string; title?: string; created_at: number; expires_at: number }

const when = (ts: number | string) => new Date(typeof ts === 'number' ? ts * 1000 : ts).toLocaleString();
const CATEGORY_KEY: Record<string, TranslationKey> = {
  fact: 'memCategoryFact', preference: 'memCategoryPreference', decision: 'memCategoryDecision', process: 'memCategoryProcess',
  person: 'memCategoryPerson', project: 'memCategoryProject', outcome: 'memCategoryOutcome', lesson: 'memCategoryLesson',
};

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(apiUrl(path));
    return res.ok ? ((await res.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function KnowsList({ allowAdd = false }: { allowAdd?: boolean }) {
  const { t } = useTranslation();
  const toast = useContext(ToastContext);
  const [mems, setMems] = useState<Mem[]>([]);
  const [notes, setNotes] = useState<ScreenNote[]>([]);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [draft, setDraft] = useState('');
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    const [m, n] = await Promise.all([
      getJson<Mem[]>('/api/memories?status=active&limit=200', []),
      getJson<{ items: ScreenNote[] }>('/api/screen-memory', { items: [] }),
    ]);
    setMems(Array.isArray(m) ? m : []);
    setNotes(n.items || []);
  }, []);
  useEffect(() => { void load(); }, [load]);

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
  const add = async () => {
    const text = draft.trim();
    if (!text || adding) return;
    setAdding(true);
    try {
      const res = await fetch(apiUrl('/api/memories'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: 'fact', summary: text, content: text, source_entity: 'manual' }),
      });
      if (res.ok) { setDraft(''); toast(t('memAdded'), 'success'); void load(); } else toast(t('pvEditFailed'), 'error');
    } finally {
      setAdding(false);
    }
  };

  const groups = mems.reduce<Record<string, Mem[]>>((acc, m) => { (acc[m.category] ||= []).push(m); return acc; }, {});
  const catLabel = (c: string) => (CATEGORY_KEY[c] ? t(CATEGORY_KEY[c]) : c);

  return (
    <section data-testid="privacy-knows">
      {allowAdd && (
        <form className="pv-add" onSubmit={e => { e.preventDefault(); void add(); }}>
          <input value={draft} onChange={e => setDraft(e.target.value)} placeholder={t('memAddPlaceholder')} aria-label={t('memAddPlaceholder')} data-testid="memory-add-input" />
          <button type="submit" disabled={!draft.trim() || adding} data-testid="memory-add-btn">{t('memAddBtn')}</button>
        </form>
      )}
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
          <h3>{catLabel(cat)} <span>{list.length}</span></h3>
          <ul className="pv-list">
            {list.map(m => (
              <li key={m.id}>
                {editing?.id === m.id ? (
                  <span className="pv-main">
                    <textarea className="pv-edit" rows={2} autoFocus aria-label={t('pvEdit')} value={editing.text} onChange={e => setEditing({ id: m.id, text: e.target.value })} data-testid="privacy-edit-input" />
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
  );
}
