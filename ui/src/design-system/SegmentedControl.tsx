import React from 'react';

export interface SegmentedOption<T extends string> {
  value: T;
  label: React.ReactNode;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
}

export interface SegmentedControlProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: SegmentedOption<T>[];
  className?: string;
  size?: 'sm' | 'md';
}

export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  className = '',
}: SegmentedControlProps<T>) {
  return (
    <div className={`ds-segmented-control ${className}`} role="tablist">
      {options.map((option) => {
        const isActive = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={`ds-segmented-item ${
              isActive ? 'ds-segmented-item--active' : ''
            }`}
            onClick={() => onChange(option.value)}
          >
            {option.icon && (
              <span style={{ display: 'inline-flex', alignItems: 'center' }} aria-hidden="true">
                {option.icon}
              </span>
            )}
            <span>{option.label}</span>
            {option.badge && (
              <span style={{ marginLeft: '4px', opacity: 0.8 }}>{option.badge}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
