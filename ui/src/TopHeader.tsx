import type { ReactNode, CSSProperties, ComponentType } from 'react';
import { Minimize2 } from 'lucide-react';
import { isTauri, minimizeToCompanion } from './desktop';
import { useTranslation } from './i18n';

export interface TopHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ComponentType<{ size?: number | string; className?: string }>;
  actions?: ReactNode;
  leading?: ReactNode;
  style?: CSSProperties;
  children?: ReactNode;
  /** 'page': a large title over a centred column (the personal screens); 'bar' (default): the compact tool bar. */
  variant?: 'bar' | 'page';
  className?: string;
}

export function TopHeader({
  title,
  subtitle,
  icon: Icon,
  actions,
  leading,
  style,
  children,
  variant = 'bar',
  className = '',
}: TopHeaderProps) {
  const { t } = useTranslation();
  const minimize = isTauri() && (
    <button
      onClick={() => minimizeToCompanion()}
      title={t('topHeaderMinimizeShortcut')}
      aria-label={t('topHeaderMinimizeCompanion')}
      data-testid="minimize-to-companion-btn"
      className="page-head-min"
    >
      <Minimize2 size={14} />
    </button>
  );
  if (variant === 'page') {
    return (
      <header data-testid="top-header" className={`top-header page-head ${className}`} style={style}>
        <div className="page-head-inner">
          <div className="page-head-text">
            {typeof title === 'string' ? <h1>{title}</h1> : title}
            {subtitle && (typeof subtitle === 'string' ? <p>{subtitle}</p> : subtitle)}
          </div>
          {(actions || children) && <div className="page-head-actions">{actions}{children}</div>}
        </div>
        {minimize}
      </header>
    );
  }
  return (
    <header
      data-testid="top-header"
      className="top-header"
      style={{
        height: '56px',
        borderBottom: '1px solid hsl(var(--border))',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        backgroundColor: 'hsl(var(--bg))',
        flexShrink: 0,
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, overflow: 'hidden' }}>
        {leading}
        {Icon && <Icon size={18} className="text-primary" />}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
          {typeof title === 'string' ? (
            <h1
              style={{
                margin: 0,
                fontSize: '15px',
                fontWeight: 600,
                color: 'hsl(var(--fg))',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {title}
            </h1>
          ) : (
            title
          )}
          {subtitle && (
            typeof subtitle === 'string' ? (
              <span className="text-muted" style={{ fontSize: '13px', whiteSpace: 'nowrap' }}>
                {subtitle}
              </span>
            ) : (
              subtitle
            )
          )}
        </div>
      </div>

      {(actions || children || isTauri()) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          {actions}
          {children}
          {isTauri() && (
            <button
              onClick={() => minimizeToCompanion()}
              title={t('topHeaderMinimizeShortcut')}
              data-testid="minimize-to-companion-btn"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '4px 8px',
                fontSize: '12px',
                fontWeight: 500,
                borderRadius: '6px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))',
                color: 'hsl(var(--muted-fg))',
                cursor: 'pointer',
              }}
            >
              <Minimize2 size={13} />
              <span>{t('topHeaderMinimizeCompanion')}</span>
            </button>
          )}
        </div>
      )}
    </header>
  );
}
