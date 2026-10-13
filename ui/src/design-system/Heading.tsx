import { forwardRef, type ElementType, type HTMLAttributes, type ReactNode } from 'react';

export type HeadingLevel = 1 | 2 | 3 | 4 | 5 | 6;

export interface HeadingProps extends HTMLAttributes<HTMLHeadingElement> {
  level?: HeadingLevel;
  as?: ElementType;
  children: ReactNode;
}

export const Heading = forwardRef<HTMLHeadingElement, HeadingProps>(
  ({ level = 2, as, className = '', style, children, ...props }, ref) => {
    const Component = as || (`h${level}` as ElementType);

    return (
      <Component
        ref={ref}
        className={`ds-heading ds-heading--${level} ${className}`}
        style={style}
        {...props}
      >
        {children}
      </Component>
    );
  }
);

Heading.displayName = 'Heading';
