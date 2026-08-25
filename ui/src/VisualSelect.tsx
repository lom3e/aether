import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import {
  SUPPORTED_ICONS,
  SUPPORTED_COLORS,
  RenderIcon,
  getIdentityColor,
  type SupportedIcon,
  type SupportedColor,
} from './identity';

export function VisualIconSelect({
  value,
  onChange,
  label,
  disabled = false,
}: {
  value: string;
  onChange: (icon: string) => void;
  label?: string;
  disabled?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const currentIcon = (value && SUPPORTED_ICONS.includes(value as SupportedIcon)) ? value : 'Bot';

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  return (
    <div className="form-group" style={{ marginBottom: 0, position: 'relative' }} ref={dropdownRef}>
      {label && <label className="form-label" style={{ fontSize: '12px' }}>{label}</label>}
      <button
        type="button"
        className="form-input"
        disabled={disabled}
        onClick={() => !disabled && setIsOpen(!isOpen)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: disabled ? 'not-allowed' : 'pointer',
          height: '38px',
          padding: '8px 12px',
          background: 'hsl(var(--card))',
          textAlign: 'left',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: '24px',
              height: '24px',
              borderRadius: '6px',
              backgroundColor: 'hsl(var(--muted))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'hsl(var(--fg))',
            }}
          >
            <RenderIcon name={currentIcon} size={14} />
          </div>
          <span style={{ fontSize: '13px', fontWeight: 500 }}>{currentIcon}</span>
        </div>
        <ChevronDown size={14} className="text-muted" />
      </button>

      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 1000,
            maxHeight: '220px',
            overflowY: 'auto',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: '10px',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.25)',
            padding: '6px',
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '4px',
          }}
        >
          {SUPPORTED_ICONS.map((iconName) => {
            const isSelected = iconName === currentIcon;
            return (
              <button
                key={iconName}
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  onChange(iconName);
                  setIsOpen(false);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '6px 8px',
                  borderRadius: '6px',
                  backgroundColor: isSelected ? 'hsl(var(--primary)/0.15)' : 'transparent',
                  color: isSelected ? 'hsl(var(--primary))' : 'hsl(var(--fg))',
                  justifyContent: 'flex-start',
                  border: isSelected ? '1px solid hsl(var(--primary)/0.4)' : '1px solid transparent',
                  fontSize: '12px',
                  textAlign: 'left',
                }}
              >
                <RenderIcon name={iconName} size={14} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {iconName}
                </span>
                {isSelected && <Check size={12} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function VisualColorSelect({
  value,
  onChange,
  label,
  disabled = false,
}: {
  value: string;
  onChange: (color: string) => void;
  label?: string;
  disabled?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const currentColor = (value && SUPPORTED_COLORS.includes(value.toLowerCase() as SupportedColor)) ? value.toLowerCase() : 'violet';
  const colorTheme = getIdentityColor(currentColor);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  return (
    <div className="form-group" style={{ marginBottom: 0, position: 'relative' }} ref={dropdownRef}>
      {label && <label className="form-label" style={{ fontSize: '12px' }}>{label}</label>}
      <button
        type="button"
        className="form-input"
        disabled={disabled}
        onClick={() => !disabled && setIsOpen(!isOpen)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: disabled ? 'not-allowed' : 'pointer',
          height: '38px',
          padding: '8px 12px',
          background: 'hsl(var(--card))',
          textAlign: 'left',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: '18px',
              height: '18px',
              borderRadius: '50%',
              backgroundColor: colorTheme.text,
              border: `2px solid ${colorTheme.border}`,
              flexShrink: 0,
            }}
          />
          <span style={{ fontSize: '13px', fontWeight: 500, textTransform: 'capitalize' }}>
            {currentColor}
          </span>
        </div>
        <ChevronDown size={14} className="text-muted" />
      </button>

      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 1000,
            maxHeight: '220px',
            overflowY: 'auto',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: '10px',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.25)',
            padding: '6px',
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '4px',
          }}
        >
          {SUPPORTED_COLORS.map((cName) => {
            const isSelected = cName === currentColor;
            const cTheme = getIdentityColor(cName);
            return (
              <button
                key={cName}
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  onChange(cName);
                  setIsOpen(false);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '6px 8px',
                  borderRadius: '6px',
                  backgroundColor: isSelected ? 'hsl(var(--primary)/0.15)' : 'transparent',
                  color: isSelected ? 'hsl(var(--primary))' : 'hsl(var(--fg))',
                  justifyContent: 'flex-start',
                  border: isSelected ? '1px solid hsl(var(--primary)/0.4)' : '1px solid transparent',
                  fontSize: '12px',
                  textTransform: 'capitalize',
                  textAlign: 'left',
                }}
              >
                <div
                  style={{
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    backgroundColor: cTheme.text,
                    border: `1px solid ${cTheme.border}`,
                    flexShrink: 0,
                  }}
                />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {cName}
                </span>
                {isSelected && <Check size={12} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
