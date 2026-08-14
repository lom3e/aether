import { useState } from 'react';
import {
  Sparkles, MessageSquare, Bot, Users, Database, Settings, ShoppingBag,
  Plus, ChevronLeft, ChevronRight, Moon, Sun, Globe, Trash2, Search
} from 'lucide-react';
import { useTranslation } from './i18n';
import { useTheme } from './theme';

interface SidebarProps {
  currentView: string;
  onNavigate: (view: string) => void;
  workspaceName: string;
  conversations: any[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
  onDeleteConversation: (id: string) => void;
  onOpenCommandPalette: () => void;
}

export function Sidebar({
  currentView,
  onNavigate,
  workspaceName,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onOpenCommandPalette
}: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [hoveredConv, setHoveredConv] = useState<string | null>(null);
  const { t, language, setLanguage } = useTranslation();
  const { theme, setTheme, isDark } = useTheme();

  const toggleLanguage = () => {
    setLanguage(language === 'en' ? 'it' : 'en');
  };

  const toggleTheme = () => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  };

  const formatRelativeTime = (isoString?: string) => {
    if (!isoString) return '';
    const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
    if (diff < 60) return 'now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    return `${Math.floor(diff / 86400)}d`;
  };

  return (
    <div style={{
      width: collapsed ? '68px' : '260px',
      height: '100vh',
      borderRight: '1px solid hsl(var(--border))',
      backgroundColor: 'hsl(var(--card))',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between',
      transition: 'width 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
      flexShrink: 0,
      zIndex: 10
    }}>
      {/* Top Section */}
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        {/* Workspace Brand Header */}
        <div style={{
          padding: '16px',
          borderBottom: '1px solid hsl(var(--border)/0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between'
        }}>
          {!collapsed ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
              <div style={{
                width: '28px',
                height: '28px',
                borderRadius: '6px',
                backgroundColor: 'hsl(var(--primary))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'hsl(var(--primary-fg))',
                fontWeight: 700,
                fontSize: '14px',
                flexShrink: 0
              }}>
                A
              </div>
              <div style={{ overflow: 'hidden' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                  {workspaceName || 'Aether Labs'}
                </div>
                <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', letterSpacing: '0.04em' }}>
                  AI WORKFORCE
                </div>
              </div>
            </div>
          ) : (
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: 'hsl(var(--primary))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'hsl(var(--primary-fg))',
              fontWeight: 700
            }}>
              A
            </div>
          )}

          <button
            className="btn btn-ghost"
            style={{ padding: '4px' }}
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        {/* New Task & Command Palette */}
        <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <button
            className="btn btn-primary"
            style={{ width: '100%', padding: collapsed ? '8px' : '9px 14px' }}
            onClick={onNewConversation}
            title={t('newTask')}
          >
            <Plus size={16} />
            {!collapsed && <span>{t('newTask')}</span>}
          </button>

          {!collapsed && (
            <button
              className="btn btn-secondary"
              style={{ width: '100%', justifyContent: 'space-between', padding: '6px 12px', fontSize: '12px', color: 'hsl(var(--muted-fg))' }}
              onClick={onOpenCommandPalette}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Search size={13} />
                <span>Search</span>
              </div>
              <kbd style={{ fontSize: '10px', background: 'hsl(var(--bg))', padding: '2px 5px', borderRadius: '4px', border: '1px solid hsl(var(--border))' }}>
                ⌘K
              </kbd>
            </button>
          )}
        </div>

