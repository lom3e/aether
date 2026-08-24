import { useState } from 'react';
import { getIdentityColor } from './identity';
import { Bot } from 'lucide-react';

export interface TopologyAgent {
  name: string;
  role: string;
  icon?: string | null;
  color?: string | null;
  delegates_to?: string[] | string;
}

interface TeamTopologyProps {
  agents: TopologyAgent[];
  teamName?: string;
  height?: number;
  className?: string;
}

export function TeamTopology({
  agents = [],
  teamName = 'Team',
  height = 170,
  className = '',
}: TeamTopologyProps) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Normalize agent list
  const normalized = (agents || []).map((a) => {
    let delegates: string[] = [];
    if (Array.isArray(a.delegates_to)) {
      delegates = a.delegates_to.filter(Boolean);
    } else if (typeof a.delegates_to === 'string') {
      delegates = a.delegates_to.split(',').map((s) => s.trim()).filter(Boolean);
    }
    return {
      name: a.name || 'Unnamed',
      role: a.role || 'Specialist',
      icon: a.icon || 'Bot',
      color: a.color || 'violet',
      delegates_to: delegates,
    };
  });

  if (normalized.length === 0) {
    return (
      <div
        className={`team-topology-empty ${className}`}
        style={{
          height: `${height}px`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          border: '1px dashed hsl(var(--border))',
          borderRadius: 'var(--radius)',
          backgroundColor: 'hsl(var(--muted)/0.2)',
          color: 'hsl(var(--muted-fg))',
          fontSize: '12px',
          gap: '6px',
        }}
      >
        <Bot size={20} className="text-muted" />
        <span>No agents configured in workforce</span>
      </div>
    );
  }

  // Find manager / root node
  // Priority: 1. named "manager" 2. role contains "manager"/"coord"/"lead" 3. delegates to others and not delegated to 4. first agent
  let managerIndex = normalized.findIndex((a) => a.name.toLowerCase() === 'manager');
  if (managerIndex === -1) {
    managerIndex = normalized.findIndex((a) =>
      /manager|coord|lead|orchestrat/i.test(a.role)
    );
  }
  if (managerIndex === -1) {
    // Find node with outgoing delegations but no incoming
    const allTargets = new Set(normalized.flatMap((a) => a.delegates_to));
    managerIndex = normalized.findIndex(
      (a) => a.delegates_to.length > 0 && !allTargets.has(a.name)
    );
  }
  if (managerIndex === -1) {
    managerIndex = 0;
  }

  const manager = normalized[managerIndex];
  const specialists = normalized.filter((_, idx) => idx !== managerIndex);

  // Layout calculations
  const totalCols = Math.max(1, specialists.length);
  const cardW = 120;
  const cardH = 46;
  const colSpacing = Math.max(130, 480 / Math.max(1, totalCols));
  const svgWidth = Math.max(360, (totalCols + 1) * 110);
  const svgHeight = normalized.length === 1 ? 120 : height;

  const managerX = svgWidth / 2;
  const managerY = 32;

  // Specialists positions
  const nodePositions = new Map<string, { x: number; y: number; isManager: boolean; agent: typeof manager }>();
  nodePositions.set(manager.name, { x: managerX, y: managerY, isManager: true, agent: manager });

  if (specialists.length > 0) {
    const totalWidth = (specialists.length - 1) * colSpacing;
    const startX = (svgWidth - totalWidth) / 2;
    const specY = svgHeight - 34;

    specialists.forEach((spec, idx) => {
      const x = startX + idx * colSpacing;
      nodePositions.set(spec.name, { x, y: specY, isManager: false, agent: spec });
    });
  }

  // Calculate links
  interface TopologyLink {
    from: string;
    to: string;
    fromX: number;
    fromY: number;
    toX: number;
    toY: number;
    color: string;
    isImplicit: boolean;
  }

  const links: TopologyLink[] = [];
  let hasExplicitDelegation = false;

  normalized.forEach((src) => {
    const srcPos = nodePositions.get(src.name);
    if (!srcPos) return;

    src.delegates_to.forEach((targetName) => {
      const tgtPos = nodePositions.get(targetName);
      if (tgtPos && targetName !== src.name) {
        hasExplicitDelegation = true;
        links.push({
          from: src.name,
          to: targetName,
          fromX: srcPos.x,
          fromY: srcPos.y + cardH / 2,
          toX: tgtPos.x,
          toY: tgtPos.y - cardH / 2,
          color: getIdentityColor(src.color).text,
          isImplicit: false,
        });
      }
    });
  });

  // If no explicit delegation in a multi-agent team, connect Manager -> Specialists implicitly
  if (!hasExplicitDelegation && specialists.length > 0) {
    specialists.forEach((spec) => {
      const specPos = nodePositions.get(spec.name)!;
      links.push({
        from: manager.name,
        to: spec.name,
        fromX: managerX,
        fromY: managerY + cardH / 2,
        toX: specPos.x,
        toY: specPos.y - cardH / 2,
        color: getIdentityColor(manager.color).text,
        isImplicit: true,
      });
    });
  }

  return (
    <div
      className={`team-topology-container ${className}`}
      style={{
        width: '100%',
        backgroundColor: 'hsl(var(--card)/0.4)',
        border: '1px solid hsl(var(--border)/0.7)',
        borderRadius: 'var(--radius)',
        padding: '8px 4px',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <svg
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        style={{
          width: '100%',
          height: `${svgHeight}px`,
          display: 'block',
          overflow: 'visible',
        }}
      >
        <defs>
          {/* Arrowhead markers */}
          <marker
            id={`arrow-manager-${teamName}`}
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="hsl(var(--primary))" />
          </marker>
          <marker
            id={`arrow-default-${teamName}`}
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="hsl(var(--muted-fg))" />
          </marker>
        </defs>

        {/* Links / Delegation Lines */}
        {links.map((link, idx) => {
          const isRelated =
            hoveredNode === null ||
            hoveredNode === link.from ||
            hoveredNode === link.to;

          const midY = (link.fromY + link.toY) / 2;
          const pathD = `M ${link.fromX} ${link.fromY} C ${link.fromX} ${midY}, ${link.toX} ${midY}, ${link.toX} ${link.toY}`;

          return (
            <g key={`link-${idx}`} style={{ transition: 'opacity 0.2s ease' }}>
              <path
                d={pathD}
                fill="none"
                stroke={link.color}
                strokeWidth={isRelated && hoveredNode ? 2.5 : 1.5}
                strokeDasharray={link.isImplicit ? '4 3' : undefined}
                strokeOpacity={isRelated ? (hoveredNode ? 0.95 : 0.45) : 0.12}
                markerEnd={link.isImplicit ? undefined : `url(#arrow-manager-${teamName})`}
              />
            </g>
          );
        })}

        {/* Agent Nodes */}
        {Array.from(nodePositions.values()).map(({ x, y, isManager, agent }) => {
          const colorTheme = getIdentityColor(agent.color);
          const isHovered = hoveredNode === agent.name;
          const isFaded = hoveredNode !== null && !isHovered;

          return (
            <g
              key={agent.name}
              transform={`translate(${x}, ${y})`}
              onMouseEnter={() => setHoveredNode(agent.name)}
              onMouseLeave={() => setHoveredNode(null)}
              style={{
                cursor: 'pointer',
                opacity: isFaded ? 0.35 : 1,
                transition: 'all 0.2s ease',
              }}
            >
              {/* Background Card */}
              <rect
                x={-cardW / 2}
                y={-cardH / 2}
                width={cardW}
                height={cardH}
                rx={8}
                ry={8}
                fill="hsl(var(--card))"
                stroke={isHovered ? colorTheme.text : (isManager ? colorTheme.border : 'hsl(var(--border))')}
                strokeWidth={isManager || isHovered ? 1.8 : 1}
                filter={isHovered ? 'drop-shadow(0 4px 12px rgba(0,0,0,0.15))' : undefined}
              />

              {/* Identity Icon Indicator */}
              <rect
                x={-cardW / 2 + 6}
                y={-cardH / 2 + 7}
                width={32}
                height={32}
                rx={6}
                fill={colorTheme.bg}
                stroke={colorTheme.border}
                strokeWidth={0.8}
              />

              {/* Manager Crown Icon / Specialist Dot */}
              <text
                x={-cardW / 2 + 22}
                y={-cardH / 2 + 26}
                textAnchor="middle"
                fontSize="13"
                fill={colorTheme.text}
              >
                {isManager ? '👑' : (agent.icon === 'Search' ? '🔍' : (agent.icon === 'Code' ? '⚡' : '🤖'))}
              </text>

              {/* Agent Name */}
              <text
                x={-cardW / 2 + 44}
                y={-cardH / 2 + 19}
                fontSize="11"
                fontWeight="600"
                fill="hsl(var(--fg))"
                letterSpacing="-0.01em"
              >
                {agent.name.length > 9 ? `${agent.name.slice(0, 8)}…` : agent.name}
              </text>

              {/* Agent Role Subtitle */}
              <text
                x={-cardW / 2 + 44}
                y={-cardH / 2 + 33}
                fontSize="9"
                fill="hsl(var(--muted-fg))"
              >
                {isManager ? 'Coordinator' : (agent.role.length > 11 ? `${agent.role.slice(0, 10)}…` : agent.role)}
              </text>

              {/* Tooltip on SVG hover */}
              <title>{`${agent.name} (${agent.role}) ${agent.delegates_to.length > 0 ? `→ Delegates to: ${agent.delegates_to.join(', ')}` : ''}`}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
