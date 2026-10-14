import { useState, useEffect, useCallback } from 'react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { Sparkles, Sliders, RotateCw } from 'lucide-react';

export const CURATED_PROVIDER_MODELS: Record<string, string[]> = {
  ollama: ['qwen3.5:9b', 'qwen3.5:14b', 'qwen3.5:0.8b', 'llama3.3:70b', 'llama3.2:3b', 'deepseek-r1:8b', 'mistral', 'phi4'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'o3-mini', 'gpt-4-turbo'],
  anthropic: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
  gemini: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
  groq: ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768', 'gemma2-9b-it'],
};

export const FEATURED_GROQ_MODELS = [
  'llama-3.3-70b-versatile',
  'llama-3.1-8b-instant',
];

export interface ModelSelectorProps {
  provider: string;
  value: string | null;
  teamDefaultModel: string;
  onChange: (model: string | null) => void;
  apiKey?: string;
  isTeamLevel?: boolean;
  disabled?: boolean;
  className?: string;
  showBadge?: boolean;
  label?: string;
}

export function ModelSelector({
  provider,
  value,
  teamDefaultModel,
  onChange,
  apiKey,
  isTeamLevel = false,
  disabled = false,
  className = '',
  showBadge = true,
  label,
}: ModelSelectorProps) {
  const { t } = useTranslation();
  const [availableModels, setAvailableModels] = useState<string[]>(
    CURATED_PROVIDER_MODELS[provider] || []
  );
  const [loadingModels, setLoadingModels] = useState(false);
  const [customInputMode, setCustomInputMode] = useState(false);
  const [customValue, setCustomValue] = useState('');

  const [modelsSource, setModelsSource] = useState<string>('curated_local');
  const [modelsError, setModelsError] = useState<string | null>(null);

  const loadModels = useCallback((prov: string, key?: string) => {
    setLoadingModels(true);
    setModelsError(null);
    // An API key is NEVER placed in the URL (it would leak into logs and browser history): POST it in the body.
    const hasKey = !!(key && key.trim());
    const request = hasKey
      ? fetch(apiUrl('/api/settings/provider/models'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: prov, api_key: (key as string).trim() }),
        })
      : fetch(apiUrl(`/api/settings/provider/models?provider=${encodeURIComponent(prov)}`));

    request
      .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          // A real failure is shown, not hidden behind a default list that looks live.
          throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`);
        }
        return data;
      })
      .then(data => {
        if (data.models && Array.isArray(data.models) && data.models.length > 0) {
          setAvailableModels(data.models);
          setModelsSource(data.source || (data.live ? 'live' : 'curated_local'));
        } else {
          setAvailableModels(data.live ? [] : (CURATED_PROVIDER_MODELS[prov] || []));
          setModelsSource(data.live ? 'live' : 'curated_local');
        }
      })
      .catch((err: Error) => {
        setAvailableModels(CURATED_PROVIDER_MODELS[prov] || []);
        setModelsSource('curated_local');
        setModelsError(err.message);
      })
      .finally(() => {
        setLoadingModels(false);
      });
  }, []);

  useEffect(() => {
    // No provider chosen: there is nothing to list, and nothing may be contacted (never assume a local one).
    if (!provider) {
      setAvailableModels([]);
      setModelsSource('curated_local');
      setModelsError(null);
      setLoadingModels(false);
      return;
    }
    loadModels(provider, apiKey);
  }, [provider, apiKey, loadModels]);

  // Determine effective value
  const isInheriting = !isTeamLevel && (value === null || value === undefined || value === '');

  const displayList = [...availableModels];
  if (value && !isInheriting && !displayList.includes(value)) {
    displayList.push(value);
  }

  const isGroq = provider === 'groq';
  const groqFeatured = isGroq ? displayList.filter(m => FEATURED_GROQ_MODELS.includes(m)) : [];
  const groqOthers = isGroq ? displayList.filter(m => !FEATURED_GROQ_MODELS.includes(m)) : [];

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    if (val === '__custom__') {
      setCustomInputMode(true);
      setCustomValue('');
    } else if (val === '__inherit__' || val === '') {
      setCustomInputMode(false);
      onChange(null);
    } else {
      setCustomInputMode(false);
      onChange(val);
    }
  };

  const handleCustomBlur = () => {
    const trimmed = customValue.trim();
    if (!trimmed) {
      setCustomInputMode(false);
      onChange(null);                         // emptied: no hidden default model, the caller asks for a real choice
    } else {
      onChange(trimmed);
    }
  };

  return (
    <div className={`model-selector-container ${className}`} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {label && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label className="form-label" style={{ marginBottom: 0, fontWeight: 600, fontSize: '13px' }}>
              {label}
            </label>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ padding: '2px 6px', height: 'auto', display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}
              onClick={() => provider && loadModels(provider, apiKey)}
              disabled={loadingModels}
              title={loadingModels ? t('syLoadingModels') : t('syReloadTheLiveModelList')}
            >
              <RotateCw size={12} className={loadingModels ? 'animate-spin' : ''} />
              {loadingModels ? 'Aggiornamento...' : 'Ricarica'}
            </button>
            {!loadingModels && modelsSource !== 'live' && (
              <span
                title={modelsError || t('syDefaultListNotVerifiedWithThe')}
                style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))' }}
              >
                {modelsError ? t('syUnverifiedList') + modelsError.slice(0, 60) : t('syDefaultListUnverified')}
              </span>
            )}
          </div>
          {showBadge && !isTeamLevel && (
            <span
              style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '10px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                backgroundColor: isInheriting ? 'hsl(var(--secondary))' : 'hsl(var(--primary) / 0.15)',
                color: isInheriting ? 'hsl(var(--muted-fg))' : 'hsl(var(--primary))',
                border: `1px solid ${isInheriting ? 'hsl(var(--border))' : 'hsl(var(--primary) / 0.3)'}`,
              }}
            >
              {isInheriting ? (
                <>
                  <Sparkles size={11} />
                  {t('inheritedFromTeamBadge') || 'Ereditato (Team)'}
                </>
              ) : (
                <>
                  <Sliders size={11} />
                  {t('customOverrideBadge') || 'Override'}: {value}
                </>
              )}
            </span>
          )}
        </div>
      )}

      {customInputMode ? (
        <div style={{ display: 'flex', gap: '6px' }}>
          <input
            type="text"
            className="form-input"
            autoFocus
            placeholder={isGroq ? "e.g. llama-3.3-70b-versatile or custom-model" : "e.g. qwen3.5:14b or custom-model"}
            value={customValue}
            onChange={e => setCustomValue(e.target.value)}
            onBlur={handleCustomBlur}
            onKeyDown={e => {
              if (e.key === 'Enter') handleCustomBlur();
              if (e.key === 'Escape') setCustomInputMode(false);
            }}
            disabled={disabled}
            style={{ fontSize: '13px' }}
          />
          <button
            type="button"
            className="btn btn-secondary"
            style={{ fontSize: '12px', padding: '0 10px' }}
            onClick={() => setCustomInputMode(false)}
          >
            Annulla
          </button>
        </div>
      ) : (
        <select
          className="form-select"
          value={isInheriting ? '__inherit__' : (value || '')}
          onChange={handleSelectChange}
          disabled={disabled}
          style={{
            fontSize: '13px',
            borderColor: !isInheriting && !isTeamLevel ? 'hsl(var(--primary) / 0.5)' : undefined,
          }}
        >
          {isTeamLevel && (
            // Without this the browser shows the first model as if it were selected while nothing is chosen.
            <option value="" disabled>{provider ? t('syChooseAModel') : t('syChooseAProviderFirst')}</option>
          )}
          {!isTeamLevel && (
            <option value="__inherit__">
              ✨ {t('inheritFromTeam') || t('syInheritFromTheTeam')} ({teamDefaultModel || 'Default'})
            </option>
          )}

          {isGroq ? (
            <>
              {groqFeatured.length > 0 && (
                <optgroup label={t('syFeaturedGroqModels')}>
                  {groqFeatured.map(m => (
                    <option key={m} value={m}>
                      {m === 'llama-3.3-70b-versatile'
                        ? '⭐ llama-3.3-70b-versatile (Consigliato / Versatile)'
                        : m === 'llama-3.1-8b-instant'
                        ? '⚡ llama-3.1-8b-instant (Ultra-Veloce)'
                        : m}
                      {m === teamDefaultModel && !isTeamLevel ? t('sySameAsTheTeam') : ''}
                    </option>
                  ))}
                </optgroup>
              )}
              {groqOthers.length > 0 && (
                <optgroup label={t('syOtherAvailableGroqModels')}>
                  {groqOthers.map(m => (
                    <option key={m} value={m}>
                      {m} {m === teamDefaultModel && !isTeamLevel ? t('sySameAsTheTeam') : ''}
                    </option>
                  ))}
                </optgroup>
              )}
            </>
          ) : (
            <optgroup label={t('syAvailableModels')}>
              {displayList.map(m => (
                <option key={m} value={m}>
                  {m} {m === teamDefaultModel && !isTeamLevel ? t('sySameAsTheTeam') : ''}
                </option>
              ))}
            </optgroup>
          )}

          <option value="__custom__">{t('syOtherCustomModelTypeOrPaste')}</option>
        </select>
      )}

      {showBadge && !label && !isTeamLevel && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
          <span
            style={{
              fontSize: '11px',
              fontWeight: 500,
              padding: '1px 6px',
              borderRadius: '6px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              backgroundColor: isInheriting ? 'hsl(var(--secondary))' : 'hsl(var(--primary) / 0.15)',
              color: isInheriting ? 'hsl(var(--muted-fg))' : 'hsl(var(--primary))',
            }}
          >
            {isInheriting ? (
              <>
                <Sparkles size={10} />
                {t('inheritedFromTeamBadge') || t('syInheritedFromTheTeam')}: {teamDefaultModel || 'Default'}
              </>
            ) : (
              <>
                <Sliders size={10} />
                {t('customOverrideBadge') || t('syExplicitOverride')}: {value}
              </>
            )}
          </span>
        </div>
      )}
    </div>
  );
}
