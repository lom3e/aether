import React from 'react';
import {
  Bot,
  Search,
  Code,
  PenTool,
  ShieldCheck,
  Cpu,
  Database,
  Sparkles,
  Terminal,
  FileText,
  Brain,
  Compass,
  Layers,
  Zap,
  CheckCircle,
  type LucideProps,
} from 'lucide-react';

export const SUPPORTED_ICONS = [
  'Bot',
  'Search',
  'Code',
  'PenTool',
  'ShieldCheck',
  'Cpu',
  'Database',
  'Sparkles',
  'Terminal',
  'FileText',
  'Brain',
  'Compass',
  'Layers',
  'Zap',
  'CheckCircle',
] as const;

export type SupportedIcon = typeof SUPPORTED_ICONS[number];

export const SUPPORTED_COLORS = [
  'violet',
  'blue',
  'emerald',
  'amber',
  'rose',
  'cyan',
  'indigo',
  'pink',
] as const;

export type SupportedColor = typeof SUPPORTED_COLORS[number];

const ICON_MAP: Record<string, React.ComponentType<LucideProps>> = {
  Bot,
  Search,
  Code,
  PenTool,
  ShieldCheck,
  Cpu,
  Database,
  Sparkles,
  Terminal,
  FileText,
  Brain,
  Compass,
  Layers,
  Zap,
  CheckCircle,
};

const COLOR_MAP: Record<string, { bg: string; text: string; border: string }> = {
  violet: {
    bg: 'hsl(262 83% 58% / 0.15)',
    text: 'hsl(262 83% 58%)',
    border: 'hsl(262 83% 58% / 0.3)',
  },
  blue: {
    bg: 'hsl(217 91% 60% / 0.15)',
    text: 'hsl(217 91% 60%)',
    border: 'hsl(217 91% 60% / 0.3)',
  },
  emerald: {
    bg: 'hsl(142 71% 45% / 0.15)',
    text: 'hsl(142 71% 45%)',
    border: 'hsl(142 71% 45% / 0.3)',
  },
  amber: {
    bg: 'hsl(38 92% 50% / 0.15)',
    text: 'hsl(38 92% 50%)',
    border: 'hsl(38 92% 50% / 0.3)',
  },
  rose: {
    bg: 'hsl(350 89% 60% / 0.15)',
    text: 'hsl(350 89% 60%)',
    border: 'hsl(350 89% 60% / 0.3)',
  },
  cyan: {
    bg: 'hsl(189 94% 43% / 0.15)',
    text: 'hsl(189 94% 43%)',
    border: 'hsl(189 94% 43% / 0.3)',
  },
  indigo: {
    bg: 'hsl(239 84% 67% / 0.15)',
    text: 'hsl(239 84% 67%)',
    border: 'hsl(239 84% 67% / 0.3)',
  },
  pink: {
    bg: 'hsl(330 81% 60% / 0.15)',
    text: 'hsl(330 81% 60%)',
    border: 'hsl(330 81% 60% / 0.3)',
  },
};

export function getIdentityColor(colorName?: string | null) {
  const normalized = (colorName || 'violet').toLowerCase();
  return COLOR_MAP[normalized] || COLOR_MAP.violet;
}

export function IdentityBadge({
  icon,
  color,
  size = 20,
  containerSize = 36,
  style,
  fallback = 'Bot',
}: {
  icon?: string | null;
  color?: string | null;
  size?: number;
  containerSize?: number;
  style?: React.CSSProperties;
  fallback?: string;
}) {
  const theme = getIdentityColor(color);
  const IconComponent = (icon && ICON_MAP[icon]) || (fallback && ICON_MAP[fallback]) || Bot;

  return (
    <div
      style={{
        width: `${containerSize}px`,
        height: `${containerSize}px`,
        borderRadius: '8px',
        backgroundColor: theme.bg,
        color: theme.text,
        border: `1px solid ${theme.border}`,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        ...style,
      }}
    >
      <IconComponent size={size} />
    </div>
  );
}

export function RenderIcon({
  name,
  size = 16,
  className,
  fallback = 'Bot',
  style,
}: {
  name?: string | null;
  size?: number;
  className?: string;
  fallback?: string;
  style?: React.CSSProperties;
}) {
  const IconComponent = (name && ICON_MAP[name]) || (fallback && ICON_MAP[fallback]) || Bot;
  return <IconComponent size={size} className={className} style={style} />;
}
