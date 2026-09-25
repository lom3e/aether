import { useState, useEffect, useCallback, useContext } from 'react';
import {
  Workflow as WorkflowIcon, Plus, Play, Save, Trash2,
  Clock, Bot, Wrench, ShieldCheck, FileCheck, RefreshCw, X
} from 'lucide-react';
import { TopHeader } from './TopHeader';
import { ToastContext } from './toast';
import { apiUrl, apiError } from './api';

export type NodeType = 'trigger' | 'agent' | 'tool' | 'approval' | 'deliverable';

export interface WorkflowNode {
  id: string;
  type: NodeType;
  title: string;
  config: Record<string, any>;
  position: { x: number; y: number };
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
}

export interface WorkflowData {
  id: string;
  name: string;
  description: string;
  graph: {
    nodes: WorkflowNode[];
    edges: WorkflowEdge[];
  };
  compiled_mission_id?: string;
  compiled_automation_id?: string;
}

interface WorkflowBuilderProps {
  navigate?: (view: string, params?: any) => void;
}

export function WorkflowBuilder({ navigate }: WorkflowBuilderProps) {
  const showToast = useContext(ToastContext);

  const [workflows, setWorkflows] = useState<WorkflowData[]>([]);
  const [activeWorkflow, setActiveWorkflow] = useState<WorkflowData | null>(null);
  const [, setLoading] = useState(false);
  const [compiling, setCompiling] = useState(false);
  const [connectingSource, setConnectingSource] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Fetch workflows
  const fetchWorkflows = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl('/api/workflows'));
      if (res.ok) {
        const data = await res.json();
        setWorkflows(data);
        if (data.length > 0 && !activeWorkflow) {
          setActiveWorkflow(data[0]);
        }
      }
    } catch (err: any) {
      console.error('Failed to fetch workflows', err);
    } finally {
      setLoading(false);
    }
  }, [activeWorkflow]);

  useEffect(() => {
    fetchWorkflows();
  }, []);

  const handleCreateNew = () => {
    const newWf: WorkflowData = {
      id: `wf_${Date.now().toString(36)}`,
      name: 'New Operational Workflow',
      description: 'Trigger -> Agent -> Approval -> Deliverable pipeline',
      graph: {
        nodes: [
          {
            id: 'node_trig_1',
            type: 'trigger',
            title: 'Schedule Trigger (Weekly)',
            config: { type: 'schedule', cron: '0 9 * * 1' },
            position: { x: 50, y: 150 },
          },
          {
            id: 'node_agent_1',
            type: 'agent',
            title: 'Security Auditor Agent',
            config: { agent_name: 'SecurityAuditor', prompt: 'Audit codebase dependencies for CVEs' },
            position: { x: 300, y: 150 },
          },
          {
            id: 'node_appr_1',
            type: 'approval',
            title: 'Operator Clearance Checkpoint',
            config: { tier: 'supervised' },
            position: { x: 550, y: 150 },
          },
          {
            id: 'node_deliv_1',
            type: 'deliverable',
            title: 'Audit Report Deliverable',
            config: { output_format: 'markdown', target_path: 'reports/security.md' },
            position: { x: 800, y: 150 },
          },
        ],
        edges: [
          { id: 'edge_1', source: 'node_trig_1', target: 'node_agent_1' },
          { id: 'edge_2', source: 'node_agent_1', target: 'node_appr_1' },
          { id: 'edge_3', source: 'node_appr_1', target: 'node_deliv_1' },
        ],
      },
    };
    setActiveWorkflow(newWf);
    setSelectedNodeId('node_trig_1');
  };

  const handleAddNode = (type: NodeType) => {
    if (!activeWorkflow) return;
    const count = activeWorkflow.graph.nodes.length + 1;
    const titles: Record<NodeType, string> = {
      trigger: 'Manual Trigger',
      agent: 'Specialist Agent',
      tool: 'GitHub Issue Tool',
      approval: 'Operator Clearance',
      deliverable: 'Dossier Deliverable',
    };
    const defaultConfigs: Record<NodeType, any> = {
      trigger: { type: 'manual' },
      agent: { agent_name: 'Coder', prompt: 'Implement task requirements' },
      tool: { tool_id: 'github.create_issue', params: { title: 'Workflow Issue' } },
      approval: { tier: 'supervised' },
      deliverable: { output_format: 'markdown', target_path: 'deliverables/summary.md' },
    };

    const newNode: WorkflowNode = {
      id: `node_${type}_${Date.now().toString(36)}`,
      type,
      title: `${titles[type]} #${count}`,
      config: defaultConfigs[type],
      position: { x: 100 + (count % 4) * 220, y: 120 + Math.floor(count / 4) * 160 },
    };

    setActiveWorkflow({
      ...activeWorkflow,
      graph: {
        ...activeWorkflow.graph,
        nodes: [...activeWorkflow.graph.nodes, newNode],
      },
    });
    setSelectedNodeId(newNode.id);
  };

  const handleSaveWorkflow = async () => {
    if (!activeWorkflow) return;
    try {
      const res = await fetch(apiUrl('/api/workflows'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(activeWorkflow),
      });
      if (!res.ok) throw await apiError(res, 'Failed to save workflow');
      const saved = await res.json();
      setActiveWorkflow(saved);
      showToast('Workflow saved successfully', 'success');
      fetchWorkflows();
    } catch (err: any) {
      showToast(err.message || 'Failed to save workflow', 'error');
    }
  };

  const handleCompileAndRun = async () => {
    if (!activeWorkflow) return;
    setCompiling(true);
    try {
      // 1. Save first
      await fetch(apiUrl('/api/workflows'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(activeWorkflow),
      });

      // 2. Run
      const res = await fetch(apiUrl(`/api/workflows/${activeWorkflow.id}/run`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ params: {} }),
      });
      if (!res.ok) throw await apiError(res, 'Failed to compile and run workflow');
      const missionData = await res.json();
      showToast(`Workflow compiled into Mission '${missionData.title}'!`, 'success');
      if (navigate) {
        navigate('missions', missionData.mission_id);
      }
    } catch (err: any) {
      showToast(err.message || 'Workflow execution error', 'error');
    } finally {
      setCompiling(false);
    }
  };

  const handleConnectClick = (nodeId: string) => {
    if (!connectingSource) {
      setConnectingSource(nodeId);
      showToast('Select target node to connect', 'info');
    } else {
      if (connectingSource === nodeId) {
        setConnectingSource(null);
        return;
      }
      // Add edge
      const newEdge: WorkflowEdge = {
        id: `edge_${Date.now().toString(36)}`,
        source: connectingSource,
        target: nodeId,
      };
      if (activeWorkflow) {
        setActiveWorkflow({
          ...activeWorkflow,
          graph: {
            ...activeWorkflow.graph,
            edges: [...activeWorkflow.graph.edges, newEdge],
          },
        });
        showToast('Connection established', 'success');
      }
      setConnectingSource(null);
    }
  };

  const handleDeleteNode = (nodeId: string) => {
    if (!activeWorkflow) return;
    setActiveWorkflow({
      ...activeWorkflow,
      graph: {
        nodes: activeWorkflow.graph.nodes.filter(n => n.id !== nodeId),
        edges: activeWorkflow.graph.edges.filter(e => e.source !== nodeId && e.target !== nodeId),
      },
    });
    if (selectedNodeId === nodeId) setSelectedNodeId(null);
  };

  const selectedNode = activeWorkflow?.graph.nodes.find(n => n.id === selectedNodeId);

  const getNodeIcon = (type: NodeType) => {
    switch (type) {
      case 'trigger': return <Clock size={16} className="text-amber-500" />;
      case 'agent': return <Bot size={16} className="text-indigo-500" />;
      case 'tool': return <Wrench size={16} className="text-emerald-500" />;
      case 'approval': return <ShieldCheck size={16} className="text-rose-500" />;
      case 'deliverable': return <FileCheck size={16} className="text-sky-500" />;
    }
  };

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <TopHeader
        title="Visual Workflow Builder"
        icon={WorkflowIcon}
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button className="btn btn-secondary" onClick={handleCreateNew}>
              <Plus size={15} /> New Workflow
            </button>
            <button className="btn btn-secondary" onClick={handleSaveWorkflow} disabled={!activeWorkflow}>
              <Save size={15} /> Save Blueprint
            </button>
            <button
              className="btn btn-primary"
              onClick={handleCompileAndRun}
              disabled={!activeWorkflow || compiling}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              {compiling ? <RefreshCw size={15} className="animate-spin" /> : <Play size={15} />}
              Compile & Run as Mission
            </button>
          </div>
        }
      />

      {/* Main Canvas Area */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' }}>
        {/* Node Toolbar */}
        <div style={{
          width: '220px',
          borderRight: '1px solid hsl(var(--border))',
          backgroundColor: 'hsl(var(--card))',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          overflowY: 'auto',
        }}>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase' }}>
            Workflow Nodes
          </div>
          <button className="btn btn-ghost" style={{ justifyContent: 'flex-start', gap: '8px', padding: '8px' }} onClick={() => handleAddNode('trigger')}>
            <Clock size={16} className="text-amber-500" /> + Trigger Node
          </button>
          <button className="btn btn-ghost" style={{ justifyContent: 'flex-start', gap: '8px', padding: '8px' }} onClick={() => handleAddNode('agent')}>
            <Bot size={16} className="text-indigo-500" /> + Agent Worker
          </button>
          <button className="btn btn-ghost" style={{ justifyContent: 'flex-start', gap: '8px', padding: '8px' }} onClick={() => handleAddNode('tool')}>
            <Wrench size={16} className="text-emerald-500" /> + Action / Tool
          </button>
          <button className="btn btn-ghost" style={{ justifyContent: 'flex-start', gap: '8px', padding: '8px' }} onClick={() => handleAddNode('approval')}>
            <ShieldCheck size={16} className="text-rose-500" /> + Human Approval
          </button>
          <button className="btn btn-ghost" style={{ justifyContent: 'flex-start', gap: '8px', padding: '8px' }} onClick={() => handleAddNode('deliverable')}>
            <FileCheck size={16} className="text-sky-500" /> + Deliverable Output
          </button>

          <hr style={{ borderColor: 'hsl(var(--border))', margin: '8px 0' }} />

          <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase' }}>
            Saved Blueprints
          </div>
          {workflows.map(w => (
            <div
              key={w.id}
              onClick={() => { setActiveWorkflow(w); setSelectedNodeId(null); }}
              style={{
                padding: '8px 10px',
                borderRadius: '6px',
                cursor: 'pointer',
                backgroundColor: activeWorkflow?.id === w.id ? 'hsl(var(--primary)/0.12)' : 'transparent',
                border: activeWorkflow?.id === w.id ? '1px solid hsl(var(--primary)/0.3)' : '1px solid transparent',
              }}
            >
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))' }}>{w.name}</div>
              <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>{w.graph.nodes.length} nodes</div>
            </div>
          ))}
        </div>

        {/* Visual Graph Canvas */}
        <div style={{
          flex: 1,
          backgroundColor: 'hsl(var(--bg))',
          backgroundImage: 'radial-gradient(hsl(var(--border)/0.4) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          position: 'relative',
          overflow: 'auto',
          padding: '40px',
        }}>
          {!activeWorkflow ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <WorkflowIcon size={48} className="text-muted" style={{ marginBottom: '16px' }} />
              <div style={{ fontSize: '16px', fontWeight: 600 }}>No Workflow Selected</div>
              <p style={{ color: 'hsl(var(--muted-fg))', fontSize: '13px', marginTop: '4px' }}>
                Select an existing blueprint or create a new visual DAG workflow.
              </p>
              <button className="btn btn-primary" onClick={handleCreateNew} style={{ marginTop: '16px' }}>
                <Plus size={15} /> Create First Workflow
              </button>
            </div>
          ) : (
            <div style={{ position: 'relative', minWidth: '1000px', minHeight: '600px' }}>
              {/* Directed Edges SVG Canvas */}
              <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
                <defs>
                  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="hsl(var(--primary))" />
                  </marker>
                </defs>
                {activeWorkflow.graph.edges.map(edge => {
                  const srcNode = activeWorkflow.graph.nodes.find(n => n.id === edge.source);
                  const tgtNode = activeWorkflow.graph.nodes.find(n => n.id === edge.target);
                  if (!srcNode || !tgtNode) return null;

                  const x1 = srcNode.position.x + 220;
                  const y1 = srcNode.position.y + 40;
                  const x2 = tgtNode.position.x;
                  const y2 = tgtNode.position.y + 40;
                  const dx = (x2 - x1) * 0.5;

                  return (
                    <path
                      key={edge.id}
                      d={`M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`}
                      fill="none"
                      stroke="hsl(var(--primary))"
                      strokeWidth="2.5"
                      markerEnd="url(#arrow)"
                      strokeDasharray="4 2"
                    />
                  );
                })}
              </svg>

              {/* Render Workflow Nodes */}
              {activeWorkflow.graph.nodes.map(node => (
                <div
                  key={node.id}
                  onClick={() => setSelectedNodeId(node.id)}
                  style={{
                    position: 'absolute',
                    left: `${node.position.x}px`,
                    top: `${node.position.y}px`,
                    width: '220px',
                    borderRadius: '10px',
                    backgroundColor: 'hsl(var(--card))',
                    border: selectedNodeId === node.id ? '2px solid hsl(var(--primary))' : '1px solid hsl(var(--border))',
                    boxShadow: selectedNodeId === node.id ? '0 8px 24px hsl(var(--primary)/0.2)' : '0 4px 12px rgba(0,0,0,0.1)',
                    padding: '12px',
                    cursor: 'pointer',
                    userSelect: 'none',
                    zIndex: 10,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {getNodeIcon(node.type)}
                      <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                        {node.type}
                      </span>
                    </div>
                    <button
                      className="btn btn-ghost"
                      style={{ padding: '2px 4px', color: 'hsl(var(--muted-fg))' }}
                      onClick={(e) => { e.stopPropagation(); handleDeleteNode(node.id); }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>

                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))', marginBottom: '4px' }}>
                    {node.title}
                  </div>

                  <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {node.type === 'agent' && `Agent: ${node.config.agent_name || 'Coder'}`}
                    {node.type === 'trigger' && `Type: ${node.config.type || 'Manual'}`}
                    {node.type === 'tool' && `Tool: ${node.config.tool_id || 'Action'}`}
                    {node.type === 'approval' && `Tier: ${node.config.tier || 'Supervised'}`}
                    {node.type === 'deliverable' && `Out: ${node.config.output_format || 'Markdown'}`}
                  </div>

                  <div style={{ marginTop: '10px', display: 'flex', justifyContent: 'flex-end' }}>
                    <button
                      className="btn btn-secondary"
                      style={{
                        padding: '3px 8px',
                        fontSize: '11px',
                        backgroundColor: connectingSource === node.id ? 'hsl(var(--primary))' : undefined,
                        color: connectingSource === node.id ? '#fff' : undefined,
                      }}
                      onClick={(e) => { e.stopPropagation(); handleConnectClick(node.id); }}
                    >
                      {connectingSource === node.id ? 'Target?' : 'Connect'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Node Properties Inspector Sidebar */}
        {selectedNode && (
          <div style={{
            width: '280px',
            borderLeft: '1px solid hsl(var(--border))',
            backgroundColor: 'hsl(var(--card))',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '14px',
            overflowY: 'auto',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'hsl(var(--primary))' }}>
                Inspector: {selectedNode.type}
              </div>
              <button className="btn btn-ghost" style={{ padding: '2px' }} onClick={() => setSelectedNodeId(null)}>
                <X size={15} />
              </button>
            </div>

            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Title</label>
              <input
                className="form-input"
                style={{ width: '100%', padding: '6px 8px', fontSize: '13px' }}
                value={selectedNode.title}
                onChange={(e) => {
                  const val = e.target.value;
                  setActiveWorkflow(prev => prev ? ({
                    ...prev,
                    graph: {
                      ...prev.graph,
                      nodes: prev.graph.nodes.map(n => n.id === selectedNode.id ? { ...n, title: val } : n),
                    }
                  }) : null);
                }}
              />
            </div>

            {selectedNode.type === 'agent' && (
              <>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Agent Name / Role</label>
                  <input
                    className="form-input"
                    style={{ width: '100%', padding: '6px 8px', fontSize: '13px' }}
                    value={selectedNode.config.agent_name || ''}
                    onChange={(e) => {
                      const val = e.target.value;
                      setActiveWorkflow(prev => prev ? ({
                        ...prev,
                        graph: {
                          ...prev.graph,
                          nodes: prev.graph.nodes.map(n => n.id === selectedNode.id ? { ...n, config: { ...n.config, agent_name: val } } : n),
                        }
                      }) : null);
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Prompt / Directive</label>
                  <textarea
                    className="form-input"
                    rows={4}
                    style={{ width: '100%', padding: '6px 8px', fontSize: '12px' }}
                    value={selectedNode.config.prompt || ''}
                    onChange={(e) => {
                      const val = e.target.value;
                      setActiveWorkflow(prev => prev ? ({
                        ...prev,
                        graph: {
                          ...prev.graph,
                          nodes: prev.graph.nodes.map(n => n.id === selectedNode.id ? { ...n, config: { ...n.config, prompt: val } } : n),
                        }
                      }) : null);
                    }}
                  />
                </div>
              </>
            )}

            {selectedNode.type === 'trigger' && (
              <>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Trigger Type</label>
                  <select
                    className="form-input"
                    style={{ width: '100%', padding: '6px 8px', fontSize: '13px' }}
                    value={selectedNode.config.type || 'manual'}
                    onChange={(e) => {
                      const val = e.target.value;
                      setActiveWorkflow(prev => prev ? ({
                        ...prev,
                        graph: {
                          ...prev.graph,
                          nodes: prev.graph.nodes.map(n => n.id === selectedNode.id ? { ...n, config: { ...n.config, type: val } } : n),
                        }
                      }) : null);
                    }}
                  >
                    <option value="manual">Manual Execution</option>
                    <option value="schedule">Schedule (Cron)</option>
                    <option value="file_watcher">File Watcher</option>
                    <option value="webhook">Webhook</option>
                  </select>
                </div>
                {selectedNode.config.type === 'schedule' && (
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Cron Expression</label>
                    <input
                      className="form-input"
                      style={{ width: '100%', padding: '6px 8px', fontSize: '13px' }}
                      value={selectedNode.config.cron || '0 9 * * 1'}
                      onChange={(e) => {
                        const val = e.target.value;
                        setActiveWorkflow(prev => prev ? ({
                          ...prev,
                          graph: {
                            ...prev.graph,
                            nodes: prev.graph.nodes.map(n => n.id === selectedNode.id ? { ...n, config: { ...n.config, cron: val } } : n),
                          }
                        }) : null);
                      }}
                    />
                  </div>
                )}
              </>
            )}

            {selectedNode.type === 'approval' && (
              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Autopilot Clearance Tier</label>
                <select
                  className="form-input"
                  style={{ width: '100%', padding: '6px 8px', fontSize: '13px' }}
                  value={selectedNode.config.tier || 'supervised'}
                  onChange={(e) => {
                    const val = e.target.value;
                    setActiveWorkflow(prev => prev ? ({
                      ...prev,
                      graph: {
                        ...prev.graph,
                        nodes: prev.graph.nodes.map(n => n.id === selectedNode.id ? { ...n, config: { ...n.config, tier: val } } : n),
                      }
                    }) : null);
                  }}
                >
                  <option value="supervised">Tier 2: Supervised Checkpoint</option>
                  <option value="manual">Tier 0: Mandatory Manual Approval</option>
                  <option value="assisted">Tier 1: Assisted Clearance</option>
                </select>
              </div>
            )}

            {selectedNode.type === 'deliverable' && (
              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>Target Artifact Path</label>
                <input
                  className="form-input"
                  style={{ width: '100%', padding: '6px 8px', fontSize: '13px' }}
                  value={selectedNode.config.target_path || 'deliverables/summary.md'}
                  onChange={(e) => {
                    const val = e.target.value;
                    setActiveWorkflow(prev => prev ? ({
                      ...prev,
                      graph: {
                        ...prev.graph,
                        nodes: prev.graph.nodes.map(n => n.id === selectedNode.id ? { ...n, config: { ...n.config, target_path: val } } : n),
                      }
                    }) : null);
                  }}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
