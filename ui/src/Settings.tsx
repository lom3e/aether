import { useState, useEffect, useContext } from 'react';
import { ToastContext } from './toast';
import {
  Settings as SettingsIcon, Cpu, Globe, Moon, Sun,
  ShieldCheck, Terminal, HardDrive, RefreshCw
} from 'lucide-react';
import { apiError, apiUrl } from './api';
import { useTranslation } from './i18n';
import { useTheme } from './theme';

export function Settings() {
  const [activeTab, setActiveTab] = useState<'general' | 'providers' | 'storage' | 'advanced'>('general');
  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('qwen3.5:9b');
  const [timeout, setTimeoutVal] = useState<number>(120);
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [workspaceInfo, setWorkspaceInfo] = useState<any>(null);

  const showToast = useContext(ToastContext);
  const { t, language, setLanguage } = useTranslation();
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    fetch(apiUrl('/api/settings/provider'))
      .then(res => res.json())
      .then(data => {
        setProvider(data.provider || 'ollama');
        setModel(data.model || 'qwen3.5:9b');
        setTimeoutVal(data.timeout || (data.provider === 'ollama' ? 120 : 30));
        setStatus(data.configured || {});
      })
      .catch(console.error);

    fetch(apiUrl('/api/workspace'))
      .then(res => res.json())
      .then(data => setWorkspaceInfo(data))
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

    // Set default recommended timeout when switching provider
    if (provider === 'ollama') {
      setTimeoutVal(120);
    } else {
      setTimeoutVal(30);
    }
  }, [provider]);

  const handleSave = async () => {
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
        showToast('Settings saved successfully.', 'success');
      } else {
        showToast((await apiError(res, 'Unable to save provider settings.')).message, 'error');
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Unable to save provider settings.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await fetch(apiUrl('/api/settings/provider/test'), {
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
        showToast('Connection successful!', 'success');
      } else {
        showToast((await apiError(res, 'Connection failed.')).message, 'error');
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Connection failed.', 'error');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <div className="top-header">
        <div className="top-header-title">
          <SettingsIcon size={18} className="text-primary" />
          <span>{t('settingsTitle')}</span>
        </div>
      </div>

      <div style={{ maxWidth: '880px', margin: '36px auto', padding: '0 24px' }}>
        {/* Navigation Tabs */}
        <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid hsl(var(--border))', marginBottom: '28px', paddingBottom: '8px' }}>
          <button
            className={`btn btn-ghost ${activeTab === 'general' ? 'active' : ''}`}
            onClick={() => setActiveTab('general')}
          >
            <Globe size={15} /> {t('generalTab')}
          </button>
          <button
            className={`btn btn-ghost ${activeTab === 'providers' ? 'active' : ''}`}
            onClick={() => setActiveTab('providers')}
          >
            <Cpu size={15} /> {t('providersTab')}
          </button>
          <button
            className={`btn btn-ghost ${activeTab === 'storage' ? 'active' : ''}`}
            onClick={() => setActiveTab('storage')}
          >
            <HardDrive size={15} /> {t('storageTab')}
          </button>
          <button
            className={`btn btn-ghost ${activeTab === 'advanced' ? 'active' : ''}`}
            onClick={() => setActiveTab('advanced')}
          >
            <Terminal size={15} /> {t('advancedTab')}
          </button>
        </div>

        {/* Tab 1: General (Language & Theme) */}
        {activeTab === 'general' && (
          <div className="card" style={{ padding: '28px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div>
              <h3 style={{ fontSize: '16px', marginBottom: '4px' }}>{t('language')}</h3>
              <p className="text-muted" style={{ fontSize: '13px', marginBottom: '12px' }}>
                Select your preferred interface language.
              </p>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  className={`btn ${language === 'en' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setLanguage('en')}
                >
                  English (EN)
                </button>
                <button
                  className={`btn ${language === 'it' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setLanguage('it')}
                >
                  Italiano (IT)
                </button>
              </div>
            </div>

            <div style={{ borderTop: '1px solid hsl(var(--border)/0.5)', paddingTop: '20px' }}>
              <h3 style={{ fontSize: '16px', marginBottom: '4px' }}>{t('theme')}</h3>
              <p className="text-muted" style={{ fontSize: '13px', marginBottom: '12px' }}>
                Customize the look and feel of your workspace.
              </p>
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
                <button
                  className={`btn ${theme === 'system' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setTheme('system')}
                >
                  <RefreshCw size={15} /> {t('themeSystem')}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: AI Providers */}
        {activeTab === 'providers' && (
          <div className="card" style={{ padding: '28px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
              <label className="form-label">{t('provider')}</label>
              <select
                className="form-select"
                value={provider}
                onChange={e => setProvider(e.target.value)}
              >
                <option value="ollama">Ollama (Local / Offline)</option>
                <option value="openai">OpenAI (GPT-4o, GPT-4o-mini)</option>
                <option value="anthropic">Anthropic (Claude 3.5 Sonnet)</option>
                <option value="gemini">Google Gemini (Gemini 1.5 Pro)</option>
                <option value="mock">Mock Provider (Testing)</option>
              </select>
            </div>

            <div>
              <label className="form-label">{t('model')}</label>
              {availableModels.length > 0 ? (
                <select
                  className="form-select"
                  value={model}
                  onChange={e => setModel(e.target.value)}
                >
                  {availableModels.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  className="form-input"
                  value={model}
                  onChange={e => setModel(e.target.value)}
                  placeholder="e.g. qwen3.5:9b, gpt-4o, claude-3-5-sonnet"
                />
              )}
            </div>

            {/* Provider Timeout Config */}
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
              <div style={{ fontSize: '11.5px', color: 'hsl(var(--muted-fg))', marginTop: '6px' }}>
                {t('timeoutHelp')}
              </div>
            </div>

            {provider !== 'ollama' && provider !== 'mock' && (
              <div>
                <label className="form-label">{t('apiKey')}</label>
                <input
                  type="password"
                  className="form-input"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder={status[provider] ? '•••••••••••••••••••• (Configured)' : 'Enter API Key'}
                />
              </div>
            )}

            <div style={{ display: 'flex', gap: '12px', marginTop: '12px', borderTop: '1px solid hsl(var(--border)/0.5)', paddingTop: '20px' }}>
              <button
                className="btn btn-primary"
                onClick={handleSave}
                disabled={saving || testing}
              >
                {saving ? t('loading') : t('saveSettings')}
              </button>
              <button
                className="btn btn-secondary"
                onClick={handleTest}
                disabled={saving || testing}
              >
                {testing ? t('testing') : t('testConnection')}
              </button>
            </div>
          </div>
        )}

        {/* Tab 3: Storage & Memory */}
        {activeTab === 'storage' && (
          <div className="card" style={{ padding: '28px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <h3 style={{ fontSize: '16px', margin: 0 }}>Persistent Workspace Storage</h3>
            <p className="text-muted" style={{ fontSize: '13px', margin: 0 }}>
              All conversations, agent identities, and knowledge chunks are persisted locally in SQLite databases.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginTop: '8px' }}>
              <div style={{ padding: '16px', backgroundColor: 'hsl(var(--muted)/0.5)', borderRadius: 'var(--radius)', border: '1px solid hsl(var(--border))' }}>
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>Knowledge Chunks</div>
                <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px' }}>
                  {workspaceInfo?.knowledge_chunks ?? 0}
                </div>
                <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                  Stored in <code>data/knowledge.db</code>
                </div>
              </div>

              <div style={{ padding: '16px', backgroundColor: 'hsl(var(--muted)/0.5)', borderRadius: 'var(--radius)', border: '1px solid hsl(var(--border))' }}>
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>Agent Identities</div>
                <div style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px' }}>
                  {workspaceInfo?.agents?.length ?? 0}
                </div>
                <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                  Stored in <code>data/identity.db</code>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: Advanced & Diagnostics */}
        {activeTab === 'advanced' && (
          <div className="card" style={{ padding: '28px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <h3 style={{ fontSize: '16px', margin: 0 }}>CLI & Developer Diagnostics</h3>
            <p className="text-muted" style={{ fontSize: '13px', margin: 0 }}>
              You can execute tasks directly from the command line while sharing the same local workspace configuration:
            </p>

            <div style={{ backgroundColor: 'hsl(var(--muted))', padding: '14px 18px', borderRadius: 'var(--radius)', fontFamily: 'var(--font-mono)', fontSize: '12.5px', lineHeight: 1.6 }}>
              <div># Run workforce task via CLI</div>
              <div style={{ color: 'hsl(var(--primary))' }}>aether run "Analizza l'azienda Acme Robotics"</div>
              <div style={{ marginTop: '8px' }}># Inspect team configuration</div>
              <div style={{ color: 'hsl(var(--primary))' }}>aether team status</div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'hsl(var(--success))', fontSize: '13px', marginTop: '8px' }}>
              <ShieldCheck size={16} />
              <span>Local-first architecture active (Zero external telemetry or cloud tracking).</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
