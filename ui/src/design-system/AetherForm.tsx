import React, { forwardRef } from 'react';

export interface AetherFormProps extends React.FormHTMLAttributes<HTMLFormElement> {
  children: React.ReactNode;
}

export const AetherForm = forwardRef<HTMLFormElement, AetherFormProps>(
  ({ className = '', children, onSubmit, ...props }, ref) => {
    return (
      <form
        ref={ref}
        className={`ds-form ${className}`}
        onSubmit={onSubmit}
        {...props}
      >
        {children}
      </form>
    );
  }
);

AetherForm.displayName = 'AetherForm';
