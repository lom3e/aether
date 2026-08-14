import { useState, useEffect } from 'react';
import { Sparkles, ArrowRight, CheckCircle2, Users, BookOpen } from 'lucide-react';
import { apiError, apiUrl } from './api';

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
      <div className="onboarding-card" style={{ maxWidth: step === 1 ? '700px' : '520px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px', color: 'hsl(var(--muted-foreground))', fontWeight: 600 }}>
          <Sparkles size={20} className="text-primary" /> Aether
        </div>

        <div className="onboarding-progress" style={{ marginBottom: '24px' }}>
          <div className={`progress-dot ${step === 1 ? 'active' : 'completed'}`} />
          <div className={`progress-dot ${step === 2 ? 'active' : (step > 2 ? 'completed' : '')}`} />
          <div className={`progress-dot ${step === 3 ? 'active' : (step > 3 ? 'completed' : '')}`} />
        </div>

        {step === 1 && (
          <div className="fade-in">
            <h1 style={{ marginBottom: '6px' }}>Welcome to Aether</h1>
            <p className="text-muted" style={{ marginBottom: '24px' }}>Let's configure your AI workforce and workspace.</p>

            <div className="form-group">
              <label className="form-label">Workspace Name</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Acme Intelligence"
                value={name}
                onChange={e => setName(e.target.value)}
                disabled={loading}
                autoFocus
              />
            </div>

            <div style={{ marginTop: '20px', marginBottom: '8px' }}>
              <label className="form-label" style={{ fontWeight: 600 }}>Choose a Starter Workforce Preset</label>
              <p className="text-muted" style={{ fontSize: '13px', marginBottom: '12px' }}>
                Pre-configured multi-agent team with topological delegations and built-in official knowledge.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                {presets.map(p => (
                  <div
                    key={p.id}
                    className="card"
                    onClick={() => setSelectedPreset(p.id)}
                    style={{
                      cursor: 'pointer',
                      padding: '16px',
                      borderRadius: '8px',
                      border: selectedPreset === p.id ? '2px solid hsl(var(--primary))' : '1px solid hsl(var(--card-border))',
                      backgroundColor: selectedPreset === p.id ? 'hsl(var(--primary)/0.05)' : 'hsl(var(--card-bg))',
                      transition: 'all 0.15s ease-in-out',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <strong style={{ fontSize: '15px' }}>{p.name}</strong>
                      <span className="badge badge-primary" style={{ fontSize: '11px' }}>{p.agent_count} Agents</span>
                    </div>
                    <p className="text-muted" style={{ fontSize: '13px', lineHeight: 1.4, margin: '0 0 10px 0' }}>
                      {p.description}
                    </p>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {p.agents.slice(0, 3).map((a, i) => (
                        <span key={i} className="badge" style={{ fontSize: '11px', background: 'hsl(var(--muted))' }}>
                          {a.name}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {error && <div className="text-error" style={{ color: 'hsl(var(--error))', marginTop: '16px', fontSize: '14px' }}>{error}</div>}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '28px' }}>
              <button
                className="btn btn-primary"
                onClick={handleNext}
                disabled={!name.trim() || loading}
              >
                Continue <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="fade-in">
            <h2 style={{ marginBottom: '8px' }}>Configure AI Provider</h2>
            <p className="text-muted" style={{ marginBottom: '24px' }}>Select the provider and model that will power your workforce.</p>

            <div className="form-group">
              <label className="form-label">Provider</label>
              <select className="form-select" value={provider} onChange={e => setProvider(e.target.value)} disabled={loading}>
                <option value="ollama">Ollama (Local)</option>
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

            {error && <div className="text-error" style={{ color: 'hsl(var(--error))', marginBottom: '16px', fontSize: '14px' }}>{error}</div>}

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '28px' }}>
              <button className="btn btn-ghost" onClick={handleBack} disabled={loading}>Back</button>
              <button
                className="btn btn-primary"
                onClick={handleFinishOnboarding}
                disabled={loading}
              >
                {loading ? 'Initializing…' : 'Initialize Workspace'} <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div style={{ textAlign: 'center', animation: 'fadeIn 0.3s ease-out' }}>
            <div style={{ width: '60px', height: '60px', borderRadius: '30px', backgroundColor: 'hsl(var(--success)/0.1)', color: 'hsl(var(--success))', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
              <CheckCircle2 size={30} />
            </div>
            <h2 style={{ marginBottom: '8px' }}>Workspace Ready!</h2>
            <p className="text-muted" style={{ marginBottom: '24px', fontSize: '14px', maxWidth: '380px', margin: '0 auto 24px' }}>
              <strong>{name}</strong> has been initialized with <strong>{activePresetObj?.name || 'Starter Workforce'}</strong> and built-in official knowledge.
            </p>

            <div className="card" style={{ textAlign: 'left', padding: '16px', marginBottom: '24px', backgroundColor: 'hsl(var(--card-bg))' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', fontSize: '13px', fontWeight: 600 }}>
                <Users size={16} className="text-primary" /> Active Agents:
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
                {activePresetObj?.agents.map((a, i) => (
                  <span key={i} className="badge badge-primary" style={{ fontSize: '12px' }}>
                    {a.name} ({a.role})
                  </span>
                ))}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'hsl(var(--muted-foreground))' }}>
                <BookOpen size={14} /> Official Aether System Knowledge pre-installed & indexed
              </div>
            </div>

            <button className="btn btn-primary" onClick={onComplete} style={{ width: '100%', padding: '12px' }}>
              Launch Aether Workforce
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
