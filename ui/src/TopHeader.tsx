import type { ReactNode, CSSProperties, ComponentType } from 'react';
import { Minimize2 } from 'lucide-react';
import { isTauri, minimizeToCompanion } from './desktop';

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

      {(actions || children || isTauri()) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          {actions}
          {children}
          {isTauri() && (
            <button
              onClick={() => minimizeToCompanion()}
              title="Minimize to Companion (Option+Space)"
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
              <span>Minimize to Companion</span>
            </button>
          )}
        </div>
      )}
    </header>
  );
}
