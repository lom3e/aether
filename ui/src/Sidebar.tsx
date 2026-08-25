import { useState, useEffect, useRef, useContext } from 'react';
import {
  Sparkles, MessageSquare, Bot, Users, Database, Settings, ShoppingBag,
  Plus, ChevronLeft, Moon, Sun, Globe, Trash2, Search,
  ChevronDown, MoreVertical, Archive, Copy, Edit2, Check,
  Pin, Folder, GitBranch, ExternalLink, RefreshCw, X, Zap, Puzzle
} from 'lucide-react';
import { useTranslation } from './i18n';
import { useTheme } from './theme';
import { apiUrl } from './api';
import { Tooltip } from './Tooltip';
import { ToastContext } from './toast';

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
  workspaceVersion?: number;
}

export function Sidebar({
  currentView,
  onNavigate,
  workspaceName,
  workspaceVersion = 0,
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

  // Projects State
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editProjectName, setEditProjectName] = useState('');
  const [activeProjectMenuId, setActiveProjectMenuId] = useState<string | null>(null);

  // GitHub Modal State (P3-03)
  const [activeGithubProject, setActiveGithubProject] = useState<any | null>(null);
  const [githubOwner, setGithubOwner] = useState('');
  const [githubRepo, setGithubRepo] = useState('');
  const [githubToken, setGithubToken] = useState('');
  const [githubLoading, setGithubLoading] = useState(false);
  const [githubError, setGithubError] = useState<string | null>(null);

  // Workspace Switcher Dropdown
  const [isWsDropdownOpen, setIsWsDropdownOpen] = useState(false);
  const [allWorkspaces, setAllWorkspaces] = useState<any[]>([]);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const convMenuRef = useRef<HTMLDivElement>(null);
  const projectSectionRef = useRef<HTMLDivElement>(null);

  const showToast = useContext(ToastContext);
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

  const fetchProjects = () => {
    fetch(apiUrl('/api/projects'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setProjects(data);
        }
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchWorkspaces();
    fetchProjects();
  }, [workspaceName, workspaceVersion]);

  // Click outside listener for popovers
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (dropdownRef.current && !dropdownRef.current.contains(target)) {
        setIsWsDropdownOpen(false);
      }
      if (convMenuRef.current && !convMenuRef.current.contains(target)) {
        setActiveMenuConvId(null);
      }
      if (projectSectionRef.current && !projectSectionRef.current.contains(target)) {
        setActiveProjectMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) {
      setIsCreatingProject(false);
      return;
    }
    try {
      const res = await fetch(apiUrl('/api/projects'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newProjectName.trim() })
      });
      if (res.ok) {
        setNewProjectName('');
        setIsCreatingProject(false);
        fetchProjects();
        showToast('Project created successfully', 'success');
      }
    } catch (err) {
      console.error('Failed to create project', err);
      showToast('Failed to create project', 'error');
    }
  };

  const handleRenameProject = async (id: string) => {
    if (!editProjectName.trim()) {
      setEditingProjectId(null);
      return;
    }
    try {
      const res = await fetch(apiUrl(`/api/projects/${id}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: editProjectName.trim() })
      });
      if (res.ok) {
        setEditingProjectId(null);
        fetchProjects();
        showToast('Project renamed', 'success');
      } else {
        showToast('Error updating project name', 'error');
      }
    } catch (err) {
      console.error('Failed to rename project', err);
      showToast('Failed to rename project', 'error');
    }
  };

  const handleDeleteProject = async (id: string) => {
    try {
      const res = await fetch(apiUrl(`/api/projects/${id}`), {
        method: 'DELETE'
      });
      if (res.ok) {
        if (selectedProjectId === id) setSelectedProjectId(null);
        fetchProjects();
        if (onRefreshConversations) onRefreshConversations();
        showToast('Project deleted', 'info');
      } else {
        showToast('Failed to delete project', 'error');
      }
    } catch (err) {
      console.error('Failed to delete project', err);
      showToast('Failed to delete project', 'error');
    }
  };

  const openGithubModal = (p: any) => {
    setActiveGithubProject(p);
    setGithubError(null);
    if (p.github_repository) {
      setGithubOwner(p.github_repository.owner || '');
      setGithubRepo(p.github_repository.repository || '');
    } else {
      setGithubOwner('');
      setGithubRepo('');
    }
    setGithubToken('');
    setActiveProjectMenuId(null);
  };

  const handleConnectGithub = async () => {
    if (!activeGithubProject || !githubOwner.trim() || !githubRepo.trim()) return;
    setGithubLoading(true);
    setGithubError(null);
    try {
      const res = await fetch(apiUrl(`/api/projects/${activeGithubProject.id}/github`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          owner: githubOwner.trim(),
          repository: githubRepo.trim(),
          token: githubToken.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to connect repository.');
      }
      setActiveGithubProject((curr: any) => curr ? { ...curr, github_repository: data.repository } : null);
      fetchProjects();
    } catch (err: any) {
      setGithubError(err.message || 'Failed to connect repository.');
    } finally {
      setGithubLoading(false);
    }
  };

  const handleVerifyGithub = async () => {
    if (!activeGithubProject) return;
    setGithubLoading(true);
    setGithubError(null);
    try {
      const res = await fetch(apiUrl(`/api/projects/${activeGithubProject.id}/github/verify`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: githubToken.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Verification failed.');
      }
      setActiveGithubProject((curr: any) => curr ? {
        ...curr,
        github_repository: { ...curr.github_repository, ...data }
      } : null);
      fetchProjects();
    } catch (err: any) {
      setGithubError(err.message || 'Verification failed.');
    } finally {
      setGithubLoading(false);
    }
  };

  const handleDisconnectGithub = async () => {
    if (!activeGithubProject) return;
    setGithubLoading(true);
    setGithubError(null);
    try {
      const res = await fetch(apiUrl(`/api/projects/${activeGithubProject.id}/github`), {
        method: 'DELETE',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to disconnect repository.');
      }
      setActiveGithubProject((curr: any) => curr ? { ...curr, github_repository: null } : null);
      setGithubOwner('');
      setGithubRepo('');
      setGithubToken('');
      fetchProjects();
    } catch (err: any) {
      setGithubError(err.message || 'Failed to disconnect repository.');
    } finally {
      setGithubLoading(false);
    }
  };

  const handlePinConversation = async (convId: string, currentPinned: boolean) => {
    try {
      const res = await fetch(apiUrl(`/api/conversations/${convId}/pin`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pinned: !currentPinned })
      });
      if (res.ok) {
        setActiveMenuConvId(null);
        if (onRefreshConversations) onRefreshConversations();
      }
    } catch (err) {
      console.error('Failed to pin conversation', err);
    }
  };

  const handleAssignProject = async (convId: string, projectId: string | null) => {
    try {
      const res = await fetch(apiUrl(`/api/conversations/${convId}/project`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId })
      });
      if (res.ok) {
        setActiveMenuConvId(null);
        fetchProjects();
        if (onRefreshConversations) onRefreshConversations();
      }
    } catch (err) {
      console.error('Failed to assign conversation to project', err);
    }
  };

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
    const matchesProject = !selectedProjectId ||
      (selectedProjectId === 'none' ? (!c.project_id) : c.project_id === selectedProjectId);
    return matchesSearch && matchesArchive && matchesProject;
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
          padding: collapsed ? '10px 8px' : '12px 14px',
          borderBottom: '1px solid hsl(var(--border)/0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          position: 'relative'
        }} ref={dropdownRef}>
          {!collapsed ? (
            <>
              <button
                className="btn btn-ghost"
                data-testid="workspace-switcher-button"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '6px 8px',
                  borderRadius: '8px',
                  maxWidth: '190px',
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
                    src="/brand/logo_viola.svg"
                    alt="Aether Logo"
                    width="18"
                    height="18"
                    style={{ width: '18px', height: '18px', objectFit: 'contain', display: 'block' }}
                  />
                </div>
                <div style={{ overflow: 'hidden', textAlign: 'left' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span>{workspaceName || t('noWorkspace')}</span>
                    <ChevronDown size={12} className="text-muted" />
                  </div>
                  <div style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))', letterSpacing: '0.04em' }}>
                    {workspaceName ? t('aiWorkforce') : t('clickToCreate')}
                  </div>
                </div>
              </button>

              <Tooltip content={t('collapseSidebar')} position="bottom">
                <button
                  className="btn btn-ghost"
                  style={{ padding: '6px', borderRadius: '6px' }}
                  onClick={() => setCollapsed(true)}
                  aria-label="Collapse Sidebar"
                >
                  <ChevronLeft size={16} />
                </button>
              </Tooltip>
            </>
          ) : (
            <Tooltip content={t('expandSidebar')} position="right">
              <button
                className="btn btn-ghost"
                style={{
                  width: '44px',
                  height: '44px',
                  minWidth: '44px',
                  minHeight: '44px',
                  padding: '0',
                  borderRadius: '10px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  backgroundColor: 'hsl(var(--primary)/0.08)',
                  transition: 'background-color 0.15s ease, transform 0.15s ease'
                }}
                onClick={() => setCollapsed(false)}
                aria-label="Expand Sidebar"
              >
                <img
                  src="/brand/logo_viola.svg"
                  alt="Aether Logo"
                  width="26"
                  height="26"
                  style={{
                    width: '26px',
                    height: '26px',
                    objectFit: 'contain',
                    display: 'block'
                  }}
                />
              </button>
            </Tooltip>
          )}

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
                {t('allWorkspaces')}
              </div>
              <div style={{ maxHeight: '180px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                {allWorkspaces.length === 0 ? (
                  <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', padding: '6px 8px' }}>
                    {t('noWorkspacesSaved')}
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
                <Plus size={13} /> {t('newWorkspaceBtn')}
              </button>

              <button
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'flex-start', padding: '6px 8px', fontSize: '12px' }}
                onClick={() => {
                  setIsWsDropdownOpen(false);
                  onNavigate('settings');
                }}
              >
                <Settings size={13} /> {t('manageWorkspaces')}
              </button>
            </div>
          )}
        </div>

        {/* New Task & Command Palette */}
        <div style={{ padding: '10px 12px 6px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <Tooltip content={t('newTask')} position={collapsed ? 'right' : 'top'}>
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
            >
              <Plus size={15} />
              {!collapsed && <span>{t('newTask')}</span>}
            </button>
          </Tooltip>

          {!collapsed && (
            <div style={{ position: 'relative', marginTop: '2px', display: 'flex', gap: '4px' }}>
              <div style={{ position: 'relative', flex: 1 }}>
                <Search size={12} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'hsl(var(--muted-fg))' }} />
                <input
                  type="text"
                  className="form-input"
                  data-testid="sidebar-search-input"
                  placeholder={t('searchPlaceholder')}
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
              <Tooltip content="Command Palette (⌘K)" position="top">
                <button
                  className="btn btn-ghost"
                  style={{ padding: '4px 6px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}
                  onClick={onOpenCommandPalette}
                >
                  ⌘K
                </button>
              </Tooltip>
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
            <Tooltip content={t('navHome')} position={collapsed ? 'right' : 'top'} disabled={!collapsed}>
              <button
                className={`btn btn-ghost ${currentView === 'home' ? 'active' : ''}`}
                style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                onClick={() => onNavigate('home')}
              >
                <Sparkles size={15} />
                {!collapsed && <span>{t('navHome')}</span>}
              </button>
            </Tooltip>
          </div>

          {/* Projects Section */}
          <div ref={projectSectionRef}>
            {!collapsed && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 8px', marginBottom: '4px' }}>
                <span style={{ fontSize: '10px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Projects
                </span>
                <Tooltip content="New Project" position="top">
                  <button
                    className="btn btn-ghost"
                    style={{ padding: '2px 4px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}
                    onClick={() => setIsCreatingProject(!isCreatingProject)}
                  >
                    <Plus size={13} />
                  </button>
                </Tooltip>
              </div>
            )}

            {isCreatingProject && !collapsed && (
              <div style={{ padding: '4px 6px', display: 'flex', gap: '4px', marginBottom: '4px' }}>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Project name..."
                  style={{ padding: '3px 6px', fontSize: '12px', height: '26px' }}
                  value={newProjectName}
                  onChange={e => setNewProjectName(e.target.value)}
                  autoFocus
                  onKeyDown={e => {
                    if (e.key === 'Enter') handleCreateProject();
                    if (e.key === 'Escape') setIsCreatingProject(false);
                  }}
                />
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              {selectedProjectId && !collapsed && (
                <button
                  className="btn btn-ghost"
                  style={{ width: '100%', justifyContent: 'space-between', padding: '5px 8px', fontSize: '11.5px', color: 'hsl(var(--primary))' }}
                  onClick={() => setSelectedProjectId(null)}
                >
                  <span>← Show All Conversations</span>
                </button>
              )}

              {projects.map(p => {
                const isSelected = selectedProjectId === p.id;
                const isEditing = editingProjectId === p.id;
                const isMenuOpen = activeProjectMenuId === p.id;

                return (
                  <div key={p.id} style={{ position: 'relative' }}>
                    {isEditing ? (
                      <div style={{ padding: '4px 6px', display: 'flex', gap: '4px' }}>
                        <input
                          type="text"
                          className="form-input"
                          style={{ padding: '3px 6px', fontSize: '12px', height: '26px' }}
                          value={editProjectName}
                          onChange={e => setEditProjectName(e.target.value)}
                          autoFocus
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleRenameProject(p.id);
                            if (e.key === 'Escape') setEditingProjectId(null);
                          }}
                        />
                      </div>
                    ) : (
                      <button
                        className={`btn btn-ghost ${isSelected ? 'active' : ''}`}
                        style={{
                          width: '100%',
                          justifyContent: collapsed ? 'center' : 'space-between',
                          padding: '5px 8px',
                          fontSize: '12px',
                          overflow: 'hidden'
                        }}
                        onClick={() => setSelectedProjectId(isSelected ? null : p.id)}
                        title={p.name}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '7px', overflow: 'hidden' }}>
                          <Folder size={13} className={isSelected ? 'text-primary' : 'text-muted'} />
                          {!collapsed && (
                            <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                              {p.name}
                            </span>
                          )}
                        </div>
                        {!collapsed && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            {p.github_repository && (
                              <span title={`GitHub: ${p.github_repository.owner}/${p.github_repository.repository}`} style={{ display: 'inline-flex' }}>
                                <GitBranch size={11} className="text-primary" />
                              </span>
                            )}
                            <span style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))' }}>
                              {p.conversation_count || 0}
                            </span>
                            <button
                              className="btn btn-ghost"
                              style={{ padding: '2px', color: 'hsl(var(--muted-fg))' }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setActiveProjectMenuId(isMenuOpen ? null : p.id);
                              }}
                            >
                              <MoreVertical size={11} />
                            </button>
                          </div>
                        )}
                      </button>
                    )}

                    {isMenuOpen && !collapsed && (
                      <div
                        onMouseDown={e => e.stopPropagation()}
                        style={{
                          position: 'absolute',
                          right: '4px',
                          top: '100%',
                          backgroundColor: 'hsl(var(--card))',
                          border: '1px solid hsl(var(--border))',
                          borderRadius: '8px',
                          boxShadow: '0 10px 25px rgba(0,0,0,0.3)',
                          padding: '4px',
                          zIndex: 50,
                          width: '150px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '2px'
                        }}
                      >
                        <button
                          className="btn btn-ghost"
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '5px 8px', fontSize: '12px' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            openGithubModal(p);
                          }}
                        >
                          <GitBranch size={12} /> {t('githubRepo')}
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '5px 8px', fontSize: '12px' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingProjectId(p.id);
                            setEditProjectName(p.name);
                            setActiveProjectMenuId(null);
                          }}
                        >
                          <Edit2 size={12} /> {t('rename')}
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '5px 8px', fontSize: '12px', color: 'hsl(var(--destructive))' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveProjectMenuId(null);
                            handleDeleteProject(p.id);
                          }}
                        >
                          <Trash2 size={12} /> {t('delete')}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Conversations Section */}
          <div ref={convMenuRef}>
            {!collapsed && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 8px', marginBottom: '4px' }}>
                <span style={{ fontSize: '10px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {showArchived ? t('archived') : t('navConversations')}
                </span>
                <button
                  className="btn btn-ghost"
                  style={{ padding: '2px 4px', fontSize: '10px', color: 'hsl(var(--muted-fg))' }}
                  onClick={() => setShowArchived(!showArchived)}
                  title={showArchived ? t('showActive') : t('showArchived')}
                >
                  {showArchived ? t('active') : t('archived')}
                </button>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              {filteredConversations.slice(0, 25).map(conv => {
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
                        title={conv.title || t('untitledTask')}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                          {conv.pinned ? (
                            <Pin size={13} className="text-primary" />
                          ) : (
                            <MessageSquare size={13} className={isActive ? 'text-primary' : (conv.unread ? 'text-primary' : 'text-muted')} />
                          )}
                          {!collapsed && (
                            <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', fontWeight: conv.unread && !isActive ? 600 : 400 }}>
                              {conv.title || t('untitledTask')}
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
                        width: '160px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '2px'
                      }}>
                        <button
                          className="btn btn-ghost"
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '5px 8px', fontSize: '12px' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            handlePinConversation(conv.id, conv.pinned);
                          }}
                        >
                          <Pin size={12} /> {conv.pinned ? 'Unpin' : 'Pin to top'}
                        </button>
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
                          <Edit2 size={12} /> {t('rename')}
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '5px 8px', fontSize: '12px' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDuplicateConversation(conv.id);
                          }}
                        >
                          <Copy size={12} /> {t('duplicate')}
                        </button>

                        {/* Assign to project list */}
                        {projects.length > 0 && (
                          <div style={{ borderTop: '1px solid hsl(var(--border)/0.5)', margin: '3px 0', paddingTop: '3px' }}>
                            <div style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))', padding: '2px 8px' }}>
                              Project
                            </div>
                            {conv.project_id && (
                              <button
                                className="btn btn-ghost"
                                style={{ width: '100%', justifyContent: 'flex-start', padding: '4px 8px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleAssignProject(conv.id, null);
                                }}
                              >
                                Remove from Project
                              </button>
                            )}
                            {projects.map(p => (
                              <button
                                key={p.id}
                                className="btn btn-ghost"
                                style={{ width: '100%', justifyContent: 'space-between', padding: '4px 8px', fontSize: '11px' }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleAssignProject(conv.id, p.id);
                                }}
                              >
                                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                  {p.name}
                                </span>
                                {conv.project_id === p.id && <Check size={11} className="text-primary" />}
                              </button>
                            ))}
                          </div>
                        )}

                        <button
                          className="btn btn-ghost"
                          style={{ width: '100%', justifyContent: 'flex-start', padding: '5px 8px', fontSize: '12px' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleArchiveConversation(conv.id, conv.status);
                          }}
                        >
                          <Archive size={12} /> {conv.status === 'archived' ? t('unarchive') : t('archive')}
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
                          <Trash2 size={12} /> {t('delete')}
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
              <Tooltip content={t('navAgents')} position={collapsed ? 'right' : 'top'} disabled={!collapsed}>
                <button
                  className={`btn btn-ghost ${currentView === 'agents' ? 'active' : ''}`}
                  style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                  onClick={() => onNavigate('agents')}
                >
                  <Bot size={15} />
                  {!collapsed && <span>{t('navAgents')}</span>}
                </button>
              </Tooltip>

              <Tooltip content={t('navTeams')} position={collapsed ? 'right' : 'top'} disabled={!collapsed}>
                <button
                  className={`btn btn-ghost ${currentView === 'teams' ? 'active' : ''}`}
                  style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                  onClick={() => onNavigate('teams')}
                >
                  <Users size={15} />
                  {!collapsed && <span>{t('navTeams')}</span>}
                </button>
              </Tooltip>

              <Tooltip content={t('navKnowledge')} position={collapsed ? 'right' : 'top'} disabled={!collapsed}>
                <button
                  className={`btn btn-ghost ${currentView === 'knowledge' ? 'active' : ''}`}
                  style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                  onClick={() => onNavigate('knowledge')}
                >
                  <Database size={15} />
                  {!collapsed && <span>{t('navKnowledge')}</span>}
                </button>
              </Tooltip>

              <Tooltip content={t('navAutomations')} position={collapsed ? 'right' : 'top'} disabled={!collapsed}>
                <button
                  className={`btn btn-ghost ${currentView === 'automations' ? 'active' : ''}`}
                  style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                  onClick={() => onNavigate('automations')}
                >
                  <Zap size={15} />
                  {!collapsed && <span>{t('navAutomations')}</span>}
                </button>
              </Tooltip>

              <Tooltip content={t('navSkills')} position={collapsed ? 'right' : 'top'} disabled={!collapsed}>
                <button
                  className={`btn btn-ghost ${currentView === 'skills' ? 'active' : ''}`}
                  style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                  onClick={() => onNavigate('skills')}
                >
                  <Puzzle size={15} />
                  {!collapsed && <span>{t('navSkills')}</span>}
                </button>
              </Tooltip>
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
              <Tooltip content={t('navSettings')} position={collapsed ? 'right' : 'top'} disabled={!collapsed}>
                <button
                  className={`btn btn-ghost ${currentView === 'settings' ? 'active' : ''}`}
                  style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                  onClick={() => onNavigate('settings')}
                >
                  <Settings size={15} />
                  {!collapsed && <span>{t('navSettings')}</span>}
                </button>
              </Tooltip>

              <Tooltip content={t('navMarketplace')} position={collapsed ? 'right' : 'top'} disabled={!collapsed}>
                <button
                  className={`btn btn-ghost ${currentView === 'marketplace' ? 'active' : ''}`}
                  style={{ width: '100%', justifyContent: collapsed ? 'center' : 'flex-start', padding: '7px 8px', fontSize: '13px' }}
                  onClick={() => onNavigate('marketplace')}
                >
                  <ShoppingBag size={15} />
                  {!collapsed && <span>{t('navMarketplace')}</span>}
                </button>
              </Tooltip>
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
              <Tooltip content={t('changeLanguage')} position="top">
                <button
                  className="btn btn-ghost"
                  style={{ padding: '6px 8px', fontSize: '12px' }}
                  onClick={toggleLanguage}
                >
                  <Globe size={14} />
                  <span>{language.toUpperCase()}</span>
                </button>
              </Tooltip>
            </div>

            <Tooltip content={isDark ? t('switchToLight') : t('switchToDark')} position="top">
              <button
                className="btn btn-ghost"
                style={{ padding: '6px' }}
                onClick={toggleTheme}
              >
                {isDark ? <Sun size={14} /> : <Moon size={14} />}
              </button>
            </Tooltip>
          </>
        ) : (
          <Tooltip content={isDark ? t('switchToLight') : t('switchToDark')} position="right">
            <button className="btn btn-ghost" style={{ padding: '6px' }} onClick={toggleTheme}>
              {isDark ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          </Tooltip>
        )}
      </div>

      {/* GitHub Repository Modal */}
      {activeGithubProject && (
        <>
          <div className="overlay" onClick={() => !githubLoading && setActiveGithubProject(null)} />
          <div className="slide-over" style={{ maxWidth: '480px' }}>
            <div className="slide-over-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <GitBranch size={18} className="text-primary" />
                <strong>{t('githubRepo')} — {activeGithubProject.name}</strong>
              </div>
              <button
                className="btn btn-ghost"
                onClick={() => setActiveGithubProject(null)}
                disabled={githubLoading}
              >
                <X size={18} />
              </button>
            </div>

            <div className="slide-over-body">
              {githubError && (
                <div style={{
                  padding: '10px 12px',
                  backgroundColor: 'hsl(var(--destructive)/0.1)',
                  color: 'hsl(var(--destructive))',
                  borderRadius: '6px',
                  fontSize: '13px',
                  marginBottom: '16px',
                  border: '1px solid hsl(var(--destructive)/0.2)',
                }}>
                  {githubError}
                </div>
              )}

              {activeGithubProject.github_repository ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div className="card" style={{ padding: '16px', backgroundColor: 'hsl(var(--card-bg))' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          backgroundColor: activeGithubProject.github_repository.connected ? 'hsl(142 71% 45%)' : 'hsl(var(--destructive))',
                          display: 'inline-block',
                        }} />
                        <span style={{ fontSize: '12px', fontWeight: 600, color: 'hsl(142 71% 45%)' }}>
                          {activeGithubProject.github_repository.connected ? t('githubConnected') : t('githubInaccessible')}
                        </span>
                      </div>
                      {activeGithubProject.github_repository.private ? (
                        <span className="badge" style={{ fontSize: '10px' }}>Private</span>
                      ) : (
                        <span className="badge" style={{ fontSize: '10px' }}>Public</span>
                      )}
                    </div>

                    <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>
                      <a
                        href={activeGithubProject.github_repository.url || `https://github.com/${activeGithubProject.github_repository.owner}/${activeGithubProject.github_repository.repository}`}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: 'hsl(var(--primary))', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                      >
                        {activeGithubProject.github_repository.owner}/{activeGithubProject.github_repository.repository}
                        <ExternalLink size={13} />
                      </a>
                    </div>

                    {activeGithubProject.github_repository.description && (
                      <p className="text-muted" style={{ fontSize: '13px', margin: '4px 0 10px 0', lineHeight: 1.4 }}>
                        {activeGithubProject.github_repository.description}
                      </p>
                    )}

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '10px' }}>
                      <div>
                        <strong>{t('githubDefaultBranch')}:</strong> <code style={{ fontSize: '11px' }}>{activeGithubProject.github_repository.default_branch || 'main'}</code>
                      </div>
                      {activeGithubProject.github_repository.verified_at && (
                        <div>
                          <strong>{t('githubLastVerified')}:</strong> {new Date(activeGithubProject.github_repository.verified_at).toLocaleString()}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">{t('githubTokenOptional')}</label>
                    <input
                      type="password"
                      className="form-input"
                      value={githubToken}
                      onChange={e => setGithubToken(e.target.value)}
                      placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                    />
                    <span className="text-muted" style={{ fontSize: '11px', marginTop: '4px', display: 'block' }}>
                      {t('githubTokenHint')}
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                    <button
                      className="btn btn-secondary"
                      onClick={handleVerifyGithub}
                      disabled={githubLoading}
                      style={{ flex: 1 }}
                    >
                      <RefreshCw size={14} className={githubLoading ? 'spin' : ''} />
                      {githubLoading ? t('verifying') : t('verifyGithubRepo')}
                    </button>
                    <button
                      className="btn btn-ghost"
                      onClick={handleDisconnectGithub}
                      disabled={githubLoading}
                      style={{ color: 'hsl(var(--destructive))' }}
                    >
                      <Trash2 size={14} />
                      {t('disconnectGithubRepo')}
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <p className="text-muted" style={{ fontSize: '13px', margin: 0 }}>
                    {t('noGithubRepo')}
                  </p>

                  <div className="form-group">
                    <label className="form-label">{t('githubOwner')} *</label>
                    <input
                      type="text"
                      className="form-input"
                      value={githubOwner}
                      onChange={e => setGithubOwner(e.target.value)}
                      placeholder="e.g. lom3e or facebook"
                      autoFocus
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">{t('githubRepoName')} *</label>
                    <input
                      type="text"
                      className="form-input"
                      value={githubRepo}
                      onChange={e => setGithubRepo(e.target.value)}
                      placeholder="e.g. aether or react"
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">{t('githubTokenOptional')}</label>
                    <input
                      type="password"
                      className="form-input"
                      value={githubToken}
                      onChange={e => setGithubToken(e.target.value)}
                      placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                    />
                    <span className="text-muted" style={{ fontSize: '11px', marginTop: '4px', display: 'block' }}>
                      {t('githubTokenHint')}
                    </span>
                  </div>

                  <button
                    className="btn btn-primary"
                    onClick={handleConnectGithub}
                    disabled={githubLoading || !githubOwner.trim() || !githubRepo.trim()}
                    style={{ marginTop: '8px' }}
                  >
                    <GitBranch size={15} />
                    {githubLoading ? t('connecting') : t('connectGithubRepo')}
                  </button>
                </div>
              )}
            </div>

            <div className="slide-over-footer">
              <button
                className="btn btn-secondary"
                onClick={() => setActiveGithubProject(null)}
                disabled={githubLoading}
              >
                {t('cancel')}
              </button>
            </div>
          </div>
        </>
      )}
    </aside>
  );
}
