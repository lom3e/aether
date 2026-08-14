import { useState, useEffect, useCallback, useContext } from 'react';
import { Sidebar } from './Sidebar';
import { Chat } from './Chat';
import { Agents } from './Agents';
import { Knowledge } from './Knowledge';
import { Onboarding } from './Onboarding';
import { Settings } from './Settings';
import { Teams } from './Teams';
import { Home } from './Home';
import { Marketplace } from './Marketplace';
import { AgentProfile } from './AgentProfile';
import { CommandPalette } from './CommandPalette';
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
  const [workspaceName, setWorkspaceName] = useState('Aether Labs');
  const [isInitialized, setIsInitialized] = useState<boolean | null>(null);

  // Conversations State
  const [conversations, setConversations] = useState<any[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);

  const showToast = useContext(ToastContext);

  const fetchConversations = useCallback(() => {
    fetch(apiUrl('/api/conversations'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setConversations(data);
          if (!activeConversationId && data.length > 0) {
            setActiveConversationId(data[0].id);
          }
        }
      })
      .catch(console.error);
  }, [activeConversationId]);

  const fetchWorkspace = useCallback(() => {
    fetch(apiUrl('/api/workspace'))
      .then(res => res.json())
      .then(data => {
        if (data.name) {
          setWorkspaceName(data.name);
          setIsInitialized(true);
          fetchConversations();
        } else {
          setIsInitialized(false);
        }
      })
      .catch(err => {
        console.error("Failed to load workspace info", err);
        setIsInitialized(false);
      });
  }, [fetchConversations]);

  useEffect(() => {
    fetchWorkspace();
  }, [fetchWorkspace]);

  // Global Command+K shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const navigate = (view: string, params: any = null) => {
    setCurrentView(view);
    setViewParams(params);
  };

  const handleNewConversation = async () => {
    try {
      const res = await fetch(apiUrl('/api/conversations'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New Task' })
      });
      if (res.ok) {
        const newConv = await res.json();
        setConversations(prev => [newConv, ...prev]);
        setActiveConversationId(newConv.id);
        setCurrentView('chat');
      }
    } catch (err) {
      console.error('Failed to create conversation', err);
    }
  };

  const handleSelectConversation = (id: string) => {
    setActiveConversationId(id);
    setCurrentView('chat');
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

  if (isInitialized === null) {
    return (
      <div className="app-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ fontSize: '14px', color: 'hsl(var(--muted-fg))' }}>Loading Aether Workspace...</div>
      </div>
    );
  }

  if (isInitialized === false) {
    return <Onboarding onComplete={fetchWorkspace} />;
  }

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
      />

      <div className="main-content">
        {currentView === 'home' && (
          <Home
            navigate={navigate}
            workspaceName={workspaceName}
            onNewTask={handleNewConversation}
            onSelectConversation={handleSelectConversation}
            conversations={conversations}
          />
        )}
        {currentView === 'chat' && (
          <Chat
            conversationId={activeConversationId}
            onNewConversation={handleNewConversation}
            onConversationUpdated={fetchConversations}
          />
        )}
        {currentView === 'agents' && <Agents navigate={navigate} />}
        {currentView === 'agent' && <AgentProfile name={viewParams} navigate={navigate} />}
        {currentView === 'teams' && <Teams />}
        {currentView === 'knowledge' && <Knowledge />}
        {currentView === 'settings' && <Settings />}
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
