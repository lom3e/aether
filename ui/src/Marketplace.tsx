import { useState, useEffect, useContext } from 'react';
import { Bot, Library, FileText, Layers, ArrowRight } from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';

export function Marketplace() {
  const [presets, setPresets] = useState<any[]>([]);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const showToast = useContext(ToastContext);

  useEffect(() => {
    fetch(apiUrl('/api/presets'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setPresets(data);
        }
      })
      .catch(console.error);
  }, []);

  const handleInstallPreset = async (presetId: string) => {
    setInstallingId(presetId);
    try {
      const res = await fetch(apiUrl(`/api/presets/${encodeURIComponent(presetId)}/apply`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seed_knowledge: true })
      });
      if (!res.ok) {
        throw await apiError(res, 'Unable to install preset.');
      }
      showToast('Workforce preset installed and activated successfully!', 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setInstallingId(null);
    }
  };

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '48px' }}>
      <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '8px' }}>
          <h1>Workforce Packs & Marketplace</h1>
          <span className="badge badge-success" style={{ fontSize: '12px', padding: '4px 10px' }}>Alpha Official Presets</span>
        </div>
        <p className="text-muted" style={{ fontSize: '17px', marginBottom: '36px', maxWidth: '680px' }}>
          Official workforce starter packs and pre-configured teams ready to deploy in your workspace.
        </p>

        <h2 style={{ marginBottom: '16px', fontSize: '20px' }}>Official Built-in Presets</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '48px' }}>
          {presets.map(preset => (
            <div key={preset.id} className="card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Layers className="text-primary" size={22} />
                    <h3 style={{ margin: 0 }}>{preset.name}</h3>
                  </div>
                  <span className="badge badge-primary">{preset.agent_count} Agents</span>
                </div>
                <p className="text-muted" style={{ fontSize: '14px', lineHeight: 1.5, marginBottom: '16px' }}>
                  {preset.description}
                </p>

                <div style={{ marginBottom: '16px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'hsl(var(--muted-foreground))', marginBottom: '6px' }}>
                    INCLUDED AGENTS & ROLES:
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {preset.agents.map((a: any, i: number) => (
                      <div key={i} style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span className="badge" style={{ fontSize: '11px', background: 'hsl(var(--muted))' }}>{a.name}</span>
                        <span className="text-muted">{a.role}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-foreground))', marginBottom: '20px' }}>
                  <strong>Knowledge:</strong> {preset.knowledge_packs.join(', ') || 'None'}
                </div>
              </div>

              <button
                className="btn btn-primary"
                onClick={() => handleInstallPreset(preset.id)}
                disabled={installingId === preset.id}
                style={{ width: '100%' }}
              >
                {installingId === preset.id ? 'Installing…' : 'Install & Activate Preset'} <ArrowRight size={16} />
              </button>
            </div>
          ))}
        </div>

        <h2 style={{ marginBottom: '16px', fontSize: '20px' }}>Community Ecosystem (Coming Soon)</h2>
        <div className="grid-container" style={{ padding: 0, marginBottom: '48px' }}>
          <div className="card" style={{ opacity: 0.8 }}>
            <Bot size={28} className="text-primary" style={{ marginBottom: '12px' }} />
            <h3 style={{ marginBottom: '6px', fontSize: '16px' }}>Community Agent Packs</h3>
            <p className="text-muted" style={{ fontSize: '13px' }}>Pre-configured specialized agents in marketing, code review, sales operations, and customer support.</p>
          </div>

          <div className="card" style={{ opacity: 0.8 }}>
            <Library size={28} className="text-primary" style={{ marginBottom: '12px' }} />
            <h3 style={{ marginBottom: '6px', fontSize: '16px' }}>Skill Libraries</h3>
            <p className="text-muted" style={{ fontSize: '13px' }}>Modular capabilities for GitHub, Jira, web search, database querying, and browser automation.</p>
          </div>

          <div className="card" style={{ opacity: 0.8 }}>
            <FileText size={28} className="text-primary" style={{ marginBottom: '12px' }} />
            <h3 style={{ marginBottom: '6px', fontSize: '16px' }}>Knowledge Packs</h3>
            <p className="text-muted" style={{ fontSize: '13px' }}>Curated industry datasets, standards, compliance guidelines, and domain frameworks.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
