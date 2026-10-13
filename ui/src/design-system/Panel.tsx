import React, { forwardRef } from 'react';

export interface PanelProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'elevated' | 'interactive';
  header?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
}

export const Panel = forwardRef<HTMLDivElement, PanelProps>(
  ({ variant = 'default', header, footer, className = '', style, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`ds-panel ds-panel--${variant} ${className}`}
        style={style}
        {...props}
      >
        {header && <div className="ds-panel-header">{header}</div>}
        <div className="ds-panel-body">{children}</div>
        {footer && <div className="ds-panel-footer">{footer}</div>}
      </div>
    );
  }
);

Panel.displayName = 'Panel';
