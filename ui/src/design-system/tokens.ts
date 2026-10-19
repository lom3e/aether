/**
 * Aether Design System — Core Design Tokens
 * 
 * Philosophy:
 * - Apple: Spacious, clean, elegant hierarchy, minimal chrome
 * - Linear: Precise geometry, compact controls, evident micro-states
 * - Vercel: Deep graphite surfaces, 1px subtle borders, crisp contrast
 * - Aether: Focused Personal AI Office, violet accent, zero cyberpunk noise
 */

export const tokens = {
  spacing: {
    none: '0px',
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '24px',
    '2xl': '32px',
    '3xl': '48px',
    '4xl': '64px',
  },
  radii: {
    none: '0px',
    xs: '4px',
    sm: '6px',
    md: '8px',
    lg: '12px',
    xl: '16px',
    '2xl': '20px',
    full: '9999px',
  },
  typography: {
    fonts: {
      sans: 'var(--font-sans, -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif)',
      mono: 'var(--font-mono, "JetBrains Mono", monospace)',
    },
    sizes: {
      xs: '11px',
      sm: '12.5px',
      base: '14px',
      md: '15px',
      lg: '18px',
      xl: '22px',
      '2xl': '28px',
      '3xl': '34px',
    },
    weights: {
      normal: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },
    lineHeights: {
      tight: 1.2,
      snug: 1.35,
      normal: 1.5,
      relaxed: 1.6,
    },
  },
  controlHeights: {
    sm: '32px',
    md: '38px',
    lg: '44px',
  },
  status: {
    connected: {
      label: 'Collegato e attivo',
      bg: 'hsl(var(--success-bg, 142 71% 95%))',
      color: 'hsl(var(--success, 142 71% 45%))',
      border: 'hsl(var(--success, 142 71% 45%) / 0.25)',
      dot: 'hsl(var(--success, 142 71% 45%))',
    },
    connecting: {
      label: 'Connessione in corso…',
      bg: 'hsl(var(--info-bg, 262 83% 95%))',
      color: 'hsl(var(--info, 262 83% 58%))',
      border: 'hsl(var(--info, 262 83% 58%) / 0.25)',
      dot: 'hsl(var(--info, 262 83% 58%))',
    },
    setup_required: {
      label: 'Configurazione richiesta',
      bg: 'hsl(var(--warning-bg, 38 92% 95%))',
      color: 'hsl(var(--warning, 38 92% 50%))',
      border: 'hsl(var(--warning, 38 92% 50%) / 0.25)',
      dot: 'hsl(var(--warning, 38 92% 50%))',
    },
    not_configured: {
      label: 'Non collegato',
      bg: 'hsl(var(--muted, 220 14% 94%) / 0.6)',
      color: 'hsl(var(--muted-fg, 220 10% 46%))',
      border: 'hsl(var(--border, 220 13% 88%))',
      dot: 'hsl(var(--muted-fg, 220 10% 46%) / 0.6)',
    },
    expired: {
      label: 'Accesso scaduto',
      bg: 'hsl(var(--warning-bg, 38 92% 95%))',
      color: 'hsl(var(--warning, 38 92% 50%))',
      border: 'hsl(var(--warning, 38 92% 50%) / 0.25)',
      dot: 'hsl(var(--warning, 38 92% 50%))',
    },
    error: {
      label: 'Errore di collegamento',
      bg: 'hsl(var(--destructive, 0 72% 51%) / 0.1)',
      color: 'hsl(var(--destructive, 0 72% 51%))',
      border: 'hsl(var(--destructive, 0 72% 51%) / 0.25)',
      dot: 'hsl(var(--destructive, 0 72% 51%))',
    },
  },
  shadows: {
    none: 'none',
    subtle: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
    card: '0 2px 8px -2px rgba(0, 0, 0, 0.08), 0 1px 3px 0 rgba(0, 0, 0, 0.04)',
    elevated: '0 8px 24px -4px rgba(0, 0, 0, 0.12), 0 4px 8px -2px rgba(0, 0, 0, 0.06)',
    modal: '0 20px 48px -8px rgba(0, 0, 0, 0.32), 0 8px 16px -4px rgba(0, 0, 0, 0.16)',
  },
  transitions: {
    fast: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)',
    normal: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
    smooth: 'all 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
  },
} as const;

export type Spacing = keyof typeof tokens.spacing;
export type Radii = keyof typeof tokens.radii;
export type TypographySize = keyof typeof tokens.typography.sizes;
export type TypographyWeight = keyof typeof tokens.typography.weights;
export type SemanticStatus = keyof typeof tokens.status;
