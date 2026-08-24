import { useState, useMemo } from 'react';
import { Keyboard, X, Search } from 'lucide-react';
import { useKeyboardShortcuts } from './ShortcutsContext';
import { CATEGORY_ORDER } from './registry';
import { useTranslation } from '../i18n';

interface ShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ShortcutsModal({ isOpen, onClose }: ShortcutsModalProps) {
  const { shortcuts, formatShortcut } = useKeyboardShortcuts();
  const { t } = useTranslation();
  const [search, setSearch] = useState('');

  const filteredShortcuts = useMemo(() => {
    if (!search.trim()) return shortcuts;
    const q = search.toLowerCase();
    return shortcuts.filter((s) => {
      const label = (t(s.labelKey as any) || s.labelKey).toLowerCase();
      const cat = s.category.toLowerCase();
      return label.includes(q) || cat.includes(q) || s.key.toLowerCase().includes(q);
    });
  }, [shortcuts, search, t]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose} data-testid="shortcuts-modal">
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: '620px',
          width: '100%',
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          padding: '24px',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                backgroundColor: 'hsl(var(--primary)/0.12)',
                color: 'hsl(var(--primary))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Keyboard size={20} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>{t('shortcutsTitle' as any)}</h3>
              <p style={{ margin: '2px 0 0', fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                {t('shortcutsSubtitle' as any)}
              </p>
            </div>
          </div>
          <button className="btn btn-ghost" onClick={onClose} style={{ padding: '6px' }}>
            <X size={16} />
          </button>
        </div>

        {/* Search Bar */}
        <div style={{ position: 'relative', marginBottom: '18px' }}>
          <Search size={15} style={{ position: 'absolute', left: '12px', top: '10px', color: 'hsl(var(--muted-fg))' }} />
          <input
            className="form-input"
            style={{ paddingLeft: '34px', fontSize: '13px' }}
            placeholder="Search shortcuts..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
        </div>

        {/* Grouped Shortcuts List */}
        <div style={{ flex: 1, overflowY: 'auto', paddingRight: '4px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {CATEGORY_ORDER.map((group) => {
            const groupShortcuts = filteredShortcuts.filter((s) => s.category === group.category);
            if (groupShortcuts.length === 0) return null;

            return (
              <div key={group.category}>
                <div
                  style={{
                    fontSize: '11px',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    color: 'hsl(var(--muted-fg))',
                    marginBottom: '8px',
                    paddingBottom: '4px',
                    borderBottom: '1px solid hsl(var(--border)/0.6)',
                  }}
                >
                  {t(group.labelKey as any)}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {groupShortcuts.map((shortcut) => {
                    const keys = formatShortcut(shortcut);
                    const label = t(shortcut.labelKey as any) || shortcut.labelKey;

                    return (
                      <div
                        key={shortcut.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '8px 10px',
                          borderRadius: '6px',
                          backgroundColor: 'hsl(var(--muted)/0.3)',
                        }}
                      >
                        <span style={{ fontSize: '13px', color: 'hsl(var(--fg))' }}>{label}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          {keys.map((k, idx) => (
                            <kbd
                              key={idx}
                              style={{
                                padding: '2px 7px',
                                fontSize: '11px',
                                fontWeight: 600,
                                fontFamily: 'inherit',
                                backgroundColor: 'hsl(var(--card))',
                                border: '1px solid hsl(var(--border))',
                                borderRadius: '4px',
                                boxShadow: '0 1px 2px hsl(var(--fg)/0.05)',
                                color: 'hsl(var(--fg))',
                              }}
                            >
                              {k}
                            </kbd>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid hsl(var(--border))', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
            Press <kbd style={{ padding: '1px 5px', fontSize: '10px', border: '1px solid hsl(var(--border))', borderRadius: '3px' }}>Esc</kbd> to dismiss
          </span>
          <button className="btn btn-secondary" onClick={onClose} style={{ fontSize: '12.5px', padding: '6px 14px' }}>
            {t('close')}
          </button>
        </div>
      </div>
    </div>
  );
}
