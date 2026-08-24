import { useState, useEffect, useCallback, useContext } from 'react';
import { Sidebar } from './Sidebar';
import { Chat } from './Chat';
import { Agents } from './Agents';
import { Knowledge } from './Knowledge';
import { Settings } from './Settings';
import { Teams } from './Teams';
import { Automations } from './Automations';
import { Home } from './Home';
import { Marketplace } from './Marketplace';
import { AgentProfile } from './AgentProfile';
import { CommandPalette } from './CommandPalette';
import { WorkspaceModal } from './WorkspaceModal';
import { ShortcutsProvider, useKeyboardShortcuts, ShortcutsModal } from './shortcuts';
import { ToastProvider, ToastContext } from './toast';
import { LanguageProvider } from './i18n';
import { ThemeProvider } from './theme';
import { apiUrl } from './api';

function MainApp() {
  const [currentView, setCurrentView] = useState('home');
  const [viewParams, setViewParams] = useState<any>(null);
  const [workspaceName, setWorkspaceName] = useState<string>('');
  const [workspaceVersion, setWorkspaceVersion] = useState<number>(0);
  const [isInitialized, setIsInitialized] = useState<boolean | null>(null);

  // Conversations State
  const [conversations, setConversations] = useState<any[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);

  // Modals & Palettes
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isWorkspaceModalOpen, setIsWorkspaceModalOpen] = useState(false);
  const [workspaceModalMode, setWorkspaceModalMode] = useState<'create' | 'manage'>('create');

  const showToast = useContext(ToastContext);

  const fetchConversations = useCallback(() => {
    fetch(apiUrl('/api/conversations'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setConversations(data);
        }
      })
      .catch(console.error);
  }, []);

  const fetchWorkspace = useCallback(() => {
    fetch(apiUrl('/api/workspace'))
      .then(res => res.json())
      .then(data => {
        if (data && data.name) {
          setWorkspaceName(data.name);
          setIsInitialized(true);
          fetchConversations();
        } else {
          setWorkspaceName('');
          setIsInitialized(false);
          setConversations([]);
          setActiveConversationId(null);
        }
      })
      .catch(err => {
        console.error("Failed to load workspace info", err);
        setWorkspaceName('');
        setIsInitialized(false);
        setConversations([]);
        setActiveConversationId(null);
      });
  }, [fetchConversations]);

  useEffect(() => {
    fetchWorkspace();
    // Brief retry in case __AETHER_API_URL__ is set right after initial mount
    const timer = setTimeout(() => {
      fetchWorkspace();
    }, 150);
    return () => clearTimeout(timer);
  }, [fetchWorkspace]);

  const handleNewConversation = () => {
    setActiveConversationId(null);
    setCurrentView('chat');
  };

  const { registerShortcut, isShortcutsModalOpen, closeShortcutsModal, openShortcutsModal } = useKeyboardShortcuts();

  // Centralized Keyboard Shortcuts registration
  useEffect(() => {
    const unregister1 = registerShortcut({
      id: 'command_palette',
      key: 'k',
      meta: true,
      labelKey: 'shortcutCmdPalette',
      category: 'general',
      allowInInput: true,
      action: () => setIsCommandPaletteOpen((prev) => !prev),
    });

    const unregister2 = registerShortcut({
      id: 'shortcuts_help',
      key: '/',
      meta: true,
      labelKey: 'shortcutHelp',
      category: 'general',
      allowInInput: true,
      action: openShortcutsModal,
    });

    const unregister3 = registerShortcut({
      id: 'new_task',
      key: 'n',
      meta: true,
      labelKey: 'shortcutNewTask',
      category: 'general',
      allowInInput: false,
      action: () => {
        if (!workspaceName) {
          handleOpenWorkspaceModal('create');
        } else {
          handleNewConversation();
        }
      },
    });

    const unregister4 = registerShortcut({
      id: 'manage_workspace',
      key: 'w',
      meta: true,
      shift: true,
      labelKey: 'shortcutManageWorkspace',
      category: 'workspace',
      allowInInput: false,
      action: () => {
        setWorkspaceModalMode('manage');
        setIsWorkspaceModalOpen((prev) => !prev);
      },
    });

    const unregister5 = registerShortcut({
      id: 'close_modal',
      key: 'Escape',
      labelKey: 'shortcutCloseModal',
      category: 'dialogs',
      allowInInput: true,
      action: () => {
        setIsCommandPaletteOpen(false);
        setIsWorkspaceModalOpen(false);
        closeShortcutsModal();
      },
    });

    const unregisterNav1 = registerShortcut({ id: 'nav_home', key: '1', meta: true, labelKey: 'shortcutNavHome', category: 'navigation', action: () => navigate('home') });
    const unregisterNav2 = registerShortcut({ id: 'nav_chat', key: '2', meta: true, labelKey: 'shortcutNavChat', category: 'navigation', action: () => navigate('chat') });
    const unregisterNav3 = registerShortcut({ id: 'nav_agents', key: '3', meta: true, labelKey: 'shortcutNavAgents', category: 'navigation', action: () => navigate('agents') });
    const unregisterNav4 = registerShortcut({ id: 'nav_teams', key: '4', meta: true, labelKey: 'shortcutNavTeams', category: 'navigation', action: () => navigate('teams') });
    const unregisterNav5 = registerShortcut({ id: 'nav_knowledge', key: '5', meta: true, labelKey: 'shortcutNavKnowledge', category: 'navigation', action: () => navigate('knowledge') });
    const unregisterNav6 = registerShortcut({ id: 'nav_automations', key: '6', meta: true, labelKey: 'shortcutNavAutomations', category: 'navigation', action: () => navigate('automations') });
    const unregisterNav7 = registerShortcut({ id: 'nav_settings', key: ',', meta: true, labelKey: 'shortcutNavSettings', category: 'navigation', action: () => navigate('settings') });

    return () => {
      unregister1();
      unregister2();
      unregister3();
      unregister4();
      unregister5();
      unregisterNav1();
      unregisterNav2();
      unregisterNav3();
      unregisterNav4();
      unregisterNav5();
      unregisterNav6();
      unregisterNav7();
    };
  }, [workspaceName, registerShortcut, openShortcutsModal, closeShortcutsModal]);

  const navigate = (view: string, params: any = null) => {
    setCurrentView(view);
    setViewParams(params);
  };

  const handleSelectConversation = (id: string, tempTitle?: string) => {
    setActiveConversationId(id);
    setCurrentView('chat');
    setConversations(prev => {
      const exists = prev.some(c => c.id === id);
      if (!exists && tempTitle) {
        return [
          {
            id,
            title: tempTitle,
            status: 'active',
            updated_at: new Date().toISOString(),
            last_message: tempTitle,
            unread: false,
          },
          ...prev,
        ];
      }
      return prev.map(c => c.id === id ? { ...c, unread: false } : c);
    });
  };

  const handleDeleteConversation = async (id: string) => {
    try {
      const res = await fetch(apiUrl(`/api/conversations/${id}`), {
        method: 'DELETE'
      });
      if (res.ok) {
        setConversations(prev => prev.filter(c => c.id !== id));
        if (activeConversationId === id) {
          const remaining = conversations.filter(c => c.id !== id);
          if (remaining.length > 0) {
            setActiveConversationId(remaining[0].id);
          } else {
            setActiveConversationId(null);
            setCurrentView('home');
          }
        }
        showToast('Conversation deleted.', 'info');
      }
    } catch (err) {
      console.error('Failed to delete conversation', err);
    }
  };

  const handleOpenWorkspaceModal = (mode: 'create' | 'manage') => {
    setWorkspaceModalMode(mode);
    setIsWorkspaceModalOpen(true);
  };

  const handleWorkspaceSwitched = () => {
    setActiveConversationId(null);
    setCurrentView('home');
    fetchWorkspace();
    setWorkspaceVersion(v => v + 1);
  };

  if (isInitialized === null) {
    return (
      <div className="app-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ fontSize: '14px', color: 'hsl(var(--muted-fg))' }}>Loading Aether...</div>
      </div>
    );
  }

  const hasWorkspace = Boolean(workspaceName && isInitialized);

  return (
    <div className="app-container">
      <Sidebar
        currentView={currentView}
        onNavigate={navigate}
        workspaceName={workspaceName}
        workspaceVersion={workspaceVersion}
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
        onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
        onOpenWorkspaceModal={handleOpenWorkspaceModal}
        onRefreshConversations={fetchConversations}
        onWorkspaceSwitched={handleWorkspaceSwitched}
      />

      <div className="main-content">
        {currentView === 'home' && (
          <Home
            navigate={navigate}
            workspaceName={workspaceName}
            onNewTask={handleNewConversation}
            onSelectConversation={handleSelectConversation}
            conversations={conversations}
            onOpenWorkspaceModal={() => handleOpenWorkspaceModal('create')}
          />
        )}
        {currentView === 'chat' && (
          <Chat
            conversationId={activeConversationId}
            onNewConversation={handleNewConversation}
            onSelectConversation={handleSelectConversation}
            onConversationUpdated={fetchConversations}
            hasWorkspace={hasWorkspace}
            onOpenWorkspaceModal={() => handleOpenWorkspaceModal('create')}
          />
        )}
        {currentView === 'agents' && <Agents navigate={navigate} />}
        {currentView === 'agent' && <AgentProfile name={viewParams} navigate={navigate} />}
        {currentView === 'teams' && <Teams />}
        {currentView === 'knowledge' && <Knowledge />}
        {currentView === 'automations' && <Automations />}
        {currentView === 'settings' && <Settings onWorkspaceSwitched={handleWorkspaceSwitched} />}
        {currentView === 'marketplace' && <Marketplace />}
      </div>

      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onNavigate={navigate}
        onNewConversation={handleNewConversation}
        conversations={conversations}
        onSelectConversation={handleSelectConversation}
      />

      <WorkspaceModal
        isOpen={isWorkspaceModalOpen}
        onClose={() => setIsWorkspaceModalOpen(false)}
        onWorkspaceSwitched={handleWorkspaceSwitched}
        initialMode={workspaceModalMode}
      />

      <ShortcutsModal
        isOpen={isShortcutsModalOpen}
        onClose={closeShortcutsModal}
      />
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <ToastProvider>
          <ShortcutsProvider>
            <MainApp />
          </ShortcutsProvider>
        </ToastProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}
