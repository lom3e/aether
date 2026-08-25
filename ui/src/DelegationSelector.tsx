import { Check, Plus, Users } from 'lucide-react';
import { IdentityBadge } from './identity';
import { useTranslation } from './i18n';

export interface DelegationCandidate {
  name: string;
  role?: string;
  icon?: string | null;
  color?: string | null;
}

export function DelegationSelector({
  currentAgentName,
  availableAgents,
  delegatesTo,
  onChange,
  label,
  hint,
  disabled = false,
}: {
  currentAgentName?: string;
  availableAgents: (string | DelegationCandidate)[];
  delegatesTo: string[];
  onChange: (delegatesTo: string[]) => void;
  label?: string;
  hint?: string;
  disabled?: boolean;
}) {
  const { t } = useTranslation();

  // Normalize candidates
  const normalizedCandidates: DelegationCandidate[] = availableAgents
    .map(agent => (typeof agent === 'string' ? { name: agent } : agent))
    .filter(agent => agent.name && agent.name.trim() && agent.name.trim() !== (currentAgentName || '').trim());

  const toggleDelegation = (targetName: string) => {
    if (disabled) return;
    const isDelegated = delegatesTo.includes(targetName);
    if (isDelegated) {
      onChange(delegatesTo.filter(name => name !== targetName));
    } else {
      onChange([...delegatesTo, targetName]);
    }
  };

  return (
    <div className="form-group" style={{ marginBottom: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
        <label className="form-label" style={{ fontSize: '12px', marginBottom: 0 }}>
          {label || t('delegatesTo') || 'Delega a:'}
        </label>
        {hint && <span className="text-muted" style={{ fontSize: '11px' }}>{hint}</span>}
      </div>

      {normalizedCandidates.length > 0 ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {normalizedCandidates.map(candidate => {
            const isDelegated = delegatesTo.includes(candidate.name);
            return (
              <button
                key={candidate.name}
                type="button"
                disabled={disabled}
                onClick={() => toggleDelegation(candidate.name)}
                className={`card card-interactive`}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '6px 10px',
                  borderRadius: '8px',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  border: isDelegated
                    ? '1.5px solid hsl(var(--primary))'
                    : '1px solid hsl(var(--border))',
                  backgroundColor: isDelegated
                    ? 'hsl(var(--primary)/0.12)'
                    : 'hsl(var(--card))',
                  transition: 'all 0.15s ease',
                  fontSize: '12px',
                  fontWeight: isDelegated ? 600 : 500,
                  color: isDelegated ? 'hsl(var(--primary))' : 'hsl(var(--fg))',
                }}
              >
                <IdentityBadge
                  icon={candidate.icon || 'Bot'}
                  color={candidate.color || 'violet'}
                  size={12}
                  containerSize={20}
                />
                <span>{candidate.name}</span>
                {isDelegated ? (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: '16px',
                      height: '16px',
                      borderRadius: '50%',
                      backgroundColor: 'hsl(var(--primary))',
                      color: 'hsl(var(--primary-fg))',
                      fontSize: '10px',
                    }}
                  >
                    <Check size={10} />
                  </span>
                ) : (
                  <span className="text-muted" style={{ fontSize: '11px' }}>
                    <Plus size={12} />
                  </span>
                )}
              </button>
            );
          })}
        </div>
      ) : (
        <div
          style={{
            padding: '10px 14px',
            borderRadius: '8px',
            backgroundColor: 'hsl(var(--muted)/0.4)',
            border: '1px dashed hsl(var(--border))',
            fontSize: '12px',
            color: 'hsl(var(--muted-fg))',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <Users size={14} className="text-muted" />
          <span>{t('noOtherAgentsForDelegation') || 'Nessun altro agente registrato nella squadra a cui delegare.'}</span>
        </div>
      )}
    </div>
  );
}