        {/* Navigation & Conversations Scroll Area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 10px 16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Main Navigation */}
          <div>
            {!collapsed && (
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', padding: '4px 10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {t('workspace')}
              </div>
            )}
            <button
              className={`btn btn-ghost ${currentView === 'home' ? 'active' : ''}`}
              style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '8px 10px' }}
              onClick={() => onNavigate('home')}
              title={t('navHome')}
            >
              <Sparkles size={16} />
              {!collapsed && <span>{t('navHome')}</span>}
            </button>
          </div>

          {/* Conversations Section */}
          <div>
            {!collapsed && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 10px' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {t('navConversations')}
                </span>
                <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                  {conversations.length}
                </span>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '4px' }}>
              {conversations.slice(0, 10).map(conv => {
                const isActive = currentView === 'chat' && activeConversationId === conv.id;
                const isHovered = hoveredConv === conv.id;

                return (
                  <div
                    key={conv.id}
                    onMouseEnter={() => setHoveredConv(conv.id)}
                    onMouseLeave={() => setHoveredConv(null)}
                    style={{ position: 'relative' }}
                  >
                    <button
                      className={`btn btn-ghost ${isActive ? 'active' : ''}`}
                      style={{
                        width: '100%',
                        justifyContent: collapsed ? 'center' : 'space-between',
                        padding: '7px 10px',
                        fontSize: '12.5px',
                        overflow: 'hidden'
                      }}
                      onClick={() => onSelectConversation(conv.id)}
                      title={conv.title || 'Untitled Task'}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                        <MessageSquare size={14} className={isActive ? 'text-primary' : 'text-muted'} />
                        {!collapsed && (
                          <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                            {conv.title || 'Untitled Task'}
                          </span>
                        )}
                      </div>

                      {!collapsed && !isHovered && (
                        <span style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))', flexShrink: 0 }}>
                          {formatRelativeTime(conv.updated_at)}
                        </span>
                      )}
                    </button>

                    {!collapsed && isHovered && (
                      <button
                        className="btn btn-ghost"
                        style={{
                          position: 'absolute',
                          right: '4px',
                          top: '50%',
                          transform: 'translateY(-50%)',
                          padding: '4px',
                          color: 'hsl(var(--destructive))'
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteConversation(conv.id);
                        }}
                        title={t('deleteConversation')}
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Workforce Entities Section */}
          <div>
            {!collapsed && (
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', padding: '4px 10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {t('workforce')}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '4px' }}>
              <button
                className={`btn btn-ghost ${currentView === 'agents' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '8px 10px' }}
                onClick={() => onNavigate('agents')}
                title={t('navAgents')}
              >
                <Bot size={16} />
                {!collapsed && <span>{t('navAgents')}</span>}
              </button>

              <button
                className={`btn btn-ghost ${currentView === 'teams' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '8px 10px' }}
                onClick={() => onNavigate('teams')}
                title={t('navTeams')}
              >
                <Users size={16} />
                {!collapsed && <span>{t('navTeams')}</span>}
              </button>

              <button
                className={`btn btn-ghost ${currentView === 'knowledge' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '8px 10px' }}
                onClick={() => onNavigate('knowledge')}
                title={t('navKnowledge')}
              >
                <Database size={16} />
                {!collapsed && <span>{t('navKnowledge')}</span>}
              </button>
            </div>
          </div>

          {/* Platform Settings */}
          <div>
            {!collapsed && (
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', padding: '4px 10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {t('platform')}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '4px' }}>
              <button
                className={`btn btn-ghost ${currentView === 'settings' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '8px 10px' }}
                onClick={() => onNavigate('settings')}
                title={t('navSettings')}
              >
                <Settings size={16} />
                {!collapsed && <span>{t('navSettings')}</span>}
              </button>

              <button
                className={`btn btn-ghost ${currentView === 'marketplace' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '8px 10px' }}
                onClick={() => onNavigate('marketplace')}
                title={t('navMarketplace')}
              >
                <ShoppingBag size={16} />
                {!collapsed && <span>{t('navMarketplace')}</span>}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Footer Controls: Language & Theme */}
      <div style={{
        padding: '12px 14px',
        borderTop: '1px solid hsl(var(--border)/0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: collapsed ? 'center' : 'space-between',
        backgroundColor: 'hsl(var(--card))'
      }}>
        {!collapsed ? (
          <>
            <button
              className="btn btn-ghost"
              style={{ padding: '6px 10px', fontSize: '12px' }}
              onClick={toggleLanguage}
              title="Switch Language (EN / IT)"
            >
              <Globe size={14} />
              <span>{language.toUpperCase()}</span>
            </button>

            <button
              className="btn btn-ghost"
              style={{ padding: '6px 10px', fontSize: '12px' }}
              onClick={toggleTheme}
              title="Toggle Theme"
            >
              {isDark ? <Sun size={14} /> : <Moon size={14} />}
              <span>{isDark ? t('themeLight') : t('themeDark')}</span>
            </button>
          </>
        ) : (
          <button
            className="btn btn-ghost"
            style={{ padding: '8px' }}
            onClick={toggleTheme}
            title="Toggle Theme"
          >
            {isDark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        )}
      </div>
    </div>
  );
}
