import { useState, useContext, useEffect } from 'react';
import {
  Sparkles, Bot, X, ArrowRight, RefreshCw, Layers,
  Trash2, Plus, Wand2, ShieldCheck,
  Code, Brain, Compass, Zap, ChevronDown, ChevronUp
} from 'lucide-react';
import { useTranslation } from './i18n';
import { apiUrl } from './api';
import { ToastContext } from './toast';
import { TeamTopology } from './TeamTopology';
import { IdentityBadge } from './identity';
import { ModelSelector } from './ModelSelector';
import { VisualIconSelect, VisualColorSelect } from './VisualSelect';
import { DelegationSelector } from './DelegationSelector';

interface ArchitectAgent {
  name: string;
  role: string;
  system_prompt: string;
  icon: string;
  color: string;
  delegates_to: string[];
  skills: string[];
  provider?: string | null;
  model?: string | null;
}

interface ArchitectBlueprint {
  team_name: string;
  description: string;
  icon: string;
  color: string;
  entry_agent: string;
  default_provider?: string;
  default_model?: string;
  agents: ArchitectAgent[];
  suggested_starter_tasks: string[];
  generation_source?: string;
}

interface AutoArchitectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (teamName: string) => void;
}

const QUICK_GOAL_SUGGESTIONS = [
  {
    icon: Compass,
    label: 'E-Commerce Competitor Intelligence',
    goal: 'Voglio monitorare i competitor e-commerce, estrarre variazioni di prezzo e cataloghi, e generare un report settimanale di intelligence competitiva.',
  },
  {
    icon: Code,
    label: 'Code Review & Automated QA',
    goal: 'Voglio una squadra per analizzare il codice sorgente, rilevare vulnerabilità di sicurezza, verificare standard di qualità e scrivere test automatici.',
  },
  {
    icon: Brain,
    label: 'Financial Balance Sheet & KPI Auditor',
    goal: 'Voglio estrarre dati contabili e bilanci da documenti PDF, calcolare metriche finanziarie (EBITDA, margini) e redigere executive brief per il board.',
  },
  {
    icon: Zap,
    label: 'Content Strategy & SEO Growth',
    goal: 'Voglio un team che effettui keyword research, rediga articoli tecnici ottimizzati SEO e crei post per LinkedIn e Twitter.',
  },
];

