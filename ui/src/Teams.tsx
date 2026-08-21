import { useState, useEffect, useContext, useCallback } from 'react';
import { Users, Plus, Edit, X, Layers, ArrowRight } from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';

type TeamAgent = { name: string; role: string; delegates_to: string; skills: string[]; provider?: string | null; model?: string | null };

function TeamBuilder({ onClose, onSaved, initialTeam }: { onClose: () => void; onSaved: () => void; initialTeam?: any }) {
  const [name, setName] = useState(initialTeam?.name || '');
  const [provider, setProvider] = useState(initialTeam?.default_provider || 'ollama');
  const [model, setModel] = useState(initialTeam?.default_model || 'qwen3.5:9b');
  const [agents, setAgents] = useState<TeamAgent[]>([
    { name: 'Manager', role: 'Coordinates the workforce', delegates_to: '', skills: [] },
    { name: 'Researcher', role: 'Researches and summarizes knowledge', delegates_to: '', skills: ['search_knowledge'] },
  ]);
  const [saving, setSaving] = useState(false);
  const showToast = useContext(ToastContext);

  useEffect(() => {
    if (!initialTeam) return;
    setName(initialTeam.name || '');
    setProvider(initialTeam.default_provider || 'ollama');
    setModel(initialTeam.default_model || '');
    setAgents((initialTeam.agents || []).map((agent: any) => ({
      name: agent.name || '',
      role: agent.role || '',
      delegates_to: (agent.delegates_to || []).join(', '),
      skills: agent.skills || [],
      provider: agent.provider || null,
      model: agent.model || null,
    })));
  }, [initialTeam]);

  const updateAgent = (index: number, key: keyof TeamAgent, value: string) => {
    setAgents(current => current.map((agent, i) => i === index ? { ...agent, [key]: value } : agent));
  };

  const save = async () => {
    if (!name.trim() || agents.some(agent => !agent.name.trim() || !agent.role.trim())) return;
    setSaving(true);
    try {
      const response = await fetch(apiUrl(initialTeam ? `/api/teams/${encodeURIComponent(initialTeam.name)}` : '/api/teams'), {
        method: initialTeam ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(), provider, default_provider: provider, default_model: model,
          agents: agents.map(agent => ({
            name: agent.name.trim(),
            role: agent.role.trim(),
            delegates_to: agent.delegates_to.split(',').map(value => value.trim()).filter(Boolean),
            skills: agent.skills,
            provider: agent.provider || null,
            model: agent.model || null,
          })),
        }),
      });
      if (!response.ok) {
        throw await apiError(response, initialTeam ? 'Unable to update team.' : 'Unable to create team.');
      }
      showToast(initialTeam ? 'Team updated.' : 'Team created.', 'success');
      onSaved();
      onClose();
    } catch (error) {
      showToast(error instanceof Error ? error.message : (initialTeam ? 'Unable to update team.' : 'Unable to create team.'), 'error');
    } finally {
      setSaving(false);
    }
  };

  return <>
    <div className="overlay" onClick={() => !saving && onClose()} />
    <div className="slide-over">
      <div className="slide-over-header"><strong>{initialTeam ? 'Edit Team' : 'Create Team'}</strong><button className="btn btn-ghost" onClick={onClose} disabled={saving}><X size={20} /></button></div>
      <div className="slide-over-body">
        <div className="form-group"><label className="form-label">Team name</label><input className="form-input" autoFocus value={name} onChange={event => setName(event.target.value)} placeholder="e.g. Product Intelligence" /></div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Provider</label><select className="form-select" value={provider} onChange={event => setProvider(event.target.value)}><option value="ollama">Ollama</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="gemini">Google Gemini</option><option value="mock">Mock</option></select></div>
          <div className="form-group"><label className="form-label">Model</label><input className="form-input" value={model} onChange={event => setModel(event.target.value)} placeholder="Model name" /></div>
        </div>
        <h3 style={{ marginTop: 24 }}>Workforce members</h3>
        {agents.map((agent, index) => <div className="card" style={{ padding: 16, marginBottom: 12 }} key={index}>
          <div className="form-group"><label className="form-label">Agent name</label><input className="form-input" value={agent.name} onChange={event => updateAgent(index, 'name', event.target.value)} /></div>
          <div className="form-group"><label className="form-label">Role</label><input className="form-input" value={agent.role} onChange={event => updateAgent(index, 'role', event.target.value)} /></div>
          <div className="form-group" style={{ marginBottom: 0 }}><label className="form-label">Delegates to <span className="text-muted">(comma separated)</span></label><input className="form-input" value={agent.delegates_to} onChange={event => updateAgent(index, 'delegates_to', event.target.value)} placeholder="Researcher" /></div>
        </div>)}
        <button className="btn btn-secondary" onClick={() => setAgents(current => [...current, { name: '', role: '', delegates_to: '', skills: [] }])}><Plus size={15} /> Add agent</button>
      </div>
      <div className="slide-over-footer"><button className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button><button className="btn btn-primary" onClick={save} disabled={saving || !name.trim() || agents.some(agent => !agent.name.trim() || !agent.role.trim())}>{saving ? 'Saving…' : (initialTeam ? 'Save changes' : 'Create Team')}</button></div>
    </div>
  </>;
}

