import { useState, useEffect, useCallback, useContext } from 'react';
import { Sidebar } from './Sidebar';
import { Chat } from './Chat';
import { Knowledge } from './Knowledge';
import { Settings } from './Settings';
import { Automations } from './Automations';
import { Home } from './Home';
import { Missions } from './Missions';
import { Marketplace } from './Marketplace';
import { AgentProfile } from './AgentProfile';
import { Connections } from './Connections';
import { WorkforceHub } from './WorkforceHub';
import { ActivityFeed } from './ActivityFeed';
import { CommandPalette } from './CommandPalette';
import { WorkspaceModal } from './WorkspaceModal';
import { ShortcutsProvider, useKeyboardShortcuts, ShortcutsModal } from './shortcuts';
import { ToastProvider, ToastContext } from './toast';
import { LanguageProvider } from './i18n';
import { ThemeProvider } from './theme';
import { apiUrl } from './api';
import { isCompanionSurface, isTauri, notifyDesktop, consumeNotificationTarget } from './desktop';
import { resolveCanonicalTarget } from './canonicalNotification';
import { listen } from '@tauri-apps/api/event';
import { AmbientCompanion } from './AmbientCompanion';
import { WorkflowBuilder } from './WorkflowBuilder';
import { ContentRepurposing } from './ContentRepurposing';
import { ProactiveWatchersView } from './ProactiveWatchersView';
import ExecutionFabricView from './ExecutionFabricView';
import { ResultsView } from './ResultsView';
import { AssistantV2 } from './AssistantV2';
import { useTranslation } from './i18n';


