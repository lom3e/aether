import React, { forwardRef } from 'react';
import { tokens } from './tokens';

export interface StackProps extends React.HTMLAttributes<HTMLDivElement> {
  direction?: 'row' | 'column';
  gap?: keyof typeof tokens.spacing | number;
  align?: 'start' | 'center' | 'end' | 'stretch' | 'baseline';
  justify?: 'start' | 'center' | 'end' | 'between' | 'around' | 'evenly';
  wrap?: boolean;
  inline?: boolean;
  children: React.ReactNode;
}

const alignMap: Record<string, string> = {
  start: 'flex-start',
  center: 'center',
  end: 'flex-end',
  stretch: 'stretch',
  baseline: 'baseline',
};

const justifyMap: Record<string, string> = {
  start: 'flex-start',
  center: 'center',
  end: 'flex-end',
  between: 'space-between',
  around: 'space-around',
  evenly: 'space-evenly',
};

export const Stack = forwardRef<HTMLDivElement, StackProps>(
  (
    {
      direction = 'column',
      gap = 'md',
      align,
      justify,
      wrap = false,
      inline = false,
      className = '',
      style,
      children,
      ...props
    },
    ref
  ) => {
    const gapValue = typeof gap === 'number' ? `${gap}px` : tokens.spacing[gap] || tokens.spacing.md;

    return (
      <div
        ref={ref}
        className={`ds-stack ${className}`}
        style={{
          display: inline ? 'inline-flex' : 'flex',
          flexDirection: direction,
          gap: gapValue,
          alignItems: align ? alignMap[align] : undefined,
          justifyContent: justify ? justifyMap[justify] : undefined,
          flexWrap: wrap ? 'wrap' : 'nowrap',
          ...style,
        }}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Stack.displayName = 'Stack';
