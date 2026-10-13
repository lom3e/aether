import React, { forwardRef } from 'react';

export interface AetherTextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  hasError?: boolean;
}

export const AetherTextarea = forwardRef<HTMLTextAreaElement, AetherTextareaProps>(
  ({ hasError = false, className = '', ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={`ds-textarea ${hasError ? 'ds-textarea--error' : ''} ${className}`}
        aria-invalid={hasError ? 'true' : undefined}
        {...props}
      />
    );
  }
);

AetherTextarea.displayName = 'AetherTextarea';
