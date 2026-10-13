import React from 'react';

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  ariaLabel?: string;
  label?: React.ReactNode;
  description?: React.ReactNode;
  className?: string;
}

export function Switch({
  checked,
  onChange,
  disabled = false,
  ariaLabel,
  label,
  description,
  className = '',
}: SwitchProps) {
  const handleToggle = () => {
    if (!disabled) {
      onChange(!checked);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      onChange(!checked);
    }
  };

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: description ? 'flex-start' : 'center',
        gap: '10px',
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
      onClick={handleToggle}
      className={className}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={ariaLabel || (typeof label === 'string' ? label : undefined)}
        disabled={disabled}
        onKeyDown={handleKeyDown}
        className={`ds-switch ${checked ? 'ds-switch--checked' : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          handleToggle();
        }}
      >
        <span className="ds-switch-thumb" />
      </button>

      {(label || description) && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {label && (
            <span
              style={{
                fontSize: '13.5px',
                fontWeight: 500,
                color: 'hsl(var(--fg))',
                opacity: disabled ? 0.5 : 1,
              }}
            >
              {label}
            </span>
          )}
          {description && (
            <span
              style={{
                fontSize: '12px',
                color: 'hsl(var(--muted-fg))',
                opacity: disabled ? 0.5 : 1,
              }}
            >
              {description}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
