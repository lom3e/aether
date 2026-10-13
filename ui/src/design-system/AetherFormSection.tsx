import React from 'react';

export interface AetherFormSectionProps {
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function AetherFormSection({
  title,
  description,
  children,
  className = '',
}: AetherFormSectionProps) {
  return (
    <div className={`ds-form-section ${className}`}>
      {(title || description) && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
          {title && (
            <h4 className="ds-heading ds-heading--5" style={{ margin: 0 }}>
              {title}
            </h4>
          )}
          {description && (
            <p className="ds-text ds-text--muted ds-text--xs" style={{ margin: 0 }}>
              {description}
            </p>
          )}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {children}
      </div>
    </div>
  );
}
