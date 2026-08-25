import { useState, useEffect, useContext, useCallback } from 'react';
import {
  Users, Plus, Edit, Trash2, ArrowRight, X, Sparkles, Layers,
  Bot, ShieldCheck, AlertTriangle, ChevronDown, ChevronUp
} from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';
import { useTranslation } from './i18n';
import { TopHeader } from './TopHeader';
import { IdentityBadge } from './identity';
import { TeamTopology } from './TeamTopology';
import { AutoArchitectModal } from './AutoArchitectModal';
import { ModelSelector } from './ModelSelector';
import { VisualIconSelect, VisualColorSelect } from './VisualSelect';
import { DelegationSelector } from './DelegationSelector';

type TeamAgent = {
  name: string;
  role: string;
  delegates_to: string[];
  skills: string[];
  provider?: string | null;
  model?: string | null;
  icon?: string | null;
  color?: string | null;
};

function TeamBuilder({
  onClose,
  onSaved,
  onDeleted,
  initialTeam
}: {
  onClose: () => void;
  onSaved: () => void;
  onDeleted?: () => void;
  initialTeam?: any;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(initialTeam?.name || '');
  const [provider, setProvider] = useState(initialTeam?.default_provider || 'ollama');
  const [model, setModel] = useState(initialTeam?.default_model || 'qwen3.5:9b');
  const [teamIcon, setTeamIcon] = useState(initialTeam?.icon || 'Bot');
  const [teamColor, setTeamColor] = useState(initialTeam?.color || 'violet');
  const [agents, setAgents] = useState<TeamAgent[]>([
    { name: 'Manager', role: 'Coordinates the workforce', delegates_to: [], skills: [], icon: 'Bot', color: 'violet', model: null },
    { name: 'Researcher', role: 'Researches and summarizes knowledge', delegates_to: [], skills: ['search_knowledge'], icon: 'Search', color: 'cyan', model: null },
  ]);
  const [openOverrides, setOpenOverrides] = useState<Record<number, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDeleteTeam, setConfirmDeleteTeam] = useState(false);
  const [showModelChangeConfirm, setShowModelChangeConfirm] = useState(false);
  const showToast = useContext(ToastContext);

  useEffect(() => {
    if (!initialTeam) return;
    setName(initialTeam.name || '');
    setProvider(initialTeam.default_provider || 'ollama');
    setModel(initialTeam.default_model || 'qwen3.5:9b');
    setTeamIcon(initialTeam.icon || 'Bot');
    setTeamColor(initialTeam.color || 'violet');
    const loadedAgents = (initialTeam.agents || []).map((agent: any) => ({
      name: agent.name || '',
      role: agent.role || '',
      delegates_to: Array.isArray(agent.delegates_to)
        ? agent.delegates_to
        : (typeof agent.delegates_to === 'string' ? agent.delegates_to.split(',').map((s: string) => s.trim()).filter(Boolean) : []),
      skills: agent.skills || [],
      provider: agent.provider || null,
      model: agent.model || null,
      icon: agent.icon || null,
      color: agent.color || null,
    }));
    setAgents(loadedAgents);

    const overridesMap: Record<number, boolean> = {};
    loadedAgents.forEach((a: TeamAgent, idx: number) => {
      if (a.model || a.provider) {
        overridesMap[idx] = true;
      }
    });
    setOpenOverrides(overridesMap);
  }, [initialTeam]);

  const updateAgent = (index: number, key: keyof TeamAgent, value: any) => {
    setAgents(current => current.map((agent, i) => i === index ? { ...agent, [key]: value } : agent));
  };

  const removeAgent = (index: number) => {
    if (agents.length <= 1) {
      showToast(t('minOneAgentRequired') || 'A team must have at least one agent.', 'warning');
      return;
    }
    const removedName = agents[index].name;
    setAgents(current =>
      current
        .filter((_, i) => i !== index)
        .map(a => ({
          ...a,
          delegates_to: a.delegates_to.filter(d => d !== removedName),
        }))
    );
  };

  const toggleOverride = (index: number) => {
    setOpenOverrides(prev => ({ ...prev, [index]: !prev[index] }));
  };

  const handleSaveClick = () => {
    if (!name.trim() || agents.some(agent => !agent.name.trim() || !agent.role.trim())) return;
    const modelChanged = initialTeam && model !== initialTeam.default_model;
    const hasAgentOverrides = agents.some(a => a.model !== null && a.model !== undefined && a.model !== '');
    if (modelChanged && hasAgentOverrides) {
      setShowModelChangeConfirm(true);
    } else {
      executeSave(false);
    }
  };

  const executeSave = async (applyToAll: boolean) => {
    setShowModelChangeConfirm(false);
    setSaving(true);
    try {
      const response = await fetch(apiUrl(initialTeam ? `/api/teams/${encodeURIComponent(initialTeam.name)}` : '/api/teams'), {
        method: initialTeam ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          provider,
          default_provider: provider,
          default_model: model,
          icon: teamIcon,
          color: teamColor,
          apply_to_all_agents: applyToAll,
          agents: agents.map(agent => ({
            name: agent.name.trim(),
            role: agent.role.trim(),
            delegates_to: agent.delegates_to,
            skills: agent.skills,
            provider: applyToAll ? null : (agent.provider || null),
            model: applyToAll ? null : (agent.model || null),
            icon: agent.icon || null,
            color: agent.color || null,
          })),
        }),
      });
      if (!response.ok) {
        throw await apiError(response, initialTeam ? 'Unable to update team.' : 'Unable to create team.');
      }
      showToast(initialTeam ? (t('teamUpdated') || 'Team aggiornato con successo.') : (t('teamCreated') || 'Team creato con successo.'), 'success');
      onSaved();
      onClose();
    } catch (error) {
      showToast(error instanceof Error ? error.message : (initialTeam ? 'Unable to update team.' : 'Unable to create team.'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteTeam = async () => {
    if (!initialTeam) return;
    if (!confirmDeleteTeam) {
      setConfirmDeleteTeam(true);
      return;
    }
    setDeleting(true);
    try {
      const response = await fetch(apiUrl(`/api/teams/${encodeURIComponent(initialTeam.name)}`), {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw await apiError(response, 'Impossibile eliminare questa squadra.');
      }
      showToast(`Squadra "${initialTeam.name}" eliminata.`, 'info');
      if (onDeleted) onDeleted();
      else onSaved();
      onClose();
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Impossibile eliminare questa squadra.', 'error');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="slide-over" style={{ maxWidth: '720px' }}>
        {/* Header */}
        <div className="slide-over-header" style={{ padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <IdentityBadge icon={teamIcon} color={teamColor} size={20} containerSize={38} />
            <div>
              <h2 style={{ fontSize: '17px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                {initialTeam ? t('editTeam') : t('createTeam')}
              </h2>
              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                {name ? `${name} · ${agents.length} ${agents.length === 1 ? 'membro' : 'membri'}` : 'Configura workforce, topologia e membri'}
              </div>
            </div>
          </div>
          <button className="btn btn-ghost" style={{ padding: '8px' }} onClick={onClose} disabled={saving || deleting}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="slide-over-body" style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>

          {/* CARD 1: Team Profile */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <Bot size={16} className="text-primary" />
              <h3 style={{ fontSize: '14.5px', fontWeight: 600, margin: 0 }}>
                {t('teamIdentitySection') || 'Profilo e Identità della Squadra'}
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">{t('teamName')}</label>
                <input
                  className="form-input"
                  value={name}
                  onChange={event => setName(event.target.value)}
                  placeholder={t('teamNamePlaceholder') || 'e.g. Market Intelligence'}
                />
              </div>

              <div className="form-row" style={{ marginBottom: 0 }}>
                <VisualIconSelect
                  value={teamIcon}
                  onChange={setTeamIcon}
                  label="Team Icon"
                  disabled={saving}
                />
                <VisualColorSelect
                  value={teamColor}
                  onChange={setTeamColor}
                  label="Team Color"
                  disabled={saving}
                />
              </div>
            </div>
          </div>

          {/* CARD 2: Team AI Model & Provider */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
              <Sparkles size={16} className="text-primary" />
              <h3 style={{ fontSize: '14.5px', fontWeight: 600, margin: 0 }}>
                {t('teamModelSection') || 'Provider e Modello IA della Squadra'}
              </h3>
            </div>
            <p style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: 0, marginBottom: '14px' }}>
              Questo è il modello predefinito utilizzato automaticamente da tutti i membri della squadra.
            </p>

            <div className="form-row" style={{ marginBottom: 0 }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">{t('provider')}</label>
                <select className="form-select" value={provider} onChange={event => setProvider(event.target.value)}>
                  <option value="ollama">Ollama (Locale)</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="mock">Mock</option>
                </select>
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <ModelSelector
                  provider={provider}
                  value={model}
                  teamDefaultModel={model}
                  onChange={newModel => setModel(newModel || 'qwen3.5:9b')}
                  isTeamLevel={true}
                  label={t('model')}
                />
              </div>
            </div>
          </div>

          {/* CARD 3: Workforce Topology */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <Layers size={16} className="text-primary" />
              <h3 style={{ fontSize: '14.5px', fontWeight: 600, margin: 0 }}>
                Workforce Topology Graph
              </h3>
            </div>
            <TeamTopology agents={agents} teamName={name || 'Team'} height={150} />
          </div>

          {/* CARD 4: Workforce Members */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Users size={16} className="text-primary" />
                <h3 style={{ fontSize: '14.5px', fontWeight: 600, margin: 0 }}>
                  {t('teamMembersSection') || 'Membri della Squadra'} ({agents.length})
                </h3>
              </div>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: '12px', padding: '5px 12px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                onClick={() => setAgents(current => [...current, { name: '', role: '', delegates_to: [], skills: [], icon: 'Bot', color: 'violet', model: null }])}
              >
                <Plus size={14} /> {t('addAgent')}
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {agents.map((agent, index) => {
                const isCustom = Boolean(agent.model || agent.provider);
                const isOverrideOpen = Boolean(openOverrides[index]);

                return (
                  <div
                    className="card"
                    style={{
                      padding: '16px',
                      borderRadius: '10px',
                      border: '1px solid hsl(var(--border))',
                      backgroundColor: 'hsl(var(--card))',
                    }}
                    key={index}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <IdentityBadge icon={agent.icon || 'Bot'} color={agent.color || 'violet'} size={15} containerSize={28} />
                        <strong style={{ fontSize: '13.5px' }}>
                          {agent.name.trim() || `${t('agent')} ${index + 1}`}
                        </strong>
                        {isCustom ? (
                          <span className="badge" style={{ fontSize: '10.5px', color: 'hsl(var(--primary))' }}>
                            ⚡ Override: {agent.model || model}
                          </span>
                        ) : (
                          <span className="badge" style={{ fontSize: '10.5px', opacity: 0.75 }}>
                            ✨ Eredita ({model})
                          </span>
                        )}
                      </div>
                      {agents.length > 1 && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{
                            padding: '4px 8px',
                            color: 'hsl(var(--destructive))',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            fontSize: '11.5px',
                          }}
                          onClick={() => removeAgent(index)}
                          title={t('removeAgent')}
                        >
                          <Trash2 size={13} />
                          <span>{t('remove')}</span>
                        </button>
                      )}
                    </div>

                    <div className="form-row" style={{ marginBottom: '10px' }}>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label" style={{ fontSize: '12px' }}>{t('agentName')}</label>
                        <input
                          className="form-input"
                          value={agent.name}
                          onChange={event => updateAgent(index, 'name', event.target.value)}
                          placeholder="e.g. Researcher"
                        />
                      </div>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <label className="form-label" style={{ fontSize: '12px' }}>{t('role')}</label>
                        <input
                          className="form-input"
                          value={agent.role}
                          onChange={event => updateAgent(index, 'role', event.target.value)}
                          placeholder="e.g. Data & analysis"
                        />
                      </div>
                    </div>

                    <div className="form-row" style={{ marginBottom: '10px' }}>
                      <VisualIconSelect
                        value={agent.icon || 'Bot'}
                        onChange={val => updateAgent(index, 'icon', val)}
                        label="Icon"
                        disabled={saving}
                      />
                      <VisualColorSelect
                        value={agent.color || 'violet'}
                        onChange={val => updateAgent(index, 'color', val)}
                        label="Color"
                        disabled={saving}
                      />
                    </div>

                    {/* Centralized Delegation Selector */}
                    <div style={{ marginBottom: '10px' }}>
                      <DelegationSelector
                        currentAgentName={agent.name}
                        availableAgents={agents.map(a => ({
                          name: a.name,
                          role: a.role,
                          icon: a.icon,
                          color: a.color,
                        }))}
                        delegatesTo={agent.delegates_to}
                        onChange={newDelegates => updateAgent(index, 'delegates_to', newDelegates)}
                        label={t('delegatesTo') || 'Delega a:'}
                        hint={t('delegatesToHint') || 'Attiva le deleghe con un click.'}
                        disabled={saving}
                      />
                    </div>

                    {/* Collapsible Model Override */}
                    <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid hsl(var(--border)/0.5)' }}>
                      <div
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', userSelect: 'none' }}
                        onClick={() => toggleOverride(index)}
                      >
                        <span style={{ fontSize: '12px', color: isCustom ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <ShieldCheck size={13} />
                          {isCustom
                            ? `Override modello attivo: ${agent.model || model}`
                            : `⚙️ Override modello (Opzionale - usa default: ${model})`}
                        </span>
                        <button type="button" className="btn btn-ghost" style={{ padding: '2px 6px' }}>
                          {isOverrideOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                      </div>

                      {isOverrideOpen && (
                        <div style={{ marginTop: '10px' }}>
                          <ModelSelector
                            provider={agent.provider || provider}
                            value={agent.model ?? null}
                            teamDefaultModel={model}
                            onChange={newModel => updateAgent(index, 'model', newModel)}
                            label={t('modelLabel') || 'Modello Dedicato per questo Agente'}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* CARD 5: Danger Zone (If editing) */}
          {initialTeam && (
            <div className="card" style={{ padding: '16px 20px', borderRadius: '12px', border: '1px solid hsl(var(--destructive)/0.3)', backgroundColor: 'hsl(var(--destructive)/0.03)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <AlertTriangle size={16} className="text-destructive" />
                  <div>
                    <strong style={{ fontSize: '13px', color: 'hsl(var(--destructive))' }}>
                      {t('dangerZoneTitle') || 'Zona Pericolosa'}
                    </strong>
                    <div style={{ fontSize: '11.5px', color: 'hsl(var(--muted-fg))' }}>
                      {t('deleteTeamWarning') || 'Rimuove definitivamente questa squadra dal workspace.'}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-destructive"
                  style={{ fontSize: '12px', padding: '6px 12px' }}
                  onClick={handleDeleteTeam}
                  disabled={saving || deleting}
                >
                  {confirmDeleteTeam ? (t('confirmDelete') || 'Conferma eliminazione') : (t('deleteTeam') || 'Elimina Team')}
                </button>
              </div>
            </div>
          )}

        </div>

        {/* Footer */}
        <div className="slide-over-footer" style={{ padding: '16px 24px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button className="btn btn-secondary" onClick={onClose} disabled={saving || deleting}>{t('cancel')}</button>
          <button
            className="btn btn-primary"
            onClick={handleSaveClick}
            disabled={saving || deleting || !name.trim() || agents.some(agent => !agent.name.trim() || !agent.role.trim())}
            style={{ padding: '8px 20px' }}
          >
            {saving ? t('saving') : (initialTeam ? t('saveChanges') : t('createTeam'))}
          </button>
        </div>
      </div>

      {/* Team Model Change Confirmation Modal (Responsive & Non-overflowing Cards) */}
      {showModelChangeConfirm && (
        <div className="modal-overlay" style={{ zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div
            className="card"
            style={{
              maxWidth: '520px',
              width: '92%',
              padding: '24px',
              borderRadius: '14px',
              backgroundColor: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              boxShadow: '0 20px 50px rgba(0, 0, 0, 0.45)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <Sparkles size={20} className="text-primary" />
              <h3 style={{ margin: 0, fontSize: '16.5px', fontWeight: 600 }}>
                {t('teamModelChangeTitle') || 'Aggiornamento Modello Squadra'}
              </h3>
            </div>
            <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', marginBottom: '18px', lineHeight: 1.5 }}>
              {t('teamModelChangePrompt') || 'Come desideri applicare il nuovo modello a questa squadra?'}
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '20px' }}>
              {/* Option 1: Only Team */}
              <div
                className="card card-interactive"
                style={{
                  cursor: 'pointer',
                  textAlign: 'left',
                  padding: '14px 16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  whiteSpace: 'normal',
                  wordBreak: 'break-word',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '10px',
                }}
                onClick={() => executeSave(false)}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <strong style={{ fontSize: '13.5px', color: 'hsl(var(--fg))' }}>
                    1. {t('applyOnlyToTeam') || 'Applica solo al Team'}
                  </strong>
                </div>
                <p style={{ margin: 0, fontSize: '12px', color: 'hsl(var(--muted-fg))', lineHeight: 1.45, whiteSpace: 'normal' }}>
                  {t('applyOnlyToTeamDesc') || 'Gli agenti che ereditano seguiranno il nuovo modello. Gli override personalizzati resteranno invariati.'}
                </p>
              </div>

              {/* Option 2: Apply to All */}
              <div
                className="card card-interactive"
                style={{
                  cursor: 'pointer',
                  textAlign: 'left',
                  padding: '14px 16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  whiteSpace: 'normal',
                  wordBreak: 'break-word',
                  border: '1.5px solid hsl(var(--primary)/0.45)',
                  backgroundColor: 'hsl(var(--primary)/0.06)',
                  borderRadius: '10px',
                }}
                onClick={() => executeSave(true)}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <strong style={{ fontSize: '13.5px', color: 'hsl(var(--primary))' }}>
                    2. {t('applyToAllAgents') || 'Applica al Team e a tutti gli agenti'}
                  </strong>
                </div>
                <p style={{ margin: 0, fontSize: '12px', color: 'hsl(var(--fg))', opacity: 0.85, lineHeight: 1.45, whiteSpace: 'normal' }}>
                  {t('applyToAllAgentsDesc') || 'Rimuovi tutti gli override individuali e uniforma l\'intera squadra con questo modello.'}
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setShowModelChangeConfirm(false)}
              >
                {t('cancel') || 'Annulla'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function PresetPickerModal({ onClose, onInstalled }: { onClose: () => void; onInstalled: () => void }) {
  const { t } = useTranslation();
  const [presets, setPresets] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const [applying, setApplying] = useState(false);
  const showToast = useContext(ToastContext);

  useEffect(() => {
    fetch(apiUrl('/api/presets'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setPresets(data);
          setSelectedId(data[0].id);
        }
      })
      .catch(() => showToast('Unable to load presets.', 'error'));
  }, [showToast]);

  const handleApply = async () => {
    if (!selectedId) return;
    setApplying(true);
    try {
      const response = await fetch(apiUrl(`/api/presets/${encodeURIComponent(selectedId)}/install`), {
        method: 'POST',
      });
      if (!response.ok) {
        throw await apiError(response, 'Unable to install this preset.');
      }
      showToast('Preset installed and activated.', 'success');
      onInstalled();
      onClose();
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to install this preset.', 'error');
    } finally {
      setApplying(false);
    }
  };

  return (
    <>
      <div className="overlay" onClick={() => !applying && onClose()} />
      <div className="slide-over" style={{ maxWidth: '600px' }}>
        <div className="slide-over-header" style={{ padding: '20px 24px' }}>
          <div>
            <h2 style={{ fontSize: '17px', fontWeight: 600, margin: 0 }}>{t('startFromOfficialPreset')}</h2>
            <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
              Seleziona un'architettura completa pre-configurata
            </div>
          </div>
          <button className="btn btn-ghost" onClick={onClose} disabled={applying}><X size={18} /></button>
        </div>
        <div className="slide-over-body" style={{ padding: '20px 24px' }}>
          <p className="text-muted" style={{ fontSize: '13px', marginBottom: '20px', lineHeight: 1.5 }}>
            {t('presetPickerDesc')}
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {presets.map(p => (
              <div
                key={p.id}
                className="card"
                onClick={() => setSelectedId(p.id)}
                style={{
                  cursor: 'pointer',
                  padding: '16px',
                  borderRadius: '10px',
                  border: selectedId === p.id ? '2px solid hsl(var(--primary))' : '1px solid hsl(var(--border))',
                  backgroundColor: selectedId === p.id ? 'hsl(var(--primary)/0.05)' : 'hsl(var(--card))',
                  transition: 'border-color 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <IdentityBadge icon={p.icon || 'Bot'} color={p.color || 'violet'} size={18} containerSize={32} />
                    <strong style={{ fontSize: '14.5px' }}>{p.name}</strong>
                  </div>
                  <span className="badge badge-primary">{p.agent_count} {p.agent_count === 1 ? t('agentSingular') : t('agentPlural')}</span>
                </div>
                <p className="text-muted" style={{ fontSize: '12.5px', lineHeight: 1.4, margin: '0 0 10px 0' }}>
                  {p.description}
                </p>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {p.agents.map((a: any, i: number) => (
                    <span key={i} className="badge" style={{ fontSize: '11px', background: 'hsl(var(--muted))' }}>
                      {a.name} ({a.role})
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="slide-over-footer" style={{ padding: '16px 24px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button className="btn btn-secondary" onClick={onClose} disabled={applying}>{t('cancel')}</button>
          <button className="btn btn-primary" onClick={handleApply} disabled={applying || !selectedId} style={{ padding: '8px 20px' }}>
            {applying ? t('applying') : t('useThisPreset')} <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </>
  );
}

export function Teams() {
  const { t } = useTranslation();
  const [teams, setTeams] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isBuilding, setIsBuilding] = useState(false);
  const [isPresetOpen, setIsPresetOpen] = useState(false);
  const [isAutoArchitectOpen, setIsAutoArchitectOpen] = useState(false);
  const [editingTeam, setEditingTeam] = useState<any | undefined>(undefined);
  const [deletingTeamName, setDeletingTeamName] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const showToast = useContext(ToastContext);

  const fetchTeams = useCallback(() => {
    fetch(apiUrl('/api/teams'))
      .then(res => res.json())
      .then(data => {
        setTeams(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => {
        showToast('Unable to load teams.', 'error');
        setLoading(false);
      });
  }, [showToast]);

  const openEditor = async (team: any) => {
    try {
      const response = await fetch(apiUrl(`/api/teams/${encodeURIComponent(team.name)}`));
      if (!response.ok) throw await apiError(response, 'Unable to open this team.');
      setEditingTeam(await response.json());
      setIsBuilding(true);
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to open this team.', 'error');
    }
  };

  const handleDeleteTeamConfirm = async () => {
    if (!deletingTeamName) return;
    setIsDeleting(true);
    try {
      const response = await fetch(apiUrl(`/api/teams/${encodeURIComponent(deletingTeamName)}`), {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw await apiError(response, 'Impossibile eliminare questa squadra.');
      }
      showToast(`Squadra "${deletingTeamName}" eliminata con successo.`, 'info');
      setDeletingTeamName(null);
      fetchTeams();
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Impossibile eliminare questa squadra.', 'error');
    } finally {
      setIsDeleting(false);
    }
  };

  useEffect(() => { fetchTeams(); }, [fetchTeams]);

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <TopHeader
        title={t('teamsTitle')}
        icon={Users}
        actions={
          <>
            <button className="btn btn-secondary" onClick={() => setIsPresetOpen(true)}>
              <Layers size={16} /> {t('usePreset')}
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => setIsAutoArchitectOpen(true)}
              style={{
                background: 'linear-gradient(135deg, hsl(var(--primary)/0.12) 0%, hsl(var(--card)) 100%)',
                borderColor: 'hsl(var(--primary)/0.35)',
                color: 'hsl(var(--primary))',
                fontWeight: 600,
              }}
            >
              <Sparkles size={16} /> {t('designWithAi') || '✨ Progetta con l\'IA'}
            </button>
            <button className="btn btn-primary" onClick={() => setIsBuilding(true)}>
              <Plus size={16} /> {t('createTeam')}
            </button>
          </>
        }
      />

      <div className="grid-container" style={{ padding: '24px 32px' }}>
        {teams.map((team, index) => (
          <div
            key={index}
            className="card card-interactive"
            style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '22px', borderRadius: '12px' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <IdentityBadge icon={team.icon || 'Bot'} color={team.color || 'violet'} size={20} containerSize={38} />
                <div>
                  <h3 style={{ fontSize: '15px', margin: 0, fontWeight: 600 }}>{team.name}</h3>
                  <div className="text-muted" style={{ fontSize: '11.5px', fontFamily: 'monospace' }}>{team.filename}</div>
                </div>
              </div>
              <span className="badge badge-primary" style={{ fontSize: '11px' }}>
                {team.agents} {team.agents === 1 ? t('agentSingular') : t('agentPlural')}
              </span>
            </div>

            <div style={{ margin: '8px 0 14px' }}>
              <TeamTopology agents={team.agents_list || []} teamName={team.name} height={135} />
            </div>

            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' }}>
              <span className="badge" style={{ fontSize: '10.5px' }}>{t('provider')}: {team.default_provider}</span>
              {team.default_model && <span className="badge" style={{ fontSize: '10.5px' }}>{t('model')}: {team.default_model}</span>}
            </div>

            <div style={{ marginTop: 'auto', paddingTop: '12px', borderTop: '1px solid hsl(var(--border)/0.4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <button
                className="btn btn-ghost"
                style={{ fontSize: '12px', padding: '5px 8px', color: 'hsl(var(--destructive))', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                onClick={(e) => {
                  e.stopPropagation();
                  setDeletingTeamName(team.name);
                }}
                disabled={teams.length <= 1}
                title={teams.length <= 1 ? "Impossibile eliminare l'unico team rimasto" : t('deleteTeam')}
              >
                <Trash2 size={13} />
                <span>{t('deleteTeam') || 'Elimina'}</span>
              </button>

              <button className="btn btn-secondary" style={{ fontSize: '12px', padding: '5px 12px', display: 'inline-flex', alignItems: 'center', gap: '6px' }} onClick={() => openEditor(team)}>
                <Edit size={13} /> {t('editTeam')}
              </button>
            </div>
          </div>
        ))}
        {teams.length === 0 && !loading && (
          <div className="empty-state" style={{ gridColumn: '1 / -1' }}>
            <Users className="empty-icon" />
            <div className="empty-title">{t('noTeamsYet')}</div>
            <p className="text-muted">{t('noTeamsDesc')}</p>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal for Grid */}
      {deletingTeamName && (
        <div className="modal-overlay" style={{ zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div
            className="card"
            style={{
              maxWidth: '440px',
              width: '90%',
              padding: '24px',
              borderRadius: '12px',
              backgroundColor: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              boxShadow: '0 20px 40px rgba(0, 0, 0, 0.4)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px', color: 'hsl(var(--destructive))' }}>
              <AlertTriangle size={20} />
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>
                {t('confirmDeleteTeam') || 'Eliminare questa squadra?'}
              </h3>
            </div>
            <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', marginBottom: '20px', lineHeight: 1.5 }}>
              Sei sicuro di voler eliminare definitivamente la squadra <strong>"{deletingTeamName}"</strong>? Questa operazione eliminerà il file di configurazione associato.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDeletingTeamName(null)}
                disabled={isDeleting}
              >
                {t('cancel')}
              </button>
              <button
                type="button"
                className="btn btn-destructive"
                onClick={handleDeleteTeamConfirm}
                disabled={isDeleting}
              >
                {isDeleting ? t('deleting') || 'Eliminazione...' : t('deleteTeam') || 'Elimina Squadra'}
              </button>
            </div>
          </div>
        </div>
      )}

      {isBuilding && (
        <TeamBuilder
          initialTeam={editingTeam}
          onClose={() => { setIsBuilding(false); setEditingTeam(undefined); }}
          onSaved={fetchTeams}
          onDeleted={fetchTeams}
        />
      )}
      {isPresetOpen && (
        <PresetPickerModal
          onClose={() => setIsPresetOpen(false)}
          onInstalled={fetchTeams}
        />
      )}
      {isAutoArchitectOpen && (
        <AutoArchitectModal
          isOpen={isAutoArchitectOpen}
          onClose={() => setIsAutoArchitectOpen(false)}
          onSuccess={fetchTeams}
        />
      )}
    </div>
  );
}
