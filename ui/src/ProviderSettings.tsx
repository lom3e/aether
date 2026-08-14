import { useState, useEffect } from 'react';

export function ProviderSettings() {
  const [provider, setProvider] = useState('openai');
  const [model, setModel] = useState('gpt-4o');
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState<any>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch('http://localhost:8000/api/settings/provider')
      .then(res => res.json())
      .then(data => {
        setProvider(data.provider);
        setModel(data.model);
        setStatus(data.configured || {});
      })
      .catch(console.error);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('http://localhost:8000/api/settings/provider', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model, api_key: apiKey || null })
      });
      if (res.ok) {
        if (apiKey) {
          setStatus({ ...status, [provider]: true });
          setApiKey(''); // clear it
        }
        alert('Settings saved!');
      }
    } catch (e) {
      console.error(e);
      alert('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const isConfigured = status[provider];

  return (
    <div className="provider-settings">
      <h2>AI Provider Setup</h2>

      <div className="form-group">
        <label>Provider</label>
        <select value={provider} onChange={e => setProvider(e.target.value)}>
          <option value="openai">OpenAI (Default)</option>
          <option value="anthropic">Anthropic</option>
          <option value="gemini">Google Gemini</option>
          <option value="ollama">Ollama (Local)</option>
        </select>
      </div>

      <div className="form-group">
        <label>Model</label>
        <input
          type="text"
          value={model}
          onChange={e => setModel(e.target.value)}
          placeholder="e.g. gpt-4o"
        />
      </div>

      {provider !== 'ollama' && (
        <div className="form-group">
          <label>API Key {isConfigured && <span className="status-badge success">Configured</span>}</label>
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder={isConfigured ? '••••••••••••' : 'Enter API Key'}
          />
        </div>
      )}

      <button className="primary-button" onClick={handleSave} disabled={saving}>
        {saving ? 'Saving...' : 'Save Configuration'}
      </button>
    </div>
  );
}
