import React from 'react';
import { AlertCircle } from 'lucide-react';

export interface AetherFormErrorProps {
  id?: string;
  children: React.ReactNode;
  className?: string;
}

export function AetherFormError({ id, children, className = '' }: AetherFormErrorProps) {
  if (!children) return null;
  return (
    <div id={id} className={`ds-form-error ${className}`} role="alert" aria-live="polite">
      <AlertCircle size={14} style={{ flexShrink: 0 }} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}
