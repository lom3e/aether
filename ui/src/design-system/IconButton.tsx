import React, { forwardRef } from 'react';
import { LoadingSpinner } from './LoadingSpinner';

export type IconButtonVariant = 'ghost' | 'secondary' | 'primary' | 'destructive';
export type IconButtonSize = 'sm' | 'md' | 'lg';

export interface IconButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  icon: React.ReactNode;
  ariaLabel: string;
  variant?: IconButtonVariant;
  size?: IconButtonSize;
  loading?: boolean;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  (
    {
      icon,
      ariaLabel,
      variant = 'ghost',
      size = 'md',
      loading = false,
      disabled = false,
      className = '',
      ...props
    },
    ref
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        type={props.type || 'button'}
        disabled={isDisabled}
        aria-label={ariaLabel}
        title={props.title || ariaLabel}
        className={`ds-icon-btn ds-icon-btn--${size} ds-btn--${variant} ${className}`.trim()}
        {...props}
      >
        {loading ? <LoadingSpinner size="sm" /> : icon}
      </button>
    );
  }
);

IconButton.displayName = 'IconButton';