function PresetPickerModal({ onClose, onInstalled }: { onClose: () => void; onInstalled: () => void }) {
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
      .catch(console.error);
  }, []);

  const handleApply = async () => {
    if (!selectedId) return;
    setApplying(true);
    try {
      const res = await fetch(apiUrl(`/api/presets/${encodeURIComponent(selectedId)}/apply`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seed_knowledge: true })
      });
      if (!res.ok) {
        throw await apiError(res, 'Unable to apply preset.');
      }
      showToast('Preset applied successfully!', 'success');
      onInstalled();
      onClose();
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setApplying(false);
    }
  };

  return (
    <>
      <div className="overlay" onClick={() => !applying && onClose()} />
      <div className="slide-over" style={{ maxWidth: '600px' }}>
        <div className="slide-over-header">
          <strong>Start from Official Preset</strong>
          <button className="btn btn-ghost" onClick={onClose} disabled={applying}><X size={20} /></button>
        </div>
        <div className="slide-over-body">
          <p className="text-muted" style={{ fontSize: '14px', marginBottom: '20px' }}>
            Choose a ready-to-run workforce starter pack. It includes configured agents, topological delegation relationships, and built-in official knowledge.
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
                  borderRadius: '8px',
                  border: selectedId === p.id ? '2px solid hsl(var(--primary))' : '1px solid hsl(var(--card-border))',
                  backgroundColor: selectedId === p.id ? 'hsl(var(--primary)/0.05)' : 'hsl(var(--card-bg))',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <strong style={{ fontSize: '15px' }}>{p.name}</strong>
                  <span className="badge badge-primary">{p.agent_count} Agents</span>
                </div>
                <p className="text-muted" style={{ fontSize: '13px', lineHeight: 1.4, margin: '0 0 10px 0' }}>
                  {p.description}
                </p>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
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
        <div className="slide-over-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={applying}>Cancel</button>
          <button className="btn btn-primary" onClick={handleApply} disabled={applying || !selectedId}>
            {applying ? 'Applying…' : 'Use this Preset'} <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </>
  );
}

export function Teams() {
  const [teams, setTeams] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isBuilding, setIsBuilding] = useState(false);
  const [isPresetOpen, setIsPresetOpen] = useState(false);
  const [editingTeam, setEditingTeam] = useState<any | undefined>(undefined);
  const showToast = useContext(ToastContext);

  const fetchTeams = useCallback(() => {
    fetch(apiUrl('/api/teams')).then(res => res.json()).then(data => { setTeams(Array.isArray(data) ? data : []); setLoading(false); }).catch(() => { showToast('Unable to load teams.', 'error'); setLoading(false); });
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

  useEffect(() => { fetchTeams(); }, [fetchTeams]);

  return <div style={{ flex: 1, overflowY: 'auto' }}>
    <div className="top-header">
      <div className="top-header-title">My Teams</div>
      <div style={{ display: 'flex', gap: '8px' }}>
        <button className="btn btn-secondary" onClick={() => setIsPresetOpen(true)}>
          <Layers size={16} /> Use Preset
        </button>
        <button className="btn btn-primary" onClick={() => setIsBuilding(true)}>
          <Plus size={16} /> Create Team
        </button>
      </div>
    </div>
    <div className="grid-container">
      {teams.map((team, index) => <div key={index} className="card card-interactive">
        <div className="card-title"><span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Users size={20} className="text-primary" />{team.name}</span></div>
        <div className="card-subtitle" style={{ fontFamily: 'monospace' }}>{team.filename}</div>
        <div style={{ marginBottom: 16, fontSize: 14 }}>Contains {team.agents} agent{team.agents !== 1 ? 's' : ''}.</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}><span className="badge badge-default">Provider: {team.default_provider}</span>{team.default_model && <span className="badge badge-default">Model: {team.default_model}</span>}</div>
        <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end' }}><button className="btn btn-ghost" onClick={() => openEditor(team)}><Edit size={16} /> Edit team</button></div>
      </div>)}
      {teams.length === 0 && !loading && <div className="empty-state" style={{ gridColumn: '1 / -1' }}><Users className="empty-icon" /><div className="empty-title">No teams yet</div><p className="text-muted">Create a team or start from an official preset.</p></div>}
    </div>
    {isBuilding && <TeamBuilder initialTeam={editingTeam} onClose={() => { setIsBuilding(false); setEditingTeam(undefined); }} onSaved={fetchTeams} />}
    {isPresetOpen && <PresetPickerModal onClose={() => setIsPresetOpen(false)} onInstalled={fetchTeams} />}
  </div>;
}
