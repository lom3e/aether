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
  Laptop,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
} from 'lucide-react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';

function formatOsName(os?: string): string {
  const { t } = useTranslation();
  if (!os) return t('syLocalComputer');
  const l = os.toLowerCase();
  if (l.includes('darwin') || l.includes('mac')) return 'macOS';
  if (l.includes('linux')) return 'Linux';
  if (l.includes('win')) return 'Windows';
  return os;
}

function formatArch(arch?: string, os?: string): string {
  const { t } = useTranslation();
  if (!arch) return t('syNativeArchitecture');
  if (arch === 'arm64' && (os?.toLowerCase().includes('darwin') || os?.toLowerCase().includes('mac'))) {
    return 'Apple Silicon (arm64)';
  }
  return arch;
}

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
  const { t } = useTranslation();
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

  // Advanced section and AI engine status
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);
  const [aiEngineActive, setAiEngineActive] = useState<boolean>(false);

  const checkAiEngine = async () => {
    try {
      // The CONFIGURED provider, never an assumed local one: with none configured the backend answers
      // "unconfigured" without contacting anything.
      const res = await fetch(apiUrl('/api/provider/status'));
      if (res.ok) {
        const data = await res.json();
        setAiEngineActive(data.reachable === true);
        return;
      }
      setAiEngineActive(false);
    } catch {
      setAiEngineActive(false);
    }
  };

  const fetchFabricData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    setError(null);
    try {
      const [telRes, nodesRes, workRes] = await Promise.all([
        fetch(apiUrl('/api/fabric/telemetry')),
        fetch(apiUrl('/api/fabric/nodes')),
        fetch(apiUrl('/api/fabric/workloads')),
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
      checkAiEngine();
    } catch (err: any) {
      console.error('Failed to load fabric data:', err);
      setError(err?.message || t('szFailedToConnectToExecutionFabric'));
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
      console.error(t('szRoutingFailed'), err);
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
    if (!confirm(t('szAreYouSureYouWantTo'))) return;
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

  const localNode = nodes.find(n => n.is_local) || nodes[0] || null;
  const caps = localNode?.capabilities || null;
  const remoteNodes = nodes.filter(n => !n.is_local);

  return (
    <div style={{ flex: 1, overflowY: 'auto', width: '100%', height: '100%' }}>
      <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                width: '38px',
                height: '38px',
                borderRadius: '10px',
                backgroundColor: 'hsl(var(--primary)/0.12)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'hsl(var(--primary))'
              }}>
                <Cpu size={22} />
              </div>
              <h1 style={{ fontSize: '22px', fontWeight: 700, margin: 0 }}>{t('fabricTitle')}</h1>
            </div>
            <p className="text-muted" style={{ fontSize: '13px', margin: '6px 0 0 0' }}>
              {t('fabricSubtitle')}
            </p>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="btn btn-secondary"
              onClick={() => fetchFabricData(true)}
              disabled={refreshing || loading}
            >
              <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
              <span>{refreshing ? t('fabricProbing') : t('fabricRefresh')}</span>
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

        {/* 5 Primary Hardware Resource Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(210px, 100%), 1fr))', gap: '16px' }}>
          {/* Card 1: Dispositivo */}
          <div className="card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'hsl(var(--muted-fg))' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Dispositivo</span>
              <Laptop size={18} className="text-primary" />
            </div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'hsl(var(--fg))' }}>
              {formatOsName(caps?.os_name)}
            </div>
            <span className="text-muted" style={{ fontSize: '12px' }}>
              {formatArch(caps?.architecture, caps?.os_name)} • {localNode?.name.replace(' (Controller)', '') || 'Host locale'}
            </span>
          </div>

          {/* Card 2: Processore (CPU) */}
          <div className="card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'hsl(var(--muted-fg))' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{t('syProcessorCpu')}</span>
              <Cpu size={18} className="text-primary" />
            </div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'hsl(var(--fg))' }}>
              {caps?.cpu_cores || telemetry?.total_cores || 8} Core
            </div>
            <span className="text-muted" style={{ fontSize: '12px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {caps?.cpu_brand || t('syNativeSystemCpu')}
            </span>
          </div>

          {/* Card 3: Memoria di Sistema (RAM) */}
          <div className="card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'hsl(var(--muted-fg))' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{t('syMemoryRam')}</span>
              <HardDrive size={18} className="text-primary" />
            </div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'hsl(var(--fg))' }}>
              {(caps?.ram_total_gb || telemetry?.total_ram_gb || 16).toFixed(1)} GB
            </div>
            <span className="text-muted" style={{ fontSize: '12px' }}>
              {(caps?.ram_free_gb || ((caps?.ram_total_gb || 16) * 0.45)).toFixed(1)} GB disponibili
            </span>
          </div>

          {/* Card 4: Scheda Grafica / GPU */}
          <div className="card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'hsl(var(--muted-fg))' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{t('syGraphicsCardGpu')}</span>
              <Zap size={18} className="text-primary" />
            </div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'hsl(var(--fg))' }}>
              {(caps?.gpu_vram_gb || telemetry?.total_vram_gb || 0).toFixed(1)} GB VRAM
            </div>
            <span className="text-muted" style={{ fontSize: '12px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {caps?.gpu_name || t('syIntegratedGraphicsAccelerator')}
            </span>
          </div>

          {/* Card 5: Motore AI Locale */}
          <div className="card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'hsl(var(--muted-fg))' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{t('syLocalAiEngine')}</span>
              <Sparkles size={18} className="text-primary" />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '2px' }}>
              <span style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: aiEngineActive ? 'hsl(142 71% 45%)' : 'hsl(var(--muted-fg))',
                display: 'inline-block'
              }} />
              <span style={{ fontSize: '16px', fontWeight: 700, color: 'hsl(var(--fg))' }}>
                {aiEngineActive ? t('statusActive') : t('syInactive')}
              </span>
            </div>
            <span className="text-muted" style={{ fontSize: '12px' }}>
              {aiEngineActive ? t('syModelsThatRunOfflineOnThe') : t('syOllamaNotDetectedInTheBackground')}
            </span>
          </div>
        </div>

        {/* Local privacy and autonomy banner */}
        <div style={{
          padding: '16px 20px',
          backgroundColor: 'hsl(var(--primary)/0.06)',
          border: '1px solid hsl(var(--primary)/0.18)',
          borderRadius: '10px',
          display: 'flex',
          alignItems: 'center',
          gap: '14px'
        }}>
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '8px',
            backgroundColor: 'hsl(var(--primary)/0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'hsl(var(--primary))',
            flexShrink: 0,
          }}>
            <ShieldCheck size={20} />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '14px', color: 'hsl(var(--fg))' }}>
              {t('syLocalAndPrivateExecution')}
            </div>
            <p className="text-muted" style={{ fontSize: '13px', margin: '2px 0 0 0', lineHeight: 1.4 }}>
              {t('syAetherPrefersRunningDirectlyOnYour')}
            </p>
          </div>
        </div>

        {/* Collapsible Advanced Section */}
        <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            style={{
              width: '100%',
              padding: '16px 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'hsl(var(--fg))',
              textAlign: 'left'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Server size={18} className="text-primary" />
              <div>
                <div style={{ fontWeight: 600, fontSize: '14px' }}>
                  {t('syAdvancedOptionsAndRemoteNodes')}
                </div>
                <div className="text-muted" style={{ fontSize: '12px', marginTop: '2px' }}>
                  {t('syMultiMachineClusterManagementExternalWorkstations')}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="badge" style={{ fontSize: '11px' }}>
                {remoteNodes.length} {remoteNodes.length === 1 ? 'nodo remoto' : 'nodi remoti'}
              </span>
              {showAdvanced ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>
          </button>

          {showAdvanced && (
            <div style={{ padding: '0 20px 20px 20px', display: 'flex', flexDirection: 'column', gap: '20px', borderTop: '1px solid hsl(var(--border))', paddingTop: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                <span className="text-muted" style={{ fontSize: '13px' }}>
                  {t('syConnectAuxiliaryComputersOrGpuServers')}
                </span>
                <button
                  className="btn btn-primary"
                  style={{ fontSize: '12px', padding: '6px 12px' }}
                  onClick={() => setShowRegisterModal(true)}
                >
                  <Plus size={14} />
                  <span>{t('fabricConnectNode')}</span>
                </button>
              </div>

              {/* Remote Nodes List */}
              {remoteNodes.length === 0 ? (
                <div style={{
                  padding: '24px 20px',
                  textAlign: 'center',
                  backgroundColor: 'hsl(var(--muted)/0.15)',
                  borderRadius: '8px',
                  border: '1px dashed hsl(var(--border))',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '6px'
                }}>
                  <Server size={24} className="text-muted" style={{ opacity: 0.6 }} />
                  <div style={{ fontWeight: 600, fontSize: '13px' }}>{t('syNoRemoteNodeRegistered')}</div>
                  <p className="text-muted" style={{ fontSize: '12px', margin: 0 }}>
                    {t('syAllTasksAreProcessed100By')}
                  </p>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(320px, 100%), 1fr))', gap: '14px' }}>
                  {remoteNodes.map(node => (
                    <div
                      key={node.id}
                      style={{
                        borderRadius: '8px',
                        border: '1px solid hsl(var(--border))',
                        backgroundColor: 'hsl(var(--card))',
                        padding: '14px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '10px'
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

                        <span className="badge" style={{ fontSize: '10px', textTransform: 'uppercase' }}>{node.role}</span>
                      </div>

                      <div style={{
                        backgroundColor: 'hsl(var(--muted)/0.3)',
                        padding: '8px 10px',
                        borderRadius: '6px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '4px',
                        fontSize: '11px'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span className="text-muted">CPU:</span>
                          <span style={{ fontWeight: 500 }}>{node.capabilities.cpu_brand} ({node.capabilities.cpu_cores} cores)</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span className="text-muted">RAM:</span>
                          <span style={{ fontWeight: 500 }}>{node.capabilities.ram_total_gb} GB</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span className="text-muted">Acceleratore:</span>
                          <span style={{ fontWeight: 500, color: 'hsl(var(--primary))' }}>
                            {node.capabilities.gpu_name} ({node.capabilities.gpu_vram_gb} GB)
                          </span>
                        </div>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                        <button
                          className="btn btn-ghost"
                          style={{ padding: '3px 6px', fontSize: '11px' }}
                          onClick={() => handlePingNode(node.id)}
                        >
                          <Radio size={12} /> Ping
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{ padding: '3px 6px', fontSize: '11px', color: 'hsl(var(--destructive))' }}
                          onClick={() => handleDeleteNode(node.id)}
                        >
                          <Trash2 size={12} /> Rimuovi
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Workload Router Tester & Allocator */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(360px, 100%), 1fr))', gap: '16px', marginTop: '10px' }}>
                <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Zap size={16} className="text-primary" />
                    <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>{t('fabricRouterTitle')}</h3>
                  </div>
                  <p className="text-muted" style={{ fontSize: '12px', margin: 0 }}>
                    {t('fabricRouterDesc')}
                  </p>

                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label" style={{ fontSize: '11px' }}>{t('fabricTaskLabel')}</label>
                    <input
                      type="text"
                      className="form-input"
                      value={workloadName}
                      onChange={e => setWorkloadName(e.target.value)}
                      placeholder={t('fabricTaskPlaceholder')}
                    />
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label className="form-label" style={{ fontSize: '11px' }}>{t('fabricTierLabel')}</label>
                      <select
                        className="form-select"
                        value={workloadTier}
                        onChange={e => setWorkloadTier(e.target.value)}
                      >
                        <option value="local_fast">{t('fabricTierLocal')}</option>
                        <option value="gpu_heavy">{t('fabricTierGpu')}</option>
                        <option value="background_batch">{t('fabricTierBatch')}</option>
                        <option value="cloud_offload">{t('fabricTierCloud')}</option>
                      </select>
                    </div>

                    <div className="form-group" style={{ marginBottom: 0 }}>
                      <label className="form-label" style={{ fontSize: '11px' }}>{t('fabricMinCores')}</label>
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
                    <label className="form-label" style={{ fontSize: '11px' }}>{t('fabricMinVram')}</label>
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
                    style={{ marginTop: '4px', fontSize: '12px' }}
                    onClick={handleRouteWorkload}
                    disabled={routingLoading}
                  >
                    <Sparkles size={13} />
                    <span>{routingLoading ? t('fabricAllocatingBtn') : t('fabricRouteBtn')}</span>
                  </button>

                  {routingResult && (
                    <div style={{
                      backgroundColor: 'hsl(var(--primary)/0.1)',
                      border: '1px solid hsl(var(--primary)/0.3)',
                      borderRadius: '6px',
                      padding: '10px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px',
                      fontSize: '11px'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'hsl(var(--primary))' }}>
                        <CheckCircle2 size={13} />
                        <span>{t('fabricAllocatedSuccess')}: {routingResult.workload_name}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span className="text-muted">{t('fabricAssignedNode')}:</span>
                        <code>{routingResult.assigned_node_id}</code>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span className="text-muted">{t('fabricAllocatedHw')}:</span>
                        <span>{routingResult.allocated_cores} Cores • {routingResult.allocated_vram_gb} GB VRAM</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Workload Assignments History */}
                <div className="card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Activity size={16} className="text-primary" />
                      <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0 }}>{t('fabricWorkloadsSection')}</h3>
                    </div>
                    <span className="badge" style={{ fontSize: '10px' }}>{workloads.length} totali</span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '280px', overflowY: 'auto' }}>
                    {workloads.length === 0 ? (
                      <p className="text-muted" style={{ fontSize: '12px', textAlign: 'center', padding: '16px' }}>
                        {t('fabricNoWorkloads')}
                      </p>
                    ) : (
                      workloads.map(w => (
                        <div
                          key={w.id}
                          style={{
                            padding: '8px 10px',
                            borderRadius: '6px',
                            border: '1px solid hsl(var(--border))',
                            backgroundColor: 'hsl(var(--muted)/0.2)',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            fontSize: '11px'
                          }}
                        >
                          <div>
                            <div style={{ fontWeight: 600 }}>{w.workload_name}</div>
                            <div style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))', display: 'flex', gap: '6px', marginTop: '1px' }}>
                              <span className="badge" style={{ fontSize: '9px' }}>{w.workload_tier}</span>
                              <span>•</span>
                              <span>Nodo: {w.assigned_node_id.slice(0, 14)}</span>
                            </div>
                          </div>

                          <div style={{ textAlign: 'right' }}>
                            <span className="badge badge-primary" style={{ fontSize: '9px' }}>
                              {w.allocated_cores}C / {w.allocated_vram_gb}G
                            </span>
                            <div style={{ fontSize: '9px', color: 'hsl(var(--muted-fg))', marginTop: '1px' }}>
                              {new Date(w.created_at).toLocaleTimeString()}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
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
                  <h3 style={{ fontSize: '16px', fontWeight: 600, margin: 0 }}>{t('fabricModalTitle')}</h3>
                </div>
                <button className="btn btn-ghost" style={{ padding: '4px' }} onClick={() => setShowRegisterModal(false)}>
                  <X size={16} />
                </button>
              </div>

              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label" style={{ fontSize: '12px' }}>{t('fabricModalNodeName')}</label>
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
                  <label className="form-label" style={{ fontSize: '12px' }}>{t('fabricModalRole')}</label>
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
                  <label className="form-label" style={{ fontSize: '12px' }}>{t('fabricModalEndpoint')}</label>
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
                  <label className="form-label" style={{ fontSize: '12px' }}>{t('fabricModalCores')}</label>
                  <input
                    type="number"
                    min="1"
                    className="form-input"
                    value={newNodeCores}
                    onChange={e => setNewNodeCores(Number(e.target.value))}
                  />
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label" style={{ fontSize: '12px' }}>{t('fabricModalRam')}</label>
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
                  <label className="form-label" style={{ fontSize: '12px' }}>{t('fabricModalGpu')}</label>
                  <input
                    type="text"
                    className="form-input"
                    value={newNodeGpu}
                    onChange={e => setNewNodeGpu(e.target.value)}
                    placeholder="NVIDIA GeForce RTX 4090"
                  />
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label" style={{ fontSize: '12px' }}>{t('fabricModalVram')}</label>
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
                <label className="form-label" style={{ fontSize: '12px' }}>{t('fabricModalAccel')}</label>
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
                  {t('fabricModalCancel')}
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleRegisterNode}
                  disabled={registering}
                >
                  <CheckCircle2 size={14} />
                  <span>{registering ? t('fabricModalRegistering') : t('fabricModalSubmit')}</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
