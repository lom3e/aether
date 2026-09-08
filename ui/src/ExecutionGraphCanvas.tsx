import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  ZoomIn, ZoomOut, Maximize2, RotateCcw,
  Target, Play, Layers, Bot, Terminal, Wrench, FileText,
  ArrowRight, X, Info, Copy, Check, RefreshCw
} from 'lucide-react';

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  status: string;
  metadata?: Record<string, any>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  label?: string;
  metadata?: Record<string, any>;
}

export interface MissionGraph {
  mission_id: string;
  execution_id?: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  metadata?: Record<string, any>;
}

interface NodePosition {
  node: GraphNode;
  x: number;
  y: number;
  width: number;
  height: number;
  tier: number;
}

interface EdgePath {
  edge: GraphEdge;
  sourceNode: NodePosition;
  targetNode: NodePosition;
  pathData: string;
  isRework: boolean;
}

interface ExecutionGraphCanvasProps {
  graph: MissionGraph | null;
  loading?: boolean;
  selectedExecutionId?: string | null;
  runNumber?: number | string | null;
  runStatus?: string | null;
  className?: string;
  height?: number | string;
  onNodeClick?: (node: GraphNode | null) => void;
}

const NODE_WIDTH = 210;
const NODE_HEIGHT = 56;
const HORIZONTAL_GAP = 36;
const VERTICAL_GAP = 76;
const PADDING = 48;

