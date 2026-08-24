import { useState, useEffect, useContext, useCallback } from 'react';
import { Users, Plus, Edit, X, Layers, ArrowRight } from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';
import { TopHeader } from './TopHeader';
import { useTranslation } from './i18n';
import { IdentityBadge, SUPPORTED_ICONS, SUPPORTED_COLORS } from './identity';
import { TeamTopology } from './TeamTopology';

type TeamAgent = {
  name: string;
  role: string;
  delegates_to: string;
  skills: string[];
  provider?: string | null;
  model?: string | null;
  icon?: string | null;
  color?: string | null;
};

function TeamBuilder({ onClose, onSaved, initialTeam }: { onClose: () => void; onSaved: () => void; initialTeam?: any }) {
  const { t } = useTranslation();
  const [name, setName] = useState(initialTeam?.name || '');
  const [provider, setProvider] = useState(initialTeam?.default_provider || 'ollama');
  const [model, setModel] = useState(initialTeam?.default_model || 'qwen3.5:9b');
  const [teamIcon, setTeamIcon] = useState(initialTeam?.icon || 'Bot');
  const [teamColor, setTeamColor] = useState(initialTeam?.color || 'violet');
  const [agents, setAgents] = useState<TeamAgent[]>([
    { name: 'Manager', role: 'Coordinates the workforce', delegates_to: '', skills: [], icon: 'Bot', color: 'violet' },
    { name: 'Researcher', role: 'Researches and summarizes knowledge', delegates_to: '', skills: ['search_knowledge'], icon: 'Search', color: 'cyan' },
  ]);
  const [saving, setSaving] = useState(false);
  const showToast = useContext(ToastContext);

  useEffect(() => {
    if (!initialTeam) return;
    setName(initialTeam.name || '');
    setProvider(initialTeam.default_provider || 'ollama');
    setModel(initialTeam.default_model || '');
    setTeamIcon(initialTeam.icon || 'Bot');
    setTeamColor(initialTeam.color || 'violet');
    setAgents((initialTeam.agents || []).map((agent: any) => ({
      name: agent.name || '',
      role: agent.role || '',
      delegates_to: (agent.delegates_to || []).join(', '),
      skills: agent.skills || [],
      provider: agent.provider || null,
      model: agent.model || null,
      icon: agent.icon || null,
      color: agent.color || null,
    })));
  }, [initialTeam]);

  const updateAgent = (index: number, key: keyof TeamAgent, value: any) => {
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
          name: name.trim(),
          provider,
          default_provider: provider,
          default_model: model,
          icon: teamIcon,
          color: teamColor,
          agents: agents.map(agent => ({
            name: agent.name.trim(),
            role: agent.role.trim(),
            delegates_to: agent.delegates_to.split(',').map(value => value.trim()).filter(Boolean),
            skills: agent.skills,
            provider: agent.provider || null,
            model: agent.model || null,
            icon: agent.icon || null,
            color: agent.color || null,
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

  return (
    <>
      <div className="overlay" onClick={() => !saving && onClose()} />
      <div className="slide-over">
        <div className="slide-over-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <IdentityBadge icon={teamIcon} color={teamColor} size={18} containerSize={32} />
            <strong>{initialTeam ? t('editTeam') : t('createTeam')}</strong>
          </div>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}><X size={20} /></button>
        </div>
        <div className="slide-over-body">
          <div className="form-group">
            <label className="form-label">{t('teamName')}</label>
            <input className="form-input" autoFocus value={name} onChange={event => setName(event.target.value)} placeholder={t('teamNamePlaceholder')} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Team Icon</label>
              <select className="form-select" value={teamIcon} onChange={e => setTeamIcon(e.target.value)}>
                {SUPPORTED_ICONS.map(i => (
                  <option key={i} value={i}>{i}</option>
                ))}
              </select>
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Team Color</label>
              <select className="form-select" value={teamColor} onChange={e => setTeamColor(e.target.value)}>
                {SUPPORTED_COLORS.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">{t('provider')}</label>
              <select className="form-select" value={provider} onChange={event => setProvider(event.target.value)}>
                <option value="ollama">Ollama</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Google Gemini</option>
                <option value="mock">Mock</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">{t('model')}</label>
              <input className="form-input" value={model} onChange={event => setModel(event.target.value)} placeholder="Model name" />
            </div>
          </div>

          <div style={{ marginTop: 24, marginBottom: 16 }}>
            <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Workforce Topology
            </div>
            <TeamTopology agents={agents} teamName={name || 'Team'} height={150} />
          </div>

          <h3 style={{ marginTop: 20 }}>{t('workforceMembers')}</h3>
          {agents.map((agent, index) => (
            <div className="card" style={{ padding: 16, marginBottom: 12 }} key={index}>
              <div className="form-group">
                <label className="form-label">{t('agentName')}</label>
                <input className="form-input" value={agent.name} onChange={event => updateAgent(index, 'name', event.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('role')}</label>
                <input className="form-input" value={agent.role} onChange={event => updateAgent(index, 'role', event.target.value)} />
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">{t('delegatesTo')} <span className="text-muted">{t('commaSeparated')}</span></label>
                <input className="form-input" value={agent.delegates_to} onChange={event => updateAgent(index, 'delegates_to', event.target.value)} placeholder="Researcher" />
              </div>
            </div>
          ))}
          <button className="btn btn-secondary" onClick={() => setAgents(current => [...current, { name: '', role: '', delegates_to: '', skills: [], icon: 'Bot', color: 'violet' }])}>
            <Plus size={15} /> {t('addAgent')}
          </button>
        </div>
        <div className="slide-over-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={saving}>{t('cancel')}</button>
          <button className="btn btn-primary" onClick={save} disabled={saving || !name.trim() || agents.some(agent => !agent.name.trim() || !agent.role.trim())}>
            {saving ? t('saving') : (initialTeam ? t('saveChanges') : t('createTeam'))}
          </button>
        </div>
      </div>
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
          <strong>{t('startFromOfficialPreset')}</strong>
          <button className="btn btn-ghost" onClick={onClose} disabled={applying}><X size={20} /></button>
        </div>
        <div className="slide-over-body">
          <p className="text-muted" style={{ fontSize: '14px', marginBottom: '20px' }}>
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
                  borderRadius: '8px',
                  border: selectedId === p.id ? '2px solid hsl(var(--primary))' : '1px solid hsl(var(--card-border))',
                  backgroundColor: selectedId === p.id ? 'hsl(var(--primary)/0.05)' : 'hsl(var(--card-bg))',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <IdentityBadge icon={p.icon || 'Bot'} color={p.color || 'violet'} size={18} containerSize={32} />
                    <strong style={{ fontSize: '15px' }}>{p.name}</strong>
                  </div>
                  <span className="badge badge-primary">{p.agent_count} {p.agent_count === 1 ? t('agentSingular') : t('agentPlural')}</span>
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
          <button className="btn btn-secondary" onClick={onClose} disabled={applying}>{t('cancel')}</button>
          <button className="btn btn-primary" onClick={handleApply} disabled={applying || !selectedId}>
            {applying ? t('applying') : t('useThisPreset')} <ArrowRight size={16} />
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
            <button className="btn btn-primary" onClick={() => setIsBuilding(true)}>
              <Plus size={16} /> {t('createTeam')}
            </button>
          </>
        }
      />

      <div className="grid-container">
        {teams.map((team, index) => (
          <div
            key={index}
            className="card card-interactive"
            style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '22px' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <IdentityBadge icon={team.icon || 'Bot'} color={team.color || 'violet'} size={20} containerSize={38} />
                <div>
                  <h3 style={{ fontSize: '15px', margin: 0, fontWeight: 600 }}>{team.name}</h3>
                  <div className="text-muted" style={{ fontSize: '12px', fontFamily: 'monospace' }}>{team.filename}</div>
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

            <div style={{ marginTop: 'auto', paddingTop: '12px', borderTop: '1px solid hsl(var(--border)/0.4)', display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-ghost" style={{ fontSize: '12px', padding: '5px 10px' }} onClick={() => openEditor(team)}>
                <Edit size={14} /> {t('editTeam')}
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
      {isBuilding && (
        <TeamBuilder
          initialTeam={editingTeam}
          onClose={() => { setIsBuilding(false); setEditingTeam(undefined); }}
          onSaved={fetchTeams}
        />
      )}
      {isPresetOpen && (
        <PresetPickerModal
          onClose={() => setIsPresetOpen(false)}
          onInstalled={fetchTeams}
        />
      )}
    </div>
  );
}
