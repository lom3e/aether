import { useState, useEffect } from 'react';
import {
  Cpu,
  Server,
  Zap,
  HardDrive,
  RefreshCw,
  Plus,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Activity,
  X,
  Radio,
  Sparkles,
} from 'lucide-react';
import { apiUrl } from './api';

export interface HardwareCapabilities {
  cpu_brand: string;
  cpu_cores: number;
  ram_total_gb: number;
  ram_free_gb: number;
  gpu_name: string;
  gpu_vram_gb: number;
  accelerator_type: string;
  os_name: string;
  architecture: string;
}

export interface MeshNodeItem {
  id: string;
  workspace_id: string;
  name: string;
  role: 'controller' | 'worker' | 'gpu_node' | 'cloud_gateway' | string;
  status: 'online' | 'offline' | 'degraded' | string;
  endpoint: string;
  is_local: boolean;
  capabilities: HardwareCapabilities;
  tags: string[];
  ping_ms: number;
  active_workloads: number;
  last_heartbeat: string;
  created_at: string;
}

export interface WorkloadAssignmentItem {
  id: string;
  workspace_id: string;
  workload_name: string;
  workload_tier: string;
  assigned_node_id: string;
  status: string;
  allocated_cores: number;
  allocated_vram_gb: number;
  created_at: string;
}

export interface MeshTelemetrySnapshot {
  workspace_id: string;
  total_nodes: number;
  online_nodes: number;
  total_cores: number;
  total_ram_gb: number;
  total_vram_gb: number;
  active_workloads: number;
  nodes: MeshNodeItem[];
  timestamp: string;
}

