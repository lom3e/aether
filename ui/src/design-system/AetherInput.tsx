import React, { forwardRef } from 'react';

export interface AetherInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  hasError?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  rightElement?: React.ReactNode;
}

export const AetherInput = forwardRef<HTMLInputElement, AetherInputProps>(
  (
    {
      hasError = false,
      leftIcon,
      rightIcon,
      rightElement,
      className = '',
      ...props
    },
    ref
  ) => {
    const hasLeft = Boolean(leftIcon);
    const hasRight = Boolean(rightIcon || rightElement);

    const inputElement = (
      <input
        ref={ref}
        className={`ds-input ${hasError ? 'ds-input--error' : ''} ${
          hasLeft ? 'ds-input--has-left-icon' : ''
        } ${hasRight ? 'ds-input--has-right-icon' : ''} ${className}`.trim()}
        aria-invalid={hasError ? 'true' : undefined}
        {...props}
      />
    );

    if (!hasLeft && !hasRight) {
      return inputElement;
    }

    return (
      <div className="ds-input-wrapper">
        {leftIcon && <span className="ds-input-icon-left">{leftIcon}</span>}
        {inputElement}
        {rightElement ? (
          <span className="ds-input-icon-right ds-input-icon-right--clickable">
            {rightElement}
          </span>
        ) : rightIcon ? (
          <span className="ds-input-icon-right">{rightIcon}</span>
        ) : null}
      </div>
    );
  }
);

AetherInput.displayName = 'AetherInput';
