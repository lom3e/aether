import { useState, useEffect, useContext } from 'react';
import { Plus, Trash2, Edit2, Layers, AlertTriangle, X } from 'lucide-react';
import { apiUrl, apiError } from './api';
import { ToastContext } from './toast';
import { useTranslation } from './i18n';
import { Tooltip } from './Tooltip';

interface WorkspaceModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentWorkspacePath?: string;
  onWorkspaceSwitched: () => void;
  initialMode?: 'create' | 'manage';
}

const DEFAULT_MODELS: Record<string, string[]> = {
  ollama: ['qwen3.5:9b', 'llama3.3:70b', 'llama3.2:3b', 'deepseek-r1:8b', 'mistral', 'phi4'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'o3-mini', 'gpt-4-turbo'],
  anthropic: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
  gemini: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
};

export function WorkspaceModal({
  isOpen,
  onClose,
  onWorkspaceSwitched,
  initialMode = 'create'
}: WorkspaceModalProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<'create' | 'manage'>(initialMode);
  const [workspaces, setWorkspaces] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Form State
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [presetId, setPresetId] = useState('starter-workforce');
  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('qwen3.5:9b');
  const [availableModels, setAvailableModels] = useState<string[]>(DEFAULT_MODELS.ollama);
  const [isCustomModel, setIsCustomModel] = useState(false);
  const [apiKey, setApiKey] = useState('');

  // Rename / Delete State
  const [editingWsId, setEditingWsId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deletingWs, setDeletingWs] = useState<any | null>(null);

  const showToast = useContext(ToastContext);

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    const fallback = DEFAULT_MODELS[provider] || [];
    fetch(apiUrl(`/api/settings/provider/models?provider=${provider}`))
      .then(res => res.json())
      .then(data => {
        if (data.models && data.models.length > 0) {
          setAvailableModels(data.models);
          if (!isCustomModel) {
            setModel(data.default || data.models[0]);
          }
        } else {
          setAvailableModels(fallback);
          if (!isCustomModel) {
            setModel(fallback[0] || '');
          }
        }
      })
      .catch(() => {
        setAvailableModels(fallback);
        if (!isCustomModel) {
          setModel(fallback[0] || '');
        }
      });
  }, [provider, isCustomModel]);

  const fetchWorkspaces = () => {
    fetch(apiUrl('/api/workspaces'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setWorkspaces(data);
        }
      })
      .catch(console.error);
  };

  useEffect(() => {
    if (isOpen) {
      fetchWorkspaces();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    try {
      const res = await fetch(apiUrl('/api/workspaces'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim(),
          preset_id: presetId,
          provider,
          model,
          api_key: apiKey || null
        })
      });

      if (res.ok) {
        showToast(`Workspace "${name}" created successfully.`, 'success');
        setName('');
        setDescription('');
        onWorkspaceSwitched();
        onClose();
      } else {
        const err = await apiError(res, 'Failed to create workspace.');
        showToast(err.message, 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Error creating workspace', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSwitch = async (ws: any) => {
    if (ws.is_active) return;
    try {
      const res = await fetch(apiUrl('/api/workspaces/switch'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workspace_id: ws.id, path: ws.path })
      });

      if (res.ok) {
        showToast(`Switched to "${ws.name}".`, 'info');
        onWorkspaceSwitched();
        onClose();
      } else {
        const err = await apiError(res, 'Failed to switch workspace.');
        showToast(err.message, 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to switch workspace', 'error');
    }
  };

  const handleRename = async (wsId: string) => {
    if (!renameValue.trim()) {
      setEditingWsId(null);
      return;
    }
    try {
      const res = await fetch(apiUrl(`/api/workspaces/${wsId}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: renameValue.trim() })
      });
      if (res.ok) {
        showToast('Workspace renamed.', 'success');
        setEditingWsId(null);
        fetchWorkspaces();
        onWorkspaceSwitched();
      } else {
        const err = await apiError(res, 'Failed to rename workspace.');
        showToast(err.message, 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to rename', 'error');
    }
  };

  const handleDelete = async () => {
    if (!deletingWs) return;
    try {
      const res = await fetch(apiUrl(`/api/workspaces/${deletingWs.id}`), {
        method: 'DELETE'
      });
      if (res.ok) {
        showToast(`Workspace "${deletingWs.name}" deleted.`, 'info');
        setDeletingWs(null);
        fetchWorkspaces();
        onWorkspaceSwitched();
      } else {
        const err = await apiError(res, 'Failed to delete workspace.');
        showToast(err.message, 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to delete', 'error');
    }
  };

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      backgroundColor: 'rgba(0,0,0,0.6)',
      backdropFilter: 'blur(4px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 100,
      padding: '20px'
    }}>
      <div style={{
        backgroundColor: 'hsl(var(--card))',
        border: '1px solid hsl(var(--border))',
        borderRadius: '12px',
        width: '100%',
        maxWidth: '560px',
        maxHeight: '90vh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 20px 40px rgba(0,0,0,0.4)',
        overflow: 'hidden'
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid hsl(var(--border))',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <button
              className={`btn btn-ghost ${mode === 'create' ? 'active' : ''}`}
              style={{ padding: '6px 12px', fontSize: '13px', fontWeight: 600 }}
              onClick={() => setMode('create')}
            >
              <Plus size={15} /> {t('newWorkspace')}
            </button>
            <button
              className={`btn btn-ghost ${mode === 'manage' ? 'active' : ''}`}
              style={{ padding: '6px 12px', fontSize: '13px', fontWeight: 600 }}
              onClick={() => setMode('manage')}
            >
              <Layers size={15} /> {t('allWorkspaces')} ({workspaces.length})
            </button>
          </div>
          <button className="btn btn-ghost" style={{ padding: '6px' }} onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
          {mode === 'create' ? (
            <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label className="form-label" style={{ fontWeight: 600, fontSize: '13px' }}>
                  {t('workspaceName')}
                </label>
                <input
                  type="text"
                  className="form-input"
                  placeholder={t('workspaceNamePlaceholder')}
                  value={name}
                  onChange={e => setName(e.target.value)}
                  required
                  autoFocus
                />
              </div>

              <div>
                <label className="form-label" style={{ fontWeight: 600, fontSize: '13px' }}>
                  {t('descriptionOptional')}
                </label>
                <input
                  type="text"
                  className="form-input"
                  placeholder={t('workspaceDescPlaceholder')}
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                />
              </div>

              <div>
                <label className="form-label" style={{ fontWeight: 600, fontSize: '13px' }}>
                  {t('starterWorkforcePreset')}
                </label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '12px 14px',
                      border: `1px solid ${presetId === 'starter-workforce' ? 'hsl(var(--primary))' : 'hsl(var(--border))'}`,
                      borderRadius: '8px',
                      backgroundColor: presetId === 'starter-workforce' ? 'hsl(var(--primary)/0.05)' : 'transparent',
                      cursor: 'pointer'
                    }}
                  >
                    <input
                      type="radio"
                      name="preset"
                      value="starter-workforce"
                      checked={presetId === 'starter-workforce'}
                      onChange={() => setPresetId('starter-workforce')}
                    />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>{t('starterWorkforceRecommended')}</div>
                      <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>{t('starterWorkforceDesc')}</div>
                    </div>
                  </label>

                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '12px 14px',
                      border: `1px solid ${presetId === 'research-workforce' ? 'hsl(var(--primary))' : 'hsl(var(--border))'}`,
                      borderRadius: '8px',
                      backgroundColor: presetId === 'research-workforce' ? 'hsl(var(--primary)/0.05)' : 'transparent',
                      cursor: 'pointer'
                    }}
                  >
                    <input
                      type="radio"
                      name="preset"
                      value="research-workforce"
                      checked={presetId === 'research-workforce'}
                      onChange={() => setPresetId('research-workforce')}
                    />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>{t('researchWorkforce')}</div>
                      <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>{t('researchWorkforceDesc')}</div>
                    </div>
                  </label>

                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '12px 14px',
                      border: `1px solid ${presetId === 'empty' ? 'hsl(var(--primary))' : 'hsl(var(--border))'}`,
                      borderRadius: '8px',
                      backgroundColor: presetId === 'empty' ? 'hsl(var(--primary)/0.05)' : 'transparent',
                      cursor: 'pointer'
                    }}
                  >
                    <input
                      type="radio"
                      name="preset"
                      value="empty"
                      checked={presetId === 'empty'}
                      onChange={() => setPresetId('empty')}
                    />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>{t('emptyWorkspace')}</div>
                      <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>{t('emptyWorkspaceDesc')}</div>
                    </div>
                  </label>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label className="form-label" style={{ fontWeight: 600, fontSize: '13px' }}>{t('provider')}</label>
                  <select
                    className="form-select"
                    value={provider}
                    onChange={e => {
                      setProvider(e.target.value);
                      setIsCustomModel(false);
                    }}
                  >
                    <option value="ollama">Ollama (Local)</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="gemini">Google Gemini</option>
                  </select>
                </div>

                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <label className="form-label" style={{ fontWeight: 600, fontSize: '13px', margin: 0 }}>{t('model')}</label>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      style={{ fontSize: '11px', padding: '1px 6px', height: 'auto', textDecoration: 'underline', color: 'hsl(var(--primary))' }}
                      onClick={() => {
                        if (isCustomModel) {
                          setIsCustomModel(false);
                          const list = availableModels.length > 0 ? availableModels : (DEFAULT_MODELS[provider] || []);
                          setModel(list[0] || '');
                        } else {
                          setIsCustomModel(true);
                        }
                      }}
                    >
                      {isCustomModel ? t('suggestedList') : t('customModel')}
                    </button>
                  </div>
                  {isCustomModel ? (
                    <input
                      type="text"
                      className="form-input"
                      value={model}
                      placeholder="e.g. custom-model:latest"
                      onChange={e => setModel(e.target.value)}
                      required
                    />
                  ) : (
                    <select
                      className="form-select"
                      value={model}
                      onChange={e => {
                        if (e.target.value === '__custom__') {
                          setIsCustomModel(true);
                        } else {
                          setModel(e.target.value);
                        }
                      }}
                    >
                      {availableModels.map(m => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                      <option value="__custom__">{t('otherCustomModel')}</option>
                    </select>
                  )}
                </div>
              </div>

              {provider !== 'ollama' && (
                <div>
                  <label className="form-label" style={{ fontWeight: 600, fontSize: '13px' }}>{t('apiKey')}</label>
                  <input
                    type="password"
                    className="form-input"
                    placeholder={`Enter ${provider.toUpperCase()} API Key`}
                    value={apiKey}
                    onChange={e => setApiKey(e.target.value)}
                  />
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '12px' }}>
                <button type="button" className="btn btn-secondary" onClick={onClose}>
                  {t('cancel')}
                </button>
                <button type="submit" className="btn btn-primary" disabled={loading || !name.trim()}>
                  {loading ? t('creating') : t('createAndOpenWorkspace')}
                </button>
              </div>
            </form>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {workspaces.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '36px 16px' }}>
                  <Layers size={36} className="text-muted" style={{ margin: '0 auto 12px', opacity: 0.6 }} />
                  <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>{t('noWorkspacesSaved')}</div>
                  <p className="text-muted" style={{ fontSize: '13px', marginBottom: '16px', maxWidth: '360px', margin: '0 auto 16px' }}>
                    {t('noActiveWorkspaceDesc')}
                  </p>
                  <button className="btn btn-primary" onClick={() => setMode('create')}>
                    <Plus size={14} /> {t('newWorkspaceBtn')}
                  </button>
                </div>
              ) : (
                workspaces.map(ws => (
                  <div
                    key={ws.id || ws.path}
                    style={{
                      padding: '14px',
                      borderRadius: '8px',
                      border: `1px solid ${ws.is_active ? 'hsl(var(--primary))' : 'hsl(var(--border))'}`,
                      backgroundColor: ws.is_active ? 'hsl(var(--primary)/0.05)' : 'hsl(var(--card))',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '12px'
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      {editingWsId === ws.id ? (
                        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                          <input
                            type="text"
                            className="form-input"
                            style={{ padding: '4px 8px', fontSize: '13px' }}
                            value={renameValue}
                            onChange={e => setRenameValue(e.target.value)}
                            autoFocus
                            onKeyDown={e => {
                              if (e.key === 'Enter') handleRename(ws.id);
                              if (e.key === 'Escape') setEditingWsId(null);
                            }}
                          />
                          <button className="btn btn-primary" style={{ padding: '4px 8px', fontSize: '12px' }} onClick={() => handleRename(ws.id)}>
                            {t('save')}
                          </button>
                          <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '12px' }} onClick={() => setEditingWsId(null)}>
                            {t('cancel')}
                          </button>
                        </div>
                      ) : (
                        <>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontWeight: 600, fontSize: '14px', color: 'hsl(var(--fg))' }}>
                              {ws.name}
                            </span>
                            {ws.is_active && (
                              <span className="badge" style={{ fontSize: '10px', background: 'hsl(var(--primary))', color: 'hsl(var(--primary-fg))' }}>
                                {t('statusActive')}
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {ws.path}
                          </div>
                        </>
                      )}
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {!ws.is_active && (
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '5px 10px', fontSize: '12px' }}
                          onClick={() => handleSwitch(ws)}
                        >
                          {t('switchWorkspace')}
                        </button>
                      )}
                      <Tooltip content={t('rename')} position="top">
                        <button
                          className="btn btn-ghost"
                          style={{ padding: '6px' }}
                          onClick={() => {
                            setEditingWsId(ws.id);
                            setRenameValue(ws.name);
                          }}
                        >
                          <Edit2 size={14} />
                        </button>
                      </Tooltip>
                      <Tooltip content={t('deleteWorkspaceTitle')} position="top">
                        <button
                          className="btn btn-ghost"
                          style={{ padding: '6px', color: 'hsl(var(--destructive))' }}
                          data-testid="delete-workspace-btn"
                          onClick={() => setDeletingWs(ws)}
                        >
                          <Trash2 size={14} />
                        </button>
                      </Tooltip>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Delete Confirmation Sub-Modal */}
        {deletingWs && (
          <div style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            zIndex: 10
          }}>
            <div style={{
              backgroundColor: 'hsl(var(--card))',
              border: '1px solid hsl(var(--destructive))',
              borderRadius: '10px',
              padding: '20px',
              maxWidth: '440px',
              width: '100%',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'hsl(var(--destructive))' }}>
                <AlertTriangle size={20} />
                <h3 style={{ fontSize: '16px', fontWeight: 600 }}>{t('deleteWorkspaceConfirmTitle')}</h3>
              </div>
              <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', lineHeight: 1.5 }}>
                {t('deleteWorkspaceConfirmDesc')}
              </p>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '6px' }}>
                <button className="btn btn-secondary" onClick={() => setDeletingWs(null)}>
                  {t('cancel')}
                </button>
                <button className="btn btn-destructive" data-testid="confirm-delete-workspace-btn" onClick={handleDelete}>
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
