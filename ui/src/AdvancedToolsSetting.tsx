import { useState } from 'react';
import { useTranslation } from './i18n';

/** Settings → General: the sidebar shows only what most people need; work queue, memory, system and team tools on request. */
export function AdvancedToolsSetting() {
  const { t } = useTranslation();
  const [on, setOn] = useState(() => { try { return localStorage.getItem('aether_show_advanced') === '1'; } catch { return false; } });
  const change = (v: boolean) => {
    setOn(v);
    try { localStorage.setItem('aether_show_advanced', v ? '1' : '0'); } catch { /* storage unavailable */ }
    window.dispatchEvent(new Event('aether-advanced-changed'));
  };
  return (
    <div className="card" style={{ padding: '24px' }} data-testid="advanced-tools-setting">
      <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', fontSize: '14px', cursor: 'pointer' }}>
        <span>
          <b style={{ display: 'block', fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>{t('advToolsTitle')}</b>
          <span className="text-muted" style={{ fontSize: '13px' }}>{t('advToolsDesc')}</span>
        </span>
        <input type="checkbox" role="switch" className="ui-switch" checked={on} onChange={e => change(e.target.checked)} data-testid="advanced-tools-toggle" />
      </label>
    </div>
  );
}
