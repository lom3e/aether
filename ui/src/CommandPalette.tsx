import { useState, useEffect, useRef } from 'react';
import {
  Search, Plus, MessageSquare, Bot, Users, Database, Settings, ShoppingBag,
  Moon, Sun, Globe, X, Sparkles, ArrowRight, Layers, Zap, Keyboard, Puzzle
} from 'lucide-react';
import { useTranslation } from './i18n';
import { useTheme } from './theme';
import { useKeyboardShortcuts } from './shortcuts';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (view: string) => void;
  onNewConversation: () => void;
  conversations: any[];
  onSelectConversation: (id: string) => void;
}

export function CommandPalette({
  isOpen,
  onClose,
  onNavigate,
  onNewConversation,
  conversations,
  onSelectConversation
}: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const { t, language, setLanguage } = useTranslation();
  const { theme, setTheme, isDark } = useTheme();
  const { openShortcutsModal } = useKeyboardShortcuts();

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const defaultActions = [
    {
      id: 'new_task',
      label: `${t('cmdNewTask')} (⌘N)`,
      icon: <Plus size={16} className="text-primary" />,
      run: () => { onNewConversation(); onClose(); }
    },
    {
      id: 'switch_workspace',
      label: `${t('switchWorkspace')} (⌘⇧W)`,
      icon: <Layers size={16} className="text-primary" />,
      run: () => { onNavigate('settings'); onClose(); }
    },
    {
      id: 'go_home',
      label: t('cmdGoHome'),
      icon: <Sparkles size={16} />,
      run: () => { onNavigate('home'); onClose(); }
    },
    {
      id: 'go_agents',
      label: t('cmdGoAgents'),
      icon: <Bot size={16} />,
      run: () => { onNavigate('agents'); onClose(); }
    },
    {
      id: 'go_teams',
      label: t('cmdGoTeams'),
      icon: <Users size={16} />,
      run: () => { onNavigate('teams'); onClose(); }
    },
    {
      id: 'go_knowledge',
      label: t('cmdGoKnowledge'),
      icon: <Database size={16} />,
      run: () => { onNavigate('knowledge'); onClose(); }
    },
    {
      id: 'go_automations',
      label: t('navAutomations'),
      icon: <Zap size={16} />,
      run: () => { onNavigate('automations'); onClose(); }
    },
    {
      id: 'go_skills',
      label: t('navSkills'),
      icon: <Puzzle size={16} />,
      run: () => { onNavigate('skills'); onClose(); }
    },
    {
      id: 'go_settings',
      label: t('cmdGoSettings'),
      icon: <Settings size={16} />,
      run: () => { onNavigate('settings'); onClose(); }
    },
    {
      id: 'show_shortcuts',
      label: `${t('shortcutsTitle')} (⌘/)`,
      icon: <Keyboard size={16} />,
      run: () => {
        onClose();
        openShortcutsModal();
      }
    },
    {
      id: 'go_marketplace',
      label: t('cmdGoMarketplace'),
      icon: <ShoppingBag size={16} />,
      run: () => { onNavigate('marketplace'); onClose(); }
    },
    {
      id: 'toggle_theme',
      label: t('cmdToggleTheme'),
      icon: isDark ? <Sun size={16} /> : <Moon size={16} />,
      run: () => {
        setTheme(theme === 'dark' ? 'light' : 'dark');
        onClose();
      }
    },
    {
      id: 'toggle_lang',
      label: t('cmdSwitchLang'),
      icon: <Globe size={16} />,
      run: () => {
        setLanguage(language === 'en' ? 'it' : 'en');
        onClose();
      }
    }
  ];

  // Filter actions & conversations
  const filteredActions = defaultActions.filter(a =>
    a.label.toLowerCase().includes(query.toLowerCase())
  );

  const filteredConversations = conversations.filter(c =>
    (c.title || '').toLowerCase().includes(query.toLowerCase()) ||
    (c.last_message || '').toLowerCase().includes(query.toLowerCase())
  ).slice(0, 5);

  const allItems = [
    ...filteredActions.map(a => ({ type: 'action', data: a })),
    ...filteredConversations.map(c => ({ type: 'conversation', data: c }))
  ];

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => (prev + 1) % (allItems.length || 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => (prev - 1 + allItems.length) % (allItems.length || 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const current = allItems[selectedIndex];
      if (current) {
        if (current.type === 'action') {
          current.data.run();
        } else {
          onSelectConversation(current.data.id);
          onClose();
        }
      }
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose} style={{ alignItems: 'flex-start', paddingTop: '15vh' }}>
      <div className="command-palette" onClick={e => e.stopPropagation()}>
        <div className="command-input-wrapper">
          <Search size={18} className="text-muted" />
          <input
            ref={inputRef}
            className="form-input"
            style={{ border: 'none', background: 'transparent', padding: '0', fontSize: '15px', boxShadow: 'none' }}
            placeholder={t('cmdSearchPlaceholder')}
            value={query}
            onChange={e => { setQuery(e.target.value); setSelectedIndex(0); }}
            onKeyDown={handleKeyDown}
          />
          <button className="btn btn-ghost" style={{ padding: '4px' }} onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div style={{ maxHeight: '360px', overflowY: 'auto', padding: '8px' }}>
          {filteredActions.length > 0 && (
            <div style={{ marginBottom: '12px' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', padding: '4px 10px', textTransform: 'uppercase' }}>
                {t('platform')}
              </div>
              {filteredActions.map((action, idx) => {
                const isSelected = selectedIndex === idx;
                return (
                  <div
                    key={action.id}
                    className={`command-item ${isSelected ? 'selected' : ''}`}
                    onClick={() => action.run()}
                    onMouseEnter={() => setSelectedIndex(idx)}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {action.icon}
                      <span>{action.label}</span>
                    </div>
                    <ArrowRight size={14} className="text-muted" style={{ opacity: isSelected ? 1 : 0 }} />
                  </div>
                );
              })}
            </div>
          )}

          {filteredConversations.length > 0 && (
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', padding: '4px 10px', textTransform: 'uppercase' }}>
                {t('recentConversations')}
              </div>
              {filteredConversations.map((conv, idx) => {
                const overallIdx = filteredActions.length + idx;
                const isSelected = selectedIndex === overallIdx;
                return (
                  <div
                    key={conv.id}
                    className={`command-item ${isSelected ? 'selected' : ''}`}
                    onClick={() => { onSelectConversation(conv.id); onClose(); }}
                    onMouseEnter={() => setSelectedIndex(overallIdx)}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
                      <MessageSquare size={16} className="text-muted" />
                      <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                        {conv.title || t('untitledTask')}
                      </span>
                    </div>
                    <span className="badge" style={{ fontSize: '10px', flexShrink: 0 }}>
                      {conv.status}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {allItems.length === 0 && (
            <div style={{ padding: '24px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
              {t('noConversationsFound')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
