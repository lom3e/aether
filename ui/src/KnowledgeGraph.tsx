import React, { useState, useEffect, useMemo } from 'react';
import {
  Network,
  Search,
  Bot,
  Users,
  CheckCircle2,
  FileCode,
  Target,
  Play,
  Layers,
  Sparkles,
  BookOpen,
  ArrowRight,
  ShieldCheck,
  X,
  Info,
  Compass,
} from 'lucide-react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';

export interface GraphNodeData {
  id: string;
  workspace_id: string;
  node_type: string;
  canonical_key: string;
  label: string;
  summary?: string | null;
  source_memory_ids: string[];
  provenance: {
    source_entity?: string;
    source_mission_id?: string;
    source_execution_id?: string;
    author_agent?: string;
    verification_status?: string;
    evidence?: Record<string, any>;
    evidence_excerpt?: string;
  };
  properties: Record<string, any>;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface GraphEdgeData {
  id: string;
  workspace_id: string;
  source_node_id: string;
  target_node_id: string;
  relation_type: string;
  weight: number;
  confidence: number;
  provenance: Record<string, any>;
  source_memory_ids: string[];
  properties: Record<string, any>;
  created_at: string;
}

export interface SubgraphData {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  seed_node_ids: string[];
}

const NODE_TYPE_COLORS: Record<string, { bg: string; border: string; text: string; icon: React.ReactNode }> = {
  agent: { bg: 'rgba(59, 130, 246, 0.12)', border: 'rgba(59, 130, 246, 0.4)', text: '#60a5fa', icon: <Bot size={14} /> },
  team: { bg: 'rgba(168, 85, 247, 0.12)', border: 'rgba(168, 85, 247, 0.4)', text: '#c084fc', icon: <Users size={14} /> },
  decision: { bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.4)', text: '#34d399', icon: <CheckCircle2 size={14} /> },
  mission: { bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.4)', text: '#fbbf24', icon: <Target size={14} /> },
  execution: { bg: 'rgba(236, 72, 153, 0.12)', border: 'rgba(236, 72, 153, 0.4)', text: '#f472b6', icon: <Play size={14} /> },
  deliverable: { bg: 'rgba(14, 165, 233, 0.12)', border: 'rgba(14, 165, 233, 0.4)', text: '#38bdf8', icon: <FileCode size={14} /> },
  lesson: { bg: 'rgba(251, 146, 60, 0.12)', border: 'rgba(251, 146, 60, 0.4)', text: '#fb923c', icon: <BookOpen size={14} /> },
  outcome: { bg: 'rgba(52, 211, 153, 0.12)', border: 'rgba(52, 211, 153, 0.4)', text: '#6ee7b7', icon: <Sparkles size={14} /> },
  fact: { bg: 'rgba(148, 163, 184, 0.12)', border: 'rgba(148, 163, 184, 0.4)', text: '#94a3b8', icon: <Info size={14} /> },
  process: { bg: 'rgba(129, 140, 248, 0.12)', border: 'rgba(129, 140, 248, 0.4)', text: '#818cf8', icon: <Layers size={14} /> },
  person: { bg: 'rgba(244, 114, 182, 0.12)', border: 'rgba(244, 114, 182, 0.4)', text: '#f472b6', icon: <Users size={14} /> },
  project: { bg: 'rgba(250, 204, 21, 0.12)', border: 'rgba(250, 204, 21, 0.4)', text: '#facc15', icon: <Compass size={14} /> },
};

const DEFAULT_COLOR = { bg: 'rgba(148, 163, 184, 0.12)', border: 'rgba(148, 163, 184, 0.4)', text: '#94a3b8', icon: <Network size={14} /> };

export function KnowledgeGraph() {
  const { t } = useTranslation();
  const [nodes, setNodes] = useState<GraphNodeData[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState<string>('all');
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [subgraph, setSubgraph] = useState<SubgraphData | null>(null);
  const [subgraphLoading, setSubgraphLoading] = useState(false);
  const [neighbors, setNeighbors] = useState<{ node: GraphNodeData; edge: GraphEdgeData }[]>([]);

  // Fetch all nodes initially
  const fetchGraph = async (query = '', type = 'all') => {
    setLoading(true);
    try {
      let url = apiUrl('/api/knowledge/nodes');
      const params = new URLSearchParams();
      if (query.trim()) params.append('q', query.trim());
      if (type !== 'all') params.append('node_type', type);
      if (params.toString()) url += `?${params.toString()}`;

      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setNodes(data);
        if (data.length > 0 && !selectedNode) {
          // Auto-select first node if none selected
          handleSelectNode(data[0]);
        }
      }
    } catch (err) {
      console.error('Failed to fetch knowledge graph nodes', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchGraph(searchQuery, selectedType);
    }, 250);
    return () => clearTimeout(timer);
  }, [searchQuery, selectedType]);

