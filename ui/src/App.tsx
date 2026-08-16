import { useState, useEffect, useCallback, useContext } from 'react';
import { Sidebar } from './Sidebar';
import { Chat } from './Chat';
import { Agents } from './Agents';
import { Knowledge } from './Knowledge';
import { Settings } from './Settings';
import { Teams } from './Teams';
import { Home } from './Home';
import { Marketplace } from './Marketplace';
import { AgentProfile } from './AgentProfile';
import { CommandPalette } from './CommandPalette';
import { WorkspaceModal } from './WorkspaceModal';
import { ToastContext } from './toast';
import { LanguageProvider } from './i18n';
import { ThemeProvider } from './theme';
import { apiUrl } from './api';

function ToastProvider({ children }: { children: any }) {
  const [toast, setToast] = useState<{ message: string; type: string } | null>(null);

  const showToast = useCallback((message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      {toast && (
        <div style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          padding: '12px 20px',
          backgroundColor: toast.type === 'error' ? 'hsl(var(--destructive))' : (toast.type === 'success' ? 'hsl(var(--success))' : 'hsl(var(--card))'),
          color: toast.type === 'info' ? 'hsl(var(--fg))' : 'hsl(var(--primary-fg))',
          border: toast.type === 'info' ? '1px solid hsl(var(--border))' : 'none',
          borderRadius: 'var(--radius)',
          boxShadow: '0 10px 25px rgba(0,0,0,0.3)',
          zIndex: 200,
          fontSize: '13px',
          fontWeight: 500
        }}>
          {toast.message}
        </div>
      )}
    </ToastContext.Provider>
  );
}

function MainApp() {
  const [currentView, setCurrentView] = useState('home');
  const [viewParams, setViewParams] = useState<any>(null);
  const [workspaceName, setWorkspaceName] = useState('');
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
  }, [fetchWorkspace]);

  const handleNewConversation = () => {
    setActiveConversationId(null);
    setCurrentView('chat');
  };

  // Keyboard Shortcuts: Cmd+K, Cmd+N, Cmd+Shift+W, Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K -> Command Palette
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen(prev => !prev);
      }
      // Cmd+N -> New Conversation
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        if (!workspaceName) {
          handleOpenWorkspaceModal('create');
        } else {
          handleNewConversation();
        }
      }
      // Cmd+Shift+W -> Workspace Modal
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'w') {
        e.preventDefault();
        setWorkspaceModalMode('manage');
        setIsWorkspaceModalOpen(prev => !prev);
      }
      // Esc -> Close modals
      if (e.key === 'Escape') {
        setIsCommandPaletteOpen(false);
        setIsWorkspaceModalOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [workspaceName]);

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
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <ToastProvider>
          <MainApp />
        </ToastProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}
