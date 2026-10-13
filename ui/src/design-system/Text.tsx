import { forwardRef, type ElementType, type HTMLAttributes, type ReactNode } from 'react';

export interface TextProps extends HTMLAttributes<HTMLParagraphElement> {
  size?: 'xs' | 'sm' | 'base' | 'md' | 'lg';
  variant?: 'default' | 'muted' | 'primary' | 'success' | 'warning' | 'error';
  weight?: 'normal' | 'medium' | 'semibold' | 'bold';
  mono?: boolean;
  as?: ElementType;
  children: ReactNode;
}

const weightMap: Record<string, number> = {
  normal: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
};

export const Text = forwardRef<HTMLParagraphElement, TextProps>(
  (
    {
      size = 'base',
      variant = 'default',
      weight,
      mono = false,
      as = 'p',
      className = '',
      style,
      children,
      ...props
    },
    ref
  ) => {
    const Component = as;
    const variantClass = variant !== 'default' ? `ds-text--${variant}` : '';
    const sizeClass = `ds-text--${size}`;
    const monoClass = mono ? 'ds-text--mono' : '';

    return (
      <Component
        ref={ref}
        className={`ds-text ${sizeClass} ${variantClass} ${monoClass} ${className}`.trim()}
        style={{
          fontWeight: weight ? weightMap[weight] : undefined,
          ...style,
        }}
        {...props}
      >
        {children}
      </Component>
    );
  }
);

Text.displayName = 'Text';