function MainApp() {
  const { t } = useTranslation();
  // Experience Mode: 'v2' (Assistant-First with Living Orb) or 'v1' (Classic Multi-Tab Workspace)
  const [experienceMode, setExperienceMode] = useState<'v1' | 'v2'>(() => {
    if (typeof window !== 'undefined') {
      try {
        const params = new URLSearchParams(window.location.search);
        const urlMode = params.get('ui');
        if (urlMode === 'v1' || urlMode === 'v2') return urlMode;
        const saved = localStorage.getItem('aether_experience_mode');
        if (saved === 'v1' || saved === 'v2') return saved;
      } catch {
        // ignore
      }
    }
    return 'v2';
  });

  const handleSwitchExperience = useCallback((mode: 'v1' | 'v2') => {
    setExperienceMode(mode);
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem('aether_experience_mode', mode);
        const url = new URL(window.location.href);
        url.searchParams.set('ui', mode);
        window.history.replaceState({}, '', url.toString());
      } catch {
        // ignore
      }
    }
  }, []);

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

  const navigate = useCallback((view: string, params: any = null) => {
    const targetView = view === 'work' ? 'missions' : view;
    if (targetView === 'chat' && params && typeof params === 'string') {
      setActiveConversationId(params);
    }
    setCurrentView(targetView);
    setViewParams(params);
    if (targetView && targetView !== 'home') {
      handleSwitchExperience('v1');
    }
  }, [handleSwitchExperience]);

  // Listen for Tauri IPC navigation events (triggered when clicking native macOS notifications or dock reopen)
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    if (isTauri()) {
      listen<any>('navigate_view', (event) => {
        console.log('[Aether App] navigate_view from Tauri:', event.payload);
        if (event.payload) {
          const resolved = resolveCanonicalTarget(event.payload);
          if (!resolved.valid && resolved.reason) {
            showToast(resolved.reason, 'info');
          }
          navigate(resolved.view, resolved.params);
        }
      }).then((fn) => {
        unlisten = fn;
      }).catch(console.error);
    }
    return () => {
      if (unlisten) unlisten();
    };
  }, [navigate, showToast]);

  // Check and consume pending notification target on window focus
  useEffect(() => {
    const checkPending = async () => {
      const target = await consumeNotificationTarget();
      if (target) {
        console.log('[Aether App] Consumed pending notification target:', target);
        const resolved = resolveCanonicalTarget(target);
        if (!resolved.valid && resolved.reason) {
          showToast(resolved.reason, 'info');
        }
        navigate(resolved.view, resolved.params);
      }
    };
    window.addEventListener('focus', checkPending);
    checkPending();
    return () => window.removeEventListener('focus', checkPending);
  }, [navigate, showToast]);

  // Listen for DOM custom navigation events (web fallback)
  useEffect(() => {
    const handleCustomNav = (e: any) => {
      if (e.detail) {
        const resolved = resolveCanonicalTarget(e.detail);
        if (!resolved.valid && resolved.reason) {
          showToast(resolved.reason, 'info');
        }
        navigate(resolved.view, resolved.params);
      }
    };
    window.addEventListener('aether:navigate', handleCustomNav);
    return () => window.removeEventListener('aether:navigate', handleCustomNav);
  }, [navigate, showToast]);

  // Global SSE subscription for notifications (Single Delivery Owner for desktop notifications)
  useEffect(() => {
    if (!workspaceName) return;
    let eventSource: EventSource | null = null;
    try {
      const token = (typeof window !== 'undefined' && (window as any).__AETHER_SESSION_TOKEN__) || '';
      const tokenQuery = token ? `&token=${encodeURIComponent(token)}` : '';
      eventSource = new EventSource(
        apiUrl(`/api/personal/events?workspace_id=${encodeURIComponent(workspaceName)}${tokenQuery}`)
      );

      eventSource.addEventListener('notification', (e: MessageEvent) => {
        try {
          const notif = JSON.parse(e.data);
          if (notif && notif.title) {
            showToast(
              `${notif.title}: ${notif.message || ''}`,
              notif.priority === 'high' ? 'warning' : 'info'
            );
            notifyDesktop(notif.title, {
              id: notif.id,
              body: notif.message,
              link_view: notif.link_view,
              link_id: notif.link_id,
              target_type: notif.target_type,
              target_id: notif.target_id,
              deep_link: notif.deep_link,
              workspaceName,
              sound: notif.metadata?.sound || 'Glass',
              onClick: () => {
                const resolved = resolveCanonicalTarget(notif);
                if (!resolved.valid && resolved.reason) {
                  showToast(resolved.reason, 'info');
                }
                navigate(resolved.view, resolved.params);
              },
            });
          }
        } catch (err) {
          console.debug('Error parsing SSE notification event:', err);
        }
      });
    } catch (err) {
      console.debug('Global notification SSE connection error:', err);
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [workspaceName, showToast, navigate]);

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
        showToast(t('sdConversationDeleted'), 'info');
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
        <div style={{ fontSize: '14px', color: 'hsl(var(--muted-fg))' }}>{t('sdLoadingAether')}</div>
      </div>
    );
  }

  const hasWorkspace = Boolean(workspaceName && isInitialized);

  if (experienceMode === 'v2') {
    return (
      <div className="app-container" style={{ padding: 0, overflow: 'hidden' }}>
        <AssistantV2
          workspaceName={workspaceName}
          navigate={navigate}
          onSwitchToV1={() => handleSwitchExperience('v1')}
          onOpenWorkspaceModal={() => handleOpenWorkspaceModal('create')}
        />

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
        onSwitchToV2={() => handleSwitchExperience('v2')}
      />

      <div className="main-content">
        {!hasWorkspace && currentView !== 'home' && currentView !== 'marketplace' ? (
          // Every other screen reads the workspace: without one they would only show raw server errors.
          <div data-testid="no-workspace-notice" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 24px' }}>
            <div className="card" style={{ maxWidth: '480px', width: '100%', padding: '36px', textAlign: 'center' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '10px' }}>{t('createFirstWorkspace')}</h2>
              <p className="text-muted" style={{ fontSize: '14px', lineHeight: 1.6, marginBottom: '22px' }}>{t('noActiveWorkspaceDesc')}</p>
              <button className="btn btn-primary" onClick={() => handleOpenWorkspaceModal('create')}>{t('createWorkspaceBtn')}</button>
            </div>
          </div>
        ) : null}
        {currentView === 'home' && (
          <Home
            navigate={navigate}
            workspaceName={workspaceName}
            initialApprovalId={viewParams}
            onNewTask={handleNewConversation}
            onSelectConversation={handleSelectConversation}
            conversations={conversations}
            onOpenWorkspaceModal={() => handleOpenWorkspaceModal('create')}
          />
        )}
        {hasWorkspace && (currentView === 'missions' || currentView === 'work') && (
          <Missions navigate={navigate} initialMissionId={viewParams} />
        )}
        {hasWorkspace && currentView === 'workforce' && <WorkforceHub navigate={navigate} />}
        {hasWorkspace && currentView === 'connections' && (
          <Connections
            navigate={navigate}
            initialExecutionId={viewParams}
            initialTab={viewParams ? 'actions' : undefined}
          />
        )}
        {hasWorkspace && (currentView === 'results' || currentView === 'deliverables') && (
          <ResultsView navigate={navigate} />
        )}
        {hasWorkspace && currentView === 'activity' && <ActivityFeed navigate={navigate} />}
        {hasWorkspace && currentView === 'chat' && (
          <Chat
            conversationId={activeConversationId}
            onNewConversation={handleNewConversation}
            onSelectConversation={handleSelectConversation}
            onConversationUpdated={fetchConversations}
            hasWorkspace={hasWorkspace}
            onOpenWorkspaceModal={() => handleOpenWorkspaceModal('create')}
          />
        )}
        {hasWorkspace && currentView === 'agents' && <WorkforceHub initialTab="agents" navigate={navigate} />}
        {hasWorkspace && currentView === 'agent' && <AgentProfile name={viewParams} navigate={navigate} />}
        {hasWorkspace && currentView === 'teams' && <WorkforceHub initialTab="teams" navigate={navigate} />}
        {hasWorkspace && currentView === 'knowledge' && <Knowledge />}
        {hasWorkspace && currentView === 'memory' && <WorkforceHub initialTab="memory" navigate={navigate} />}
        {hasWorkspace && currentView === 'learning' && <WorkforceHub initialTab="learning" navigate={navigate} />}
        {hasWorkspace && currentView === 'automations' && <Automations initialAutomationId={viewParams} />}
        {hasWorkspace && currentView === 'workflows' && <WorkflowBuilder navigate={navigate} />}
        {hasWorkspace && currentView === 'skills' && <WorkforceHub initialTab="skills" navigate={navigate} />}
        {hasWorkspace && currentView === 'content' && <ContentRepurposing navigate={navigate} />}
        {hasWorkspace && currentView === 'proactive' && <ProactiveWatchersView />}
        {hasWorkspace && currentView === 'fabric' && <ExecutionFabricView />}
        {hasWorkspace && currentView === 'settings' && <Settings onWorkspaceSwitched={handleWorkspaceSwitched} />}
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
  const isCompanion = isCompanionSurface();

  if (isCompanion) {
    return (
      <ThemeProvider>
        <LanguageProvider>
          <ToastProvider>
            <AmbientCompanion />
          </ToastProvider>
        </LanguageProvider>
      </ThemeProvider>
    );
  }

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
