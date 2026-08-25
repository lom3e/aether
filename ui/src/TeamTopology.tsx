import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  ZoomIn, ZoomOut, Maximize2, RotateCcw, Bot, Crown
} from 'lucide-react';
import { getIdentityColor, RenderIcon } from './identity';

export interface TopologyAgent {
  name: string;
  role: string;
  icon?: string | null;
  color?: string | null;
  delegates_to?: string[] | string;
  skills?: string[];
}

interface TeamTopologyProps {
  agents: TopologyAgent[];
  teamName?: string;
  height?: number;
  className?: string;
  interactive?: boolean;
}

interface NodeLayout {
  agent: {
    name: string;
    role: string;
    icon: string;
    color: string;
    delegates_to: string[];
  };
  x: number;
  y: number;
  width: number;
  height: number;
  isManager: boolean;
  level: number;
}

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

export function TeamTopology({
  agents = [],
  teamName = 'Team',
  height = 200,
  className = '',
  interactive = true,
}: TeamTopologyProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Pan & Zoom State
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  // 1. Normalize Agents
  const normalized = useMemo(() => {
    return (agents || []).map((a) => {
      let delegates: string[] = [];
      if (Array.isArray(a.delegates_to)) {
        delegates = a.delegates_to.filter(Boolean);
      } else if (typeof a.delegates_to === 'string') {
        delegates = a.delegates_to.split(',').map((s) => s.trim()).filter(Boolean);
      }
      return {
        name: (a.name || 'Agente').trim(),
        role: (a.role || 'Specialista').trim(),
        icon: a.icon || 'Bot',
        color: a.color || 'violet',
        delegates_to: delegates,
      };
    });
  }, [agents]);

  // 2. Compute Layout & Node Dimensions (Adapt to full text content with NO TRUNCATION)
  const { nodes, links, bounds } = useMemo(() => {
    if (normalized.length === 0) {
      return { nodes: [], links: [], bounds: { minX: 0, minY: 0, maxX: 400, maxY: 200, width: 400, height: 200 } };
    }

    // Determine manager / coordinator
    let managerIndex = normalized.findIndex((a) => a.name.toLowerCase() === 'manager');
    if (managerIndex === -1) {
      managerIndex = normalized.findIndex((a) =>
        /manager|coord|lead|orchestrat|dirett|capo/i.test(a.role)
      );
    }
    if (managerIndex === -1) {
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

    // Calculate individual node width based on character count to guarantee ZERO truncation
    const calculatedNodes: NodeLayout[] = [];
    const nodeH = 50;

    // Helper to calculate exact width needed for text
    const calcNodeWidth = (name: string, role: string) => {
      const nameChars = name.length;
      const roleChars = role.length;
      const neededForName = nameChars * 8.2 + 56;
      const neededForRole = roleChars * 6.5 + 56;
      return Math.max(160, Math.ceil(Math.max(neededForName, neededForRole)));
    };

    const maxNodeWidth = Math.max(...normalized.map(a => calcNodeWidth(a.name, a.role)));
    const uniformNodeW = Math.min(Math.max(170, maxNodeWidth), 280);

    // Layout configuration
    if (specialists.length === 0) {
      // Single Agent
      calculatedNodes.push({
        agent: manager,
        x: 200,
        y: 80,
        width: uniformNodeW,
        height: nodeH,
        isManager: true,
        level: 0,
      });
    } else {
      // Multi-Agent Hierarchical Topology
      // Level 0: Manager (Top Center)
      const mgrWidth = uniformNodeW;
      const mgrX = Math.max(250, (specialists.length * (uniformNodeW + 36)) / 2);
      const mgrY = 45;

      calculatedNodes.push({
        agent: manager,
        x: mgrX,
        y: mgrY,
        width: mgrWidth,
        height: nodeH,
        isManager: true,
        level: 0,
      });

      // Level 1: Specialists
      const totalSpecs = specialists.length;
      const horizontalGap = 32;
      const totalRowWidth = totalSpecs * uniformNodeW + (totalSpecs - 1) * horizontalGap;
      const startX = mgrX - totalRowWidth / 2 + uniformNodeW / 2;
      const specY = mgrY + 110;

      specialists.forEach((spec, idx) => {
        const posX = startX + idx * (uniformNodeW + horizontalGap);
        calculatedNodes.push({
          agent: spec,
          x: posX,
          y: specY,
          width: uniformNodeW,
          height: nodeH,
          isManager: false,
          level: 1,
        });
      });
    }

    // Map for fast position lookups
    const nodeMap = new Map<string, NodeLayout>();
    calculatedNodes.forEach((n) => nodeMap.set(n.agent.name, n));

    // Calculate Links
    const computedLinks: TopologyLink[] = [];
    let hasExplicit = false;

    calculatedNodes.forEach((srcNode) => {
      srcNode.agent.delegates_to.forEach((targetName) => {
        const tgtNode = nodeMap.get(targetName);
        if (tgtNode && tgtNode.agent.name !== srcNode.agent.name) {
          hasExplicit = true;
          computedLinks.push({
            from: srcNode.agent.name,
            to: targetName,
            fromX: srcNode.x,
            fromY: srcNode.y + srcNode.height / 2,
            toX: tgtNode.x,
            toY: tgtNode.y - tgtNode.height / 2,
            color: getIdentityColor(srcNode.agent.color).text,
            isImplicit: false,
          });
        }
      });
    });

    // Implicit fallback connections if no explicit delegations
    if (!hasExplicit && specialists.length > 0) {
      const mgrNode = calculatedNodes[0];
      calculatedNodes.slice(1).forEach((specNode) => {
        computedLinks.push({
          from: mgrNode.agent.name,
          to: specNode.agent.name,
          fromX: mgrNode.x,
          fromY: mgrNode.y + mgrNode.height / 2,
          toX: specNode.x,
          toY: specNode.y - specNode.height / 2,
          color: getIdentityColor(mgrNode.agent.color).text,
          isImplicit: true,
        });
      });
    }

    // Compute bounding box
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    calculatedNodes.forEach((n) => {
      const halfW = n.width / 2;
      const halfH = n.height / 2;
      minX = Math.min(minX, n.x - halfW - 20);
      minY = Math.min(minY, n.y - halfH - 20);
      maxX = Math.max(maxX, n.x + halfW + 20);
      maxY = Math.max(maxY, n.y + halfH + 20);
    });

    const bWidth = Math.max(maxX - minX, 300);
    const bHeight = Math.max(maxY - minY, 150);

    return {
      nodes: calculatedNodes,
      links: computedLinks,
      bounds: { minX, minY, maxX, maxY, width: bWidth, height: bHeight },
    };
  }, [normalized]);

  // 3. Auto-Fit to View
  const handleFitToView = useCallback(() => {
    if (!containerRef.current || nodes.length === 0) return;
    const containerW = containerRef.current.clientWidth || 400;
    const containerH = height || 200;

    const padding = 36;
    const availableW = containerW - padding * 2;
    const availableH = containerH - padding * 2;

    const scaleX = availableW / bounds.width;
    const scaleY = availableH / bounds.height;
    const optimalScale = Math.min(Math.max(Math.min(scaleX, scaleY), 0.35), 1.25);

    // Center content in container
    const centerX = bounds.minX + bounds.width / 2;
    const centerY = bounds.minY + bounds.height / 2;

    const panX = containerW / 2 - centerX * optimalScale;
    const panY = containerH / 2 - centerY * optimalScale;

    setScale(optimalScale);
    setPan({ x: panX, y: panY });
  }, [bounds, height, nodes.length]);

  useEffect(() => {
    handleFitToView();
  }, [handleFitToView]);

  // ResizeObserver to re-fit on container dimension changes
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(() => {
      handleFitToView();
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [handleFitToView]);

  // Drag Pan Handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!interactive || e.button !== 0) return; // Only left click
    setIsDragging(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: pan.x,
      panY: pan.y,
    };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;
    setPan({
      x: dragStartRef.current.panX + dx,
      y: dragStartRef.current.panY + dy,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Toolbar zoom helpers
  const handleZoomIn = () => {
    const nextScale = Math.min(scale * 1.2, 3.0);
    if (!containerRef.current) return;
    const cx = containerRef.current.clientWidth / 2;
    const cy = height / 2;
    const nextPanX = cx - (cx - pan.x) * (nextScale / scale);
    const nextPanY = cy - (cy - pan.y) * (nextScale / scale);
    setScale(nextScale);
    setPan({ x: nextPanX, y: nextPanY });
  };

  const handleZoomOut = () => {
    const nextScale = Math.max(scale * 0.8, 0.25);
    if (!containerRef.current) return;
    const cx = containerRef.current.clientWidth / 2;
    const cy = height / 2;
    const nextPanX = cx - (cx - pan.x) * (nextScale / scale);
    const nextPanY = cy - (cy - pan.y) * (nextScale / scale);
    setScale(nextScale);
    setPan({ x: nextPanX, y: nextPanY });
  };

  const handleResetZoom = () => {
    if (!containerRef.current) return;
    const cx = containerRef.current.clientWidth / 2;
    const cy = height / 2;
    const contentCx = bounds.minX + bounds.width / 2;
    const contentCy = bounds.minY + bounds.height / 2;
    setScale(1);
    setPan({ x: cx - contentCx, y: cy - contentCy });
  };

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
          fontSize: '12.5px',
          gap: '8px',
        }}
      >
        <Bot size={22} className="text-muted" />
        <span>Nessun agente configurato nella squadra</span>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`team-topology-viewport ${className}`}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      style={{
        width: '100%',
        height: `${height}px`,
        backgroundColor: 'hsl(var(--card)/0.5)',
        border: '1px solid hsl(var(--border)/0.8)',
        borderRadius: '12px',
        position: 'relative',
        overflow: 'hidden',
        cursor: isDragging ? 'grabbing' : (interactive ? 'grab' : 'default'),
        userSelect: 'none',
      }}
    >
      {/* Floating Control Toolbar */}
      {interactive && (
        <div
          style={{
            position: 'absolute',
            top: '10px',
            right: '10px',
            zIndex: 20,
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: '8px',
            padding: '3px 6px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.18)',
          }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', padding: '0 4px' }}>
            {Math.round(scale * 100)}%
          </span>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ padding: '4px', height: '24px', width: '24px', borderRadius: '4px' }}
            onClick={handleZoomIn}
            title="Zoom In (+)"
          >
            <ZoomIn size={13} />
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ padding: '4px', height: '24px', width: '24px', borderRadius: '4px' }}
            onClick={handleZoomOut}
            title="Zoom Out (-)"
          >
            <ZoomOut size={13} />
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ padding: '4px', height: '24px', width: '24px', borderRadius: '4px' }}
            onClick={handleFitToView}
            title="Adatta alla vista (Fit to View)"
          >
            <Maximize2 size={13} />
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ padding: '4px', height: '24px', width: '24px', borderRadius: '4px' }}
            onClick={handleResetZoom}
            title="Ripristina 100%"
          >
            <RotateCcw size={13} />
          </button>
        </div>
      )}

      {/* SVG Canvas with Transform Matrix */}
      <svg
        style={{
          width: '100%',
          height: '100%',
          display: 'block',
          overflow: 'visible',
        }}
      >
        <defs>
          {/* Reusable Arrowhead Markers */}
          <marker
            id={`arrow-head-${teamName}`}
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
            id={`arrow-head-implicit-${teamName}`}
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 2 L 6 5 L 0 8 z" fill="hsl(var(--muted-fg))" />
          </marker>
        </defs>

        <g transform={`translate(${pan.x}, ${pan.y}) scale(${scale})`}>
          {/* Grid Background Pattern */}
          <pattern id={`topo-grid-${teamName}`} width="30" height="30" patternUnits="userSpaceOnUse">
            <circle cx="15" cy="15" r="1" fill="hsl(var(--border)/0.5)" />
          </pattern>
          <rect
            x={bounds.minX - 500}
            y={bounds.minY - 500}
            width={bounds.width + 1000}
            height={bounds.height + 1000}
            fill={`url(#topo-grid-${teamName})`}
            style={{ pointerEvents: 'none' }}
          />

          {/* Delegation Links */}
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
                  strokeWidth={isRelated && hoveredNode ? 2.5 : 1.8}
                  strokeDasharray={link.isImplicit ? '5 4' : undefined}
                  strokeOpacity={isRelated ? (hoveredNode ? 0.95 : 0.55) : 0.12}
                  markerEnd={link.isImplicit ? `url(#arrow-head-implicit-${teamName})` : `url(#arrow-head-${teamName})`}
                />
              </g>
            );
          })}

          {/* Node Cards (NO TRUNCATION, FULL COMPLETE TEXT) */}
          {nodes.map(({ x, y, width, height: nodeH, isManager, agent }) => {
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
                  transition: 'opacity 0.2s ease',
                }}
              >
                {/* Card Container */}
                <rect
                  x={-width / 2}
                  y={-nodeH / 2}
                  width={width}
                  height={nodeH}
                  rx={10}
                  ry={10}
                  fill="hsl(var(--card))"
                  stroke={isHovered ? colorTheme.text : (isManager ? colorTheme.border : 'hsl(var(--border))')}
                  strokeWidth={isHovered || isManager ? 2 : 1.2}
                  filter={isHovered ? 'drop-shadow(0 6px 16px rgba(0,0,0,0.22))' : undefined}
                />

                {/* Left Identity Badge Container */}
                <rect
                  x={-width / 2 + 8}
                  y={-nodeH / 2 + 8}
                  width={34}
                  height={34}
                  rx={8}
                  fill={colorTheme.bg}
                  stroke={colorTheme.border}
                  strokeWidth={1}
                />

                {/* Identity Icon Indicator */}
                <g transform={`translate(${-width / 2 + 25}, ${-nodeH / 2 + 25})`}>
                  {isManager ? (
                    <Crown size={18} color={colorTheme.text} style={{ transform: 'translate(-9px, -9px)' }} />
                  ) : (
                    <RenderIcon name={agent.icon} size={16} style={{ color: colorTheme.text, transform: 'translate(-8px, -8px)' }} />
                  )}
                </g>

                {/* Complete Agent Name (NO TRUNCATION) */}
                <text
                  x={-width / 2 + 48}
                  y={-nodeH / 2 + 21}
                  fontSize="12.5"
                  fontWeight="600"
                  fill="hsl(var(--fg))"
                  letterSpacing="-0.01em"
                >
                  {agent.name}
                </text>

                {/* Complete Agent Role Subtitle (NO TRUNCATION) */}
                <text
                  x={-width / 2 + 48}
                  y={-nodeH / 2 + 37}
                  fontSize="10"
                  fontWeight="400"
                  fill="hsl(var(--muted-fg))"
                >
                  {isManager ? `${agent.role} (Coordinator)` : agent.role}
                </text>

                {/* Rich SVG Tooltip */}
                <title>{`${agent.name} · ${agent.role}${agent.delegates_to.length > 0 ? `\nDelega a: ${agent.delegates_to.join(', ')}` : ''}`}</title>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
