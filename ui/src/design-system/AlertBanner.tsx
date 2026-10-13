import React from 'react';
import { Info, CheckCircle2, AlertTriangle, AlertCircle, X } from 'lucide-react';

export type AlertBannerVariant = 'info' | 'success' | 'warning' | 'error';

export interface AlertBannerProps {
  variant?: AlertBannerVariant;
  title?: React.ReactNode;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  onDismiss?: () => void;
  children: React.ReactNode;
  className?: string;
}

const defaultIcons = {
  info: <Info size={18} />,
  success: <CheckCircle2 size={18} />,
  warning: <AlertTriangle size={18} />,
  error: <AlertCircle size={18} />,
};

export function AlertBanner({
  variant = 'info',
  title,
  icon,
  action,
  onDismiss,
  children,
  className = '',
}: AlertBannerProps) {
  const displayIcon = icon !== undefined ? icon : defaultIcons[variant];

  return (
    <div
      className={`ds-alert-banner ds-alert-banner--${variant} ${className}`}
      role={variant === 'error' ? 'alert' : 'status'}
    >
      {displayIcon && <div className="ds-alert-icon">{displayIcon}</div>}
      <div className="ds-alert-content">
        {title && <div className="ds-alert-title">{title}</div>}
        <div>{children}</div>
      </div>
      {action && <div>{action}</div>}
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="ds-icon-btn ds-icon-btn--sm"
          aria-label="Chiudi avviso"
          style={{ alignSelf: 'flex-start', margin: '-4px -6px 0 0' }}
        >
          <X size={15} />
        </button>
      )}
    </div>
  );
}
