import { useState, useEffect, useContext } from 'react';
import { ToastContext } from './toast';
import {
  Cpu, Globe, Moon, Sun,
  HardDrive, Layers, AlertTriangle, Folder, Keyboard
} from 'lucide-react';
import { apiError, apiUrl } from './api';
import { MorningBriefSetting } from './MorningBriefSetting';
import { ProfileSetting } from './ProfileSetting';
import { VoiceSetting } from './VoiceSetting';
import { AdvancedToolsSetting } from './AdvancedToolsSetting';
import { useTranslation } from './i18n';
import type { TranslationKey } from './i18n';
import { useTheme } from './theme';
import { checkForUpdate, installUpdate, isTauri } from './desktop';
import type { UpdateError, UpdateInfo } from './desktop';
import { TopHeader } from './TopHeader';
import './privacy.css';
import { useKeyboardShortcuts, CATEGORY_ORDER } from './shortcuts';
import { ModelSelector } from './ModelSelector';

interface SettingsProps {
  onWorkspaceSwitched?: () => void;
}

export function Settings({ onWorkspaceSwitched }: SettingsProps) {
  const [activeTab, setActiveTab] = useState<'workspace' | 'providers' | 'general' | 'storage' | 'shortcuts' | 'advanced'>('workspace');

  // Provider Settings State
  const [provider, setProvider] = useState('');      // '' = nothing chosen yet (never an assumed provider)
  const [model, setModel] = useState('');
  const [applyToAllAgents, setApplyToAllAgents] = useState(false);
  const [timeout, setTimeoutVal] = useState<number>(120);
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  // Workspace Settings State
  const [workspaceInfo, setWorkspaceInfo] = useState<any>(null);
  const [workspaceStats, setWorkspaceStats] = useState<any>(null);
  const [otherSpaces, setOtherSpaces] = useState<any[]>([]);

  // Connected Project State
  const [projectPathInput, setProjectPathInput] = useState('');
  const [isEditingProject, setIsEditingProject] = useState(false);
  const [savingProject, setSavingProject] = useState(false);

  const showToast = useContext(ToastContext);
  const { t, language, setLanguage } = useTranslation();
  const [updateState, setUpdateState] = useState<'idle' | 'checking' | 'installing'>('idle');
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [updateError, setUpdateError] = useState<UpdateError | null>(null);
  const { theme, setTheme } = useTheme();
  const { shortcuts, formatShortcut, openShortcutsModal } = useKeyboardShortcuts();

  const useSpace = async (sp: any) => {
    try {
      const res = await fetch(apiUrl('/api/workspaces/switch'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ workspace_id: sp.id, path: sp.path }) });
      if (res.ok && onWorkspaceSwitched) onWorkspaceSwitched();
    } catch (err) {
      console.error(err);
    }
  };

  const fetchWorkspaceData = () => {
    fetch(apiUrl('/api/workspaces'))
      .then(res => res.json())
      .then(list => setOtherSpaces(Array.isArray(list) ? list.filter((w: any) => !w.is_active) : []))
      .catch(() => setOtherSpaces([]));
    fetch(apiUrl('/api/workspace'))
      .then(res => res.json())
      .then(data => {
        setWorkspaceInfo(data);
        if (data && data.name) {
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
        setProvider(data.provider || '');
        setModel(data.model || '');
        setTimeoutVal(data.timeout || (data.provider === 'ollama' ? 120 : 30));
        setStatus(data.configured || {});
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (provider === 'ollama') {
      setTimeoutVal(120);
    } else {
      setTimeoutVal(30);
    }
  }, [provider]);

  const handleSaveProvider = async () => {
    if (!provider || !model.trim()) {
      showToast(t('szChooseAProviderAndAModel2'), 'error');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(apiUrl('/api/settings/provider'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          model,
          timeout: Number(timeout),
          api_key: apiKey || null,
          apply_to_all_agents: applyToAllAgents,
        })
      });
      if (res.ok) {
        if (apiKey) {
          setStatus({ ...status, [provider]: true });
          setApiKey('');
        }
        showToast(t('szProviderSettingsSavedSuccessfully'), 'success');
      } else {
        showToast((await apiError(res, t('szUnableToSaveProviderSettings'))).message, 'error');
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : t('szUnableToSaveProviderSettings'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleTestProvider = async () => {
    if (!provider || !model.trim()) {
      showToast(t('szChooseAProviderAndAModel3'), 'error');
      return;
    }
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
        showToast(t('szProviderConnectionSuccessful'), 'success');
      } else {
        showToast((await apiError(res, t('szProviderTestFailed'))).message, 'error');
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : t('szProviderTestFailed'), 'error');
    } finally {
      setTesting(false);
    }
  };

  const handleClearKnowledge = async () => {
    try {
      const res = await fetch(apiUrl('/api/workspaces/current/clear-knowledge'), {
        method: 'POST'
      });
      if (res.ok) {
        showToast(t('szWorkspaceKnowledgeCleared'), 'info');
        fetchWorkspaceData();
      } else {
        const err = await apiError(res, t('szFailedToClearKnowledge'));
        showToast(err.message, 'error');
      }
    } catch (err: any) {
      console.error(err);
      showToast(err?.message || t('szErrorClearingKnowledge'), 'error');
    }
  };

  const handleResetWorkspace = async () => {
    try {
      const res = await fetch(apiUrl('/api/workspaces/current/reset'), {
        method: 'POST'
      });
      if (res.ok) {
        showToast(t('szWorkspaceResetToInitialCleanState'), 'info');
        fetchWorkspaceData();
        if (onWorkspaceSwitched) onWorkspaceSwitched();
      } else {
        const err = await apiError(res, t('szFailedToResetWorkspace'));
        showToast(err.message, 'error');
      }
    } catch (err: any) {
      console.error(err);
      showToast(err?.message || t('szErrorResettingWorkspace'), 'error');
    }
  };

  const handleConnectProject = async () => {
    if (!projectPathInput.trim()) return;
    setSavingProject(true);
    try {
      const res = await fetch(apiUrl('/api/workspace/project'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: projectPathInput.trim(),
          project_type: 'local'
        })
      });
      if (res.ok) {
        showToast(language === 'it' ? 'Progetto collegato con successo.' : 'Project connected successfully.', 'info');
        setProjectPathInput('');
        setIsEditingProject(false);
        fetchWorkspaceData();
      } else {
        const err = await apiError(res, t('szFailedToConnectProject'));
        showToast(err.message, 'error');
      }
    } catch (err: any) {
      showToast(err?.message || t('szFailedToConnectProject'), 'error');
    } finally {
      setSavingProject(false);
    }
  };

  const handleDisconnectProject = async () => {
    try {
      const res = await fetch(apiUrl('/api/workspace/project'), {
        method: 'DELETE'
      });
      if (res.ok) {
        showToast(language === 'it' ? 'Progetto disconnesso.' : 'Project disconnected.', 'info');
        fetchWorkspaceData();
        setIsEditingProject(false);
      } else {
        const err = await apiError(res, t('szFailedToDisconnectProject'));
        showToast(err.message, 'error');
      }
    } catch (err: any) {
      showToast(err?.message || t('szFailedToDisconnectProject'), 'error');
    }
  };


  const formatBytes = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const UPDATE_ERROR_KEYS: Record<UpdateError['code'], TranslationKey> = {
    not_configured: 'updatesErrorNotConfigured',
    network: 'updatesErrorNetwork',
    signature: 'updatesErrorSignature',
    install: 'updatesErrorInstall',
    busy: 'updatesErrorBusy',
    unknown: 'updatesErrorNetwork',
  };
  const updateErrorKey = (code: UpdateError['code']): TranslationKey => UPDATE_ERROR_KEYS[code] ?? 'updatesErrorNetwork';

  const handleCheckUpdate = async () => {
    setUpdateState('checking');
    setUpdateError(null);
    setUpdateInfo(null);
    try {
      setUpdateInfo(await checkForUpdate());
    } catch (e) {
      setUpdateError(e as UpdateError);
    } finally {
      setUpdateState('idle');
    }
  };

  const handleInstallUpdate = async () => {
    setUpdateState('installing');
    setUpdateError(null);
    try {
      await installUpdate(); // the app relaunches itself on success
    } catch (e) {
      setUpdateError(e as UpdateError);
      setUpdateState('idle');
    }
  };

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <TopHeader variant="page" title={t('settingsTitle')} subtitle={t('settingsIntro')} />
      <div className="settings-body">

      {/* Tabs */}
      <div className="pv-tabs settings-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === 'workspace'}
          className={activeTab === 'workspace' ? 'on' : ''}
          onClick={() => setActiveTab('workspace')}
        >
          <Layers size={16} /> {t('workspace')}
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'providers'}
          className={activeTab === 'providers' ? 'on' : ''}
          onClick={() => setActiveTab('providers')}
        >
          <Cpu size={16} /> {t('providersTab')}
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'storage'}
          className={activeTab === 'storage' ? 'on' : ''}
          onClick={() => setActiveTab('storage')}
        >
          <HardDrive size={16} /> {t('storageTab')}
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'general'}
          className={activeTab === 'general' ? 'on' : ''}
          onClick={() => setActiveTab('general')}
        >
          <Globe size={16} /> {t('generalTab')}
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'shortcuts'}
          className={activeTab === 'shortcuts' ? 'on' : ''}
          onClick={() => setActiveTab('shortcuts')}
        >
          <Keyboard size={16} /> {t('shortcutsTab')}
        </button>
      </div>

      {/* WORKSPACE TAB */}
      {activeTab === 'workspace' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Connected Project Access */}
          <div className="card" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Folder size={18} className="text-primary" />
                <h3 style={{ fontSize: '16px', fontWeight: 600 }}>{language === 'it' ? 'Cartella di lavoro' : 'Working folder'}</h3>
              </div>
              {workspaceInfo?.project && (
                <span
                  style={{
                    fontSize: '11px',
                    fontWeight: 600,
                    padding: '3px 8px',
                    borderRadius: '12px',
                    backgroundColor: workspaceInfo.project.exists ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                    color: workspaceInfo.project.exists ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)',
                    border: `1px solid ${workspaceInfo.project.exists ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`
                  }}
                >
                  {workspaceInfo.project.exists ? (language === 'it' ? 'Collegato' : 'Connected') : (language === 'it' ? 'Directory non trovata' : 'Directory not found')}
                </span>
              )}
            </div>

            <p className="text-muted" style={{ fontSize: '13px', marginBottom: '16px', lineHeight: 1.5 }}>
              {language === 'it'
                ? 'Scegli una cartella del tuo computer in cui Aether può leggere e scrivere file per te. Fuori da qui non tocca nulla.'
                : 'Connect a local directory to this workspace. Agents will securely access and edit files directly within this project folder.'}
            </p>

            {workspaceInfo?.project && !isEditingProject ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{
                  padding: '12px 14px',
                  backgroundColor: 'hsl(var(--muted)/0.5)',
                  borderRadius: '8px',
                  border: '1px solid hsl(var(--border))',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '12px'
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: '13.5px', color: 'hsl(var(--fg))' }}>
                      📁 {workspaceInfo.project.name || 'Project'}
                    </div>
                    <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontFamily: 'monospace', marginTop: '2px', wordBreak: 'break-all' }}>
                      {workspaceInfo.project.path}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                    <button className="btn btn-secondary" style={{ fontSize: '12px', padding: '6px 12px' }} onClick={() => { setProjectPathInput(workspaceInfo.project.path); setIsEditingProject(true); }}>
                      {language === 'it' ? 'Cambia' : 'Change'}
                    </button>
                    <button className="btn btn-destructive" style={{ fontSize: '12px', padding: '6px 12px' }} onClick={handleDisconnectProject}>
                      {language === 'it' ? 'Disconnetti' : 'Disconnect'}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div>
                <label className="form-label">{language === 'it' ? 'Cartella' : 'Folder'}</label>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="/Users/name/projects/my-app"
                    value={projectPathInput}
                    onChange={e => setProjectPathInput(e.target.value)}
                  />
                  <button
                    className="btn btn-primary"
                    style={{ padding: '8px 18px', flexShrink: 0 }}
                    onClick={handleConnectProject}
                    disabled={savingProject || !projectPathInput.trim()}
                  >
                    {language === 'it' ? 'Collega' : 'Connect'}
                  </button>
                  {isEditingProject && (
                    <button
                      className="btn btn-ghost"
                      style={{ padding: '8px 12px', flexShrink: 0 }}
                      onClick={() => setIsEditingProject(false)}
                    >
                      {language === 'it' ? 'Annulla' : 'Cancel'}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Previous spaces: Aether is one personal space now; older ones stay reachable here, nothing is deleted. */}
          {otherSpaces.length > 0 && (
            <div className="card" style={{ padding: '24px' }} data-testid="previous-spaces">
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>{t('prevSpacesTitle')}</h3>
              <p className="text-muted" style={{ fontSize: '13px', marginBottom: '14px' }}>{t('prevSpacesDesc')}</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {otherSpaces.map(sp => (
                  <div key={sp.id || sp.path} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '10px 12px', background: 'hsl(var(--muted)/0.5)', borderRadius: '10px' }}>
                    <span style={{ fontSize: '13.5px' }}>{sp.name}</span>
                    <button className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: '12.5px' }} onClick={() => useSpace(sp)} data-testid={`use-space-${sp.id}`}>{t('prevSpacesUse')}</button>
                  </div>
                ))}
              </div>
            </div>
          )}

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
                    // The model belongs to the provider: a new provider starts with NO model, the user picks one.
                    setProvider(e.target.value);
                    setModel('');
                  }}
                >
                  <option value="">— Choose a provider —</option>
                  <option value="ollama">Ollama (Local)</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="groq">Groq</option>
                </select>
              </div>

              <div>
                <ModelSelector
                  provider={provider}
                  apiKey={apiKey}
                  value={model}
                  teamDefaultModel={model}
                  onChange={newModel => setModel(newModel || '')}
                  isTeamLevel={true}
                  label={t('model')}
                />
              </div>

              <label htmlFor="settings-apply-all-checkbox" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', padding: '6px 0', fontSize: '13.5px', cursor: 'pointer', userSelect: 'none' }}>
                <span>
                  {language === 'it' ? 'Usa questo modello per tutti gli assistenti' : 'Use this model for every assistant'}
                  <small className="text-muted" style={{ display: 'block', fontSize: '12.5px', marginTop: '2px' }}>
                    {language === 'it' ? 'Sostituisce le scelte fatte per i singoli assistenti.' : 'Replaces the choices made for single assistants.'}
                  </small>
                </span>
                <input
                  type="checkbox"
                  role="switch"
                  className="ui-switch"
                  id="settings-apply-all-checkbox"
                  checked={applyToAllAgents}
                  onChange={e => setApplyToAllAgents(e.target.checked)}
                />
              </label>

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

              {provider && provider !== 'ollama' && (
                <div>
                  <label className="form-label">{t('apiKey')}</label>
                  <input
                    type="password"
                    className="form-input"
                    placeholder={
                      status[provider]
                        ? '•••••••••••••••• (Configured)'
                        : provider === 'groq'
                        ? 'Enter GROQ API Key (gsk_...)'
                        : `Enter ${provider.toUpperCase()} API Key`
                    }
                    value={apiKey}
                    onChange={e => setApiKey(e.target.value)}
                  />
                </div>
              )}

              <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                <button
                  className="btn btn-primary"
                  onClick={handleSaveProvider}
                  disabled={saving || !provider || !model.trim()}
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
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(200px, 100%), 1fr))', gap: '16px' }}>
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
          <ProfileSetting onReplay={() => window.location.reload()} />
          <VoiceSetting />
          <MorningBriefSetting />
          <AdvancedToolsSetting />
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

          {isTauri() && (
            <div className="card" style={{ padding: '24px' }} data-testid="updates-card">
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>{t('updatesTitle')}</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {updateInfo && (
                  <div style={{ fontSize: '13.5px' }}>
                    {t('updatesCurrentVersion', { version: updateInfo.current_version })}
                  </div>
                )}
                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <button className="btn btn-secondary" onClick={handleCheckUpdate} disabled={updateState !== 'idle'}>
                    {updateState === 'checking' ? t('updatesChecking') : t('updatesCheck')}
                  </button>
                  {updateInfo?.available && (
                    <button className="btn btn-primary" onClick={handleInstallUpdate} disabled={updateState !== 'idle'}>
                      {t('updatesInstall')}
                    </button>
                  )}
                </div>
                {updateState === 'installing' && <div style={{ fontSize: '13.5px' }}>{t('updatesInstalling')}</div>}
                {updateInfo && !updateInfo.available && <div style={{ fontSize: '13.5px' }}>{t('updatesUpToDate')}</div>}
                {updateInfo?.available && (
                  <div style={{ fontSize: '13.5px' }}>
                    <strong>{t('updatesAvailable', { version: updateInfo.version ?? '' })}</strong>
                    {updateInfo.notes && <div style={{ opacity: 0.8, marginTop: '4px' }}>{updateInfo.notes}</div>}
                  </div>
                )}
                {updateError && (
                  <div role="alert" style={{ fontSize: '13.5px', color: 'hsl(var(--destructive, 0 70% 55%))' }}>
                    {t(updateErrorKey(updateError.code))}
                  </div>
                )}
                <div style={{ fontSize: '12.5px', opacity: 0.7 }}>{t('updatesManualHint')}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* SHORTCUTS TAB */}
      {activeTab === 'shortcuts' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div className="card" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Keyboard size={20} className="text-primary" />
                <div>
                  <h3 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{t('shortcutsTitle')}</h3>
                  <p style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', margin: '2px 0 0' }}>
                    {t('shortcutsSubtitle')}
                  </p>
                </div>
              </div>
              <button className="btn btn-secondary" onClick={openShortcutsModal} style={{ fontSize: '12.5px' }}>
                {t('szOpenQuickHelp')}
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {CATEGORY_ORDER.map((group) => {
                const groupShortcuts = shortcuts.filter((s) => s.category === group.category);
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
                              padding: '8px 12px',
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
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
