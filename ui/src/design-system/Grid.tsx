import React, { forwardRef } from 'react';
import { tokens } from './tokens';

export interface GridProps extends React.HTMLAttributes<HTMLDivElement> {
  cols?: number | string;
  minItemWidth?: string | number;
  gap?: keyof typeof tokens.spacing | number;
  children: React.ReactNode;
}

export const Grid = forwardRef<HTMLDivElement, GridProps>(
  ({ cols, minItemWidth, gap = 'lg', className = '', style, children, ...props }, ref) => {
    const gapValue = typeof gap === 'number' ? `${gap}px` : tokens.spacing[gap] || tokens.spacing.lg;

    let gridTemplateColumns: string | undefined;
    if (minItemWidth) {
      const minWidth = typeof minItemWidth === 'number' ? `${minItemWidth}px` : minItemWidth;
      gridTemplateColumns = `repeat(auto-fill, minmax(min(${minWidth}, 100%), 1fr))`;
    } else if (typeof cols === 'number') {
      gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
    } else if (typeof cols === 'string') {
      gridTemplateColumns = cols;
    }

    return (
      <div
        ref={ref}
        className={`ds-grid ${className}`}
        style={{
          display: 'grid',
          gap: gapValue,
          gridTemplateColumns,
          ...style,
        }}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Grid.displayName = 'Grid';
