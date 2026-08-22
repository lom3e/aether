import { useState, useEffect, useContext } from 'react';
import { ToastContext } from './toast';
import {
  Cpu, Globe, Moon, Sun,
  HardDrive, Layers, AlertTriangle, Sliders
} from 'lucide-react';
import { apiError, apiUrl } from './api';
import { useTranslation } from './i18n';
import { useTheme } from './theme';
import { TopHeader } from './TopHeader';

interface SettingsProps {
  onWorkspaceSwitched?: () => void;
}

export function Settings({ onWorkspaceSwitched }: SettingsProps) {
  const [activeTab, setActiveTab] = useState<'workspace' | 'providers' | 'general' | 'storage' | 'advanced'>('workspace');

  // Provider Settings State
  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('qwen3.5:9b');
  const [timeout, setTimeoutVal] = useState<number>(120);
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  // Workspace Settings State
  const [workspaceInfo, setWorkspaceInfo] = useState<any>(null);
  const [workspaceStats, setWorkspaceStats] = useState<any>(null);
  const [wsName, setWsName] = useState('');
  const [savingWs, setSavingWs] = useState(false);
  const [isDeletingWs, setIsDeletingWs] = useState(false);

  const showToast = useContext(ToastContext);
  const { t, language, setLanguage } = useTranslation();
  const { theme, setTheme } = useTheme();

  const fetchWorkspaceData = () => {
    fetch(apiUrl('/api/workspace'))
      .then(res => res.json())
      .then(data => {
        setWorkspaceInfo(data);
        if (data && data.name) {
          setWsName(data.name);
        }
      })
      .catch(console.error);

    fetch(apiUrl('/api/workspaces/current/stats'))
      .then(res => res.json())
      .then(data => setWorkspaceStats(data))
      .catch(console.error);
  };

  useEffect(() => {
    fetchWorkspaceData();

    fetch(apiUrl('/api/settings/provider'))
      .then(res => res.json())
      .then(data => {
        setProvider(data.provider || 'ollama');
        setModel(data.model || 'qwen3.5:9b');
        setTimeoutVal(data.timeout || (data.provider === 'ollama' ? 120 : 30));
        setStatus(data.configured || {});
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    fetch(apiUrl(`/api/settings/provider/models?provider=${provider}`))
      .then(res => res.json())
      .then(data => {
        if (data.models && data.models.length > 0) {
          setAvailableModels(data.models);
          if (!data.models.includes(model)) {
            setModel(data.models[0]);
          }
        } else {
          setAvailableModels([]);
        }
      })
      .catch(console.error);

    if (provider === 'ollama') {
      setTimeoutVal(120);
    } else {
      setTimeoutVal(30);
    }
  }, [provider]);

  const handleSaveProvider = async () => {
    setSaving(true);
    try {
      const res = await fetch(apiUrl('/api/settings/provider'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          model,
          timeout: Number(timeout),
          api_key: apiKey || null
        })
      });
      if (res.ok) {
        if (apiKey) {
          setStatus({ ...status, [provider]: true });
          setApiKey('');
        }
        showToast('Provider settings saved successfully.', 'success');
      } else {
        showToast((await apiError(res, 'Unable to save provider settings.')).message, 'error');
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Unable to save provider settings.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleTestProvider = async () => {
    setTesting(true);
    try {
      const res = await fetch(apiUrl('/api/settings/provider/test'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          model,
          api_key: apiKey || null
        })
      });
      if (res.ok) {
        showToast('Provider connection successful!', 'success');
      } else {
        showToast((await apiError(res, 'Provider test failed.')).message, 'error');
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Provider test failed.', 'error');
    } finally {
      setTesting(false);
    }
  };

  const handleSaveWorkspaceName = async () => {
    if (!wsName.trim()) return;
    setSavingWs(true);
    try {
      const wsListRes = await fetch(apiUrl('/api/workspaces'));
      const wsList = await wsListRes.json();
      const current = wsList.find((w: any) => w.is_active);
      if (!current) throw new Error('Active workspace not found');

      const res = await fetch(apiUrl(`/api/workspaces/${current.id}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: wsName.trim() })
      });

      if (res.ok) {
        showToast('Workspace name updated.', 'success');
        fetchWorkspaceData();
        if (onWorkspaceSwitched) onWorkspaceSwitched();
      } else {
        const err = await apiError(res, 'Failed to update workspace name.');
        showToast(err.message, 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to update workspace', 'error');
    } finally {
      setSavingWs(false);
    }
  };

  const handleClearKnowledge = async () => {
    try {
      const res = await fetch(apiUrl('/api/workspaces/current/clear-knowledge'), {
        method: 'POST'
      });
      if (res.ok) {
        showToast('Workspace knowledge cleared.', 'info');
        fetchWorkspaceData();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleResetWorkspace = async () => {
    try {
      const res = await fetch(apiUrl('/api/workspaces/current/reset'), {
        method: 'POST'
      });
      if (res.ok) {
        showToast('Workspace reset to initial clean state.', 'info');
        fetchWorkspaceData();
        if (onWorkspaceSwitched) onWorkspaceSwitched();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteCurrentWorkspace = async () => {
    try {
      const wsListRes = await fetch(apiUrl('/api/workspaces'));
      const wsList = await wsListRes.json();
      const current = Array.isArray(wsList) ? (wsList.find((w: any) => w.is_active) || wsList[0]) : null;
      if (!current) {
        showToast('No workspace found to delete.', 'error');
        setIsDeletingWs(false);
        return;
      }

      const res = await fetch(apiUrl(`/api/workspaces/${current.id}`), {
        method: 'DELETE'
      });
      if (res.ok) {
        showToast(`Workspace "${current.name}" deleted.`, 'info');
        setIsDeletingWs(false);
        if (onWorkspaceSwitched) onWorkspaceSwitched();
      } else {
        const err = await apiError(res, 'Failed to delete workspace.');
        showToast(err.message, 'error');
      }
    } catch (err: any) {
      console.error('Failed to delete workspace', err);
      showToast(err?.message || 'Failed to delete workspace.', 'error');
    }
  };

  const formatBytes = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <TopHeader
        title={t('settingsTitle')}
        icon={Sliders}
      />
      <div style={{ maxWidth: '840px', margin: '0 auto', padding: '32px 24px' }}>
        <p className="text-muted" style={{ fontSize: '14px', marginBottom: '24px' }}>
          Configure your workspace, default AI providers, knowledge storage, and system preferences.
        </p>

      {/* Tabs */}
      <div style={{
        display: 'flex',
        gap: '8px',
        borderBottom: '1px solid hsl(var(--border))',
        marginBottom: '28px',
        overflowX: 'auto'
      }}>
        <button
          className={`btn btn-ghost ${activeTab === 'workspace' ? 'active' : ''}`}
          style={{ borderRadius: '0', borderBottom: activeTab === 'workspace' ? '2px solid hsl(var(--primary))' : 'none', padding: '10px 16px', fontSize: '13.5px' }}
          onClick={() => setActiveTab('workspace')}
        >
          <Layers size={16} /> {t('workspace')}
        </button>
        <button
          className={`btn btn-ghost ${activeTab === 'providers' ? 'active' : ''}`}
          style={{ borderRadius: '0', borderBottom: activeTab === 'providers' ? '2px solid hsl(var(--primary))' : 'none', padding: '10px 16px', fontSize: '13.5px' }}
          onClick={() => setActiveTab('providers')}
        >
          <Cpu size={16} /> {t('providersTab')}
        </button>
        <button
          className={`btn btn-ghost ${activeTab === 'storage' ? 'active' : ''}`}
          style={{ borderRadius: '0', borderBottom: activeTab === 'storage' ? '2px solid hsl(var(--primary))' : 'none', padding: '10px 16px', fontSize: '13.5px' }}
          onClick={() => setActiveTab('storage')}
        >
          <HardDrive size={16} /> {t('storageTab')}
        </button>
        <button
          className={`btn btn-ghost ${activeTab === 'general' ? 'active' : ''}`}
          style={{ borderRadius: '0', borderBottom: activeTab === 'general' ? '2px solid hsl(var(--primary))' : 'none', padding: '10px 16px', fontSize: '13.5px' }}
          onClick={() => setActiveTab('general')}
        >
          <Globe size={16} /> {t('generalTab')}
        </button>
      </div>

      {/* WORKSPACE TAB */}
      {activeTab === 'workspace' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* General Workspace Info */}
          <div className="card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>{t('generalWorkspace')}</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label className="form-label">{t('workspaceDisplayName')}</label>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <input
                    type="text"
                    className="form-input"
                    value={wsName}
                    onChange={e => setWsName(e.target.value)}
                  />
                  <button
                    className="btn btn-primary"
                    style={{ padding: '8px 18px', flexShrink: 0 }}
                    onClick={handleSaveWorkspaceName}
                    disabled={savingWs || !wsName.trim()}
                  >
                    {t('save')}
                  </button>
                </div>
              </div>

              <div>
                <label className="form-label">{t('activeTeam')}</label>
                <div style={{ fontSize: '13.5px', color: 'hsl(var(--fg))', padding: '8px 12px', background: 'hsl(var(--muted)/0.5)', borderRadius: '6px' }}>
                  {workspaceInfo?.name || 'default'} ({workspaceInfo?.agents?.length || 0} {workspaceInfo?.agents?.length === 1 ? t('agentSingular').toLowerCase() : t('agentPlural').toLowerCase()} {t('statusActive').toLowerCase()})
                </div>
              </div>
            </div>
          </div>

          {/* Danger Zone */}
          <div className="card" style={{ padding: '24px', border: '1px solid hsl(var(--destructive)/0.3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'hsl(var(--destructive))', marginBottom: '16px' }}>
              <AlertTriangle size={18} />
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>{t('dangerZone')}</h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', background: 'hsl(var(--bg))', borderRadius: '8px' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '13px' }}>{t('clearKnowledgeTitle')}</div>
                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>{t('clearKnowledgeDesc')}</div>
                </div>
                <button className="btn btn-secondary" onClick={handleClearKnowledge}>
                  {t('clearKnowledgeBtn')}
                </button>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', background: 'hsl(var(--bg))', borderRadius: '8px' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '13px' }}>{t('resetWorkspaceTitle')}</div>
                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>{t('resetWorkspaceDesc')}</div>
                </div>
                <button className="btn btn-secondary" onClick={handleResetWorkspace}>
                  {t('resetBtn')}
                </button>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', background: 'hsl(var(--destructive)/0.05)', borderRadius: '8px', border: '1px solid hsl(var(--destructive)/0.2)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '13px', color: 'hsl(var(--destructive))' }}>{t('deleteWorkspaceTitle')}</div>
                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>{t('deleteWorkspaceDesc')}</div>
                </div>
                <button className="btn btn-destructive" onClick={() => setIsDeletingWs(true)}>
                  {t('deleteWorkspaceTitle')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* PROVIDERS TAB */}
      {activeTab === 'providers' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>{t('defaultAiProvider')}</h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label className="form-label">{t('selectProvider')}</label>
                <select
                  className="form-select"
                  value={provider}
                  onChange={e => {
                    const p = e.target.value;
                    setProvider(p);
                    if (p === 'ollama') setModel('qwen3.5:9b');
                    else if (p === 'openai') setModel('gpt-4o');
                    else if (p === 'anthropic') setModel('claude-3-5-sonnet-20241022');
                    else if (p === 'gemini') setModel('gemini-2.0-flash');
                  }}
                >
                  <option value="ollama">Ollama (Local Default)</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="gemini">Google Gemini</option>
                </select>
              </div>

              <div>
                <label className="form-label">{t('model')}</label>
                {availableModels.length > 0 ? (
                  <select className="form-select" value={model} onChange={e => setModel(e.target.value)}>
                    {availableModels.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                ) : (
                  <input
                    type="text"
                    className="form-input"
                    value={model}
                    onChange={e => setModel(e.target.value)}
                  />
                )}
              </div>

              <div>
                <label className="form-label">{t('providerTimeout')}</label>
                <input
                  type="number"
                  className="form-input"
                  value={timeout}
                  onChange={e => setTimeoutVal(Number(e.target.value))}
                  min={5}
                  max={600}
                />
              </div>

              {provider !== 'ollama' && (
                <div>
                  <label className="form-label">{t('apiKey')}</label>
                  <input
                    type="password"
                    className="form-input"
                    placeholder={status[provider] ? '•••••••••••••••• (Configured)' : `Enter ${provider.toUpperCase()} API Key`}
                    value={apiKey}
                    onChange={e => setApiKey(e.target.value)}
                  />
                </div>
              )}

              <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                <button
                  className="btn btn-primary"
                  onClick={handleSaveProvider}
                  disabled={saving}
                >
                  {saving ? t('saving') : t('saveSettings')}
                </button>

                <button
                  className="btn btn-secondary"
                  onClick={handleTestProvider}
                  disabled={testing}
                >
                  {testing ? t('testing') : t('testConnection')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STORAGE & DATA TAB */}
      {activeTab === 'storage' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>{t('localPersistenceMetrics')}</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
              <div style={{ padding: '16px', backgroundColor: 'hsl(var(--bg))', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginBottom: '4px' }}>{t('conversationsDb')}</div>
                <div style={{ fontSize: '20px', fontWeight: 700 }}>{workspaceStats?.conversations_count || 0} {t('navConversations').toLowerCase()}</div>
                <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                  {formatBytes(workspaceStats?.conversations_size_bytes)}
                </div>
              </div>

              <div style={{ padding: '16px', backgroundColor: 'hsl(var(--bg))', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginBottom: '4px' }}>{t('knowledgeStore')}</div>
                <div style={{ fontSize: '20px', fontWeight: 700 }}>{workspaceStats?.knowledge_chunks_count || 0} {t('chunks').toLowerCase()}</div>
                <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                  {workspaceStats?.knowledge_documents_count || 0} docs ({formatBytes(workspaceStats?.knowledge_size_bytes)})
                </div>
              </div>

              <div style={{ padding: '16px', backgroundColor: 'hsl(var(--bg))', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginBottom: '4px' }}>{t('totalLocalFootprint')}</div>
                <div style={{ fontSize: '20px', fontWeight: 700 }}>
                  {formatBytes(workspaceStats?.total_size_bytes)}
                </div>
                <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                  SQLite 100% Local-first
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* GENERAL TAB */}
      {activeTab === 'general' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>{t('appearanceAndLanguage')}</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label className="form-label">{t('language')}</label>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button
                    className={`btn ${language === 'en' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setLanguage('en')}
                  >
                    English
                  </button>
                  <button
                    className={`btn ${language === 'it' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setLanguage('it')}
                  >
                    Italiano
                  </button>
                </div>
              </div>

              <div>
                <label className="form-label">{t('theme')}</label>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button
                    className={`btn ${theme === 'dark' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setTheme('dark')}
                  >
                    <Moon size={15} /> {t('themeDark')}
                  </button>
                  <button
                    className={`btn ${theme === 'light' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setTheme('light')}
                  >
                    <Sun size={15} /> {t('themeLight')}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Workspace Confirmation Modal */}
      {isDeletingWs && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          zIndex: 100
        }}>
          <div style={{
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--destructive))',
            borderRadius: '10px',
            padding: '24px',
            maxWidth: '440px',
            width: '100%',
            display: 'flex',
            flexDirection: 'column',
            gap: '14px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'hsl(var(--destructive))' }}>
              <AlertTriangle size={20} />
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>{t('deleteCurrentWorkspaceTitle')}</h3>
            </div>
            <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', lineHeight: 1.5 }}>
              {t('deleteWorkspaceConfirmDesc')}
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '6px' }}>
              <button className="btn btn-secondary" onClick={() => setIsDeletingWs(false)}>
                {t('cancel')}
              </button>
              <button className="btn btn-destructive" onClick={handleDeleteCurrentWorkspace}>
                {t('deleteWorkspaceTitle')}
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
