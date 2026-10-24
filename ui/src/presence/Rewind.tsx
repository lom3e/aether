import { useCallback, useContext, useEffect, useState } from 'react';
import { CalendarDays, FileText, GitBranch, History, Loader2, Mail, RotateCcw, Undo2, Users, X } from 'lucide-react';
import { apiUrl } from '../api';
import { ToastContext } from '../toast';
import type { TranslationKey } from '../i18n';

type T = (key: TranslationKey, params?: Record<string, string | number>) => string;

interface Item { execution_id: string; action_id: string; title: string; created_at: string; reversible: boolean; reason: string; undone: boolean; service: string }

const ICON: Record<string, typeof Mail> = { google_calendar: CalendarDays, calendar: CalendarDays, gmail: Mail, email: Mail, github: GitBranch, life: Users, files: FileText };
const WHAT: Record<string, TranslationKey> = {
  'google_calendar.create_event': 'rwCalCreate', 'google_calendar.update_event': 'rwCalMove', 'google_calendar.delete_event': 'rwCalDelete',
  'gmail.create_draft': 'rwMailDraft', 'gmail.send': 'rwMailSend', 'gmail.trash': 'rwMailTrash', 'gmail.modify_labels': 'rwMailLabels',
  'github.create_issue': 'rwGhIssue', 'life.save': 'rwLife', 'files.create_document': 'rwFile',
};
const WHY: Record<string, TranslationKey> = { already_sent: 'rwWhySent', changed_since: 'rwWhyChanged', no_undo: 'rwWhyNoUndo', missing_backup: 'rwWhyNoUndo', already_undone: 'rwUndone' };

/** Rewind: one timeline of every change Aether made for you, across services, with Undo for each and "put everything back
 *  as it was before this". What cannot be undone says why, it is never hidden. */
export function Rewind({ t, language, onClose }: { t: T; language: string; onClose: () => void }) {
  const toast = useContext(ToastContext);
  const [items, setItems] = useState<Item[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmRewind, setConfirmRewind] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/undo/timeline?limit=100'));
      setItems(res.ok ? (await res.json()).items || [] : []);
    } catch { setItems([]); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onClose]);

  const undoOne = async (id: string) => {
    setBusy(id);
    try {
      const res = await fetch(apiUrl(`/api/undo/${encodeURIComponent(id)}`), { method: 'POST' });
      toast(res.ok ? t('chUndoneToast') : t('chUndoFailed'), res.ok ? 'success' : 'error');
    } finally { setBusy(null); void load(); }
  };
  const rewindTo = async (id: string) => {
    setBusy(id);
    setConfirmRewind(null);
    try {
      const res = await fetch(apiUrl(`/api/undo/rewind/${encodeURIComponent(id)}`), { method: 'POST' });
      const data = res.ok ? await res.json() : null;
      if (data) toast(t('rwRewound', { count: data.undone.length }) + (data.kept.length ? ` ${t('rwKept', { count: data.kept.length })}` : ''), data.kept.length ? 'warning' : 'success');
      else toast(t('chUndoFailed'), 'error');
    } finally { setBusy(null); void load(); }
  };

  const locale = language === 'it' ? 'it-IT' : 'en-US';
  const dayOf = (iso: string) => new Date(iso).toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' });
  const groups: Array<[string, Item[]]> = [];
  for (const it of items || []) {
    const d = dayOf(it.created_at);
    const last = groups[groups.length - 1];
    if (last && last[0] === d) last[1].push(it); else groups.push([d, [it]]);
  }

  return (
    <div className="rw-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <section className="rw-panel" role="dialog" aria-modal="true" aria-labelledby="rw-title" data-testid="rewind">
        <header className="rw-head">
          <div>
            <h2 id="rw-title"><History size={18} />{t('rwTitle')}</h2>
            <p>{t('rwSub')}</p>
          </div>
          <button type="button" className="rw-close" onClick={onClose} aria-label={t('close')}><X size={18} /></button>
        </header>
        <div className="rw-body">
          {items === null && <p className="rw-empty"><Loader2 size={15} className="pr-spin" /> {t('loading')}</p>}
          {items !== null && items.length === 0 && <p className="rw-empty">{t('rwEmpty')}</p>}
          {groups.map(([day, list]) => (
            <div key={day} className="rw-day">
              <h3>{day}</h3>
              <ol>
                {list.map(it => {
                  const Icon = ICON[it.service] || History;
                  const when = new Date(it.created_at).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
                  return (
                    <li key={it.execution_id} className={it.undone ? 'undone' : ''} data-testid={`rw-item-${it.execution_id}`}>
                      <span className="rw-dot"><Icon size={14} /></span>
                      <span className="rw-main">
                        <small>{when} · {WHAT[it.action_id] ? t(WHAT[it.action_id]) : it.action_id}</small>
                        <b>{it.title}</b>
                        {it.undone ? <em>{t('rwUndone')}</em> : !it.reversible ? <em>{t(WHY[it.reason] || 'rwWhyNoUndo')}</em> : null}
                      </span>
                      {!it.undone && (
                        <span className="rw-actions">
                          {it.reversible && (
                            <button type="button" className="rw-btn" disabled={!!busy} onClick={() => undoOne(it.execution_id)} data-testid={`rw-undo-${it.execution_id}`}>
                              {busy === it.execution_id ? <Loader2 size={13} className="pr-spin" /> : <Undo2 size={13} />}{t('chUndo')}
                            </button>
                          )}
                          {confirmRewind === it.execution_id ? (
                            <button type="button" className="rw-btn danger" disabled={!!busy} onClick={() => rewindTo(it.execution_id)} data-testid={`rw-rewind-confirm-${it.execution_id}`}>
                              <RotateCcw size={13} />{t('rwRewindConfirm')}
                            </button>
                          ) : (
                            <button type="button" className="rw-btn ghost" disabled={!!busy} onClick={() => setConfirmRewind(it.execution_id)} title={t('rwRewindHint')} data-testid={`rw-rewind-${it.execution_id}`}>
                              <RotateCcw size={13} />{t('rwRewindHere')}
                            </button>
                          )}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ol>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
