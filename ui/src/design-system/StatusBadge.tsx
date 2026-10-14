import { useTranslation } from '../i18n';

export type ConnectionStatusType =
  | 'CONNECTED'
  | 'CONNECTING'
  | 'SETUP_REQUIRED'
  | 'NOT_CONFIGURED'
  | 'EXPIRED'
  | 'ERROR'
  | 'connected'
  | 'verified'
  | 'connecting'
  | 'setup_required'
  | 'configured'
  | 'verification_required'
  | 'not_configured'
  | 'disconnected'
  | 'expired'
  | 'needs_auth'
  | 'verification_failed'
  | 'error';

export interface StatusBadgeProps {
  status: ConnectionStatusType | string;
  label?: string;
  className?: string;
}

interface StatusConfig {
  variant: 'connected' | 'connecting' | 'setup_required' | 'not_configured' | 'expired' | 'error';
  defaultLabel: string;   // an i18n key
}

function resolveStatus(status: string): StatusConfig {
  const s = status.toLowerCase();

  if (s === 'connected' || s === 'verified') {
    return { variant: 'connected', defaultLabel: 'badgeConnectedActive' };
  }
  if (s === 'connecting') {
    return { variant: 'connecting', defaultLabel: 'badgeConnecting' };
  }
  if (s === 'setup_required' || s === 'configured' || s === 'verification_required') {
    return { variant: 'setup_required', defaultLabel: 'badgeSetupRequired' };
  }
  if (s === 'expired' || s === 'needs_auth') {
    return { variant: 'expired', defaultLabel: 'badgeAccessExpired' };
  }
  if (s === 'error' || s === 'verification_failed') {
    return { variant: 'error', defaultLabel: 'badgeConnectionError' };
  }
  // Default fallback
  return { variant: 'not_configured', defaultLabel: 'badgeNotConnected' };
}

export function StatusBadge({ status, label, className = '' }: StatusBadgeProps) {
  const { t } = useTranslation();
  const config = resolveStatus(status);
  const displayLabel = label || t(config.defaultLabel as any);

  return (
    <span
      className={`ds-status-badge ds-status-badge--${config.variant} ${className}`}
      role="status"
    >
      <span className="ds-status-dot" aria-hidden="true" />
      <span>{displayLabel}</span>
    </span>
  );
}
