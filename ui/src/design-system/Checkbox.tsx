import React from 'react';
import { Check } from 'lucide-react';

export interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: React.ReactNode;
  description?: React.ReactNode;
  disabled?: boolean;
  hasError?: boolean;
  className?: string;
}

export function Checkbox({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  hasError = false,
  className = '',
}: CheckboxProps) {
  const handleClick = () => {
    if (!disabled) {
      onChange(!checked);
    }
  };

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: description ? 'flex-start' : 'center',
        gap: '9px',
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
      onClick={handleClick}
      className={className}
    >
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        disabled={disabled}
        style={{
          width: '18px',
          height: '18px',
          borderRadius: '4px',
          border: `1.5px solid ${
            hasError
              ? 'hsl(var(--destructive))'
              : checked
              ? 'hsl(var(--primary))'
              : 'hsl(var(--border))'
          }`,
          backgroundColor: checked ? 'hsl(var(--primary))' : 'hsl(var(--card))',
          color: 'white',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: disabled ? 'not-allowed' : 'pointer',
          padding: 0,
          outline: 'none',
          transition: 'all 0.15s ease',
          opacity: disabled ? 0.5 : 1,
          flexShrink: 0,
          marginTop: description ? '2px' : 0,
        }}
      >
        {checked && <Check size={12} strokeWidth={3} />}
      </button>

      {(label || description) && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {label && (
            <span
              style={{
                fontSize: '13px',
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
