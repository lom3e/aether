import React from 'react';

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  secondaryAction?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  secondaryAction,
  className = '',
}: EmptyStateProps) {
  return (
    <div className={`ds-empty-state ${className}`}>
      {icon && <div className="ds-empty-icon">{icon}</div>}
      <h3 className="ds-heading ds-heading--4" style={{ marginBottom: '6px' }}>
        {title}
      </h3>
      {description && (
        <p
          className="ds-text ds-text--muted ds-text--sm"
          style={{ maxWidth: '440px', marginBottom: action ? '20px' : 0 }}
        >
          {description}
        </p>
      )}
      {(action || secondaryAction) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  );
}
