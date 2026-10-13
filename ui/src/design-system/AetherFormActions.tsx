import React from 'react';

export interface AetherFormActionsProps {
  align?: 'right' | 'left' | 'between';
  children: React.ReactNode;
  className?: string;
}

export function AetherFormActions({
  align = 'right',
  children,
  className = '',
}: AetherFormActionsProps) {
  const justifyStyle =
    align === 'left' ? 'flex-start' : align === 'between' ? 'space-between' : 'flex-end';

  return (
    <div
      className={`ds-form-actions ${className}`}
      style={{ justifyContent: justifyStyle }}
    >
      {children}
    </div>
  );
}
