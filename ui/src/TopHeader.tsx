import type { ReactNode, CSSProperties, ComponentType } from 'react';

export interface TopHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ComponentType<{ size?: number | string; className?: string }>;
  actions?: ReactNode;
  leading?: ReactNode;
  style?: CSSProperties;
  children?: ReactNode;
}

export function TopHeader({
  title,
  subtitle,
  icon: Icon,
  actions,
  leading,
  style,
  children,
}: TopHeaderProps) {
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
            <span
              style={{
                fontSize: '15px',
                fontWeight: 600,
                color: 'hsl(var(--fg))',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {title}
            </span>
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

      {(actions || children) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          {actions}
          {children}
        </div>
      )}
    </header>
  );
}
