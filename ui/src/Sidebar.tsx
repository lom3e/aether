import { useState, useEffect, useRef } from 'react';
import {
  Sparkles, MessageSquare, Bot, Users, Database, Settings, ShoppingBag,
  Plus, ChevronLeft, ChevronRight, Moon, Sun, Globe, Trash2, Search,
  ChevronDown, MoreVertical, Archive, Copy, Edit2, Check
} from 'lucide-react';
import { useTranslation } from './i18n';
import { useTheme } from './theme';
import { apiUrl } from './api';

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
  onOpenWorkspaceModal?: (mode: 'create' | 'manage') => void;
  onRefreshConversations?: () => void;
  onWorkspaceSwitched?: () => void;
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
  onOpenCommandPalette,
  onOpenWorkspaceModal,
  onRefreshConversations,
  onWorkspaceSwitched
}: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [hoveredConv, setHoveredConv] = useState<string | null>(null);
  const [activeMenuConvId, setActiveMenuConvId] = useState<string | null>(null);
  const [editingConvId, setEditingConvId] = useState<string | null>(null);
  const [editTitleValue, setEditTitleValue] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  // Workspace Switcher Dropdown
  const [isWsDropdownOpen, setIsWsDropdownOpen] = useState(false);
  const [allWorkspaces, setAllWorkspaces] = useState<any[]>([]);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const convMenuRef = useRef<HTMLDivElement>(null);

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

  // Fetch workspaces list for dropdown
  const fetchWorkspaces = () => {
    fetch(apiUrl('/api/workspaces'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setAllWorkspaces(data);
        }
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchWorkspaces();
  }, [workspaceName]);

  // Click outside listener for popovers
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsWsDropdownOpen(false);
      }
      if (convMenuRef.current && !convMenuRef.current.contains(e.target as Node)) {
        setActiveMenuConvId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSwitchWorkspace = async (ws: any) => {
    if (ws.is_active) {
      setIsWsDropdownOpen(false);
      return;
    }
    try {
      const res = await fetch(apiUrl('/api/workspaces/switch'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workspace_id: ws.id, path: ws.path })
      });
      if (res.ok) {
        setIsWsDropdownOpen(false);
        if (onWorkspaceSwitched) onWorkspaceSwitched();
      }
    } catch (err) {
      console.error('Failed to switch workspace', err);
    }
  };

  const handleRenameConversation = async (convId: string) => {
    if (!editTitleValue.trim()) {
      setEditingConvId(null);
      return;
    }
    try {
      const res = await fetch(apiUrl(`/api/conversations/${convId}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: editTitleValue.trim() })
      });
      if (res.ok) {
        setEditingConvId(null);
        if (onRefreshConversations) onRefreshConversations();
      }
    } catch (err) {
      console.error('Failed to rename conversation', err);
    }
  };

  const handleDuplicateConversation = async (convId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/conversations/${convId}/duplicate`), {
        method: 'POST'
      });
      if (res.ok) {
        setActiveMenuConvId(null);
        if (onRefreshConversations) onRefreshConversations();
      }
    } catch (err) {
      console.error('Failed to duplicate conversation', err);
    }
  };

  const handleArchiveConversation = async (convId: string, currentStatus: string) => {
    const isArchived = currentStatus === 'archived';
    try {
      const res = await fetch(apiUrl(`/api/conversations/${convId}/archive`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archived: !isArchived })
      });
      if (res.ok) {
        setActiveMenuConvId(null);
        if (onRefreshConversations) onRefreshConversations();
      }
    } catch (err) {
      console.error('Failed to archive conversation', err);
    }
  };

  // Filter conversations
  const filteredConversations = conversations.filter(c => {
    const matchesSearch = !searchQuery.trim() ||
      (c.title || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.last_message || '').toLowerCase().includes(searchQuery.toLowerCase());
    const matchesArchive = showArchived ? c.status === 'archived' : c.status !== 'archived';
    return matchesSearch && matchesArchive;
  });

  return (
    <aside className="sidebar" style={{
      width: collapsed ? '68px' : '260px',
      height: '100vh',
      borderRight: '1px solid hsl(var(--border))',
      backgroundColor: 'hsl(var(--card))',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between',
      transition: 'width 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
      flexShrink: 0,
      zIndex: 10,
      position: 'relative'
    }}>
      {/* Top Section */}
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        {/* Workspace Switcher Header */}
        <div style={{
          padding: '12px 14px',
          borderBottom: '1px solid hsl(var(--border)/0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          position: 'relative'
        }} ref={dropdownRef}>
          {!collapsed ? (
            <button
              className="btn btn-ghost"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '6px 8px',
                borderRadius: '8px',
                maxWidth: '200px',
                overflow: 'hidden'
              }}
              onClick={() => {
                fetchWorkspaces();
                setIsWsDropdownOpen(!isWsDropdownOpen);
              }}
            >
              <div style={{
                width: '26px',
                height: '26px',
                borderRadius: '6px',
                backgroundColor: 'hsl(var(--primary)/0.12)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0
              }}>
                <img
                  src={isDark ? "/brand/logo_bianco.svg" : "/brand/logo_nero.svg"}
                  alt="Aether Logo"
                  width="18"
                  height="18"
                  style={{ width: '18px', height: '18px', display: 'block' }}
                />
              </div>
              <div style={{ overflow: 'hidden', textAlign: 'left' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span>{workspaceName || (language === 'it' ? 'Nessun workspace' : 'No workspace')}</span>
                  <ChevronDown size={12} className="text-muted" />
                </div>
                <div style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))', letterSpacing: '0.04em' }}>
                  {workspaceName ? 'AI WORKFORCE' : (language === 'it' ? 'CLICCA PER CREARE' : 'CLICK TO CREATE')}
                </div>
              </div>
            </button>
          ) : (
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                backgroundColor: 'hsl(var(--primary)/0.12)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer'
              }}
              onClick={() => setCollapsed(false)}
            >
              <img
                src={isDark ? "/brand/logo_bianco.svg" : "/brand/logo_nero.svg"}
                alt="Aether Logo"
                width="20"
                height="20"
                style={{ width: '20px', height: '20px', display: 'block' }}
              />
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

          {/* Workspace Switcher Popover Dropdown */}
          {isWsDropdownOpen && !collapsed && (
            <div style={{
              position: 'absolute',
              top: '56px',
              left: '12px',
              width: '236px',
              backgroundColor: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: '8px',
              boxShadow: '0 10px 25px rgba(0,0,0,0.3)',
              padding: '6px',
              zIndex: 100,
              display: 'flex',
              flexDirection: 'column',
              gap: '2px'
            }}>
              <div style={{ fontSize: '10px', fontWeight: 600, color: 'hsl(var(--muted-fg))', padding: '4px 8px', textTransform: 'uppercase' }}>
                Workspaces
              </div>
              <div style={{ maxHeight: '180px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                {allWorkspaces.length === 0 ? (
                  <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', padding: '6px 8px' }}>
                    {language === 'it' ? 'Nessun workspace salvato' : 'No workspaces saved'}
                  </div>
                ) : (
                  allWorkspaces.map(ws => (
                    <button
                      key={ws.id || ws.path}
                      className={`btn btn-ghost ${ws.is_active ? 'active' : ''}`}
                      style={{
                        width: '100%',
                        justifyContent: 'space-between',
                        padding: '6px 8px',
                        fontSize: '12px',
                        borderRadius: '6px'
                      }}
                      onClick={() => handleSwitchWorkspace(ws)}
                    >
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {ws.name}
                      </span>
                      {ws.is_active && <Check size={13} className="text-primary" />}
                    </button>
                  ))
                )}
              </div>

              <div style={{ height: '1px', backgroundColor: 'hsl(var(--border))', margin: '4px 0' }} />

              <button
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'flex-start', padding: '6px 8px', fontSize: '12px' }}
                onClick={() => {
                  setIsWsDropdownOpen(false);
                  if (onOpenWorkspaceModal) onOpenWorkspaceModal('create');
                }}
              >
                <Plus size={13} /> + New Workspace
              </button>

              <button
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'flex-start', padding: '6px 8px', fontSize: '12px' }}
                onClick={() => {
                  setIsWsDropdownOpen(false);
                  onNavigate('settings');
                }}
              >
                <Settings size={13} /> ⚙ Manage Workspaces
              </button>
            </div>
          )}
        </div>

        {/* New Task & Command Palette */}
        <div style={{ padding: '10px 12px 6px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <button
            className="btn btn-primary"
            style={{ width: '100%', padding: collapsed ? '8px' : '8px 12px', fontSize: '13px' }}
            onClick={() => {
              if (!workspaceName) {
                if (onOpenWorkspaceModal) onOpenWorkspaceModal('create');
              } else {
                onNewConversation();
              }
            }}
            title={t('newTask')}
          >
            <Plus size={15} />
            {!collapsed && <span>{t('newTask')}</span>}
          </button>

          {!collapsed && (
            <div style={{ position: 'relative', marginTop: '2px', display: 'flex', gap: '4px' }}>
              <div style={{ position: 'relative', flex: 1 }}>
                <Search size={12} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'hsl(var(--muted-fg))' }} />
                <input
                  type="text"
                  className="form-input"
                  placeholder="Search..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  style={{
                    padding: '5px 8px 5px 28px',
                    fontSize: '12px',
                    height: '28px',
                    borderRadius: '6px'
                  }}
                />
              </div>
              <button
                className="btn btn-ghost"
                style={{ padding: '4px 6px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}
                onClick={onOpenCommandPalette}
                title="Command Palette (⌘K)"
              >
                ⌘K
              </button>
            </div>
          )}
        </div>

        {/* Navigation & Conversations Scroll Area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '6px 8px 16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* Main Navigation */}
          <div>
            {!collapsed && (
              <div style={{ fontSize: '10px', fontWeight: 600, color: 'hsl(var(--muted-fg))', padding: '2px 8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {t('workspace')}
              </div>
            )}
            <button
              className={`btn btn-ghost ${currentView === 'home' ? 'active' : ''}`}
              style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
              onClick={() => onNavigate('home')}
              title={t('navHome')}
            >
              <Sparkles size={15} />
              {!collapsed && <span>{t('navHome')}</span>}
            </button>
          </div>

          {/* Conversations Section */}
          <div ref={convMenuRef}>
            {!collapsed && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 8px', marginBottom: '4px' }}>
                <span style={{ fontSize: '10px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {showArchived ? 'Archived' : t('navConversations')}
                </span>
                <button
                  className="btn btn-ghost"
                  style={{ padding: '2px 4px', fontSize: '10px', color: 'hsl(var(--muted-fg))' }}
                  onClick={() => setShowArchived(!showArchived)}
                  title={showArchived ? 'Show Active' : 'Show Archived'}
                >
                  {showArchived ? 'Active' : 'Archived'}
                </button>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              {filteredConversations.slice(0, 15).map(conv => {
                const isActive = currentView === 'chat' && activeConversationId === conv.id;
                const isHovered = hoveredConv === conv.id;
                const isMenuOpen = activeMenuConvId === conv.id;
                const isEditing = editingConvId === conv.id;

                return (
                  <div
                    key={conv.id}
                    onMouseEnter={() => setHoveredConv(conv.id)}
                    onMouseLeave={() => setHoveredConv(null)}
                    style={{ position: 'relative' }}
                  >
                    {isEditing ? (
                      <div style={{ padding: '4px 6px', display: 'flex', gap: '4px' }}>
                        <input
                          type="text"
                          className="form-input"
                          style={{ padding: '3px 6px', fontSize: '12px', height: '26px' }}
                          value={editTitleValue}
                          onChange={e => setEditTitleValue(e.target.value)}
                          autoFocus
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleRenameConversation(conv.id);
                            if (e.key === 'Escape') setEditingConvId(null);
                          }}
                        />
                      </div>
                    ) : (
                      <button
                        className={`btn btn-ghost ${isActive ? 'active' : ''}`}
                        style={{
                          width: '100%',
                          justifyContent: collapsed ? 'center' : 'space-between',
                          padding: '6px 8px',
                          fontSize: '12.5px',
                          overflow: 'hidden'
                        }}
                        onClick={() => onSelectConversation(conv.id)}
                        onDoubleClick={() => {
                          setEditingConvId(conv.id);
                          setEditTitleValue(conv.title || '');
                        }}
                        title={conv.title || 'Untitled Task'}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                          <MessageSquare size={13} className={isActive ? 'text-primary' : (conv.unread ? 'text-primary' : 'text-muted')} />
                          {!collapsed && (
                            <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', fontWeight: conv.unread && !isActive ? 600 : 400 }}>
                              {conv.title || 'Untitled Task'}
                            </span>
                          )}
                        </div>

                        {!collapsed && !isHovered && !isMenuOpen && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            {conv.unread && !isActive && (
                              <span
                                className="unread-dot"
                                style={{
                                  width: '6px',
                                  height: '6px',
                                  borderRadius: '50%',
                                  backgroundColor: 'hsl(var(--primary))',
                                  boxShadow: '0 0 6px hsl(var(--primary)/0.6)',
                                  flexShrink: 0
                                }}
                              />
                            )}
                            <span style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))', flexShrink: 0 }}>
                              {formatRelativeTime(conv.updated_at)}
                            </span>
                          </div>
                        )}
                      </button>
                    )}

                    {!collapsed && (isHovered || isMenuOpen) && !isEditing && (
                      <button
                        className="btn btn-ghost"
                        style={{
                          position: 'absolute',
                          right: '4px',
                          top: '50%',
                          transform: 'translateY(-50%)',
                          padding: '4px',
                          color: 'hsl(var(--fg))'
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveMenuConvId(isMenuOpen ? null : conv.id);
                        }}
                        title="Conversation Actions"
                      >
                        <MoreVertical size={13} />
                      </button>
                    )}

                    {/* Dropdown Menu for Conversation Actions */}
                    {isMenuOpen && !collapsed && (
                      <div style={{
                        position: 'absolute',
                        right: '4px',
                        top: '100%',
                        backgroundColor: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px',
                        boxShadow: '0 10px 25px rgba(0,0,0,0.3)',
                        padding: '4px',
                        zIndex: 50,
                        width: '140px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '2px'
                      }}>
                        <button
                          className="btn btn-ghost"
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '5px 8px', fontSize: '12px' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingConvId(conv.id);
                            setEditTitleValue(conv.title || '');
                            setActiveMenuConvId(null);
                          }}
                        >
                          <Edit2 size={12} /> Rename
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '5px 8px', fontSize: '12px' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDuplicateConversation(conv.id);
                          }}
                        >
                          <Copy size={12} /> Duplicate
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '5px 8px', fontSize: '12px' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleArchiveConversation(conv.id, conv.status);
                          }}
                        >
                          <Archive size={12} /> {conv.status === 'archived' ? 'Unarchive' : 'Archive'}
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '5px 8px', fontSize: '12px', color: 'hsl(var(--destructive))' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveMenuConvId(null);
                            onDeleteConversation(conv.id);
                          }}
                        >
                          <Trash2 size={12} /> Delete
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Workforce Section */}
          <div>
            {!collapsed && (
              <div style={{ fontSize: '10px', fontWeight: 600, color: 'hsl(var(--muted-fg))', padding: '2px 8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {t('workforce')}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '2px' }}>
              <button
                className={`btn btn-ghost ${currentView === 'agents' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                onClick={() => onNavigate('agents')}
                title={t('navAgents')}
              >
                <Bot size={15} />
                {!collapsed && <span>{t('navAgents')}</span>}
              </button>

              <button
                className={`btn btn-ghost ${currentView === 'teams' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                onClick={() => onNavigate('teams')}
                title={t('navTeams')}
              >
                <Users size={15} />
                {!collapsed && <span>{t('navTeams')}</span>}
              </button>

              <button
                className={`btn btn-ghost ${currentView === 'knowledge' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                onClick={() => onNavigate('knowledge')}
                title={t('navKnowledge')}
              >
                <Database size={15} />
                {!collapsed && <span>{t('navKnowledge')}</span>}
              </button>
            </div>
          </div>

          {/* Platform Settings */}
          <div>
            {!collapsed && (
              <div style={{ fontSize: '10px', fontWeight: 600, color: 'hsl(var(--muted-fg))', padding: '2px 8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {t('platform')}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '2px' }}>
              <button
                className={`btn btn-ghost ${currentView === 'settings' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                onClick={() => onNavigate('settings')}
                title={t('navSettings')}
              >
                <Settings size={15} />
                {!collapsed && <span>{t('navSettings')}</span>}
              </button>

              <button
                className={`btn btn-ghost ${currentView === 'marketplace' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                onClick={() => onNavigate('marketplace')}
                title={t('navMarketplace')}
              >
                <ShoppingBag size={15} />
                {!collapsed && <span>{t('navMarketplace')}</span>}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Footer: Language & Theme */}
      <div style={{
        padding: '10px',
        borderTop: '1px solid hsl(var(--border)/0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: collapsed ? 'center' : 'space-between',
        backgroundColor: 'hsl(var(--card))'
      }}>
        {!collapsed ? (
          <>
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                className="btn btn-ghost"
                style={{ padding: '6px 8px', fontSize: '12px' }}
                onClick={toggleLanguage}
                title="Change Language"
              >
                <Globe size={14} />
                <span>{language.toUpperCase()}</span>
              </button>
            </div>

            <button
              className="btn btn-ghost"
              style={{ padding: '6px' }}
              onClick={toggleTheme}
              title={isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
            >
              {isDark ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          </>
        ) : (
          <button className="btn btn-ghost" style={{ padding: '6px' }} onClick={toggleTheme}>
            {isDark ? <Sun size={14} /> : <Moon size={14} />}
          </button>
        )}
      </div>
    </aside>
  );
}
