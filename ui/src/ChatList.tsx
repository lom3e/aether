import { useEffect, useRef, useState } from 'react';
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { useTranslation, type TranslationKey } from './i18n';

export interface ChatItem { id: string; title?: string; updated_at?: string; created_at?: string }

const GROUPS: Array<[TranslationKey, number]> = [['chToday', 0], ['chYesterday', 1], ['chLast7', 7], ['chLast30', 30]];

function groupOf(iso?: string): TranslationKey {
  const d = iso ? new Date(iso) : new Date();
  const start = new Date(); start.setHours(0, 0, 0, 0);
  const days = Math.floor((start.getTime() - new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) / 86400000);
  for (const [key, max] of GROUPS) if (days <= max) return key;
  return 'chOlder';
}

/** The chats with Aether, newest first, grouped like ChatGPT/Claude (Today, Yesterday, …). Rename and delete on hover. */
export function ChatList({ chats, activeId, query, onOpen, onDelete, onRename }: {
  chats: ChatItem[]; activeId: string | null; query: string;
  onOpen: (id: string) => void; onDelete: (id: string) => void; onRename: (id: string, title: string) => void;
}) {
  const { t } = useTranslation();
  const [menu, setMenu] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) { setMenu(null); setConfirmDelete(null); } };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { setMenu(null); setConfirmDelete(null); } };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [menu]);

  const q = query.trim().toLowerCase();
  const visible = chats
    .filter(c => !q || (c.title || '').toLowerCase().includes(q))
    .sort((a, b) => String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || '')));
  if (!visible.length) return q ? <p className="sb-empty">{t('chNoChatsFound')}</p> : null;

  const grouped: Array<[TranslationKey, ChatItem[]]> = [];
  for (const c of visible) {
    const g = groupOf(c.updated_at || c.created_at);
    const last = grouped[grouped.length - 1];
    if (last && last[0] === g) last[1].push(c); else grouped.push([g, [c]]);
  }

  return (
    <div className="sb-chats" ref={ref} data-testid="sidebar-chats">
      {grouped.map(([g, list]) => (
        <div key={g} className="sb-group">
          <div className="sb-label">{t(g)}</div>
          {list.map(c => (
            <div key={c.id} className={`sb-chat ${activeId === c.id ? 'active' : ''}`} data-testid={`chat-item-${c.id}`}>
              {editing?.id === c.id ? (
                <input className="sb-rename" autoFocus value={editing.text} aria-label={t('rename')}
                  onChange={e => setEditing({ id: c.id, text: e.target.value })}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && editing.text.trim()) { onRename(c.id, editing.text.trim()); setEditing(null); }
                    if (e.key === 'Escape') setEditing(null);
                  }}
                  onBlur={() => { if (editing.text.trim() && editing.text.trim() !== c.title) onRename(c.id, editing.text.trim()); setEditing(null); }} />
              ) : (
                <button type="button" className="sb-chat-open" onClick={() => onOpen(c.id)} title={c.title || t('chUntitled')}>
                  {c.title || t('chUntitled')}
                </button>
              )}
              {editing?.id !== c.id && (
                <button type="button" className="sb-chat-more" aria-label={t('chChatOptions')} aria-expanded={menu === c.id} onClick={() => { setMenu(menu === c.id ? null : c.id); setConfirmDelete(null); }}>
                  <MoreHorizontal size={15} />
                </button>
              )}
              {menu === c.id && (
                <div className="sb-menu" role="menu">
                  <button type="button" role="menuitem" onClick={() => { setEditing({ id: c.id, text: c.title || '' }); setMenu(null); }}><Pencil size={14} />{t('rename')}</button>
                  {confirmDelete === c.id ? (
                    <button type="button" role="menuitem" className="danger" onClick={() => { onDelete(c.id); setMenu(null); setConfirmDelete(null); }} data-testid="chat-delete-confirm"><Trash2 size={14} />{t('chDeleteConfirm')}</button>
                  ) : (
                    <button type="button" role="menuitem" className="danger" onClick={() => setConfirmDelete(c.id)}><Trash2 size={14} />{t('delete')}</button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
