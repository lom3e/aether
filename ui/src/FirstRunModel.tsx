import { useCallback, useContext, useEffect, useState } from 'react';
import { apiUrl } from './api';
import { ToastContext } from './toast';
import { useTranslation } from './i18n';

const PROVIDERS: { id: string; label: string; model: string }[] = [
  { id: 'groq', label: 'Groq', model: 'llama-3.3-70b-versatile' },
  { id: 'openai', label: 'OpenAI', model: 'gpt-4o-mini' },
  { id: 'anthropic', label: 'Anthropic', model: 'claude-sonnet-5-5' },
  { id: 'gemini', label: 'Gemini', model: 'gemini-2.0-flash' },
];

/**
 * First launch: Aether has its personal space but no model yet. One calm card on Home asks for a provider and a key (stored
 * in the encrypted vault by the existing settings route) and disappears once a model is configured. Nothing is sent anywhere
 * until the user presses Save.
 */
export function FirstRunModel({ onDone }: { onDone?: () => void }) {
  const { t } = useTranslation();
  const toast = useContext(ToastContext);
  const [needed, setNeeded] = useState(false);
  const [provider, setProvider] = useState('groq');
  const [model, setModel] = useState(PROVIDERS[0].model);
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);

  const check = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/settings/provider'));
      if (!res.ok) return;
      const d = await res.json();
      const c = d.configured || {};
      setNeeded(!d.provider && !(c.openai || c.anthropic || c.gemini || c.groq));
    } catch {
      /* no card if we cannot tell */
    }
  }, []);
  useEffect(() => { void check(); }, [check]);
  if (!needed) return null;

  const save = async () => {
    if (!key.trim() || !model.trim()) return;
    setBusy(true);
    try {
      const res = await fetch(apiUrl('/api/settings/provider'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider, model: model.trim(), api_key: key.trim(), apply_to_all_agents: true }) });
      if (!res.ok) throw new Error(String(res.status));
      setKey('');
      setNeeded(false);
      toast(t('frmSaved'), 'success');
      onDone?.();
    } catch {
      toast(t('frmFailed'), 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="frm" data-testid="first-run-model">
      <h3>{t('frmTitle')}</h3>
      <p>{t('frmDesc')}</p>
      <div className="frm-row">
        <select aria-label={t('frmProvider')} value={provider} onChange={e => { setProvider(e.target.value); setModel(PROVIDERS.find(p => p.id === e.target.value)?.model || ''); }} data-testid="frm-provider">
          {PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        <input aria-label={t('frmModel')} value={model} onChange={e => setModel(e.target.value)} data-testid="frm-model" />
      </div>
      <div className="frm-row">
        <input type="password" autoComplete="off" spellCheck={false} aria-label={t('frmKey')} placeholder={t('frmKey')} value={key} onChange={e => setKey(e.target.value)} data-testid="frm-key" />
        <button className="btn btn-primary" disabled={busy || !key.trim()} onClick={save} data-testid="frm-save">{t('frmSave')}</button>
      </div>
      <small>{t('frmNote')}</small>
    </div>
  );
}
