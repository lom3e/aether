import { useState, useEffect, useContext } from 'react';
import { X, Bot, Cpu } from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';
import { useTranslation } from './i18n';
import { SUPPORTED_ICONS, SUPPORTED_COLORS } from './identity';

export function AgentBuilder({
  onClose,
  onSave,
  initialData
}: {
  onClose: () => void,
  onSave: () => void,
  initialData?: any
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(initialData?.name || '');
  const [role, setRole] = useState(initialData?.role || '');
  const [icon, setIcon] = useState(initialData?.icon || 'Bot');
  const [color, setColor] = useState(initialData?.color || 'violet');
  const [instructions, setInstructions] = useState(initialData?.description || '');
  const [provider, setProvider] = useState(initialData?.provider || '');
  const [model, setModel] = useState(initialData?.model || '');
  const [delegatesTo, setDelegatesTo] = useState((initialData?.delegates_to || []).join(', '));
  const [selectedSkills, setSelectedSkills] = useState<string[]>(initialData?.skills || []);
  const [availableSkills, setAvailableSkills] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const showToast = useContext(ToastContext);

  useEffect(() => {
    fetch(apiUrl('/api/skills'))
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) setAvailableSkills(data);
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!name || !role) return;
    setSaving(true);
    const method = initialData ? 'PUT' : 'POST';
    const url = initialData
      ? apiUrl(`/api/agents/${encodeURIComponent(initialData.name)}`)
      : apiUrl('/api/agents');

    const delegatesList = delegatesTo.split(',').map((s: string) => s.trim()).filter(Boolean);

    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          role,
          icon: icon || null,
          color: color || null,
          instructions: instructions || null,
          provider: provider || null,
          model: model || null,
          skills: selectedSkills,
          delegates_to: delegatesList
        })
      });
      if (!res.ok) {
        throw await apiError(res, 'Unable to save this agent.');
      } else {
        showToast(initialData ? 'Agent updated.' : 'Agent created.', 'success');
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
        method: 'DELETE'
      });
      if (res.ok) {
        showToast('Agent deleted.', 'success');
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

  return (
    <>
      <div className="overlay" onClick={onClose}></div>
      <div className="slide-over">
        <div className="slide-over-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontWeight: 600, fontSize: '18px' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '6px', backgroundColor: 'hsl(var(--primary)/0.1)', color: 'hsl(var(--primary))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={18} />
            </div>
            {initialData ? t('editAgent') : t('createAgent')}
          </div>
          <button className="btn btn-ghost" style={{ padding: '8px' }} onClick={onClose} disabled={saving}>
            <X size={20} />
          </button>
        </div>

        <div className="slide-over-body">
          <div className="form-group">
            <label className="form-label">{t('name')}</label>
            <input
              type="text"
              className="form-input"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Researcher"
            />
          </div>

          <div className="form-group">
            <label className="form-label">{t('role')}</label>
            <input
              type="text"
              className="form-input"
              value={role}
              onChange={e => setRole(e.target.value)}
              placeholder="e.g. Research and analyze data"
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Icon</label>
              <select className="form-select" value={icon} onChange={e => setIcon(e.target.value)}>
                {SUPPORTED_ICONS.map(i => (
                  <option key={i} value={i}>{i}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Color</label>
              <select className="form-select" value={color} onChange={e => setColor(e.target.value)}>
                {SUPPORTED_COLORS.map(c => (
                  <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">{t('instructions')}</label>
            <textarea
              className="form-textarea"
              value={instructions}
              onChange={e => setInstructions(e.target.value)}
              placeholder="You are responsible for..."
              rows={8}
            />
            <p className="text-muted" style={{ fontSize: '12px', marginTop: '6px' }}>{t('agentInstructionsDesc')}</p>
          </div>

          <div className="form-group">
            <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Cpu size={14} className="text-primary" /> Skills
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '6px' }}>
              {availableSkills.map((s) => {
                const active = selectedSkills.includes(s.name);
                return (
                  <button
                    key={s.name}
                    type="button"
                    className={`btn ${active ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ fontSize: '12px', padding: '5px 12px', borderRadius: '16px' }}
                    onClick={() => {
                      setSelectedSkills(prev =>
                        active ? prev.filter(x => x !== s.name) : [...prev, s.name]
                      );
                    }}
                  >
                    {s.name}
                  </button>
                );
              })}
            </div>
            <p className="text-muted" style={{ fontSize: '12px', marginTop: '6px' }}>
              Select specialized capabilities and instructions for this agent.
            </p>
          </div>

          <div className="form-group">
            <label className="form-label">{t('delegatesTo')}</label>
            <input
              type="text"
              className="form-input"
              value={delegatesTo}
              onChange={e => setDelegatesTo(e.target.value)}
              placeholder="e.g. writer, reviewer (comma separated)"
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">{t('providerOptional')}</label>
              <select className="form-select" value={provider} onChange={e => setProvider(e.target.value)}>
                <option value="">{t('teamDefault')}</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Google Gemini</option>
                <option value="ollama">Ollama</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">{t('modelOptional')}</label>
              <input
                type="text"
                className="form-input"
                value={model}
                onChange={e => setModel(e.target.value)}
                placeholder="e.g. gpt-4"
              />
            </div>
          </div>
        </div>

        <div className="slide-over-footer">
          {initialData && (
            <button className="btn btn-danger" style={{ marginRight: 'auto' }} onClick={handleDelete} disabled={saving}>
              {confirmDelete ? t('confirmDelete') : t('deleteAgent')}
            </button>
          )}
          <button className="btn btn-secondary" onClick={onClose} disabled={saving}>{t('cancel')}</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={!name || !role || saving}>
            {saving ? t('saving') : t('saveAgent')}
          </button>
        </div>
      </div>
    </>
  );
}
