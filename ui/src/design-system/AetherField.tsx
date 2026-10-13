import React, { useId } from 'react';
import { Label } from './Label';
import { AetherHelperText } from './AetherHelperText';
import { AetherFormError } from './AetherFormError';

export interface AetherFieldProps {
  id?: string;
  label?: React.ReactNode;
  required?: boolean;
  helperText?: React.ReactNode;
  error?: React.ReactNode;
  className?: string;
  children:
    | React.ReactNode
    | ((props: {
        id: string;
        'aria-describedby'?: string;
        hasError: boolean;
      }) => React.ReactNode);
}

export function AetherField({
  id: explicitId,
  label,
  required = false,
  helperText,
  error,
  className = '',
  children,
}: AetherFieldProps) {
  const generatedId = useId();
  const id = explicitId || generatedId;
  const helperId = helperText ? `${id}-helper` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, helperId].filter(Boolean).join(' ') || undefined;
  const hasError = Boolean(error);

  return (
    <div className={`ds-field ${className}`}>
      {label && (
        <Label htmlFor={id} required={required}>
          {label}
        </Label>
      )}

      {typeof children === 'function'
        ? children({ id, 'aria-describedby': describedBy, hasError })
        : React.isValidElement(children)
        ? React.cloneElement(children as React.ReactElement<any>, {
            id: (children.props as any).id || id,
            'aria-describedby': (children.props as any)['aria-describedby'] || describedBy,
            hasError: (children.props as any).hasError !== undefined ? (children.props as any).hasError : hasError,
          })
        : children}

      {error ? (
        <AetherFormError id={errorId}>{error}</AetherFormError>
      ) : helperText ? (
        <AetherHelperText id={helperId}>{helperText}</AetherHelperText>
      ) : null}
    </div>
  );
}