export function ExecutionGraphCanvas({
  graph,
  loading = false,
  selectedExecutionId = null,
  runNumber = null,
  runStatus = null,
  className = '',
  height = '100%',
  onNodeClick,
}: ExecutionGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Pan & Zoom State
  const [scale, setScale] = useState<number>(1);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const dragStartRef = useRef<{ x: number; y: number; panX: number; panY: number }>({ x: 0, y: 0, panX: 0, panY: 0 });
  const hasUserPannedOrZoomedRef = useRef<boolean>(false);

  // Selection & Hover State
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<boolean>(false);
  const [showLegend, setShowLegend] = useState<boolean>(true);

  // Preserve selection if graph updates and node still exists
  useEffect(() => {
    if (selectedNodeId && graph?.nodes) {
      const exists = graph.nodes.some(n => n.id === selectedNodeId);
      if (!exists) {
        setSelectedNodeId(null);
        onNodeClick?.(null);
      }
    }
  }, [graph, selectedNodeId, onNodeClick]);

  // Color & Icon resolution by Node Type
  const getNodeTypeStyle = useCallback((type: string) => {
    switch (type) {
      case 'mission':
        return {
          bg: 'hsl(var(--primary) / 0.12)',
          border: 'hsl(var(--primary))',
          text: 'hsl(var(--primary))',
          icon: Target,
          label: 'Mission',
        };
      case 'execution':
        return {
          bg: 'rgba(168, 85, 247, 0.12)',
          border: '#a855f7',
          text: '#c084fc',
          icon: Play,
          label: 'Execution',
        };
      case 'milestone':
        return {
          bg: 'rgba(59, 130, 246, 0.12)',
          border: '#3b82f6',
          text: '#60a5fa',
          icon: Layers,
          label: 'Milestone',
        };
      case 'agent':
        return {
          bg: 'rgba(6, 182, 212, 0.12)',
          border: '#06b6d4',
          text: '#22d3ee',
          icon: Bot,
          label: 'Agent',
        };
      case 'task':
        return {
          bg: 'rgba(245, 158, 11, 0.12)',
          border: '#f59e0b',
          text: '#fbbf24',
          icon: Terminal,
          label: 'Task',
        };
      case 'tool':
        return {
          bg: 'rgba(113, 113, 122, 0.12)',
          border: '#71717a',
          text: '#a1a1aa',
          icon: Wrench,
          label: 'Tool',
        };
      case 'deliverable':
        return {
          bg: 'rgba(16, 185, 129, 0.12)',
          border: '#10b981',
          text: '#34d399',
          icon: FileText,
          label: 'Deliverable',
        };
      default:
        return {
          bg: 'hsl(var(--muted))',
          border: 'hsl(var(--border))',
          text: 'hsl(var(--fg))',
          icon: Info,
          label: type,
        };
    }
  }, []);

  const getStatusColor = useCallback((status: string) => {
    switch (status) {
      case 'completed':
      case 'verified':
      case 'final':
        return { dot: '#10b981', badgeBg: 'rgba(16, 185, 129, 0.12)', text: '#34d399' };
      case 'running':
      case 'active':
        return { dot: '#3b82f6', badgeBg: 'rgba(59, 130, 246, 0.12)', text: '#60a5fa', pulse: true };
      case 'verifying':
        return { dot: '#a855f7', badgeBg: 'rgba(168, 85, 247, 0.12)', text: '#c084fc', pulse: true };
      case 'awaiting_approval':
      case 'needs_revision':
        return { dot: '#f59e0b', badgeBg: 'rgba(245, 158, 11, 0.12)', text: '#fbbf24' };
      case 'failed':
        return { dot: '#ef4444', badgeBg: 'rgba(239, 68, 68, 0.12)', text: '#f87171' };
      case 'interrupted':
      case 'cancelled':
        return { dot: '#f97316', badgeBg: 'rgba(249, 115, 22, 0.12)', text: '#fb923c' };
      default:
        return { dot: '#71717a', badgeBg: 'rgba(113, 113, 122, 0.12)', text: '#a1a1aa' };
    }
  }, []);

  // 1. Layout Computation (Hierarchical DAG Layering)
  const { nodePositions, edgePaths, bounds } = useMemo(() => {
    if (!graph || !graph.nodes || graph.nodes.length === 0) {
      return {
        nodePositions: [] as NodePosition[],
        edgePaths: [] as EdgePath[],
        bounds: { minX: 0, minY: 0, maxX: 600, maxY: 400, width: 600, height: 400 },
      };
    }

    // Categorize nodes into tier buckets
    const typeTierMap: Record<string, number> = {
      mission: 0,
      execution: 1,
      milestone: 2,
      agent: 3,
      task: 4,
      tool: 5,
      deliverable: 5,
    };

    const buckets: Map<number, GraphNode[]> = new Map();
    for (let i = 0; i <= 5; i++) {
      buckets.set(i, []);
    }

    graph.nodes.forEach(node => {
      const tier = typeTierMap[node.type] ?? 3;
      buckets.get(tier)?.push(node);
    });

    // Collapse empty tiers to prevent huge blank vertical gaps
    const activeTiers: { originalTier: number; nodes: GraphNode[] }[] = [];
    for (let i = 0; i <= 5; i++) {
      const list = buckets.get(i) || [];
      if (list.length > 0) {
        // Sort nodes within milestones/agents/tasks for stable deterministic order
        list.sort((a, b) => a.id.localeCompare(b.id));
        activeTiers.push({ originalTier: i, nodes: list });
      }
    }

    // Calculate maximum width to center rows
    let maxRowWidth = 0;
    activeTiers.forEach(t => {
      const rowWidth = t.nodes.length * NODE_WIDTH + Math.max(0, t.nodes.length - 1) * HORIZONTAL_GAP;
      if (rowWidth > maxRowWidth) maxRowWidth = rowWidth;
    });

    const calculatedNodes: NodePosition[] = [];
    const nodeMap = new Map<string, NodePosition>();

    activeTiers.forEach((tierObj, layerIdx) => {
      const rowNodes = tierObj.nodes;
      const count = rowNodes.length;
      const rowWidth = count * NODE_WIDTH + Math.max(0, count - 1) * HORIZONTAL_GAP;
      const startX = PADDING + (maxRowWidth - rowWidth) / 2;
      const y = PADDING + layerIdx * (NODE_HEIGHT + VERTICAL_GAP);

      rowNodes.forEach((node, nodeIdx) => {
        const x = startX + nodeIdx * (NODE_WIDTH + HORIZONTAL_GAP);
        const pos: NodePosition = {
          node,
          x: x + NODE_WIDTH / 2,
          y: y + NODE_HEIGHT / 2,
          width: NODE_WIDTH,
          height: NODE_HEIGHT,
          tier: tierObj.originalTier,
        };
        calculatedNodes.push(pos);
        nodeMap.set(node.id, pos);
      });
    });

    // Calculate Edge Paths
    const calculatedEdges: EdgePath[] = [];
    graph.edges.forEach(edge => {
      const src = nodeMap.get(edge.source);
      const tgt = nodeMap.get(edge.target);
      if (!src || !tgt) return; // Discard invalid/orphan edges

      const isRework = edge.type === 'rework';
      let pathData = '';

      if (isRework || tgt.y < src.y) {
        // Backward loop (e.g. Quality Gate rework or cycle)
        const x1 = src.x + src.width / 2;
        const y1 = src.y;
        const x2 = tgt.x + tgt.width / 2;
        const y2 = tgt.y;
        const lateralArc = Math.max(x1, x2) + 60;
        pathData = `M ${x1} ${y1} C ${lateralArc} ${y1}, ${lateralArc} ${y2}, ${x2} ${y2}`;
      } else if (Math.abs(tgt.y - src.y) < 10) {
        // Same-tier horizontal edge (e.g. sequential milestones)
        if (tgt.x > src.x) {
          const x1 = src.x + src.width / 2;
          const y1 = src.y;
          const x2 = tgt.x - tgt.width / 2;
          const y2 = tgt.y;
          pathData = `M ${x1} ${y1} L ${x2} ${y2}`;
        } else {
          const x1 = src.x - src.width / 2;
          const y1 = src.y;
          const x2 = tgt.x + tgt.width / 2;
          const y2 = tgt.y;
          pathData = `M ${x1} ${y1} L ${x2} ${y2}`;
        }
      } else {
        // Standard forward vertical edge (top-to-bottom)
        const x1 = src.x;
        const y1 = src.y + src.height / 2;
        const x2 = tgt.x;
        const y2 = tgt.y - tgt.height / 2;
        const dy = y2 - y1;
        const cy1 = y1 + dy * 0.45;
        const cy2 = y2 - dy * 0.45;
        pathData = `M ${x1} ${y1} C ${x1} ${cy1}, ${x2} ${cy2}, ${x2} ${y2}`;
      }

      calculatedEdges.push({
        edge,
        sourceNode: src,
        targetNode: tgt,
        pathData,
        isRework,
      });
    });

    // Compute bounding box for fit-to-view
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    calculatedNodes.forEach(n => {
      const left = n.x - n.width / 2;
      const right = n.x + n.width / 2;
      const top = n.y - n.height / 2;
      const bottom = n.y + n.height / 2;

      if (left < minX) minX = left;
      if (top < minY) minY = top;
      if (right > maxX) maxX = right;
      if (bottom > maxY) maxY = bottom;
    });

    if (minX === Infinity) {
      minX = 0;
      minY = 0;
      maxX = 600;
      maxY = 400;
    }

    const bWidth = Math.max(maxX - minX + PADDING * 2, 400);
    const bHeight = Math.max(maxY - minY + PADDING * 2, 300);

    return {
      nodePositions: calculatedNodes,
      edgePaths: calculatedEdges,
      bounds: { minX: minX - PADDING, minY: minY - PADDING, maxX: maxX + PADDING, maxY: maxY + PADDING, width: bWidth, height: bHeight },
    };
  }, [graph]);

  // 2. Auto-Fit to View Logic
  const handleFitToView = useCallback(() => {
    if (!containerRef.current || nodePositions.length === 0) return;
    const containerW = containerRef.current.clientWidth || 600;
    const containerH = containerRef.current.clientHeight || 400;

    const pad = 40;
    const availableW = Math.max(containerW - pad * 2, 200);
    const availableH = Math.max(containerH - pad * 2, 200);

    const scaleX = availableW / bounds.width;
    const scaleY = availableH / bounds.height;
    const optimalScale = Math.min(Math.max(Math.min(scaleX, scaleY), 0.35), 1.15);

    const centerX = bounds.minX + bounds.width / 2;
    const centerY = bounds.minY + bounds.height / 2;

    const panX = containerW / 2 - centerX * optimalScale;
    const panY = containerH / 2 - centerY * optimalScale;

    setScale(optimalScale);
    setPan({ x: panX, y: panY });
  }, [bounds, nodePositions.length]);

  // Initial fit-to-view only once or when graph completely changes
  useEffect(() => {
    if (!hasUserPannedOrZoomedRef.current && nodePositions.length > 0) {
      handleFitToView();
    }
  }, [nodePositions.length, handleFitToView]);

  // Zoom Controls
  const handleZoomIn = () => {
    hasUserPannedOrZoomedRef.current = true;
    setScale(prev => Math.min(prev * 1.25, 2.5));
  };

  const handleZoomOut = () => {
    hasUserPannedOrZoomedRef.current = true;
    setScale(prev => Math.max(prev * 0.8, 0.25));
  };

  const handleResetZoom = () => {
    hasUserPannedOrZoomedRef.current = false;
    handleFitToView();
  };

  // Mouse Drag / Pan Handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    // Only left click on SVG canvas background
    if (e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (target.closest('.interactive-node') || target.closest('.canvas-toolbar') || target.closest('.node-inspector-drawer')) {
      return;
    }
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
    hasUserPannedOrZoomedRef.current = true;
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

  // Mouse Wheel Zoom
  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    hasUserPannedOrZoomedRef.current = true;
    const zoomFactor = e.deltaY < 0 ? 1.12 : 0.89;
    setScale(prev => Math.min(Math.max(prev * zoomFactor, 0.25), 2.5));
  };

  // Node Selection Handlers
  const handleSelectNode = (node: GraphNode | null) => {
    const nextId = node && node.id !== selectedNodeId ? node.id : null;
    setSelectedNodeId(nextId);
    onNodeClick?.(nextId && node ? node : null);
  };

  // Compute Active Selection Relationships
  const selectedNodeObj = useMemo(() => {
    if (!selectedNodeId || !graph) return null;
    return graph.nodes.find(n => n.id === selectedNodeId) || null;
  }, [selectedNodeId, graph]);

  const connectedEdges = useMemo(() => {
    if (!selectedNodeId || !graph) return { inbound: [] as GraphEdge[], outbound: [] as GraphEdge[] };
    const inbound = graph.edges.filter(e => e.target === selectedNodeId);
    const outbound = graph.edges.filter(e => e.source === selectedNodeId);
    return { inbound, outbound };
  }, [selectedNodeId, graph]);

  const connectedNodeIds = useMemo(() => {
    if (!selectedNodeId) return new Set<string>();
    const set = new Set<string>();
    set.add(selectedNodeId);
    connectedEdges.inbound.forEach(e => set.add(e.source));
    connectedEdges.outbound.forEach(e => set.add(e.target));
    return set;
  }, [selectedNodeId, connectedEdges]);

  // Copy ID Helper
  const handleCopyId = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 1800);
  };

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setSelectedNodeId(null);
      onNodeClick?.(null);
    } else if (e.key === '+' || e.key === '=') {
      handleZoomIn();
    } else if (e.key === '-') {
      handleZoomOut();
    } else if (e.key === '0') {
      handleResetZoom();
    }
  };

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onWheel={handleWheel}
      className={`execution-graph-canvas-container ${className}`}
      style={{
        position: 'relative',
        width: '100%',
        height: typeof height === 'number' ? `${height}px` : height,
        minHeight: '420px',
        backgroundColor: 'hsl(var(--bg))',
        overflow: 'hidden',
        cursor: isDragging ? 'grabbing' : 'grab',
        userSelect: 'none',
        outline: 'none',
        borderRadius: '8px',
        border: '1px solid hsl(var(--border))',
      }}
      aria-label="Interactive Execution Graph Canvas"
    >
      {/* Background Dot Grid */}
      <svg
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
          opacity: 0.25,
        }}
      >
        <defs>
          <pattern id="canvas-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <circle cx="2" cy="2" r="1" fill="hsl(var(--muted-fg))" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#canvas-grid)" />
      </svg>

      {/* Top Floating Control Bar */}
      <div
        className="canvas-toolbar"
        style={{
          position: 'absolute',
          top: '12px',
          left: '12px',
          right: '12px',
          zIndex: 10,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          pointerEvents: 'none',
        }}
      >
        {/* Left: Execution Scope Indicator */}
        <div
          style={{
            pointerEvents: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 12px',
            borderRadius: '6px',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
            fontSize: '12px',
          }}
        >
          {selectedExecutionId ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontWeight: 600, color: 'hsl(var(--fg))' }}>
                Run #{runNumber || selectedExecutionId.slice(0, 8)}
              </span>
              {runStatus && (
                <span
                  style={{
                    fontSize: '10px',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    padding: '1px 6px',
                    borderRadius: '4px',
                    backgroundColor: getStatusColor(runStatus).badgeBg,
                    color: getStatusColor(runStatus).text,
                  }}
                >
                  {runStatus}
                </span>
              )}
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontWeight: 600, color: 'hsl(var(--fg))' }}>Blueprint Specification</span>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 600,
                  padding: '1px 6px',
                  borderRadius: '4px',
                  backgroundColor: 'hsl(var(--muted))',
                  color: 'hsl(var(--muted-fg))',
                }}
              >
                Template
              </span>
            </div>
          )}

          {graph && (
            <span style={{ color: 'hsl(var(--muted-fg))', fontSize: '11px', marginLeft: '4px' }}>
              · {graph.nodes.length} nodes · {graph.edges.length} edges
            </span>
          )}
        </div>

        {/* Right: Zoom Controls */}
        <div
          style={{
            pointerEvents: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px',
            borderRadius: '6px',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
          }}
        >
          <button
            onClick={handleZoomIn}
            className="btn btn-ghost"
            style={{ padding: '4px 6px', height: '26px' }}
            title="Zoom In (+)"
            aria-label="Zoom In"
          >
            <ZoomIn size={14} />
          </button>
          <span
            style={{
              fontSize: '11px',
              fontFamily: 'monospace',
              padding: '0 6px',
              minWidth: '42px',
              textAlign: 'center',
              color: 'hsl(var(--muted-fg))',
            }}
          >
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={handleZoomOut}
            className="btn btn-ghost"
            style={{ padding: '4px 6px', height: '26px' }}
            title="Zoom Out (-)"
            aria-label="Zoom Out"
          >
            <ZoomOut size={14} />
          </button>
          <div style={{ width: '1px', height: '16px', backgroundColor: 'hsl(var(--border))', margin: '0 2px' }} />
          <button
            onClick={handleFitToView}
            className="btn btn-ghost"
            style={{ padding: '4px 6px', height: '26px' }}
            title="Fit to View"
            aria-label="Fit to View"
          >
            <Maximize2 size={13} />
          </button>
          <button
            onClick={handleResetZoom}
            className="btn btn-ghost"
            style={{ padding: '4px 6px', height: '26px' }}
            title="Reset (1:1)"
            aria-label="Reset View"
          >
            <RotateCcw size={13} />
          </button>
          <div style={{ width: '1px', height: '16px', backgroundColor: 'hsl(var(--border))', margin: '0 2px' }} />
          <button
            onClick={() => setShowLegend(prev => !prev)}
            className={`btn btn-ghost ${showLegend ? 'text-primary' : ''}`}
            style={{ padding: '4px 6px', height: '26px' }}
            title={showLegend ? "Hide Legend" : "Show Legend"}
            aria-label="Toggle Legend"
          >
            <Info size={13} />
          </button>
        </div>
      </div>

      {/* Main Interactive SVG Graph */}
      {loading ? (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '10px',
            color: 'hsl(var(--muted-fg))',
            fontSize: '13px',
          }}
        >
          <RefreshCw size={24} className="animate-spin text-primary" />
          <span>Compiling live execution graph...</span>
        </div>
      ) : !graph || nodePositions.length === 0 ? (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            color: 'hsl(var(--muted-fg))',
            fontSize: '13px',
          }}
        >
          <Layers size={32} style={{ opacity: 0.3, marginBottom: '6px' }} />
          <div style={{ fontWeight: 600, color: 'hsl(var(--fg))' }}>No execution nodes registered yet</div>
          <p style={{ fontSize: '12px', maxWidth: '340px', textAlign: 'center', margin: 0 }}>
            Start the mission or trigger a step to compile real-time DAG nodes and relationships.
          </p>
        </div>
      ) : (
        <svg
          width="100%"
          height="100%"
          style={{ position: 'absolute', inset: 0, overflow: 'visible' }}
        >
          {/* Arrow Markers Definition */}
          <defs>
            <marker
              id="arrow-default"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 9 5 L 0 9 z" fill="hsl(var(--border))" />
            </marker>

            <marker
              id="arrow-inbound"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 9 5 L 0 9 z" fill="hsl(var(--primary))" />
            </marker>

            <marker
              id="arrow-outbound"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 9 5 L 0 9 z" fill="#06b6d4" />
            </marker>

            <marker
              id="arrow-rework"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 9 5 L 0 9 z" fill="#f43f5e" />
            </marker>
          </defs>

          {/* Transform Container for Pan & Zoom */}
          <g transform={`translate(${pan.x}, ${pan.y}) scale(${scale})`}>
            {/* 1. Render Edges */}
            <g className="edges-layer">
              {edgePaths.map(({ edge, pathData, isRework }) => {
                const isInbound = selectedNodeId && edge.target === selectedNodeId;
                const isOutbound = selectedNodeId && edge.source === selectedNodeId;
                const isHovered = hoveredEdgeId === edge.id;
                const isDimmed = selectedNodeId && !isInbound && !isOutbound;

                let strokeColor = 'hsl(var(--border))';
                let markerId = 'arrow-default';
                let strokeWidth = 1.5;

                if (isRework) {
                  strokeColor = '#f43f5e';
                  markerId = 'arrow-rework';
                  strokeWidth = 2;
                } else if (isInbound) {
                  strokeColor = 'hsl(var(--primary))';
                  markerId = 'arrow-inbound';
                  strokeWidth = 2.4;
                } else if (isOutbound) {
                  strokeColor = '#06b6d4';
                  markerId = 'arrow-outbound';
                  strokeWidth = 2.4;
                } else if (isHovered) {
                  strokeColor = 'hsl(var(--fg))';
                  strokeWidth = 2;
                }

                return (
                  <g
                    key={edge.id}
                    onMouseEnter={() => setHoveredEdgeId(edge.id)}
                    onMouseLeave={() => setHoveredEdgeId(null)}
                    style={{ cursor: 'pointer' }}
                  >
                    {/* Invisible thicker hit-area for easier hover */}
                    <path
                      d={pathData}
                      fill="none"
                      stroke="transparent"
                      strokeWidth={14}
                    />
                    {/* Visual Path */}
                    <path
                      d={pathData}
                      fill="none"
                      stroke={strokeColor}
                      strokeWidth={strokeWidth}
                      strokeDasharray={isRework ? '4 3' : undefined}
                      markerEnd={`url(#${markerId})`}
                      opacity={isDimmed ? 0.25 : 0.85}
                      style={{ transition: 'opacity 0.2s ease, stroke-width 0.2s ease' }}
                    />
                  </g>
                );
              })}
            </g>

            {/* 2. Render Nodes */}
            <g className="nodes-layer">
              {nodePositions.map(({ node, x, y, width, height }) => {
                const isSelected = selectedNodeId === node.id;
                const isHovered = hoveredNodeId === node.id;
                const isConnected = connectedNodeIds.has(node.id);
                const isDimmed = selectedNodeId && !isConnected;

                const typeStyle = getNodeTypeStyle(node.type);
                const statusStyle = getStatusColor(node.status);
                const NodeIcon = typeStyle.icon;

                return (
                  <g
                    key={node.id}
                    className="interactive-node"
                    transform={`translate(${x}, ${y})`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSelectNode(node);
                    }}
                    onMouseEnter={() => setHoveredNodeId(node.id)}
                    onMouseLeave={() => setHoveredNodeId(null)}
                    style={{
                      cursor: 'pointer',
                      opacity: isDimmed ? 0.35 : 1,
                      transition: 'opacity 0.2s ease',
                    }}
                  >
                    {/* Node Container Card */}
                    <rect
                      x={-width / 2}
                      y={-height / 2}
                      width={width}
                      height={height}
                      rx={8}
                      ry={8}
                      fill="hsl(var(--card))"
                      stroke={
                        isSelected
                          ? 'hsl(var(--primary))'
                          : isConnected && selectedNodeId
                          ? typeStyle.border
                          : isHovered
                          ? 'hsl(var(--fg) / 0.3)'
                          : 'hsl(var(--border))'
                      }
                      strokeWidth={isSelected ? 2 : isConnected && selectedNodeId ? 1.8 : 1}
                      filter={isSelected ? 'drop-shadow(0 4px 12px rgba(var(--primary-rgb, 99, 102, 241), 0.25))' : 'drop-shadow(0 1px 3px rgba(0,0,0,0.04))'}
                    />

                    {/* Left Accent Stripe */}
                    <rect
                      x={-width / 2}
                      y={-height / 2}
                      width={4}
                      height={height}
                      rx={2}
                      ry={2}
                      fill={typeStyle.border}
                    />

                    {/* Node Type Pill & Icon */}
                    <g transform={`translate(${-width / 2 + 12}, ${-height / 2 + 16})`}>
                      <NodeIcon size={12} color={typeStyle.text} />
                      <text
                        x={16}
                        y={9}
                        fontSize={9.5}
                        fontWeight={700}
                        letterSpacing="0.04em"
                        fill={typeStyle.text}
                        style={{ textTransform: 'uppercase' }}
                      >
                        {typeStyle.label}
                      </text>
                    </g>

                    {/* Status Dot / Indicator */}
                    <g transform={`translate(${width / 2 - 16}, ${-height / 2 + 15})`}>
                      <circle
                        cx={0}
                        cy={0}
                        r={4}
                        fill={statusStyle.dot}
                      />
                    </g>

                    {/* Node Label (Clipped to prevent overflow) */}
                    <text
                      x={-width / 2 + 12}
                      y={14}
                      fontSize={12}
                      fontWeight={600}
                      fill="hsl(var(--fg))"
                      style={{
                        fontFamily: 'inherit',
                      }}
                    >
                      {node.label.length > 24 ? `${node.label.slice(0, 22)}…` : node.label}
                    </text>
                  </g>
                );
              })}
            </g>
          </g>
        </svg>
      )}

      {/* Bottom Floating Minimal Legend */}
      {showLegend && graph && nodePositions.length > 0 && (
        <div
          style={{
            position: 'absolute',
            bottom: '12px',
            left: '12px',
            zIndex: 10,
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '5px 12px',
            borderRadius: '6px',
            backgroundColor: 'hsl(var(--card) / 0.92)',
            backdropFilter: 'blur(4px)',
            border: '1px solid hsl(var(--border))',
            fontSize: '11px',
            color: 'hsl(var(--muted-fg))',
            boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#6366f1' }} />
            <span>Mission</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#a855f7' }} />
            <span>Execution</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#3b82f6' }} />
            <span>Milestone</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#06b6d4' }} />
            <span>Agent</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#f59e0b' }} />
            <span>Task</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#71717a' }} />
            <span>Tool</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#10b981' }} />
            <span>Deliverable</span>
          </div>
        </div>
      )}

      {/* Selected Node Details Drawer (Slide-over Inside Canvas) */}
      {selectedNodeObj && (
        <div
          className="node-inspector-drawer"
          style={{
            position: 'absolute',
            top: '12px',
            right: '12px',
            bottom: '12px',
            width: '320px',
            zIndex: 20,
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: '8px',
            boxShadow: '-4px 0 16px rgba(0,0,0,0.1)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Drawer Header */}
          <div
            style={{
              padding: '14px 16px',
              borderBottom: '1px solid hsl(var(--border))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: 'hsl(var(--bg))',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  backgroundColor: getNodeTypeStyle(selectedNodeObj.type).bg,
                  color: getNodeTypeStyle(selectedNodeObj.type).text,
                }}
              >
                {selectedNodeObj.type}
              </span>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 600,
                  padding: '2px 6px',
                  borderRadius: '4px',
                  backgroundColor: getStatusColor(selectedNodeObj.status).badgeBg,
                  color: getStatusColor(selectedNodeObj.status).text,
                }}
              >
                {selectedNodeObj.status}
              </span>
            </div>

            <button
              onClick={() => {
                setSelectedNodeId(null);
                onNodeClick?.(null);
              }}
              className="btn btn-ghost"
              style={{ padding: '4px' }}
              title="Close Details"
              aria-label="Close Node Details"
              data-testid="close-node-drawer-btn"
            >
              <X size={14} />
            </button>
          </div>

          {/* Drawer Body */}
          <div style={{ flex: 1, padding: '16px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Title & Identifier */}
            <div>
              <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'hsl(var(--fg))', margin: 0 }}>
                {selectedNodeObj.label}
              </h4>
              <div
                style={{
                  marginTop: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  fontSize: '11px',
                  fontFamily: 'monospace',
                  color: 'hsl(var(--muted-fg))',
                }}
              >
                <span>ID: {selectedNodeObj.id}</span>
                <button
                  onClick={() => handleCopyId(selectedNodeObj.id)}
                  className="btn btn-ghost"
                  style={{ padding: '2px 4px', fontSize: '10px', display: 'inline-flex', alignItems: 'center', gap: '3px' }}
                  title="Copy ID"
                >
                  {copiedId ? <Check size={11} className="text-emerald-500" /> : <Copy size={11} />}
                </button>
              </div>
            </div>

            {/* Relation Explorer */}
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', marginBottom: '6px' }}>
                Relationships ({connectedEdges.inbound.length + connectedEdges.outbound.length})
              </div>

              {connectedEdges.inbound.length === 0 && connectedEdges.outbound.length === 0 ? (
                <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', fontStyle: 'italic', padding: '6px 0' }}>
                  No connected edges.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {/* Inbound */}
                  {connectedEdges.inbound.map(edge => {
                    const srcNode = graph?.nodes.find(n => n.id === edge.source);
                    return (
                      <div
                        key={edge.id}
                        onClick={() => srcNode && handleSelectNode(srcNode)}
                        style={{
                          padding: '6px 8px',
                          borderRadius: '4px',
                          backgroundColor: 'hsl(var(--bg))',
                          border: '1px solid hsl(var(--border))',
                          fontSize: '11px',
                          cursor: srcNode ? 'pointer' : 'default',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '6px',
                        }}
                        title={srcNode ? `Jump to ${srcNode.label}` : undefined}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden' }}>
                          <span style={{ color: 'hsl(var(--primary))', fontWeight: 600 }}>← {edge.type}</span>
                          <span style={{ color: 'hsl(var(--fg))', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {srcNode ? srcNode.label : edge.source}
                          </span>
                        </div>
                        {srcNode && <ArrowRight size={11} style={{ opacity: 0.5 }} />}
                      </div>
                    );
                  })}

                  {/* Outbound */}
                  {connectedEdges.outbound.map(edge => {
                    const tgtNode = graph?.nodes.find(n => n.id === edge.target);
                    return (
                      <div
                        key={edge.id}
                        onClick={() => tgtNode && handleSelectNode(tgtNode)}
                        style={{
                          padding: '6px 8px',
                          borderRadius: '4px',
                          backgroundColor: 'hsl(var(--bg))',
                          border: '1px solid hsl(var(--border))',
                          fontSize: '11px',
                          cursor: tgtNode ? 'pointer' : 'default',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '6px',
                        }}
                        title={tgtNode ? `Jump to ${tgtNode.label}` : undefined}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden' }}>
                          <span style={{ color: '#06b6d4', fontWeight: 600 }}>→ {edge.type}</span>
                          <span style={{ color: 'hsl(var(--fg))', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {tgtNode ? tgtNode.label : edge.target}
                          </span>
                        </div>
                        {tgtNode && <ArrowRight size={11} style={{ opacity: 0.5 }} />}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Sanitized Metadata */}
            {selectedNodeObj.metadata && Object.keys(selectedNodeObj.metadata).length > 0 && (
              <div>
                <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', marginBottom: '6px' }}>
                  Operational Telemetry
                </div>
                <pre
                  style={{
                    backgroundColor: 'hsl(var(--bg))',
                    border: '1px solid hsl(var(--border))',
                    padding: '8px',
                    borderRadius: '4px',
                    fontSize: '10px',
                    fontFamily: 'monospace',
                    overflowX: 'auto',
                    margin: 0,
                    color: 'hsl(var(--fg))',
                  }}
                >
                  {JSON.stringify(selectedNodeObj.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
