import { useState, useContext } from 'react';
import { X, Bot } from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';

export function AgentBuilder({
  onClose,
  onSave,
  initialData
}: {
  onClose: () => void,
  onSave: () => void,
  initialData?: any
}) {
  const [name, setName] = useState(initialData?.name || '');
  const [role, setRole] = useState(initialData?.role || '');
  const [instructions, setInstructions] = useState(initialData?.description || '');
  const [provider, setProvider] = useState(initialData?.provider || '');
  const [model, setModel] = useState(initialData?.model || '');
  const [delegatesTo, setDelegatesTo] = useState((initialData?.delegates_to || []).join(', '));
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const showToast = useContext(ToastContext);

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
          instructions: instructions || null,
          provider: provider || null,
          model: model || null,
          skills: [],
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
            {initialData ? 'Edit Agent' : 'Create Agent'}
          </div>
          <button className="btn btn-ghost" style={{ padding: '8px' }} onClick={onClose} disabled={saving}>
            <X size={20} />
          </button>
        </div>

        <div className="slide-over-body">
          <div className="form-group">
            <label className="form-label">Name</label>
            <input
              type="text"
              className="form-input"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Researcher"
            />
          </div>

          <div className="form-group">
            <label className="form-label">Role</label>
            <input
              type="text"
              className="form-input"
              value={role}
              onChange={e => setRole(e.target.value)}
              placeholder="e.g. Research and analyze data"
            />
          </div>

          <div className="form-group">
            <label className="form-label">Instructions</label>
            <textarea
              className="form-textarea"
              value={instructions}
              onChange={e => setInstructions(e.target.value)}
              placeholder="You are responsible for..."
              rows={8}
            />
            <p className="text-muted" style={{ fontSize: '12px', marginTop: '6px' }}>Detailed instructions shape the agent's behavior and constraints.</p>
          </div>

          <div className="form-group">
            <label className="form-label">Delegates To</label>
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
              <label className="form-label">Provider (Optional)</label>
              <select className="form-select" value={provider} onChange={e => setProvider(e.target.value)}>
                <option value="">Team Default</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Google Gemini</option>
                <option value="ollama">Ollama</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Model (Optional)</label>
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
              {confirmDelete ? 'Confirm delete' : 'Delete Agent'}
            </button>
          )}
          <button className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={!name || !role || saving}>
            {saving ? 'Saving...' : 'Save Agent'}
          </button>
        </div>
      </div>
    </>
  );
}