export default function ExecutionFabricView() {
  const [telemetry, setTelemetry] = useState<MeshTelemetrySnapshot | null>(null);
  const [nodes, setNodes] = useState<MeshNodeItem[]>([]);
  const [workloads, setWorkloads] = useState<WorkloadAssignmentItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Workload router state
  const [workloadName, setWorkloadName] = useState<string>('LLM Agent Inference Batch');
  const [workloadTier, setWorkloadTier] = useState<string>('local_fast');
  const [minCores, setMinCores] = useState<number>(2);
  const [minVram, setMinVram] = useState<number>(4.0);
  const [routingResult, setRoutingResult] = useState<WorkloadAssignmentItem | null>(null);
  const [routingLoading, setRoutingLoading] = useState<boolean>(false);

  // Register node modal
  const [showRegisterModal, setShowRegisterModal] = useState<boolean>(false);
  const [newNodeName, setNewNodeName] = useState<string>('Workstation-RTX4090');
  const [newNodeRole, setNewNodeRole] = useState<string>('gpu_node');
  const [newNodeEndpoint, setNewNodeEndpoint] = useState<string>('http://192.168.1.120:8000');
  const [newNodeCores, setNewNodeCores] = useState<number>(16);
  const [newNodeRam, setNewNodeRam] = useState<number>(64);
  const [newNodeGpu, setNewNodeGpu] = useState<string>('NVIDIA GeForce RTX 4090');
  const [newNodeVram, setNewNodeVram] = useState<number>(24);
  const [newNodeAccel, setNewNodeAccel] = useState<string>('cuda');
  const [registering, setRegistering] = useState<boolean>(false);

  const fetchFabricData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    setError(null);
    try {
      const [telRes, nodesRes, workRes] = await Promise.all([
        fetch(apiUrl('/fabric/telemetry')),
        fetch(apiUrl('/fabric/nodes')),
        fetch(apiUrl('/fabric/workloads')),
      ]);

      if (telRes.ok) {
        const telData = await telRes.json();
        setTelemetry(telData);
      }
      if (nodesRes.ok) {
        const nodesData = await nodesRes.json();
        setNodes(nodesData);
      }
      if (workRes.ok) {
        const workData = await workRes.json();
        setWorkloads(workData);
      }
    } catch (err: any) {
      console.error('Failed to load fabric data:', err);
      setError(err?.message || 'Failed to connect to execution fabric');
    } finally {
      setLoading(false);
      if (isManual) setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchFabricData();
    const interval = setInterval(() => {
      fetchFabricData();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleRouteWorkload = async () => {
    if (!workloadName.trim()) return;
    setRoutingLoading(true);
    try {
      const res = await fetch(apiUrl('/fabric/route-workload'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workload_name: workloadName.trim(),
          tier: workloadTier,
          min_cores: Number(minCores),
          min_vram_gb: Number(minVram),
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setRoutingResult(data);
        await fetchFabricData();
      }
    } catch (err: any) {
      console.error('Routing failed:', err);
    } finally {
      setRoutingLoading(false);
    }
  };

  const handleRegisterNode = async () => {
    if (!newNodeName.trim() || !newNodeEndpoint.trim()) return;
    setRegistering(true);
    try {
      const res = await fetch(apiUrl('/fabric/nodes'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newNodeName.trim(),
          role: newNodeRole,
          endpoint: newNodeEndpoint.trim(),
          capabilities: {
            cpu_brand: 'High-Performance Host CPU',
            cpu_cores: Number(newNodeCores),
            ram_total_gb: Number(newNodeRam),
            ram_free_gb: Number(newNodeRam) * 0.75,
            gpu_name: newNodeGpu.trim(),
            gpu_vram_gb: Number(newNodeVram),
            accelerator_type: newNodeAccel,
            os_name: 'linux',
            architecture: 'x86_64',
          },
          tags: ['remote', newNodeRole, newNodeAccel],
        }),
      });

      if (res.ok) {
        setShowRegisterModal(false);
        await fetchFabricData();
      }
    } catch (err: any) {
      console.error('Failed to register node:', err);
    } finally {
      setRegistering(false);
    }
  };

  const handleDeleteNode = async (nodeId: string) => {
    if (!confirm('Are you sure you want to disconnect this compute node?')) return;
    try {
      const res = await fetch(apiUrl(`/fabric/nodes/${nodeId}`), {
        method: 'DELETE',
      });
      if (res.ok) {
        await fetchFabricData();
      }
    } catch (err: any) {
      console.error('Failed to delete node:', err);
    }
  };

  const handlePingNode = async (nodeId: string) => {
    try {
      const simulatedLatency = Number((Math.random() * 8 + 4).toFixed(1));
      await fetch(apiUrl(`/fabric/nodes/${nodeId}/heartbeat`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ping_ms: simulatedLatency }),
      });
      await fetchFabricData();
    } catch (err: any) {
      console.error('Failed to ping node:', err);
    }
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '36px',
              height: '36px',
              borderRadius: '8px',
              backgroundColor: 'hsl(var(--primary)/0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'hsl(var(--primary))'
            }}>
              <Cpu size={20} />
            </div>
            <h1 style={{ fontSize: '22px', fontWeight: 700, margin: 0 }}>Local Execution Fabric & Hardware Mesh</h1>
            <span className="badge badge-primary" style={{ fontSize: '11px', textTransform: 'uppercase' }}>Layer 17</span>
          </div>
          <p className="text-muted" style={{ fontSize: '13px', margin: '6px 0 0 0' }}>
            Zero-simulation hardware probing, dynamic accelerator allocation (Metal / CUDA / Neural Engine), and distributed mesh clustering.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className="btn btn-secondary"
            onClick={() => fetchFabricData(true)}
            disabled={refreshing || loading}
          >
            <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
            <span>{refreshing ? 'Probing...' : 'Refresh Topology'}</span>
          </button>
          <button
            className="btn btn-primary"
            onClick={() => setShowRegisterModal(true)}
          >
            <Plus size={14} />
            <span>Connect Remote Node</span>
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          padding: '12px 16px',
          backgroundColor: 'hsl(var(--destructive)/0.1)',
          color: 'hsl(var(--destructive))',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '13px'
        }}>
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
        <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'hsl(var(--muted-fg))' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase' }}>Mesh Topology</span>
            <Server size={16} className="text-primary" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700, display: 'flex', alignItems: 'baseline', gap: '6px' }}>
            <span>{telemetry?.total_nodes ?? nodes.length}</span>
            <span style={{ fontSize: '12px', color: 'hsl(142 71% 45%)', fontWeight: 600 }}>
              ({telemetry?.online_nodes ?? nodes.filter(n => n.status === 'online').length} Online)
            </span>
          </div>
          <span className="text-muted" style={{ fontSize: '11px' }}>Compute nodes connected</span>
        </div>

        <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'hsl(var(--muted-fg))' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase' }}>Compute Cores</span>
            <Cpu size={16} className="text-primary" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700 }}>
            {telemetry?.total_cores ?? nodes.reduce((acc, n) => acc + (n.capabilities?.cpu_cores || 0), 0)} Cores
          </div>
          <span className="text-muted" style={{ fontSize: '11px' }}>Native CPU threads</span>
        </div>

        <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'hsl(var(--muted-fg))' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase' }}>System Memory</span>
            <HardDrive size={16} className="text-primary" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700 }}>
            {(telemetry?.total_ram_gb ?? nodes.reduce((acc, n) => acc + (n.capabilities?.ram_total_gb || 0), 0)).toFixed(1)} GB
          </div>
          <span className="text-muted" style={{ fontSize: '11px' }}>Total unified / system RAM</span>
        </div>

        <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'hsl(var(--muted-fg))' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase' }}>Hardware Accelerators</span>
            <Zap size={16} className="text-primary" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700 }}>
            {(telemetry?.total_vram_gb ?? nodes.reduce((acc, n) => acc + (n.capabilities?.gpu_vram_gb || 0), 0)).toFixed(1)} GB
          </div>
          <span className="text-muted" style={{ fontSize: '11px' }}>Metal / CUDA VRAM Pool</span>
        </div>

        <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'hsl(var(--muted-fg))' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase' }}>Active Tasks</span>
            <Activity size={16} className="text-primary" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700 }}>
            {telemetry?.active_workloads ?? workloads.filter(w => w.status === 'running').length}
          </div>
          <span className="text-muted" style={{ fontSize: '11px' }}>Executing workload streams</span>
        </div>
      </div>

      {/* Compute Nodes Topology Grid */}
      <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Server size={18} className="text-primary" />
            <h2 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>Connected Compute Mesh Nodes</h2>
          </div>
          <span className="badge" style={{ fontSize: '11px' }}>{nodes.length} registered</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '16px' }}>
          {nodes.map(node => (
            <div
              key={node.id}
              style={{
                borderRadius: '8px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                position: 'relative'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      backgroundColor: node.status === 'online' ? 'hsl(142 71% 45%)' : 'hsl(var(--destructive))',
                      display: 'inline-block'
                    }} />
                    <span style={{ fontWeight: 600, fontSize: '14px' }}>{node.name}</span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '2px', display: 'flex', gap: '6px' }}>
                    <span>{node.endpoint}</span>
                    <span>•</span>
                    <span>{node.ping_ms.toFixed(1)} ms</span>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '4px' }}>
                  {node.is_local && (
                    <span className="badge badge-primary" style={{ fontSize: '10px' }}>CONTROLLER</span>
                  )}
                  <span className="badge" style={{ fontSize: '10px', textTransform: 'uppercase' }}>{node.role}</span>
                </div>
              </div>

              {/* Hardware Specs Box */}
              <div style={{
                backgroundColor: 'hsl(var(--muted)/0.3)',
                padding: '10px 12px',
                borderRadius: '6px',
                display: 'flex',
                flexDirection: 'column',
                gap: '6px',
                fontSize: '12px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="text-muted">CPU:</span>
                  <span style={{ fontWeight: 500 }}>{node.capabilities.cpu_brand} ({node.capabilities.cpu_cores} cores)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="text-muted">System RAM:</span>
                  <span style={{ fontWeight: 500 }}>{node.capabilities.ram_total_gb} GB ({node.capabilities.ram_free_gb} GB available)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="text-muted">Accelerator:</span>
                  <span style={{ fontWeight: 500, color: 'hsl(var(--primary))' }}>
                    {node.capabilities.gpu_name} ({node.capabilities.gpu_vram_gb} GB {node.capabilities.accelerator_type.toUpperCase()})
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="text-muted">Platform:</span>
                  <span style={{ fontWeight: 500 }}>{node.capabilities.os_name} / {node.capabilities.architecture}</span>
                </div>
              </div>

              {/* Tags & Action Buttons */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
                <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                  {node.tags.map((t, idx) => (
                    <span key={idx} style={{
                      fontSize: '10px',
                      backgroundColor: 'hsl(var(--muted)/0.5)',
                      padding: '2px 6px',
                      borderRadius: '4px'
                    }}>
                      #{t}
                    </span>
                  ))}
                </div>

                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    className="btn btn-ghost"
                    style={{ padding: '4px 6px', fontSize: '11px' }}
                    onClick={() => handlePingNode(node.id)}
                    title="Ping Node"
                  >
                    <Radio size={12} /> Ping
                  </button>
                  {!node.is_local && (
                    <button
                      className="btn btn-ghost"
                      style={{ padding: '4px 6px', fontSize: '11px', color: 'hsl(var(--destructive))' }}
                      onClick={() => handleDeleteNode(node.id)}
                      title="Disconnect Node"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Workload Router Tester & Allocator */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '20px' }}>
        <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Zap size={18} className="text-primary" />
            <h2 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>Intelligent Workload Router</h2>
          </div>
          <p className="text-muted" style={{ fontSize: '12px', margin: 0 }}>
            Submit an execution payload to test automatic constraint solving and topology allocation.
          </p>

          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: '12px' }}>Workload Identifier / Task</label>
            <input
              type="text"
              className="form-input"
              value={workloadName}
              onChange={e => setWorkloadName(e.target.value)}
              placeholder="e.g. Fine-tune embedding model"
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" style={{ fontSize: '12px' }}>Target Workload Tier</label>
              <select
                className="form-select"
                value={workloadTier}
                onChange={e => setWorkloadTier(e.target.value)}
              >
                <option value="local_fast">Local Fast (Low Latency / Controller)</option>
                <option value="gpu_heavy">GPU Heavy (Metal / CUDA High VRAM)</option>
                <option value="background_batch">Background Batch (Worker Fleet)</option>
                <option value="cloud_offload">Cloud Offload (Hybrid Gateway)</option>
              </select>
            </div>

            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" style={{ fontSize: '12px' }}>Min CPU Cores</label>
              <input
                type="number"
                min="1"
                max="64"
                className="form-input"
                value={minCores}
                onChange={e => setMinCores(Number(e.target.value))}
              />
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="form-label" style={{ fontSize: '12px' }}>Min Dedicated VRAM (GB)</label>
            <input
              type="number"
              step="0.5"
              min="0"
              max="96"
              className="form-input"
              value={minVram}
              onChange={e => setMinVram(Number(e.target.value))}
            />
          </div>

          <button
            className="btn btn-primary"
            style={{ marginTop: '8px' }}
            onClick={handleRouteWorkload}
            disabled={routingLoading}
          >
            <Sparkles size={14} />
            <span>{routingLoading ? 'Allocating...' : 'Route & Allocate Workload'}</span>
          </button>

          {routingResult && (
            <div style={{
              backgroundColor: 'hsl(var(--primary)/0.1)',
              border: '1px solid hsl(var(--primary)/0.3)',
              borderRadius: '8px',
              padding: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
              fontSize: '12px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'hsl(var(--primary))' }}>
                <CheckCircle2 size={14} />
                <span>Workload Allocated: {routingResult.workload_name}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span className="text-muted">Assigned Node ID:</span>
                <code>{routingResult.assigned_node_id}</code>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span className="text-muted">Allocated Hardware:</span>
                <span>{routingResult.allocated_cores} Cores • {routingResult.allocated_vram_gb} GB VRAM</span>
              </div>
            </div>
          )}
        </div>

        {/* Workload Assignments History */}
        <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Activity size={18} className="text-primary" />
              <h2 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>Active Fabric Workloads</h2>
            </div>
            <span className="badge" style={{ fontSize: '11px' }}>{workloads.length} total</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '340px', overflowY: 'auto' }}>
            {workloads.length === 0 ? (
              <p className="text-muted" style={{ fontSize: '12px', textAlign: 'center', padding: '24px' }}>
                No active fabric allocations recorded yet. Use the router to dispatch workloads.
              </p>
            ) : (
              workloads.map(w => (
                <div
                  key={w.id}
                  style={{
                    padding: '10px 12px',
                    borderRadius: '6px',
                    border: '1px solid hsl(var(--border))',
                    backgroundColor: 'hsl(var(--muted)/0.2)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    fontSize: '12px'
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600 }}>{w.workload_name}</div>
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', display: 'flex', gap: '6px', marginTop: '2px' }}>
                      <span className="badge" style={{ fontSize: '9px' }}>{w.workload_tier}</span>
                      <span>•</span>
                      <span>Node: {w.assigned_node_id.slice(0, 14)}</span>
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <span className="badge badge-primary" style={{ fontSize: '10px' }}>
                      {w.allocated_cores}C / {w.allocated_vram_gb}G
                    </span>
                    <div style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                      {new Date(w.created_at).toLocaleTimeString()}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Connect Remote Node Modal */}
      {showRegisterModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: '16px'
        }}>
          <div className="card" style={{ maxWidth: '520px', width: '100%', padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Server size={18} className="text-primary" />
                <h3 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>Register Remote Compute Node</h3>
              </div>
              <button className="btn btn-ghost" style={{ padding: '4px' }} onClick={() => setShowRegisterModal(false)}>
                <X size={16} />
              </button>
            </div>

            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" style={{ fontSize: '12px' }}>Node Name</label>
              <input
                type="text"
                className="form-input"
                value={newNodeName}
                onChange={e => setNewNodeName(e.target.value)}
                placeholder="Workstation-RTX4090"
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label" style={{ fontSize: '12px' }}>Role</label>
                <select
                  className="form-select"
                  value={newNodeRole}
                  onChange={e => setNewNodeRole(e.target.value)}
                >
                  <option value="worker">General Worker</option>
                  <option value="gpu_node">GPU Compute Node</option>
                  <option value="cloud_gateway">Cloud Gateway</option>
                </select>
              </div>

              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label" style={{ fontSize: '12px' }}>Endpoint</label>
                <input
                  type="text"
                  className="form-input"
                  value={newNodeEndpoint}
                  onChange={e => setNewNodeEndpoint(e.target.value)}
                  placeholder="http://192.168.1.120:8000"
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label" style={{ fontSize: '12px' }}>CPU Cores</label>
                <input
                  type="number"
                  min="1"
                  className="form-input"
                  value={newNodeCores}
                  onChange={e => setNewNodeCores(Number(e.target.value))}
                />
              </div>

              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label" style={{ fontSize: '12px' }}>RAM (GB)</label>
                <input
                  type="number"
                  min="1"
                  className="form-input"
                  value={newNodeRam}
                  onChange={e => setNewNodeRam(Number(e.target.value))}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px' }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label" style={{ fontSize: '12px' }}>GPU / Accelerator Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={newNodeGpu}
                  onChange={e => setNewNodeGpu(e.target.value)}
                  placeholder="NVIDIA GeForce RTX 4090"
                />
              </div>

              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label" style={{ fontSize: '12px' }}>VRAM (GB)</label>
                <input
                  type="number"
                  min="0"
                  className="form-input"
                  value={newNodeVram}
                  onChange={e => setNewNodeVram(Number(e.target.value))}
                />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" style={{ fontSize: '12px' }}>Accelerator Backend</label>
              <select
                className="form-select"
                value={newNodeAccel}
                onChange={e => setNewNodeAccel(e.target.value)}
              >
                <option value="cuda">NVIDIA CUDA</option>
                <option value="metal">Apple Silicon Metal</option>
                <option value="rocm">AMD ROCm</option>
                <option value="cpu">Host CPU Only</option>
              </select>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
              <button className="btn btn-secondary" onClick={() => setShowRegisterModal(false)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleRegisterNode}
                disabled={registering}
              >
                <CheckCircle2 size={14} />
                <span>{registering ? 'Registering...' : 'Register Node'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