  const handleSelectNode = async (node: GraphNodeData) => {
    setSelectedNode(node);
    setSubgraphLoading(true);
    try {
      // Fetch subgraph for visual rendering
      const subRes = await fetch(apiUrl(`/api/knowledge/nodes/${node.id}/subgraph?max_depth=2&max_nodes=30`));
      if (subRes.ok) {
        const subData: SubgraphData = await subRes.json();
        setSubgraph(subData);
      }

      // Fetch neighbors for inspector
      const nRes = await fetch(apiUrl(`/api/knowledge/nodes/${node.id}/neighbors`));
      if (nRes.ok) {
        const nData = await nRes.json();
        setNeighbors(nData);
      }
    } catch (err) {
      console.error('Failed to load subgraph details for node', err);
    } finally {
      setSubgraphLoading(false);
    }
  };

  // Node types present in current results
  const availableTypes = ['all', 'agent', 'decision', 'lesson', 'mission', 'execution', 'deliverable', 'outcome', 'team', 'fact', 'process', 'project'];

  // Simple layout computation for subgraph visualization
  const graphLayout = useMemo(() => {
    if (!subgraph || subgraph.nodes.length === 0) return { nodes: [], edges: [] };

    const centerId = selectedNode?.id || subgraph.nodes[0]?.id;
    const width = 640;
    const height = 400;
    const centerX = width / 2;
    const centerY = height / 2;

    const otherNodes = subgraph.nodes.filter(n => n.id !== centerId);
    const radius = Math.min(180, 50 + otherNodes.length * 16);

    const positions: Record<string, { x: number; y: number }> = {};
    positions[centerId] = { x: centerX, y: centerY };

    otherNodes.forEach((n, idx) => {
      const angle = (idx / otherNodes.length) * 2 * Math.PI - Math.PI / 2;
      positions[n.id] = {
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
      };
    });

    const renderedNodes = subgraph.nodes.map(n => ({
      ...n,
      x: positions[n.id]?.x || centerX,
      y: positions[n.id]?.y || centerY,
      isCenter: n.id === centerId,
    }));

    const renderedEdges = subgraph.edges.map(e => {
      const src = positions[e.source_node_id] || { x: centerX, y: centerY };
      const tgt = positions[e.target_node_id] || { x: centerX, y: centerY };
      return {
        ...e,
        x1: src.x,
        y1: src.y,
        x2: tgt.x,
        y2: tgt.y,
      };
    });

    return { nodes: renderedNodes, edges: renderedEdges };
  }, [subgraph, selectedNode]);

