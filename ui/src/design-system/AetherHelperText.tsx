import React from 'react';

export interface AetherHelperTextProps {
  id?: string;
  children: React.ReactNode;
  className?: string;
}

export function AetherHelperText({ id, children, className = '' }: AetherHelperTextProps) {
  if (!children) return null;
  return (
    <p id={id} className={`ds-helper-text ${className}`}>
      {children}
    </p>
  );
}
