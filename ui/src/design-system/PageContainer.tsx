import React, { forwardRef } from 'react';

export interface PageContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  children: React.ReactNode;
}

export const PageContainer = forwardRef<HTMLDivElement, PageContainerProps>(
  ({ size = 'lg', className = '', style, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`ds-page-container ds-page-container--${size} ${className}`}
        style={style}
        {...props}
      >
        {children}
      </div>
    );
  }
);

PageContainer.displayName = 'PageContainer';
