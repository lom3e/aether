import { useState, useEffect } from 'react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { Sparkles, Sliders } from 'lucide-react';

export const CURATED_PROVIDER_MODELS: Record<string, string[]> = {
  ollama: ['qwen3.5:9b', 'qwen3.5:14b', 'qwen3.5:0.8b', 'llama3.3:70b', 'llama3.2:3b', 'deepseek-r1:8b', 'mistral', 'phi4'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'o3-mini', 'gpt-4-turbo'],
  anthropic: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
  gemini: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
};

export interface ModelSelectorProps {
  provider: string;
  value: string | null;
  teamDefaultModel: string;
  onChange: (model: string | null) => void;
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
  const [customInputMode, setCustomInputMode] = useState(false);
  const [customValue, setCustomValue] = useState('');

  useEffect(() => {
    let isMounted = true;
    const prov = provider || 'ollama';
    fetch(apiUrl(`/api/settings/provider/models?provider=${encodeURIComponent(prov)}`))
      .then(res => res.json())
      .then(data => {
        if (!isMounted) return;
        if (data.models && Array.isArray(data.models) && data.models.length > 0) {
          setAvailableModels(data.models);
        } else {
          setAvailableModels(CURATED_PROVIDER_MODELS[prov] || []);
        }
      })
      .catch(() => {
        if (isMounted) {
          setAvailableModels(CURATED_PROVIDER_MODELS[prov] || []);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [provider]);

  // Determine effective value
  const isInheriting = !isTeamLevel && (value === null || value === undefined || value === '');

  const displayList = [...availableModels];
  if (value && !isInheriting && !displayList.includes(value)) {
    displayList.push(value);
  }

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
      onChange(isTeamLevel ? availableModels[0] || 'qwen3.5:9b' : null);
    } else {
      onChange(trimmed);
    }
  };

  return (
    <div className={`model-selector-container ${className}`} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {label && (
        <label className="form-label" style={{ marginBottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>{label}</span>
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
        </label>
      )}

      {customInputMode ? (
        <div style={{ display: 'flex', gap: '6px' }}>
          <input
            type="text"
            className="form-input"
            autoFocus
            placeholder="e.g. qwen3.5:14b or custom-model"
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
          {!isTeamLevel && (
            <option value="__inherit__">
              ✨ {t('inheritFromTeam') || 'Eredita dal Team'} ({teamDefaultModel || 'Default'})
            </option>
          )}

          <optgroup label="Modelli Disponibili">
            {displayList.map(m => (
              <option key={m} value={m}>
                {m} {m === teamDefaultModel && !isTeamLevel ? ' (Uguale al Team)' : ''}
              </option>
            ))}
          </optgroup>

          <option value="__custom__">➕ Altro modello personalizzato...</option>
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
                {t('inheritedFromTeamBadge') || 'Ereditato dal Team'}: {teamDefaultModel || 'Default'}
              </>
            ) : (
              <>
                <Sliders size={10} />
                {t('customOverrideBadge') || 'Override Esplicito'}: {value}
              </>
            )}
          </span>
        </div>
      )}
    </div>
  );
}