export function AutoArchitectModal({ isOpen, onClose, onSuccess }: AutoArchitectModalProps) {
  const { t } = useTranslation();
  const showToast = useContext(ToastContext);

  const [step, setStep] = useState<'input' | 'generating' | 'preview'>('input');
  const [goal, setGoal] = useState('');
  const [loadingTextIndex, setLoadingTextIndex] = useState(0);
  const [blueprint, setBlueprint] = useState<ArchitectBlueprint | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [enhancingIndex, setEnhancingIndex] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<'agents' | 'topology'>('agents');
  const [expandedAgentIndexes, setExpandedAgentIndexes] = useState<number[]>([]);
  const [openAgentOverrides, setOpenAgentOverrides] = useState<Record<number, boolean>>({});

  const [workspaceProvider, setWorkspaceProvider] = useState('ollama');
  const [workspaceModel, setWorkspaceModel] = useState('qwen3.5:9b');

  useEffect(() => {
    fetch(apiUrl('/api/settings/provider'))
      .then(res => res.json())
      .then(data => {
        if (data.provider) setWorkspaceProvider(data.provider);
        if (data.model) setWorkspaceModel(data.model);
      })
      .catch(() => {});
  }, []);

  const loadingMessages = [
    t('architectStep1') || 'Analisi semantica del tuo obiettivo...',
    t('architectStep2') || 'Progettazione dei ruoli e gerarchia della squadra...',
    t('architectStep3') || 'Generazione dei prompt di sistema con guardrail...',
    t('architectStep4') || 'Configurazione della topologia e strumenti...',
  ];

  useEffect(() => {
    let interval: any;
    if (step === 'generating') {
      setLoadingTextIndex(0);
      interval = setInterval(() => {
        setLoadingTextIndex(prev => (prev + 1) % loadingMessages.length);
      }, 1500);
    }
    return () => clearInterval(interval);
  }, [step]);

  if (!isOpen) return null;

  const handleGenerate = async (overrideGoal?: string) => {
    const targetGoal = overrideGoal || goal;
    if (!targetGoal.trim()) {
      showToast(t('enterGoalPrompt') || 'Inserisci un obiettivo per la tua squadra', 'error');
      return;
    }

    setStep('generating');
    try {
      const res = await fetch(apiUrl('/api/architect/workforce'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: targetGoal.trim(),
          provider: workspaceProvider,
          model: workspaceModel,
        }),
      });

      if (!res.ok) {
        throw new Error('Failed to generate workforce architecture');
      }

      const data: ArchitectBlueprint = await res.json();
      data.default_provider = data.default_provider || workspaceProvider || 'ollama';
      data.default_model = data.default_model || workspaceModel || 'qwen3.5:9b';
      data.agents = (data.agents || []).map(a => ({
        ...a,
        provider: a.provider || null,
        model: a.model || null, // inherits from team by default
      }));

      setBlueprint(data);
      setExpandedAgentIndexes([]); // Collapsed by default
      setOpenAgentOverrides({});
      setStep('preview');
      showToast(t('workforceGeneratedSuccess') || 'Squadra progettata con successo!', 'success');
    } catch (err) {
      console.error('Architect generation failed', err);
      showToast(t('architectError') || 'Errore nella generazione della squadra. Riprova.', 'error');
      setStep('input');
    }
  };

  const handleEnhanceAgentPrompt = async (index: number) => {
    if (!blueprint || !blueprint.agents[index]) return;
    const agent = blueprint.agents[index];
    setEnhancingIndex(index);

    try {
      const res = await fetch(apiUrl('/api/architect/enhance-prompt'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt_hint: agent.system_prompt,
          role: agent.role,
          agent_name: agent.name,
          team_name: blueprint.team_name,
          provider: agent.provider || blueprint.default_provider || workspaceProvider,
          model: agent.model || blueprint.default_model || workspaceModel,
        }),
      });

      if (!res.ok) throw new Error('Failed to enhance prompt');
      const data = await res.json();
      if (data.enhanced_prompt) {
        const updatedAgents = [...blueprint.agents];
        updatedAgents[index] = { ...agent, system_prompt: data.enhanced_prompt };
        setBlueprint({ ...blueprint, agents: updatedAgents });
        showToast(t('promptEnhancedSuccess') || 'Prompt ottimizzato con successo!', 'success');
      }
    } catch (err) {
      console.error('Enhance prompt failed', err);
      showToast(t('promptEnhanceError') || 'Impossibile ottimizzare il prompt', 'error');
    } finally {
      setEnhancingIndex(null);
    }
  };

  const handleApply = async () => {
    if (!blueprint || !blueprint.team_name.trim()) return;
    if (blueprint.agents.length === 0) {
      showToast(t('minOneAgentRequired') || 'La squadra deve avere almeno un agente.', 'error');
      return;
    }

    setIsApplying(true);
    try {
      const res = await fetch(apiUrl('/api/architect/apply'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          team_name: blueprint.team_name.trim(),
          description: blueprint.description,
          icon: blueprint.icon,
          color: blueprint.color,
          default_provider: blueprint.default_provider || workspaceProvider || 'ollama',
          default_model: blueprint.default_model || workspaceModel || 'qwen3.5:9b',
          agents: blueprint.agents.map(a => ({
            name: a.name,
            role: a.role,
            system_prompt: a.system_prompt,
            icon: a.icon,
            color: a.color,
            delegates_to: a.delegates_to,
            skills: a.skills,
            provider: a.provider || null,
            model: a.model || null,
          })),
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to save workforce');
      }

      showToast(t('teamCreatedSuccess') || 'Squadra creata e attivata con successo!', 'success');
      if (onSuccess) onSuccess(blueprint.team_name.trim());
      onClose();
    } catch (err: any) {
      console.error('Failed to apply architect workforce', err);
      showToast(err.message || 'Errore durante il salvataggio della squadra', 'error');
    } finally {
      setIsApplying(false);
    }
  };

  const handleRemoveAgent = (index: number) => {
    if (!blueprint) return;
    if (blueprint.agents.length <= 1) {
      showToast(t('minOneAgentRequired') || 'La squadra deve avere almeno un agente.', 'error');
      return;
    }
    const removedName = blueprint.agents[index].name;
    const nextAgents = blueprint.agents
      .filter((_, i) => i !== index)
      .map(a => ({
        ...a,
        delegates_to: a.delegates_to.filter(d => d !== removedName),
      }));
    setExpandedAgentIndexes(prev => prev.filter(i => i !== index).map(i => i > index ? i - 1 : i));
    setBlueprint({ ...blueprint, agents: nextAgents });
  };

  const handleAddAgent = () => {
    if (!blueprint) return;
    const newIdx = blueprint.agents.length;
    const newName = `Specialist ${newIdx + 1}`;
    const newAgent: ArchitectAgent = {
      name: newName,
      role: 'Domain Specialist',
      system_prompt: `You are ${newName}. Execute assigned tasks with high accuracy.`,
      icon: 'Bot',
      color: 'violet',
      delegates_to: [],
      skills: ['search_knowledge', 'filesystem_tools'],
      provider: null,
      model: null,
    };
    setBlueprint({ ...blueprint, agents: [...blueprint.agents, newAgent] });
    setExpandedAgentIndexes(prev => [...prev, newIdx]);
  };

  const toggleAgentOverride = (index: number) => {
    setOpenAgentOverrides(prev => ({ ...prev, [index]: !prev[index] }));
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        onClick={e => e.stopPropagation()}
        style={{
          maxWidth: step === 'preview' ? '880px' : '620px',
          width: '100%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          padding: 0,
          borderRadius: '16px',
          overflow: 'hidden',
          transition: 'max-width 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 24px',
            borderBottom: '1px solid hsl(var(--border))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'linear-gradient(135deg, hsl(var(--primary)/0.08) 0%, hsl(var(--card)) 100%)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '10px',
                backgroundColor: 'hsl(var(--primary)/0.15)',
                color: 'hsl(var(--primary))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Wand2 size={20} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '16.5px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
                {t('autoArchitectTitle') || 'Auto-Architect AI Workforce'}
              </h3>
              <p style={{ margin: '2px 0 0', fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                {step === 'preview'
                  ? (t('reviewAndApplyWorkforce') || 'Personalizza e attiva la tua squadra')
                  : (t('autoArchitectSubtitle') || 'Descrivi il tuo obiettivo in linguaggio naturale')}
              </p>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onClose}
            style={{ padding: '6px', borderRadius: '8px' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div
          style={{
            padding: '24px',
            overflowY: 'auto',
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* STEP 1: NATURAL LANGUAGE INPUT */}
          {step === 'input' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <label className="form-label" style={{ fontSize: '14px', marginBottom: '8px', display: 'block' }}>
                  {t('whatDoYouWantYourWorkforceToDo') || 'Cosa vorresti che facesse la tua squadra Aether?'}
                </label>
                <textarea
                  className="form-textarea"
                  rows={4}
                  value={goal}
                  onChange={e => setGoal(e.target.value)}
                  placeholder={t('architectGoalPlaceholder') || 'Es. Voglio monitorare i competitor, estrarre variazioni di prezzo e cataloghi da e-commerce e ricevere un report settimanale dettagliato in formato markdown...'}
                  style={{
                    fontSize: '13.5px',
                    lineHeight: 1.5,
                    padding: '12px 14px',
                    borderRadius: '10px',
                  }}
                  autoFocus
                />
              </div>

              {/* Quick Template Chips */}
              <div>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {t('orPickSuggestedArchitecture') || 'Oppure scegli un obiettivo suggerito:'}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  {QUICK_GOAL_SUGGESTIONS.map((sug, i) => {
                    const IconComp = sug.icon;
                    return (
                      <div
                        key={i}
                        className="card card-interactive"
                        onClick={() => {
                          setGoal(sug.goal);
                          handleGenerate(sug.goal);
                        }}
                        style={{
                          padding: '12px 14px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '10px',
                          borderRadius: '10px',
                          border: '1px solid hsl(var(--border))',
                          backgroundColor: 'hsl(var(--card))',
                          textAlign: 'left',
                        }}
                      >
                        <div
                          style={{
                            width: '28px',
                            height: '28px',
                            borderRadius: '6px',
                            backgroundColor: 'hsl(var(--primary)/0.12)',
                            color: 'hsl(var(--primary))',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexShrink: 0,
                            marginTop: '2px',
                          }}
                        >
                          <IconComp size={15} />
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <strong style={{ fontSize: '13px', display: 'block', color: 'hsl(var(--fg))', marginBottom: '2px' }}>
                            {sug.label}
                          </strong>
                          <p style={{ margin: 0, fontSize: '11.5px', color: 'hsl(var(--muted-fg))', lineHeight: 1.35, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                            {sug.goal}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* STEP 2: GENERATING SPINNER */}
          {step === 'generating' && (
            <div
              style={{
                padding: '60px 20px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                textAlign: 'center',
              }}
            >
              <div
                style={{
                  width: '64px',
                  height: '64px',
                  borderRadius: '50%',
                  backgroundColor: 'hsl(var(--primary)/0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '24px',
                  position: 'relative',
                }}
              >
                <RefreshCw size={32} className="animate-spin text-primary" style={{ animation: 'spin 2s linear infinite' }} />
                <Sparkles size={16} style={{ position: 'absolute', top: 4, right: 4, color: 'hsl(var(--primary))' }} />
              </div>

              <h4 style={{ margin: '0 0 8px', fontSize: '17px', fontWeight: 600 }}>
                {t('designingWorkforce') || 'Progettazione della Workforce in corso...'}
              </h4>
              <p
                className="text-primary"
                style={{
                  margin: 0,
                  fontSize: '14px',
                  fontWeight: 500,
                  minHeight: '22px',
                  transition: 'all 0.3s ease',
                }}
              >
                {loadingMessages[loadingTextIndex]}
              </p>
            </div>
          )}

          {/* STEP 3: PREVIEW & CUSTOMIZATION */}
          {step === 'preview' && blueprint && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {/* Team Profile Card */}
              <div
                className="card"
                style={{
                  padding: '16px 20px',
                  borderRadius: '12px',
                  background: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                }}
              >
                <div className="form-row" style={{ marginBottom: '12px' }}>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">{t('teamName') || 'Nome della Squadra'}</label>
                    <input
                      type="text"
                      className="form-input"
                      value={blueprint.team_name}
                      onChange={e => setBlueprint({ ...blueprint, team_name: e.target.value })}
                      style={{ fontWeight: 600, fontSize: '14px' }}
                    />
                  </div>

                  <div className="form-row" style={{ marginBottom: 0 }}>
                    <VisualIconSelect
                      value={blueprint.icon}
                      onChange={i => setBlueprint({ ...blueprint, icon: i })}
                      label="Team Icon"
                    />
                    <VisualColorSelect
                      value={blueprint.color}
                      onChange={c => setBlueprint({ ...blueprint, color: c })}
                      label="Team Color"
                    />
                  </div>
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">{t('teamDescription') || 'Descrizione Missione'}</label>
                  <input
                    type="text"
                    className="form-input"
                    value={blueprint.description}
                    onChange={e => setBlueprint({ ...blueprint, description: e.target.value })}
                    style={{ fontSize: '13px' }}
                  />
                </div>
              </div>

              {/* Team AI Model Card */}
              <div
                className="card"
                style={{
                  padding: '16px 20px',
                  borderRadius: '12px',
                  background: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                  <Sparkles size={16} className="text-primary" />
                  <h4 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>
                    {t('teamModelSection') || 'Provider e Modello IA della Squadra'}
                  </h4>
                </div>

                <div className="form-row" style={{ marginBottom: 0 }}>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">{t('provider')}</label>
                    <select
                      className="form-select"
                      value={blueprint.default_provider || workspaceProvider}
                      onChange={e => setBlueprint({ ...blueprint, default_provider: e.target.value })}
                    >
                      <option value="ollama">Ollama (Locale)</option>
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                      <option value="gemini">Google Gemini</option>
                      <option value="mock">Mock</option>
                    </select>
                  </div>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <ModelSelector
                      provider={blueprint.default_provider || workspaceProvider}
                      value={blueprint.default_model || workspaceModel}
                      teamDefaultModel={blueprint.default_model || workspaceModel}
                      onChange={newModel => setBlueprint({ ...blueprint, default_model: newModel || 'qwen3.5:9b' })}
                      isTeamLevel={true}
                      label={t('model')}
                    />
                  </div>
                </div>
              </div>

              {/* View Switcher Tabs (Agents List vs Topology SVG) */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button
                    type="button"
                    className={`btn ${activeTab === 'agents' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '6px 14px', fontSize: '12.5px' }}
                    onClick={() => setActiveTab('agents')}
                  >
                    <Bot size={14} style={{ marginRight: '6px' }} />
                    <span>{t('members') || 'Agenti Specializzati'} ({blueprint.agents.length})</span>
                  </button>
                  <button
                    type="button"
                    className={`btn ${activeTab === 'topology' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '6px 14px', fontSize: '12.5px' }}
                    onClick={() => setActiveTab('topology')}
                  >
                    <Layers size={14} style={{ marginRight: '6px' }} />
                    <span>{t('topologyGraph') || 'Grafo di Topologia'}</span>
                  </button>
                </div>

                {activeTab === 'agents' && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      style={{ fontSize: '11.5px', padding: '4px 8px' }}
                      onClick={() => {
                        if (expandedAgentIndexes.length === blueprint.agents.length) {
                          setExpandedAgentIndexes([]);
                        } else {
                          setExpandedAgentIndexes(blueprint.agents.map((_, i) => i));
                        }
                      }}
                    >
                      {expandedAgentIndexes.length === blueprint.agents.length
                        ? (t('collapseAll') || 'Comprimi tutti')
                        : (t('expandAll') || 'Espandi tutti')}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{ fontSize: '12px', padding: '4px 10px', gap: '4px' }}
                      onClick={handleAddAgent}
                    >
                      <Plus size={14} />
                      <span>{t('addAgent') || 'Aggiungi Agente'}</span>
                    </button>
                  </div>
                )}
              </div>

              {/* TAB 1: EDITABLE AGENTS LIST (COLLAPSED BY DEFAULT) */}
              {activeTab === 'agents' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {blueprint.agents.map((agent, idx) => {
                    const isExpanded = expandedAgentIndexes.includes(idx);
                    const isEnhancing = enhancingIndex === idx;
                    const isCustom = Boolean(agent.model || agent.provider);
                    const isOverrideOpen = Boolean(openAgentOverrides[idx]);
                    const teamDefault = blueprint.default_model || workspaceModel;

                    return (
                      <div
                        key={idx}
                        className="card"
                        style={{
                          borderRadius: '10px',
                          border: '1px solid hsl(var(--border))',
                          background: 'hsl(var(--card))',
                          overflow: 'hidden',
                          transition: 'all 0.2s ease',
                        }}
                      >
                        {/* Collapsed Header Bar */}
                        <div
                          style={{
                            padding: '10px 14px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            cursor: 'pointer',
                            backgroundColor: isExpanded ? 'hsl(var(--muted)/0.25)' : 'transparent',
                            borderBottom: isExpanded ? '1px solid hsl(var(--border))' : 'none',
                          }}
                          onClick={() => {
                            if (isExpanded) {
                              setExpandedAgentIndexes(prev => prev.filter(i => i !== idx));
                            } else {
                              setExpandedAgentIndexes(prev => [...prev, idx]);
                            }
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1, minWidth: 0 }}>
                            <IdentityBadge
                              icon={agent.icon || 'Bot'}
                              color={agent.color || 'violet'}
                              size={15}
                              containerSize={28}
                            />
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ fontWeight: 600, fontSize: '13px', color: 'hsl(var(--fg))' }}>
                                  {agent.name || `Specialist ${idx + 1}`}
                                </span>
                                {isCustom ? (
                                  <span className="badge" style={{ fontSize: '10px', color: 'hsl(var(--primary))' }}>
                                    ⚡ Override: {agent.model || teamDefault}
                                  </span>
                                ) : (
                                  <span className="badge" style={{ fontSize: '10px', opacity: 0.75 }}>
                                    ✨ Eredita ({teamDefault})
                                  </span>
                                )}
                              </div>
                              <div className="text-muted" style={{ fontSize: '11.5px', marginTop: '1px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {agent.role || 'Specialist'}
                                {agent.delegates_to.length > 0 && ` • Delega a: ${agent.delegates_to.join(', ')}`}
                              </div>
                            </div>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }} onClick={e => e.stopPropagation()}>
                            {blueprint.agents.length > 1 && (
                              <button
                                type="button"
                                className="btn btn-ghost"
                                style={{ padding: '4px 6px', color: 'hsl(var(--destructive))' }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRemoveAgent(idx);
                                }}
                                title={t('removeAgent') || 'Rimuovi Agente'}
                              >
                                <Trash2 size={14} />
                              </button>
                            )}
                            <button
                              type="button"
                              className="btn btn-ghost"
                              style={{ padding: '4px 6px' }}
                              onClick={() => {
                                if (isExpanded) {
                                  setExpandedAgentIndexes(prev => prev.filter(i => i !== idx));
                                } else {
                                  setExpandedAgentIndexes(prev => [...prev, idx]);
                                }
                              }}
                            >
                              {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                            </button>
                          </div>
                        </div>

                        {/* Expanded Form Body */}
                        {isExpanded && (
                          <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            <div className="form-row" style={{ marginBottom: 0 }}>
                              <div className="form-group" style={{ marginBottom: 0 }}>
                                <label className="form-label">{t('name') || 'Nome Agente'}</label>
                                <input
                                  type="text"
                                  className="form-input"
                                  value={agent.name}
                                  onChange={e => {
                                    const next = [...blueprint.agents];
                                    next[idx].name = e.target.value;
                                    setBlueprint({ ...blueprint, agents: next });
                                  }}
                                  placeholder="Nome Agente"
                                  style={{ fontWeight: 600 }}
                                />
                              </div>
                              <div className="form-group" style={{ marginBottom: 0 }}>
                                <label className="form-label">{t('role') || 'Ruolo'}</label>
                                <input
                                  type="text"
                                  className="form-input"
                                  value={agent.role}
                                  onChange={e => {
                                    const next = [...blueprint.agents];
                                    next[idx].role = e.target.value;
                                    setBlueprint({ ...blueprint, agents: next });
                                  }}
                                  placeholder="Ruolo Agente"
                                />
                              </div>
                            </div>

                            <div className="form-row" style={{ marginBottom: 0 }}>
                              <VisualIconSelect
                                value={agent.icon || 'Bot'}
                                onChange={i => {
                                  const next = [...blueprint.agents];
                                  next[idx].icon = i;
                                  setBlueprint({ ...blueprint, agents: next });
                                }}
                                label="Icon"
                              />
                              <VisualColorSelect
                                value={agent.color || 'violet'}
                                onChange={c => {
                                  const next = [...blueprint.agents];
                                  next[idx].color = c;
                                  setBlueprint({ ...blueprint, agents: next });
                                }}
                                label="Color"
                              />
                            </div>

                            {/* System Prompt Textarea */}
                            <div className="form-group" style={{ marginBottom: 0 }}>
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                                <label className="form-label" style={{ marginBottom: 0 }}>
                                  {t('systemInstructions') || 'Istruzioni di Sistema (Prompt)'}
                                </label>
                                <button
                                  type="button"
                                  className="btn btn-ghost"
                                  style={{ padding: '2px 8px', fontSize: '11px', color: 'hsl(var(--primary))', gap: '4px' }}
                                  onClick={() => handleEnhanceAgentPrompt(idx)}
                                  disabled={isEnhancing}
                                >
                                  {isEnhancing ? (
                                    <RefreshCw size={11} className="animate-spin" />
                                  ) : (
                                    <Sparkles size={11} />
                                  )}
                                  <span>{isEnhancing ? t('enhancing') || 'Ottimizzazione...' : t('magicEnhance') || '✨ Migliora con l\'IA'}</span>
                                </button>
                              </div>
                              <textarea
                                className="form-textarea"
                                rows={4}
                                value={agent.system_prompt}
                                onChange={e => {
                                  const next = [...blueprint.agents];
                                  next[idx].system_prompt = e.target.value;
                                  setBlueprint({ ...blueprint, agents: next });
                                }}
                                style={{
                                  fontSize: '12px',
                                  lineHeight: 1.4,
                                  fontFamily: 'var(--font-mono, monospace)',
                                }}
                              />
                            </div>

                            {/* Delegation Selector */}
                            <DelegationSelector
                              currentAgentName={agent.name}
                              availableAgents={blueprint.agents.map(a => ({
                                name: a.name,
                                role: a.role,
                                icon: a.icon,
                                color: a.color,
                              }))}
                              delegatesTo={agent.delegates_to}
                              onChange={nextDelegates => {
                                const next = [...blueprint.agents];
                                next[idx].delegates_to = nextDelegates;
                                setBlueprint({ ...blueprint, agents: next });
                              }}
                              label={t('delegatesTo') || 'Delega a:'}
                              hint={t('delegatesToHint') || 'Attiva le deleghe con un click.'}
                            />

                            {/* Collapsible Model Override */}
                            <div style={{ marginTop: '6px', paddingTop: '10px', borderTop: '1px solid hsl(var(--border)/0.5)' }}>
                              <div
                                style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', userSelect: 'none' }}
                                onClick={() => toggleAgentOverride(idx)}
                              >
                                <span style={{ fontSize: '12px', color: isCustom ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                  <ShieldCheck size={13} />
                                  {isCustom
                                    ? `Override modello attivo: ${agent.model || teamDefault}`
                                    : `⚙️ Override modello (Opzionale - usa default: ${teamDefault})`}
                                </span>
                                <button type="button" className="btn btn-ghost" style={{ padding: '2px 6px' }}>
                                  {isOverrideOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                                </button>
                              </div>

                              {isOverrideOpen && (
                                <div style={{ marginTop: '10px' }}>
                                  <ModelSelector
                                    provider={agent.provider || blueprint.default_provider || workspaceProvider}
                                    value={agent.model ?? null}
                                    teamDefaultModel={teamDefault}
                                    onChange={newModel => {
                                      const next = [...blueprint.agents];
                                      next[idx].model = newModel;
                                      setBlueprint({ ...blueprint, agents: next });
                                    }}
                                    label={t('modelLabel') || 'Modello Dedicato per questo Agente'}
                                  />
                                </div>
                              )}
                            </div>

                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* TAB 2: TOPOLOGY VISUALIZER */}
              {activeTab === 'topology' && (
                <div
                  className="card"
                  style={{
                    padding: '20px',
                    borderRadius: '12px',
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                  }}
                >
                  <TeamTopology
                    agents={blueprint.agents.map(a => ({
                      name: a.name,
                      role: a.role,
                      icon: a.icon,
                      color: a.color,
                      delegates_to: a.delegates_to,
                      skills: a.skills,
                    }))}
                    teamName={blueprint.team_name}
                    height={220}
                  />
                  <p style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', margin: '14px 0 0', textAlign: 'center' }}>
                    {t('topologyExplanation') || 'Il grafo illustra le gerarchie di delega tra gli agenti generati.'}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '16px 24px',
            borderTop: '1px solid hsl(var(--border))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'hsl(var(--card))',
          }}
        >
          {step === 'input' && (
            <>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={onClose}
              >
                {t('cancel') || 'Annulla'}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => handleGenerate()}
                disabled={!goal.trim()}
                style={{ padding: '8px 20px', display: 'inline-flex', alignItems: 'center', gap: '8px' }}
              >
                <Sparkles size={16} />
                <span>{t('generateWorkforce') || 'Progetta con l\'IA'}</span>
              </button>
            </>
          )}

          {step === 'generating' && (
            <div style={{ width: '100%', textAlign: 'center' }}>
              <span className="text-muted" style={{ fontSize: '13px' }}>
                {t('pleaseWaitGenerating') || 'Attendere, generazione della squadra in corso...'}
              </span>
            </div>
          )}

          {step === 'preview' && (
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setStep('input')}
                disabled={isApplying}
              >
                {t('back') || 'Indietro'}
              </button>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={onClose}
                  disabled={isApplying}
                >
                  {t('cancel') || 'Annulla'}
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleApply}
                  disabled={isApplying || !blueprint?.team_name.trim()}
                  style={{ padding: '8px 22px', display: 'inline-flex', alignItems: 'center', gap: '8px' }}
                >
                  {isApplying ? (
                    <>
                      <RefreshCw size={15} className="animate-spin" />
                      <span>{t('saving') || 'Salvataggio...'}</span>
                    </>
                  ) : (
                    <>
                      <span>{t('applyAndActivateWorkforce') || 'Salva & Attiva Squadra'}</span>
                      <ArrowRight size={16} />
                    </>
                  )}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
