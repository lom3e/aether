import { useState, useEffect } from 'react';
import { ArrowRight, CheckCircle2, Users, BookOpen, Layers } from 'lucide-react';
import { apiError, apiUrl } from './api';
import { useTheme } from './theme';

interface PresetItem {
  id: string;
  name: string;
  version: string;
  description: string;
  agent_count: number;
  agents: Array<{ name: string; role: string }>;
  knowledge_packs: string[];
}

export function Onboarding({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [selectedPreset, setSelectedPreset] = useState('starter-workforce');
  const [presets, setPresets] = useState<PresetItem[]>([]);
  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('qwen3.5:9b');
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const { isDark } = useTheme();

  useEffect(() => {
    fetch(apiUrl('/api/presets'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setPresets(data);
          setSelectedPreset(data[0].id);
        }
      })
      .catch(console.error);
  }, []);

  const handleNext = () => setStep(s => s + 1);
  const handleBack = () => setStep(s => s - 1);

  const handleFinishOnboarding = async () => {
    setLoading(true);
    setError('');

    try {
      // 1. Initialize workspace with preset
      const res = await fetch(apiUrl('/api/workspace/init'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          preset_id: selectedPreset,
          provider,
          model,
          api_key: apiKey || null,
        }),
      });

      if (!res.ok) {
        throw await apiError(res, 'Unable to initialize workspace with preset.');
      }

      // 2. Also save provider settings to ensure .env is active
      await fetch(apiUrl('/api/settings/provider'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model, api_key: apiKey || null }),
      });

      handleNext();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (step === 2) {
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
    }
  }, [provider, step, model]);

  const activePresetObj = presets.find(p => p.id === selectedPreset);

  return (
    <div className="onboarding-wrap">
      <div className="onboarding-card" style={{ maxWidth: step === 1 ? '720px' : '540px' }}>
        {/* Brand Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '28px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <img src={isDark ? "/brand/logo_bianco.svg" : "/brand/logo_nero.svg"} alt="Aether" width="28" height="28" style={{ height: '28px', width: 'auto', display: 'block' }} />
            <span style={{ fontWeight: 700, fontSize: '16px', letterSpacing: '0.06em', color: 'hsl(var(--fg))' }}>AETHER</span>
          </div>

          <div className="onboarding-progress">
            <div className={`progress-dot ${step === 1 ? 'active' : 'completed'}`} />
            <div className={`progress-dot ${step === 2 ? 'active' : (step > 2 ? 'completed' : '')}`} />
            <div className={`progress-dot ${step === 3 ? 'active' : (step > 3 ? 'completed' : '')}`} />
          </div>
        </div>

        {/* STEP 1: Workspace Name & Preset Selection */}
        {step === 1 && (
          <div className="fade-in">
            <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '6px', color: 'hsl(var(--fg))' }}>
              Welcome to Aether
            </h1>
            <p className="text-muted" style={{ fontSize: '14px', marginBottom: '26px' }}>
              Configure your local workspace and choose an AI workforce starter preset.
            </p>

            <div className="form-group">
              <label className="form-label" style={{ fontWeight: 600 }}>Workspace Name</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Aether Operations Hub"
                value={name}
                onChange={e => setName(e.target.value)}
                disabled={loading}
                autoFocus
              />
            </div>

            <div style={{ marginTop: '22px', marginBottom: '8px' }}>
              <label className="form-label" style={{ fontWeight: 600 }}>Choose a Starter Workforce Preset</label>
              <p className="text-muted" style={{ fontSize: '13px', marginBottom: '14px' }}>
                Pre-configured multi-agent team with coordination topology and built-in knowledge.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
                {presets.map(p => {
                  const isSelected = selectedPreset === p.id;
                  return (
                    <div
                      key={p.id}
                      className="card"
                      onClick={() => setSelectedPreset(p.id)}
                      style={{
                        cursor: 'pointer',
                        padding: '18px',
                        borderRadius: '12px',
                        border: isSelected ? '2px solid hsl(var(--primary))' : '1px solid hsl(var(--border))',
                        backgroundColor: isSelected ? 'hsl(var(--primary)/0.06)' : 'hsl(var(--card))',
                        transition: 'all 0.18s ease-in-out',
                        boxShadow: isSelected ? '0 4px 18px hsl(var(--primary)/0.12)' : 'none',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <strong style={{ fontSize: '15px', color: 'hsl(var(--fg))' }}>{p.name}</strong>
                        <span className="badge badge-primary" style={{ fontSize: '11px', fontWeight: 600 }}>
                          {p.agent_count} Agents
                        </span>
                      </div>
                      <p className="text-muted" style={{ fontSize: '13px', lineHeight: 1.45, margin: '0 0 14px 0' }}>
                        {p.description}
                      </p>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        {p.agents.slice(0, 3).map((a, i) => (
                          <span key={i} className="badge" style={{ fontSize: '11px' }}>
                            {a.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {error && <div className="text-error" style={{ color: 'hsl(var(--destructive))', marginTop: '16px', fontSize: '14px' }}>{error}</div>}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '30px' }}>
              <button
                className="btn btn-primary"
                onClick={handleNext}
                disabled={!name.trim() || loading}
                style={{ padding: '10px 22px', fontSize: '14px' }}
              >
                Continue <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* STEP 2: Configure AI Provider */}
        {step === 2 && (
          <div className="fade-in">
            <h2 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '6px' }}>Configure AI Provider</h2>
            <p className="text-muted" style={{ fontSize: '14px', marginBottom: '24px' }}>
              Select the engine and model that will power your autonomous agents.
            </p>

            <div className="form-group">
              <label className="form-label">Provider</label>
              <select className="form-select" value={provider} onChange={e => setProvider(e.target.value)} disabled={loading}>
                <option value="ollama">Ollama (Local & Private)</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Google Gemini</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Model</label>
              {availableModels.length > 0 ? (
                <select
                  className="form-select"
                  value={model}
                  onChange={e => setModel(e.target.value)}
                  disabled={loading}
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
                  placeholder="e.g. qwen2.5:14b or llama3.3:70b"
                  onChange={e => setModel(e.target.value)}
                  disabled={loading}
                />
              )}
            </div>

            {provider !== 'ollama' && (
              <div className="form-group">
                <label className="form-label">API Key</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder={`Enter your ${provider} API Key`}
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  disabled={loading}
                />
              </div>
            )}

            {error && <div className="text-error" style={{ color: 'hsl(var(--destructive))', marginBottom: '16px', fontSize: '14px' }}>{error}</div>}

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '30px' }}>
              <button className="btn btn-secondary" onClick={handleBack} disabled={loading}>
                Back
              </button>
              <button
                className="btn btn-primary"
                onClick={handleFinishOnboarding}
                disabled={loading}
                style={{ padding: '10px 22px' }}
              >
                {loading ? 'Initializing…' : 'Initialize Workspace'} <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* STEP 3: Workspace Ready */}
        {step === 3 && (
          <div style={{ textAlign: 'center', animation: 'fadeIn 0.3s ease-out' }}>
            <div style={{ width: '64px', height: '64px', borderRadius: '32px', backgroundColor: 'hsl(var(--success)/0.12)', color: 'hsl(var(--success))', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
              <CheckCircle2 size={32} />
            </div>
            <h2 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>Workspace Ready!</h2>
            <p className="text-muted" style={{ marginBottom: '24px', fontSize: '14px', maxWidth: '420px', margin: '0 auto 24px', lineHeight: 1.5 }}>
              <strong>{name}</strong> is now configured with <strong>{activePresetObj?.name || 'Starter Workforce'}</strong> and built-in system knowledge.
            </p>

            <div className="card" style={{ textAlign: 'left', padding: '18px', marginBottom: '26px', borderRadius: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px', fontSize: '13px', fontWeight: 600 }}>
                <Users size={16} className="text-primary" /> Active Agents:
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' }}>
                {activePresetObj?.agents.map((a, i) => (
                  <span key={i} className="badge badge-primary" style={{ fontSize: '12px' }}>
                    {a.name} ({a.role})
                  </span>
                ))}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
                <BookOpen size={14} /> Official Aether System Knowledge pre-installed & indexed
              </div>
            </div>

            <button className="btn btn-primary" onClick={onComplete} style={{ width: '100%', padding: '12px', fontSize: '14px' }}>
              <Layers size={16} /> Launch Aether Workspace
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
