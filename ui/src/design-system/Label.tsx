import React, { forwardRef } from 'react';

export interface LabelProps extends React.LabelHTMLAttributes<HTMLLabelElement> {
  required?: boolean;
  children: React.ReactNode;
}

export const Label = forwardRef<HTMLLabelElement, LabelProps>(
  ({ required = false, className = '', children, ...props }, ref) => {
    return (
      <label ref={ref} className={`ds-label ${className}`} {...props}>
        {children}
        {required && (
          <span className="ds-label-required" aria-hidden="true">
            *
          </span>
        )}
      </label>
    );
  }
);

Label.displayName = 'Label';
