import { useState, useEffect, useContext } from 'react';
import { ShoppingBag, Bot, Library, FileText, Layers, ArrowRight } from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';
import { TopHeader } from './TopHeader';
import { useTranslation } from './i18n';

export function Marketplace() {
  const { t } = useTranslation();
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
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <TopHeader
        title={t('marketplaceTitle')}
        icon={ShoppingBag}
        actions={
          <span className="badge badge-success" style={{ fontSize: '11px', padding: '4px 10px' }}>
            {t('alphaOfficialPresets')}
          </span>
        }
      />

      <div style={{ maxWidth: '1000px', margin: '32px auto', padding: '0 32px' }}>
        <p className="text-muted" style={{ fontSize: '15px', marginBottom: '28px' }}>
          {t('marketplaceSubtitle')}
        </p>

        <h2 style={{ marginBottom: '16px', fontSize: '18px' }}>{t('officialPresets')}</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '20px', marginBottom: '44px' }}>
          {presets.map(preset => (
            <div key={preset.id} className="card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Layers className="text-primary" size={22} />
                    <h3 style={{ margin: 0 }}>{preset.name}</h3>
                  </div>
                  <span className="badge badge-primary">{preset.agent_count} {preset.agent_count === 1 ? t('agentSingular') : t('agentPlural')}</span>
                </div>
                <p className="text-muted" style={{ fontSize: '14px', lineHeight: 1.5, marginBottom: '16px' }}>
                  {preset.description}
                </p>

                <div style={{ marginBottom: '16px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '6px' }}>
                    {t('includedAgentsRoles')}
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

                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginBottom: '20px' }}>
                  <strong>{t('navKnowledge')}:</strong> {preset.knowledge_packs.join(', ') || 'None'}
                </div>
              </div>

              <button
                className="btn btn-primary"
                onClick={() => handleInstallPreset(preset.id)}
                disabled={installingId === preset.id}
                style={{ width: '100%' }}
              >
                {installingId === preset.id ? t('installing') : t('installPreset')} <ArrowRight size={16} />
              </button>
            </div>
          ))}
        </div>

        <h2 style={{ marginBottom: '16px', fontSize: '18px' }}>{t('communityEcosystemComingSoon')}</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px', marginBottom: '48px' }}>
          <div className="card" style={{ opacity: 0.85, padding: '20px' }}>
            <Bot size={26} className="text-primary" style={{ marginBottom: '12px' }} />
            <h3 style={{ marginBottom: '6px', fontSize: '15px' }}>{t('communityAgentPacks')}</h3>
            <p className="text-muted" style={{ fontSize: '13px', lineHeight: 1.4 }}>{t('communityAgentPacksDesc')}</p>
          </div>

          <div className="card" style={{ opacity: 0.85, padding: '20px' }}>
            <Library size={26} className="text-primary" style={{ marginBottom: '12px' }} />
            <h3 style={{ marginBottom: '6px', fontSize: '15px' }}>{t('skillLibraries')}</h3>
            <p className="text-muted" style={{ fontSize: '13px', lineHeight: 1.4 }}>{t('skillLibrariesDesc')}</p>
          </div>

          <div className="card" style={{ opacity: 0.85, padding: '20px' }}>
            <FileText size={26} className="text-primary" style={{ marginBottom: '12px' }} />
            <h3 style={{ marginBottom: '6px', fontSize: '15px' }}>{t('knowledgePacks')}</h3>
            <p className="text-muted" style={{ fontSize: '13px', lineHeight: 1.4 }}>{t('knowledgePacksDesc')}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
