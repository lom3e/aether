import { useState, useEffect, useContext } from 'react';
import {
  X, Bot, Cpu, Sparkles, ChevronDown, ChevronUp, AlertTriangle,
  ShieldCheck, RefreshCw, Wand2, PenLine
} from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';
import { useTranslation } from './i18n';
import { IdentityBadge } from './identity';
import { MagicEnhancePromptButton } from './MagicEnhancePromptButton';
import { ModelSelector } from './ModelSelector';
import { VisualIconSelect, VisualColorSelect } from './VisualSelect';
import { DelegationSelector, type DelegationCandidate } from './DelegationSelector';

export function AgentBuilder({
  onClose,
  onSave,
  initialData,
}: {
  onClose: () => void;
  onSave: () => void;
  initialData?: any;
}) {
  const { t } = useTranslation();
  const [creationMode, setCreationMode] = useState<'manual' | 'ai'>('manual');
  const [aiGoal, setAiGoal] = useState('');
  const [isGeneratingDraft, setIsGeneratingDraft] = useState(false);
  const [name, setName] = useState(initialData?.name || '');
  const [role, setRole] = useState(initialData?.role || '');
  const [icon, setIcon] = useState(initialData?.icon || 'Bot');
  const [color, setColor] = useState(initialData?.color || 'violet');
  const [instructions, setInstructions] = useState(
    initialData?.instructions ||
    (initialData?.description && initialData.description !== 'No description' && initialData.description !== 'No instructions provided' ? initialData.description : '') ||
    ''
  );
  const [provider, setProvider] = useState(initialData?.provider || '');
  const [model, setModel] = useState<string | null>(initialData?.model || null);
  const [teamProvider, setTeamProvider] = useState('ollama');
  const [teamDefaultModel, setTeamDefaultModel] = useState('qwen3.5:9b');
  const [delegatesList, setDelegatesList] = useState<string[]>(initialData?.delegates_to || []);
  const [selectedSkills, setSelectedSkills] = useState<string[]>(initialData?.skills || []);
  const [availableSkills, setAvailableSkills] = useState<any[]>([]);
  const [availableAgents, setAvailableAgents] = useState<DelegationCandidate[]>([]);
  const [saving, setSaving] = useState(false);
  const [showAdvancedModel, setShowAdvancedModel] = useState(Boolean(initialData?.model || initialData?.provider));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const showToast = useContext(ToastContext);

  useEffect(() => {
    fetch(apiUrl('/api/skills'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) setAvailableSkills(data);
      })
      .catch(() => {});

    fetch(apiUrl('/api/agents'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setAvailableAgents(data.map(a => ({
            name: a.name,
            role: a.role,
            icon: a.icon,
            color: a.color,
          })));
        }
      })
      .catch(() => {});

    fetch(apiUrl('/api/settings/provider'))
      .then(res => res.json())
      .then(data => {
        if (data.provider) setTeamProvider(data.provider);
        if (data.model) setTeamDefaultModel(data.model);
      })
      .catch(() => {});
  }, []);

  const handleGenerateDraft = async () => {
    if (!aiGoal.trim()) return;
    setIsGeneratingDraft(true);
    try {
      const response = await fetch(apiUrl('/api/architect/agent-draft'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: aiGoal.trim(),
          available_skills: availableSkills.map(s => s.name || s.id),
          available_agents: availableAgents.map(a => a.name),
        }),
      });
      if (!response.ok) {
        throw await apiError(response, 'Impossibile generare la bozza dell\'agente.');
      }
      const draft = await response.json();
      if (draft.name) setName(draft.name);
      if (draft.role) setRole(draft.role);
      if (draft.icon) setIcon(draft.icon);
      if (draft.color) setColor(draft.color);
      if (draft.system_prompt) setInstructions(draft.system_prompt);
      if (Array.isArray(draft.skills)) setSelectedSkills(draft.skills);
      if (Array.isArray(draft.delegates_to)) setDelegatesList(draft.delegates_to);
      setModel(null); // Explicitly inherit from team

      showToast('✨ Bozza generata con successo! Puoi rifinire qualsiasi campo qui sotto.', 'success');
      setCreationMode('manual');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Errore durante la generazione della bozza', 'error');
    } finally {
      setIsGeneratingDraft(false);
    }
  };

  const handleSave = async () => {
    if (!name.trim() || !role.trim()) return;
    setSaving(true);
    try {
      const url = initialData ? `/api/agents/${encodeURIComponent(initialData.name)}` : '/api/agents';
      const method = initialData ? 'PUT' : 'POST';

      const res = await fetch(apiUrl(url), {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          role: role.trim(),
          icon,
          color,
          instructions: instructions.trim(),
          provider: provider ? provider.trim() : null,
          model: model ? model.trim() : null,
          skills: selectedSkills,
          delegates_to: delegatesList,
        }),
      });
      if (!res.ok) {
        throw await apiError(res, 'Unable to save this agent.');
      } else {
        showToast(initialData ? t('agentUpdated') : t('agentCreated'), 'success');
        onSave();
        onClose();
      }
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to save this agent.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!initialData) return;
    if (!confirmDelete) { setConfirmDelete(true); return; }

    setSaving(true);
    try {
      const res = await fetch(apiUrl(`/api/agents/${encodeURIComponent(initialData.name)}`), {
        method: 'DELETE',
      });
      if (res.ok) {
        showToast(t('agentDeleted'), 'info');
        onSave();
        onClose();
      } else {
        throw await apiError(res, 'Unable to delete this agent.');
      }
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to delete this agent.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const toggleSkill = (skillName: string) => {
    setSelectedSkills(prev =>
      prev.includes(skillName)
        ? prev.filter(s => s !== skillName)
        : [...prev, skillName]
    );
  };

  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="slide-over" style={{ maxWidth: '680px' }}>
        {/* Header */}
        <div className="slide-over-header" style={{ padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <IdentityBadge icon={icon} color={color} size={20} containerSize={38} />
            <div>
              <h2 style={{ fontSize: '17px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                {initialData ? t('editAgent') : t('createAgent')}
              </h2>
              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                {name ? `${name} · ${role || 'Agente autonomo'}` : 'Configura identità, prompt e competenze'}
              </div>
            </div>
          </div>
          <button className="btn btn-ghost" style={{ padding: '8px' }} onClick={onClose} disabled={saving}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="slide-over-body" style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>

          {/* Mode Switch (Only when creating new agent) */}
          {!initialData && (
            <div
              style={{
                display: 'flex',
                background: 'hsl(var(--muted)/0.5)',
                padding: '4px',
                borderRadius: '10px',
                gap: '4px',
                border: '1px solid hsl(var(--border))',
              }}
            >
              <button
                type="button"
                className={`btn ${creationMode === 'manual' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ flex: 1, padding: '7px 12px', fontSize: '12.5px', borderRadius: '7px' }}
                onClick={() => setCreationMode('manual')}
              >
                <PenLine size={14} style={{ marginRight: '6px' }} />
                <span>✍️ {t('manualConfig') || 'Configurazione Manuale'}</span>
              </button>
              <button
                type="button"
                className={`btn ${creationMode === 'ai' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ flex: 1, padding: '7px 12px', fontSize: '12.5px', borderRadius: '7px' }}
                onClick={() => setCreationMode('ai')}
              >
                <Sparkles size={14} style={{ marginRight: '6px' }} />
                <span>✨ {t('createWithAi') || 'Crea con l\'IA'}</span>
              </button>
            </div>
          )}

          {/* AI Drafting Assistant Card */}
          {creationMode === 'ai' && !initialData && (
            <div
              className="card"
              style={{
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid hsl(var(--primary)/0.35)',
                background: 'linear-gradient(135deg, hsl(var(--primary)/0.08) 0%, hsl(var(--card)) 100%)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
                <Wand2 size={18} className="text-primary" />
                <h3 style={{ fontSize: '14.5px', fontWeight: 600, margin: 0 }}>
                  {t('aiAgentArchitectTitle') || 'Descrivi l\'Agente da costruire'}
                </h3>
              </div>
              <p style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', margin: '0 0 14px 0', lineHeight: 1.5 }}>
                {t('aiAgentArchitectDesc') || 'L\'IA progetterà istantaneamente nome, ruolo, istruzioni, competenze e deleghe ideali. Potrai poi perfezionare ogni singolo dettaglio.'}
              </p>

              <textarea
                className="form-textarea"
                rows={3}
                value={aiGoal}
                onChange={e => setAiGoal(e.target.value)}
                placeholder="es. Voglio un analista finanziario che legga bilanci PDF, cerchi notizie su Google e rediga report esecutivi in markdown."
                style={{ marginBottom: '14px', fontSize: '13px', lineHeight: 1.5 }}
                disabled={isGeneratingDraft}
              />

              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleGenerateDraft}
                  disabled={isGeneratingDraft || !aiGoal.trim()}
                  style={{ padding: '8px 18px', display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                >
                  {isGeneratingDraft ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      <span>{t('generating') || 'Generazione in corso...'}</span>
                    </>
                  ) : (
                    <>
                      <Sparkles size={14} />
                      <span>{t('generateAgentDraft') || '✨ Genera Bozza Agente'}</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* CARD 1: Agent Identity */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <Bot size={16} className="text-primary" />
              <h3 style={{ fontSize: '14.5px', fontWeight: 600, margin: 0 }}>
                {t('agentIdentitySection') || 'Identità Agente'}
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-row" style={{ marginBottom: 0 }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">{t('agentName')}</label>
                  <input
                    className="form-input"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="e.g. Market Analyst"
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">{t('role')}</label>
                  <input
                    className="form-input"
                    value={role}
                    onChange={e => setRole(e.target.value)}
                    placeholder="e.g. Competitive Intelligence"
                  />
                </div>
              </div>

              <div className="form-row" style={{ marginBottom: 0 }}>
                <VisualIconSelect
                  value={icon}
                  onChange={setIcon}
                  label="Icona Agente"
                  disabled={saving}
                />
                <VisualColorSelect
                  value={color}
                  onChange={setColor}
                  label="Colore Agente"
                  disabled={saving}
                />
              </div>
            </div>
          </div>

          {/* CARD 2: Prompt & Instructions */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={16} className="text-primary" />
                <h3 style={{ fontSize: '14.5px', fontWeight: 600, margin: 0 }}>
                  {t('agentPromptSection') || 'Istruzioni e Prompt di Sistema'}
                </h3>
              </div>
              <MagicEnhancePromptButton
                prompt={instructions}
                role={role}
                agentName={name}
                teamName="Squadra"
                onEnhanced={enhanced => setInstructions(enhanced)}
              />
            </div>

            <div className="form-group" style={{ marginBottom: 0 }}>
              <textarea
                className="form-textarea"
                rows={6}
                value={instructions}
                onChange={e => setInstructions(e.target.value)}
                placeholder="Fornisci istruzioni dettagliate su ruolo, workflow, formato di risposta e vincoli..."
                style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '12.5px', lineHeight: 1.5 }}
              />
              <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '6px' }}>
                💡 {t('promptTip') || 'Puoi cliccare "✨ Migliora con l\'IA" in qualsiasi momento per strutturare il prompt in sezioni professionali.'}
              </div>
            </div>
          </div>

          {/* CARD 3: Skills & Delegations */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
              <Cpu size={16} className="text-primary" />
              <h3 style={{ fontSize: '14.5px', fontWeight: 600, margin: 0 }}>
                {t('agentSkillsSection') || 'Competenze e Deleghe'}
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Skills */}
              <div>
                <label className="form-label" style={{ fontSize: '12px', marginBottom: '8px', display: 'block' }}>
                  {t('skills')} ({selectedSkills.length} {t('active')})
                </label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {availableSkills.map((s: any) => {
                    const isSelected = selectedSkills.includes(s.name || s.id);
                    return (
                      <button
                        key={s.name || s.id}
                        type="button"
                        className={`card card-interactive`}
                        onClick={() => toggleSkill(s.name || s.id)}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '6px 12px',
                          borderRadius: '8px',
                          cursor: 'pointer',
                          border: isSelected ? '1.5px solid hsl(var(--primary))' : '1px solid hsl(var(--border))',
                          backgroundColor: isSelected ? 'hsl(var(--primary)/0.12)' : 'hsl(var(--card))',
                          color: isSelected ? 'hsl(var(--primary))' : 'hsl(var(--fg))',
                          fontSize: '12px',
                          fontWeight: isSelected ? 600 : 500,
                        }}
                      >
                        <Cpu size={12} className={isSelected ? 'text-primary' : 'text-muted'} />
                        <span>{s.name || s.id}</span>
                        {isSelected && <span style={{ fontSize: '10px' }}>✓</span>}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Centralized Delegation Selector */}
              <DelegationSelector
                currentAgentName={name}
                availableAgents={availableAgents}
                delegatesTo={delegatesList}
                onChange={setDelegatesList}
                label={t('delegatesTo') || 'Delega a:'}
                hint={t('delegatesToHint') || 'Clicca sugli agenti a cui questo agente può delegare compiti.'}
                disabled={saving}
              />
            </div>
          </div>

          {/* CARD 4: Advanced Model Options */}
          <div className="card" style={{ padding: '16px 20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <div
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', userSelect: 'none' }}
              onClick={() => setShowAdvancedModel(!showAdvancedModel)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShieldCheck size={16} className={model ? 'text-primary' : 'text-muted'} />
                <div>
                  <strong style={{ fontSize: '13.5px' }}>
                    {t('advancedModelOptions') || 'Opzioni Avanzate (Modello & Provider)'}
                  </strong>
                  <div style={{ fontSize: '11.5px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                    {model
                      ? `⚡ Override attivo: ${model}`
                      : `✨ Predefinito: eredita dal Team (${teamDefaultModel})`}
                  </div>
                </div>
              </div>
              <button type="button" className="btn btn-ghost" style={{ padding: '4px' }}>
                {showAdvancedModel ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
            </div>

            {showAdvancedModel && (
              <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid hsl(var(--border)/0.5)', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <p style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', margin: 0 }}>
                  {t('advancedModelDesc') || 'Di default, questo agente eredita il modello della Squadra. Seleziona un modello dedicato solo se necessiti di un override specifico.'}
                </p>

                <div className="form-row" style={{ marginBottom: 0 }}>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">{t('providerOptional') || 'Provider'}</label>
                    <select
                      className="form-select"
                      value={provider}
                      onChange={e => setProvider(e.target.value)}
                    >
                      <option value="">{t('inheritFromTeam') || 'Eredita dal Team'} ({teamProvider})</option>
                      <option value="ollama">Ollama (Locale)</option>
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                      <option value="gemini">Google Gemini</option>
                    </select>
                  </div>

                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <ModelSelector
                      provider={provider || teamProvider}
                      value={model}
                      teamDefaultModel={teamDefaultModel}
                      onChange={newModel => setModel(newModel)}
                      label={t('modelOptional') || 'Modello IA'}
                    />
                  </div>
                </div>

                {model && (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    style={{ fontSize: '12px', alignSelf: 'flex-start', padding: '4px 8px', color: 'hsl(var(--primary))' }}
                    onClick={() => setModel(null)}
                  >
                    ↺ {t('resetToTeamDefault') || 'Ripristina predefinito del Team'}
                  </button>
                )}
              </div>
            )}
          </div>

          {/* CARD 5: Danger Zone (If Editing) */}
          {initialData && (
            <div className="card" style={{ padding: '16px 20px', borderRadius: '12px', border: '1px solid hsl(var(--destructive)/0.3)', backgroundColor: 'hsl(var(--destructive)/0.03)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <AlertTriangle size={16} className="text-destructive" />
                  <div>
                    <strong style={{ fontSize: '13px', color: 'hsl(var(--destructive))' }}>
                      {t('dangerZoneTitle') || 'Zona Pericolosa'}
                    </strong>
                    <div style={{ fontSize: '11.5px', color: 'hsl(var(--muted-fg))' }}>
                      {t('deleteAgentWarning') || 'Rimuove definitivamente questo agente dalla squadra.'}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-destructive"
                  style={{ fontSize: '12px', padding: '6px 12px' }}
                  onClick={handleDelete}
                  disabled={saving}
                >
                  {confirmDelete ? (t('confirmDelete') || 'Conferma eliminazione') : (t('deleteAgent') || 'Elimina Agente')}
                </button>
              </div>
            </div>
          )}

        </div>

        {/* Footer */}
        <div className="slide-over-footer" style={{ padding: '16px 24px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button className="btn btn-secondary" onClick={onClose} disabled={saving}>{t('cancel')}</button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving || !name.trim() || !role.trim()}
            style={{ padding: '8px 20px' }}
          >
            {saving ? t('saving') : (initialData ? t('saveChanges') : t('saveAgent'))}
          </button>
        </div>
      </div>
    </>
  );
}