  return (
    <div className="knowledge-graph-container" data-testid="knowledge-graph-container" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '16px' }}>
      {/* Header controls */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ position: 'relative', flex: '1 1 280px', maxWidth: '440px' }}>
          <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            data-testid="kg-search-input"
            placeholder={t('searchKnowledgeGraphPlaceholder')}
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="input input-sm"
            style={{ width: '100%', paddingLeft: '36px', background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '8px' }}
          />
        </div>

        {/* Type Filter Pills */}
        <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', paddingBottom: '4px', maxWidth: '100%' }}>
          {availableTypes.map(tKey => {
            const active = selectedType === tKey;
            const styleInfo = NODE_TYPE_COLORS[tKey] || DEFAULT_COLOR;
            return (
              <button
                key={tKey}
                data-testid={`kg-node-pill-${tKey}`}
                className={`badge ${active ? 'badge-primary' : 'badge-ghost'}`}
                style={{
                  cursor: 'pointer',
                  fontSize: '11px',
                  textTransform: 'capitalize',
                  padding: '4px 10px',
                  borderRadius: '16px',
                  border: active ? '1px solid var(--primary)' : '1px solid var(--border-color)',
                  background: active ? 'var(--primary)' : 'var(--bg-card)',
                  color: active ? '#fff' : 'var(--text-secondary)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
                onClick={() => setSelectedType(tKey)}
              >
                {tKey !== 'all' && styleInfo.icon}
                <span>{tKey === 'all' ? t('allNodeTypes') : tKey}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Graph Content Area: Left list & canvas + Right Inspector */}
      <div style={{ display: 'grid', gridTemplateColumns: selectedNode ? '1fr 360px' : '1fr', gap: '16px', flex: 1, minHeight: 0 }}>
        {/* Left Section: Visual Graph Canvas & Entity Grid */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          {/* Visual Subgraph Canvas */}
          {selectedNode && (
            <div
              className="card"
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                padding: '16px',
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Network size={16} color="var(--primary)" />
                  <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {t('viewConnected')}: {selectedNode.label}
                  </span>
                  <span className="badge badge-sm" style={{ fontSize: '10px' }}>
                    {subgraph?.nodes.length || 0} nodes · {subgraph?.edges.length || 0} edges
                  </span>
                </div>
              </div>

              {subgraphLoading ? (
                <div style={{ height: '240px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
                  Loading subgraph...
                </div>
              ) : (
                <div style={{ width: '100%', height: '260px', position: 'relative', background: 'rgba(0,0,0,0.02)', borderRadius: '8px' }}>
                  <svg width="100%" height="100%" viewBox="0 0 640 400" style={{ overflow: 'visible' }}>
                    <defs>
                      <marker id="arrow" viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 1 L 10 5 L 0 9 z" fill="var(--text-muted)" opacity="0.6" />
                      </marker>
                    </defs>

                    {/* Edges */}
                    {graphLayout.edges.map(edge => {
                      const midX = (edge.x1 + edge.x2) / 2;
                      const midY = (edge.y1 + edge.y2) / 2;
                      return (
                        <g key={edge.id}>
                          <line
                            x1={edge.x1}
                            y1={edge.y1}
                            x2={edge.x2}
                            y2={edge.y2}
                            stroke="var(--border-color)"
                            strokeWidth="1.5"
                            strokeDasharray="4 2"
                            markerEnd="url(#arrow)"
                          />
                          <text
                            x={midX}
                            y={midY - 4}
                            textAnchor="middle"
                            fontSize="9"
                            fill="var(--text-muted)"
                            style={{ userSelect: 'none', background: 'var(--bg-card)' }}
                          >
                            {edge.relation_type.replace(/_/g, ' ')}
                          </text>
                        </g>
                      );
                    })}

                    {/* Nodes */}
                    {graphLayout.nodes.map(n => {
                      const color = NODE_TYPE_COLORS[n.node_type] || DEFAULT_COLOR;
                      const isSelected = n.id === selectedNode.id;
                      return (
                        <g
                          key={n.id}
                          transform={`translate(${n.x}, ${n.y})`}
                          style={{ cursor: 'pointer' }}
                          onClick={() => handleSelectNode(n)}
                        >
                          <circle
                            r={n.isCenter ? 24 : 18}
                            fill={color.bg}
                            stroke={isSelected ? 'var(--primary)' : color.border}
                            strokeWidth={isSelected ? '3' : '1.5'}
                          />
                          <text
                            textAnchor="middle"
                            dy="4"
                            fontSize="11"
                            fontWeight={n.isCenter ? 'bold' : 'normal'}
                            fill="var(--text-primary)"
                          >
                            {n.label.slice(0, 10)}
                          </text>
                          <text
                            textAnchor="middle"
                            dy={n.isCenter ? 36 : 28}
                            fontSize="9"
                            fill={color.text}
                          >
                            {n.node_type}
                          </text>
                        </g>
                      );
                    })}
                  </svg>
                </div>
              )}
            </div>
          )}

          {/* Node Grid Cards */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)' }}>
                Knowledge Entities ({nodes.length})
              </span>
            </div>

            {loading ? (
              <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                Loading knowledge graph...
              </div>
            ) : nodes.length === 0 ? (
              <div className="card" style={{ padding: '32px', textAlign: 'center', background: 'var(--bg-card)' }}>
                <Network size={32} style={{ margin: '0 auto 12px', color: 'var(--text-muted)' }} />
                <h4 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>{t('noNodesFound')}</h4>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)', maxWidth: '400px', margin: '0 auto' }}>
                  {t('noNodesDesc')}
                </p>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '10px' }}>
                {nodes.map(node => {
                  const styleInfo = NODE_TYPE_COLORS[node.node_type] || DEFAULT_COLOR;
                  const isSelected = selectedNode?.id === node.id;
                  return (
                    <div
                      key={node.id}
                      data-testid={`kg-node-${node.id}`}
                      className="card"
                      style={{
                        padding: '12px',
                        borderRadius: '10px',
                        background: isSelected ? styleInfo.bg : 'var(--bg-card)',
                        border: isSelected ? `2px solid ${styleInfo.border}` : '1px solid var(--border-color)',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                      onClick={() => handleSelectNode(node)}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                        <span
                          className="badge"
                          style={{
                            fontSize: '10px',
                            textTransform: 'uppercase',
                            background: styleInfo.bg,
                            color: styleInfo.text,
                            border: `1px solid ${styleInfo.border}`,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          {styleInfo.icon}
                          <span>{node.node_type}</span>
                        </span>
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                          {node.canonical_key}
                        </span>
                      </div>

                      <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                        {node.label}
                      </h4>

                      {node.summary && (
                        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.4', margin: 0, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                          {node.summary}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right Section: Node Inspector Drawer */}
        {selectedNode && (
          <div
            data-testid="kg-node-inspector"
            className="card"
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '16px',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
              overflowY: 'auto',
              maxHeight: 'calc(100vh - 180px)',
            }}
          >
            {/* Inspector Header */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div>
                <span
                  className="badge"
                  style={{
                    fontSize: '10px',
                    textTransform: 'uppercase',
                    marginBottom: '6px',
                    ...(NODE_TYPE_COLORS[selectedNode.node_type] || DEFAULT_COLOR),
                  }}
                >
                  {selectedNode.node_type}
                </span>
                <h3 style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                  {selectedNode.label}
                </h3>
              </div>
              <button
                data-testid="close-node-inspector"
                className="btn btn-ghost btn-sm"
                onClick={() => setSelectedNode(null)}
                style={{ padding: '4px' }}
              >
                <X size={16} />
              </button>
            </div>

            {/* Canonical Key & ID */}
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', background: 'rgba(0,0,0,0.03)', padding: '6px 8px', borderRadius: '6px' }}>
              <div><strong>{t('nodeCanonicalKey')}:</strong> <code>{selectedNode.canonical_key}</code></div>
              <div><strong>ID:</strong> <code>{selectedNode.id}</code></div>
            </div>

            {/* Summary */}
            {selectedNode.summary && (
              <div>
                <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  {t('memorySummary')}
                </span>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.5', marginTop: '4px', margin: 0 }}>
                  {selectedNode.summary}
                </p>
              </div>
            )}

            {/* Provenance Card */}
            <div
              data-testid="kg-provenance-card"
              style={{
                border: '1px solid rgba(16, 185, 129, 0.2)',
                background: 'rgba(16, 185, 129, 0.04)',
                borderRadius: '8px',
                padding: '10px',
                fontSize: '11px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px', color: '#10b981', fontWeight: 600 }}>
                <ShieldCheck size={14} />
                <span>{t('memoryProvenance')}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', color: 'var(--text-secondary)' }}>
                {selectedNode.provenance.source_entity && (
                  <div><strong>Source:</strong> {selectedNode.provenance.source_entity}</div>
                )}
                {selectedNode.provenance.author_agent && (
                  <div><strong>Author / Reviewer:</strong> {selectedNode.provenance.author_agent}</div>
                )}
                {selectedNode.provenance.source_mission_id && (
                  <div><strong>Mission:</strong> <code>{selectedNode.provenance.source_mission_id}</code></div>
                )}
                {selectedNode.provenance.source_execution_id && (
                  <div><strong>Execution Run:</strong> <code>{selectedNode.provenance.source_execution_id}</code></div>
                )}
                <div><strong>Verification:</strong> <span className="badge badge-success badge-sm" style={{ fontSize: '9px', padding: '2px 6px' }}>{selectedNode.provenance.verification_status || 'verified'}</span></div>
              </div>
            </div>

            {/* Connected Relationships */}
            <div>
              <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                {t('connectedRelations')} ({neighbors.length})
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
                {neighbors.length === 0 ? (
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>No direct neighbors</span>
                ) : (
                  neighbors.map(({ node: nNode, edge }) => {
                    const nStyle = NODE_TYPE_COLORS[nNode.node_type] || DEFAULT_COLOR;
                    return (
                      <div
                        key={edge.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '6px 8px',
                          background: 'var(--bg-card)',
                          border: '1px solid var(--border-color)',
                          borderRadius: '6px',
                          cursor: 'pointer',
                        }}
                        onClick={() => handleSelectNode(nNode)}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
                          <span style={{ fontSize: '9px', textTransform: 'uppercase', color: 'var(--primary)', fontWeight: 600 }}>
                            {edge.relation_type.replace(/_/g, ' ')}
                          </span>
                          <ArrowRight size={10} color="var(--text-muted)" />
                          <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-primary)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                            {nNode.label}
                          </span>
                        </div>
                        <span className="badge badge-sm" style={{ fontSize: '9px', background: nStyle.bg, color: nStyle.text, border: `1px solid ${nStyle.border}` }}>
                          {nNode.node_type}
                        </span>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Source Memory IDs */}
            {selectedNode.source_memory_ids && selectedNode.source_memory_ids.length > 0 && (
              <div>
                <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  {t('sourceMemories')} ({selectedNode.source_memory_ids.length})
                </span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '4px' }}>
                  {selectedNode.source_memory_ids.map(mid => (
                    <span key={mid} className="badge badge-sm" style={{ fontSize: '10px', fontFamily: 'monospace' }}>
                      {mid}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
