import React, { useState, useEffect, useContext, useCallback, useMemo, useRef } from 'react';
import {
  Target, Plus, CheckCircle, Circle, Play, AlertCircle, Trash2,
  Users, Layers, Sparkles, X, RefreshCw, Pause,
  Square, RotateCcw, FileText, MessageSquare, Check, ArrowLeft,
  Clock, ShieldAlert, ChevronRight, FileCode, Table, FolderArchive,
  Copy, Activity, Terminal, Workflow, User, ExternalLink, Download, FolderOpen,
  ChevronDown, ChevronUp
} from 'lucide-react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { ToastContext } from './toast';
import { Tooltip } from './Tooltip';
import { MarkdownRenderer } from './MarkdownRenderer';

interface AgentInfo {
  name: string;
  role: string;
  instructions?: string;
  provider?: string;
  model?: string;
  icon?: string;
  color?: string;
  skills?: string[];
  tools?: string[];
  delegates_to?: string[];
}

interface TeamInfo {
  name: string;
  agents: number;
  agent_count: number;
  agents_list: AgentInfo[];
  icon?: string;
  color?: string;
  default_provider?: string;
  default_model?: string;
  filename?: string;
}

interface Deliverable {
  id: string;
  mission_id: string;
  execution_id?: string | null;
  milestone_id?: string | null;
  name: string;
  path: string;
  type: 'document' | 'code' | 'data' | 'archive';
  size_bytes: number;
  sha256?: string | null;
  status: 'verified' | 'draft' | 'final';
  metadata: Record<string, any>;
  created_at: string;
  updated_at?: string;
}

interface ExecutionMilestoneState {
  milestone_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  started_at?: string | null;
  completed_at?: string | null;
  output?: string | null;
  error_message?: string | null;
}

interface MissionExecution {
  id: string;
  mission_id: string;
  run_number: number;
  status: 'pending' | 'running' | 'awaiting_approval' | 'verifying' | 'completed' | 'failed' | 'interrupted' | 'cancelled';
  current_milestone_id?: string | null;
  team_name?: string | null;
  started_at: string;
  completed_at?: string | null;
  duration_seconds: number;
  recovery_state: string;
  pending_approval?: {
    id: string;
    milestone_id: string;
    milestone_title: string;
    prompt: string;
    requested_at: string;
  } | null;
  approval_history: any[];
  milestone_states: ExecutionMilestoneState[];
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
}

interface ActivityItem {
  id: string;
  agent: string;
  activity_type: string;
  message: string;
  metadata?: Record<string, any>;
  created_at: string;
}

interface Milestone {
  id: string;
  mission_id: string;
  title: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  order_idx: number;
  dependencies: string[];
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

interface Mission {
  id: string;
  workspace_id: string;
  title: string;
  objective: string;
  status: 'draft' | 'planning' | 'running' | 'verifying' | 'awaiting_approval' | 'completed' | 'failed' | 'interrupted' | 'cancelled' | 'blocked';
  team_name?: string | null;
  conversation_id?: string | null;
  project_id?: string | null;
  active_execution_id?: string | null;
  active_execution?: MissionExecution | null;
  milestones: Milestone[];
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
}

interface GraphNode {
  id: string;
  type: string;
  label: string;
  status: string;
  metadata: Record<string, any>;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  label?: string;
}

interface MissionGraph {
  mission_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface MissionsProps {
  navigate: (view: string, params?: any) => void;
  initialMissionId?: string | null;
}

export function Missions({ navigate, initialMissionId }: MissionsProps) {
  const { t } = useTranslation();
  const showToast = useContext(ToastContext);

  const [missions, setMissions] = useState<Mission[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'active' | 'completed' | 'draft'>('all');
  const [selectedMission, setSelectedMission] = useState<Mission | null>(null);
  const [graphData, setGraphData] = useState<MissionGraph | null>(null);
  const [loadingGraph, setLoadingGraph] = useState(false);

  // Inspector Modal State (Progressive Disclosure - Slice 2E placeholder)
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);

  // Deletion Confirmation Modals
  const [missionToDelete, setMissionToDelete] = useState<string | null>(null);
  const [milestoneToDelete, setMilestoneToDelete] = useState<string | null>(null);
  const [hoveredMilestoneId, setHoveredMilestoneId] = useState<string | null>(null);

  // New Mission Modal State
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newObjective, setNewObjective] = useState('');
  const [newTeam, setNewTeam] = useState('');
  const [newMilestones, setNewMilestones] = useState<Array<{ title: string; description: string }>>([
    { title: '', description: '' }
  ]);
  const [creating, setCreating] = useState(false);

  // Add Milestone inline in Detail view
  const [isAddingMilestone, setIsAddingMilestone] = useState(false);
  const [newMTitle, setNewMTitle] = useState('');
  const [newMDesc, setNewMDesc] = useState('');

  // Stage details expansion state
  const [expandedStageIds, setExpandedStageIds] = useState<Set<string>>(new Set());

  const toggleStageExpanded = (id: string) => {
    setExpandedStageIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Teams list for selector
  const [availableTeams, setAvailableTeams] = useState<string[]>([]);
  const [teams, setTeams] = useState<TeamInfo[]>([]);
  const [selectedSpecialistForPopover, setSelectedSpecialistForPopover] = useState<AgentInfo | null>(null);

  // Deliverables (Slice 2D)
  const [deliverables, setDeliverables] = useState<Deliverable[]>([]);
  const [loadingDeliverables, setLoadingDeliverables] = useState(false);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  // Executions (Runs) State (Phase A - Mission Runtime)
  const [executions, setExecutions] = useState<MissionExecution[]>([]);
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Inspector & Activities (Slice 2E)
  const [activeInspectorTab, setActiveInspectorTab] = useState<'graph' | 'trace' | 'telemetry'>('graph');
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loadingActivities, setLoadingActivities] = useState(false);
  const [selectedGraphNode, setSelectedGraphNode] = useState<GraphNode | null>(null);

  const selectedMissionRef = useRef<Mission | null>(selectedMission);
  selectedMissionRef.current = selectedMission;

  const fetchMissions = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(apiUrl('/api/missions'));
      if (!res.ok) throw new Error('Failed to load missions');
      const data = await res.json();
      setMissions(data);

      if (initialMissionId) {
        const match = data.find((m: Mission) => m.id === initialMissionId);
        if (match) setSelectedMission(match);
      } else if (selectedMissionRef.current) {
        const updatedCurrent = data.find((m: Mission) => m.id === selectedMissionRef.current?.id);
        if (updatedCurrent) setSelectedMission(updatedCurrent);
      }
    } catch (err: any) {
      console.error(err);
      showToast?.('Error loading missions', 'error');
    } finally {
      setLoading(false);
    }
  }, [initialMissionId, showToast]);

  const fetchTeams = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/teams'));
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setTeams(data);
          setAvailableTeams(data.map((tm: any) => tm.name || tm.id));
          if (data.length > 0 && !newTeam) {
            setNewTeam(data[0].name || data[0].id);
          }
        }
      }
    } catch (err) {
      console.error(err);
    }
  }, [newTeam]);

  useEffect(() => {
    fetchMissions();
    fetchTeams();
  }, [fetchMissions, fetchTeams]);

  // Load Graph for Selected Mission
  const loadGraph = useCallback(async (missionId: string) => {
    try {
      setLoadingGraph(true);
      const res = await fetch(apiUrl(`/api/missions/${missionId}/graph`));
      if (!res.ok) throw new Error('Failed to load graph');
      const data = await res.json();
      setGraphData(data);
    } catch (err) {
      console.error(err);
      setGraphData(null);
    } finally {
      setLoadingGraph(false);
    }
  }, []);

  const fetchExecutions = useCallback(async (missionId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/missions/${missionId}/executions`));
      if (res.ok) {
        const data = await res.json();
        const runs: MissionExecution[] = Array.isArray(data) ? data : [];
        setExecutions(runs);
        if (runs.length > 0) {
          setSelectedExecutionId(prev => {
            if (prev && runs.some(r => r.id === prev)) return prev;
            return runs[runs.length - 1].id;
          });
        } else {
          setSelectedExecutionId(null);
        }
      }
    } catch (err) {
      console.error(err);
      setExecutions([]);
    }
  }, []);

  const fetchDeliverables = useCallback(async (missionId: string, executionId?: string | null) => {
    try {
      setLoadingDeliverables(true);
      const q = executionId ? `?execution_id=${encodeURIComponent(executionId)}` : '';
      const res = await fetch(apiUrl(`/api/missions/${missionId}/deliverables${q}`));
      if (res.ok) {
        const data = await res.json();
        setDeliverables(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      console.error(err);
      setDeliverables([]);
    } finally {
      setLoadingDeliverables(false);
    }
  }, []);

  const fetchActivities = useCallback(async (missionId: string) => {
    try {
      setLoadingActivities(true);
      const res = await fetch(apiUrl(`/api/missions/${missionId}/activities`));
      if (res.ok) {
        const data = await res.json();
        setActivities(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      console.error(err);
      setActivities([]);
    } finally {
      setLoadingActivities(false);
    }
  }, []);

  useEffect(() => {
    if (selectedMission) {
      loadGraph(selectedMission.id);
      fetchExecutions(selectedMission.id);
      fetchDeliverables(selectedMission.id, selectedExecutionId);
      fetchActivities(selectedMission.id);
    } else {
      setGraphData(null);
      setDeliverables([]);
      setActivities([]);
      setExecutions([]);
      setSelectedExecutionId(null);
      setSelectedSpecialistForPopover(null);
      setSelectedGraphNode(null);
    }
  }, [selectedMission?.id, loadGraph, fetchExecutions, fetchDeliverables, fetchActivities]);

  useEffect(() => {
    if (selectedMission?.id && selectedExecutionId) {
      fetchDeliverables(selectedMission.id, selectedExecutionId);
    }
  }, [selectedMission?.id, selectedExecutionId, fetchDeliverables]);

  // Real-time polling when mission execution is active
  useEffect(() => {
    if (!selectedMission) return;
    const isLive = selectedMission.status === 'running' || selectedMission.status === 'verifying';
    if (!isLive) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(apiUrl(`/api/missions/${selectedMission.id}`));
        if (res.ok) {
          const fresh = await res.json();
          setSelectedMission(fresh);
          setMissions(prev => prev.map(m => m.id === fresh.id ? fresh : m));
          fetchExecutions(fresh.id);
          fetchActivities(fresh.id);
          loadGraph(fresh.id);
        }
      } catch (err) {
        // ignore polling failures
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [selectedMission?.id, selectedMission?.status, fetchExecutions, fetchActivities, loadGraph]);

  const handleMissionAction = async (actionName: string, endpoint: string, body?: any) => {
    if (!selectedMission) return;
    setActionLoading(endpoint);
    try {
      const res = await fetch(apiUrl(`/api/missions/${selectedMission.id}/${endpoint}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to ${endpoint}`);
      }
      const data = await res.json();
      const updatedMission = data.mission || {
        ...selectedMission,
        status: data.execution?.status || selectedMission.status,
        active_execution_id: data.execution?.id || selectedMission.active_execution_id,
      };
      setSelectedMission(updatedMission);
      setMissions(prev => prev.map(m => m.id === updatedMission.id ? updatedMission : m));
      showToast?.(`${actionName} triggered`, 'success');
      await fetchExecutions(updatedMission.id);
      if (data.execution?.id) {
        setSelectedExecutionId(data.execution.id);
      }
      loadGraph(updatedMission.id);
      fetchDeliverables(updatedMission.id, data.execution?.id);
      fetchActivities(updatedMission.id);
    } catch (err: any) {
      showToast?.(err.message, 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleCreateMission = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newObjective.trim()) {
      showToast?.('Title and objective are required.', 'error');
      return;
    }

    try {
      setCreating(true);
      const filteredMilestones = newMilestones
        .filter(m => m.title.trim())
        .map((m, idx) => ({
          title: m.title.trim(),
          description: m.description.trim(),
          order_idx: idx,
        }));

      const payload = {
        title: newTitle.trim(),
        objective: newObjective.trim(),
        team_name: newTeam || null,
        status: 'draft',
        milestones: filteredMilestones,
      };

      const res = await fetch(apiUrl('/api/missions'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to create mission');
      }

      const created = await res.json();
      showToast?.('Mission created successfully.', 'success');
      setIsCreateOpen(false);
      setNewTitle('');
      setNewObjective('');
      setNewMilestones([{ title: '', description: '' }]);
      setSelectedMission(created);
      await fetchMissions();
    } catch (err: any) {
      const msg = err?.message === 'Load failed'
        ? 'Unable to connect to local Aether backend. Please verify that the runtime is running.'
        : (err?.message || 'Failed to create mission');
      showToast?.(msg, 'error');
    } finally {
      setCreating(false);
    }
  };

  const handleUpdateTeam = async (teamName: string) => {
    if (!selectedMission) return;
    try {
      const res = await fetch(apiUrl(`/api/missions/${selectedMission.id}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team_name: teamName }),
      });
      if (!res.ok) throw new Error('Failed to update workforce');
      const updated = await res.json();
      setSelectedMission(updated);
      setMissions(prev => prev.map(m => m.id === updated.id ? updated : m));
      showToast?.('Workforce team assigned', 'success');
      loadGraph(updated.id);
    } catch (err: any) {
      showToast?.(err.message, 'error');
    }
  };

  const handleCopyPath = (id: string, path: string) => {
    navigator.clipboard?.writeText(path);
    setCopiedPath(id);
    showToast?.(t('pathCopied'), 'success');
    setTimeout(() => {
      setCopiedPath(null);
    }, 2000);
  };

  const handleOpenDeliverable = async (deliverableId: string, reveal: boolean = false) => {
    if (!selectedMission) return;
    try {
      const res = await fetch(
        apiUrl(`/api/missions/${selectedMission.id}/deliverables/${deliverableId}/open?reveal=${reveal}`),
        { method: 'POST' }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || t('deliverableOpenFailed'));
      }
      showToast?.(reveal ? t('deliverableRevealedSuccess') : t('deliverableOpenedSuccess'), 'success');
    } catch (err: any) {
      showToast?.(err.message || t('deliverableOpenFailed'), 'error');
    }
  };

  const handleDownloadDeliverable = async (deliverableId: string, filename: string) => {
    if (!selectedMission) return;
    try {
      const res = await fetch(
        apiUrl(`/api/missions/${selectedMission.id}/deliverables/${deliverableId}/download`)
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || t('deliverableDownloadFailed'));
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      showToast?.(err.message || t('deliverableDownloadFailed'), 'error');
    }
  };

  const formatBytes = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const confirmDeleteMission = async () => {
    if (!missionToDelete) return;
    try {
      const res = await fetch(apiUrl(`/api/missions/${missionToDelete}`), {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error('Failed to delete mission');
      showToast?.('Mission deleted', 'success');
      if (selectedMission?.id === missionToDelete) {
        setSelectedMission(null);
      }
      setMissionToDelete(null);
      await fetchMissions();
    } catch (err: any) {
      showToast?.(err.message, 'error');
    }
  };

  const handleToggleMilestone = async (m: Milestone) => {
    if (!selectedMission) return;
    const newStatus = m.status === 'completed' ? 'pending' : 'completed';
    try {
      const res = await fetch(apiUrl(`/api/missions/${selectedMission.id}/milestones/${m.id}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error('Failed to toggle milestone');
      const updatedMilestone = await res.json();

      const updatedMilestones = selectedMission.milestones.map(item =>
        item.id === updatedMilestone.id ? updatedMilestone : item
      );
      const updatedMission = { ...selectedMission, milestones: updatedMilestones };
      setSelectedMission(updatedMission);
      setMissions(prev => prev.map(mis => mis.id === updatedMission.id ? updatedMission : mis));
      loadGraph(selectedMission.id);
    } catch (err: any) {
      showToast?.(err.message, 'error');
    }
  };

  const handleAddMilestone = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMission || !newMTitle.trim()) return;

    try {
      const res = await fetch(apiUrl(`/api/missions/${selectedMission.id}/milestones`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newMTitle.trim(),
          description: newMDesc.trim(),
        }),
      });
      if (!res.ok) throw new Error('Failed to add milestone');
      const createdMilestone = await res.json();

      const updatedMilestones = [...selectedMission.milestones, createdMilestone];
      const updatedMission = { ...selectedMission, milestones: updatedMilestones };
      setSelectedMission(updatedMission);
      setMissions(prev => prev.map(mis => mis.id === updatedMission.id ? updatedMission : mis));
      setNewMTitle('');
      setNewMDesc('');
      setIsAddingMilestone(false);
      loadGraph(selectedMission.id);
      showToast?.('Milestone added', 'success');
    } catch (err: any) {
      showToast?.(err.message, 'error');
    }
  };

  const confirmDeleteMilestone = async () => {
    if (!selectedMission || !milestoneToDelete) return;
    try {
      const res = await fetch(apiUrl(`/api/missions/${selectedMission.id}/milestones/${milestoneToDelete}`), {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error('Failed to delete milestone');
      const updatedMilestones = selectedMission.milestones.filter(m => m.id !== milestoneToDelete);
      const updatedMission = { ...selectedMission, milestones: updatedMilestones };
      setSelectedMission(updatedMission);
      setMissions(prev => prev.map(mis => mis.id === updatedMission.id ? updatedMission : mis));
      setMilestoneToDelete(null);
      loadGraph(selectedMission.id);
      showToast?.('Milestone removed', 'success');
    } catch (err: any) {
      showToast?.(err.message, 'error');
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <span className="badge badge-emerald" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontWeight: 600 }}>
            <CheckCircle size={12} /> {t('statusCompleted')}
          </span>
        );
      case 'running':
        return (
          <span className="badge badge-indigo" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontWeight: 600 }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#6366f1', display: 'inline-block' }} />
            {t('statusRunning')}
          </span>
        );
      case 'planning':
        return (
          <span className="badge badge-amber" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontWeight: 600 }}>
            <Layers size={12} /> Planning
          </span>
        );
      case 'verifying':
        return (
          <span className="badge badge-amber" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontWeight: 600 }}>
            <Sparkles size={12} /> Verifying
          </span>
        );
      case 'awaiting_approval':
        return (
          <span className="badge badge-amber" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontWeight: 600 }}>
            <ShieldAlert size={12} /> {t('filterReviewNeeded')}
          </span>
        );
      case 'interrupted':
        return (
          <span className="badge badge-amber" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontWeight: 600 }}>
            <Pause size={12} /> {t('statusInterrupted')}
          </span>
        );
      case 'cancelled':
        return (
          <span className="badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', background: 'hsl(var(--muted))', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>
            Cancelled
          </span>
        );
      case 'failed':
        return (
          <span className="badge badge-rose" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontWeight: 600 }}>
            <AlertCircle size={12} /> {t('statusFailed')}
          </span>
        );
      case 'draft':
      default:
        return (
          <span className="badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', background: 'hsl(var(--muted))', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>
            Draft
          </span>
        );
    }
  };

  const filteredMissions = missions.filter(m => {
    if (filter === 'active') return ['running', 'planning', 'verifying', 'awaiting_approval'].includes(m.status);
    if (filter === 'completed') return m.status === 'completed';
    if (filter === 'draft') return m.status === 'draft';
    return true;
  });

  // Real Workforce resolution (Slice 2B)
  const currentTeam = useMemo(() => {
    if (!selectedMission?.team_name) return null;
    return teams.find(t => t.name === selectedMission.team_name) || null;
  }, [selectedMission?.team_name, teams]);

  const missionLead = useMemo(() => {
    if (!currentTeam || !currentTeam.agents_list || currentTeam.agents_list.length === 0) return null;
    return currentTeam.agents_list[0];
  }, [currentTeam]);

  const assignedSpecialists = useMemo(() => {
    if (!currentTeam || !currentTeam.agents_list || currentTeam.agents_list.length <= 1) return [];
    return currentTeam.agents_list.slice(1);
  }, [currentTeam]);

  const pipelineStats = useMemo(() => {
    if (!selectedMission || !selectedMission.milestones) return { completed: 0, running: 0, pending: 0, blocked: 0 };
    const activeExec = executions.find(e => e.id === selectedExecutionId) || (executions.length > 0 ? executions[executions.length - 1] : null);
    const execMilestoneMap = new Map((activeExec?.milestone_states || []).map(s => [s.milestone_id, s]));

    let completed = 0;
    let running = 0;
    let blocked = 0;
    let pending = 0;

    for (const m of selectedMission.milestones) {
      const execState = execMilestoneMap.get(m.id);
      const st = execState ? execState.status : m.status;
      if (st === 'completed') completed++;
      else if (st === 'running') running++;
      else if (st === 'failed') blocked++;
      else pending++;
    }

    return { completed, running, pending, blocked };
  }, [selectedMission, executions, selectedExecutionId]);

  const workforceStatus = useMemo(() => {
    if (!selectedMission) return { key: 'assigned', label: t('statusAssigned'), color: 'hsl(var(--muted-fg))', bg: 'hsl(var(--muted))' };
    const activeExec = executions.find(e => e.id === selectedExecutionId) || (executions.length > 0 ? executions[executions.length - 1] : null);
    if (!activeExec || selectedMission.status === 'draft') {
      return { key: 'assigned', label: t('statusAssigned'), color: 'hsl(var(--muted-fg))', bg: 'hsl(var(--muted))' };
    }
    if (selectedMission.status === 'completed' || activeExec.status === 'completed') {
      return { key: 'completed', label: t('statusCompleted'), color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' };
    }
    if (selectedMission.status === 'running' || activeExec.status === 'running') {
      return { key: 'running', label: t('statusExecuting'), color: 'hsl(var(--primary))', bg: 'hsl(var(--primary) / 0.15)' };
    }
    if (selectedMission.status === 'interrupted' || activeExec.status === 'interrupted') {
      return { key: 'paused', label: t('statusPaused'), color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' };
    }
    if (selectedMission.status === 'failed' || activeExec.status === 'failed' || selectedMission.status === 'cancelled' || activeExec.status === 'cancelled') {
      return { key: 'failed', label: t('statusFailed'), color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)' };
    }
    return { key: 'assigned', label: t('statusAssigned'), color: 'hsl(var(--muted-fg))', bg: 'hsl(var(--muted))' };
  }, [selectedMission, executions, selectedExecutionId, t]);


  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', backgroundColor: 'hsl(var(--bg))' }}>
      {/* Top Main Navigation Bar */}
      <div style={{
        padding: '14px 24px',
        borderBottom: '1px solid hsl(var(--border))',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: 'hsl(var(--card))'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '10px',
            background: 'hsl(var(--primary) / 0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'hsl(var(--primary))'
          }}>
            <Target size={20} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1 style={{ fontSize: '18px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                {t('missionsTitle')}
              </h1>
              <span style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '1px 7px',
                borderRadius: '12px',
                backgroundColor: 'hsl(var(--primary) / 0.15)',
                color: 'hsl(var(--primary))'
              }}>
                Phase A
              </span>
            </div>
            <p style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', margin: '2px 0 0' }}>
              {t('missionsSubtitle')}
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            className="btn btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
            onClick={() => setIsCreateOpen(true)}
          >
            <Plus size={15} />
            <span>{t('newMission')}</span>
          </button>
        </div>
      </div>

      {/* Main Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left Side: Mission Survey List */}
        <div style={{
          width: selectedMission ? '380px' : '100%',
          borderRight: selectedMission ? '1px solid hsl(var(--border))' : 'none',
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          transition: 'width 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
          backgroundColor: 'hsl(var(--card) / 0.5)'
        }}>
          {/* Filter Bar */}
          <div style={{
            padding: '10px 16px',
            borderBottom: '1px solid hsl(var(--border))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '6px'
          }}>
            <div style={{ display: 'flex', gap: '4px' }}>
              {(['all', 'active', 'completed', 'draft'] as const).map(tabKey => {
                const label = tabKey === 'all' ? t('filterAll')
                  : tabKey === 'active' ? t('filterActive')
                  : tabKey === 'completed' ? t('filterCompleted')
                  : t('filterDraft');
                const count = missions.filter(m => {
                  if (tabKey === 'active') return ['running', 'planning', 'verifying', 'awaiting_approval'].includes(m.status);
                  if (tabKey === 'completed') return m.status === 'completed';
                  if (tabKey === 'draft') return m.status === 'draft';
                  return true;
                }).length;

                return (
                  <button
                    key={tabKey}
                    onClick={() => setFilter(tabKey)}
                    className={`btn btn-sm ${filter === tabKey ? 'btn-secondary' : 'btn-ghost'}`}
                    style={{ fontSize: '12px', padding: '3px 10px', borderRadius: '6px' }}
                  >
                    <span>{label}</span>
                    <span style={{ fontSize: '10px', opacity: 0.7, marginLeft: '4px' }}>{count}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Missions List Container (Centered Max-width 860px when full-screen) */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
            <div style={{
              maxWidth: selectedMission ? '100%' : '860px',
              margin: '0 auto',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px'
            }}>
              {loading ? (
                <div style={{ padding: '40px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
                  <RefreshCw size={22} className="animate-spin" style={{ margin: '0 auto 10px', opacity: 0.6 }} />
                  Loading missions...
                </div>
              ) : filteredMissions.length === 0 ? (
                <div style={{
                  padding: '48px 24px',
                  textAlign: 'center',
                  color: 'hsl(var(--muted-fg))',
                  border: '1px dashed hsl(var(--border))',
                  borderRadius: '12px',
                  marginTop: '16px'
                }}>
                  <Target size={36} style={{ margin: '0 auto 14px', opacity: 0.35 }} />
                  <div style={{ fontSize: '15px', fontWeight: 600, color: 'hsl(var(--fg))' }}>{t('noMissionsYet')}</div>
                  <div style={{ fontSize: '13px', marginTop: '6px', maxWidth: '340px', marginInline: 'auto', lineHeight: 1.5 }}>
                    {t('noMissionsDesc')}
                  </div>
                  <button
                    className="btn btn-primary"
                    style={{ marginTop: '16px', fontSize: '13px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                    onClick={() => setIsCreateOpen(true)}
                  >
                    <Plus size={14} />
                    <span>{t('newMission')}</span>
                  </button>
                </div>
              ) : (
                filteredMissions.map(m => {
                  const completedCount = m.milestones.filter(ms => ms.status === 'completed').length;
                  const totalCount = m.milestones.length;
                  const progressPct = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
                  const isSelected = selectedMission?.id === m.id;

                  return (
                    <div
                      key={m.id}
                      onClick={() => setSelectedMission(m)}
                      style={{
                        padding: '14px 16px',
                        borderRadius: '10px',
                        border: isSelected
                          ? '1.5px solid hsl(var(--primary))'
                          : '1px solid hsl(var(--border))',
                        backgroundColor: isSelected
                          ? 'hsl(var(--primary) / 0.05)'
                          : 'hsl(var(--card))',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                        boxShadow: isSelected ? '0 0 0 1px hsl(var(--primary) / 0.2)' : 'none'
                      }}
                      className="hover:border-primary/60 hover:shadow-sm"
                    >
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '10px' }}>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: 'hsl(var(--fg))', lineHeight: 1.3 }}>
                          {m.title}
                        </div>
                        {getStatusBadge(m.status)}
                      </div>

                      <div style={{
                        fontSize: '12px',
                        color: 'hsl(var(--muted-fg))',
                        marginTop: '6px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        display: '-webkit-box',
                        WebkitLineClamp: selectedMission ? 2 : 3,
                        WebkitBoxOrient: 'vertical',
                        lineHeight: 1.45
                      }}>
                        {m.objective}
                      </div>

                      {/* Progress Bar & Milestone Status */}
                      <div style={{ marginTop: '10px' }}>
                        <div style={{
                          height: '4px',
                          width: '100%',
                          backgroundColor: 'hsl(var(--muted))',
                          borderRadius: '2px',
                          overflow: 'hidden',
                          marginBottom: '6px'
                        }}>
                          <div style={{
                            height: '100%',
                            width: `${progressPct}%`,
                            backgroundColor: progressPct === 100 ? '#10b981' : 'hsl(var(--primary))',
                            transition: 'width 0.3s ease'
                          }} />
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <Users size={12} />
                            <span>{m.team_name || t('defaultWorkforce')}</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <span>{completedCount} {t('ofMilestones')} {totalCount} {t('completedCount')}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Right Side: Single-Pane Executive Mission Cockpit */}
        {selectedMission ? (
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            overflowY: 'auto',
            backgroundColor: 'hsl(var(--bg))'
          }}>
            {/* Cockpit Executive Header */}
            <div style={{
              padding: '16px 28px',
              borderBottom: '1px solid hsl(var(--border))',
              backgroundColor: 'hsl(var(--card))',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                {/* Back to survey button */}
                <button
                  onClick={() => setSelectedMission(null)}
                  className="btn btn-ghost"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '12px',
                    color: 'hsl(var(--muted-fg))',
                    padding: '4px 8px',
                    marginLeft: '-8px'
                  }}
                >
                  <ArrowLeft size={14} />
                  <span>{t('backToMissions')}</span>
                </button>

                {/* Destructive Mission Action */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Tooltip content={t('deleteMission')} position="left">
                    <button
                      onClick={() => setMissionToDelete(selectedMission.id)}
                      className="btn btn-ghost text-rose-500 hover:bg-rose-500/10"
                      style={{ padding: '6px', borderRadius: '6px' }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </Tooltip>
                </div>
              </div>

              {/* Title & Contextual Action Controls */}
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: '280px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                    <h2 style={{ fontSize: '20px', fontWeight: 700, margin: 0, color: 'hsl(var(--fg))' }}>
                      {selectedMission.title}
                    </h2>
                    {getStatusBadge(selectedMission.status)}

                    {/* Run Identity Badge & Run History Selector */}
                    {executions.length > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{
                          fontSize: '11px',
                          fontWeight: 700,
                          backgroundColor: 'hsl(var(--primary) / 0.14)',
                          color: 'hsl(var(--primary))',
                          padding: '2px 8px',
                          borderRadius: '999px',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}>
                          <Layers size={11} />
                          <span>{t('runNumber')}{executions.find(e => e.id === selectedExecutionId)?.run_number || executions[executions.length - 1].run_number}</span>
                        </span>

                        {executions.length > 1 && (
                          <select
                            value={selectedExecutionId || ''}
                            onChange={(e) => setSelectedExecutionId(e.target.value)}
                            style={{
                              fontSize: '11px',
                              padding: '2px 8px',
                              height: '24px',
                              borderRadius: '6px',
                              backgroundColor: 'hsl(var(--card))',
                              borderColor: 'hsl(var(--border))',
                              color: 'hsl(var(--fg))'
                            }}
                            title={t('missionRunsHistory')}
                          >
                            {executions.map((ex) => (
                              <option key={ex.id} value={ex.id}>
                                Run #{ex.run_number} ({ex.status})
                              </option>
                            ))}
                          </select>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Context-Driven Action Buttons (Truthful Mission Runtime) */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  {/* DRAFT STATE */}
                  {selectedMission.status === 'draft' && (
                    <button
                      onClick={() => handleMissionAction(t('startMission'), 'start')}
                      disabled={actionLoading === 'start'}
                      className="btn btn-primary"
                      style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 600 }}
                    >
                      <Play size={14} fill="currentColor" />
                      <span>{actionLoading === 'start' ? 'Starting...' : t('startMission')}</span>
                    </button>
                  )}

                  {/* RUNNING STATE */}
                  {selectedMission.status === 'running' && (
                    <>
                      <button
                        onClick={() => handleMissionAction(t('pauseMission'), 'pause')}
                        disabled={actionLoading === 'pause'}
                        className="btn btn-secondary"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <Pause size={14} />
                        <span>{actionLoading === 'pause' ? 'Pausing...' : t('pauseMission')}</span>
                      </button>
                      <button
                        onClick={() => handleMissionAction(t('stopMission'), 'cancel')}
                        disabled={actionLoading === 'cancel'}
                        className="btn btn-ghost text-rose-500 hover:bg-rose-500/10"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <Square size={14} />
                        <span>{actionLoading === 'cancel' ? 'Stopping...' : t('stopMission')}</span>
                      </button>
                    </>
                  )}

                  {/* INTERRUPTED / PAUSED STATE */}
                  {selectedMission.status === 'interrupted' && (
                    <>
                      <button
                        onClick={() => handleMissionAction(t('resumeMission'), 'resume')}
                        disabled={actionLoading === 'resume'}
                        className="btn btn-primary"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <Play size={14} fill="currentColor" />
                        <span>{actionLoading === 'resume' ? 'Resuming...' : t('resumeMission')}</span>
                      </button>
                      <button
                        onClick={() => handleMissionAction(t('cancelMission'), 'cancel')}
                        disabled={actionLoading === 'cancel'}
                        className="btn btn-ghost text-rose-500 hover:bg-rose-500/10"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <Square size={14} />
                        <span>{actionLoading === 'cancel' ? 'Cancelling...' : t('cancelMission')}</span>
                      </button>
                    </>
                  )}

                  {/* AWAITING APPROVAL STATE */}
                  {selectedMission.status === 'awaiting_approval' && (
                    <>
                      <button
                        onClick={() => handleMissionAction(t('approveMission'), 'approve')}
                        disabled={actionLoading === 'approve'}
                        className="btn btn-primary"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', backgroundColor: '#10b981' }}
                      >
                        <Check size={15} />
                        <span>{actionLoading === 'approve' ? 'Approving...' : t('approveMission')}</span>
                      </button>
                      <button
                        onClick={() => handleMissionAction(t('rejectMission'), 'reject')}
                        disabled={actionLoading === 'reject'}
                        className="btn btn-ghost text-rose-500 hover:bg-rose-500/10"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <X size={15} />
                        <span>{actionLoading === 'reject' ? 'Rejecting...' : t('rejectMission')}</span>
                      </button>
                    </>
                  )}

                  {/* COMPLETED STATE */}
                  {selectedMission.status === 'completed' && (
                    <>
                      <button
                        onClick={() => handleMissionAction(t('rerunMission'), 'rerun')}
                        disabled={actionLoading === 'rerun'}
                        className="btn btn-secondary"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <RotateCcw size={13} />
                        <span>{actionLoading === 'rerun' ? 'Re-running...' : t('rerunMission')}</span>
                      </button>
                    </>
                  )}

                  {/* FAILED STATE */}
                  {selectedMission.status === 'failed' && (
                    <>
                      <button
                        onClick={() => handleMissionAction(t('retryStep'), 'retry')}
                        disabled={actionLoading === 'retry'}
                        className="btn btn-secondary text-rose-500"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <RotateCcw size={13} />
                        <span>{actionLoading === 'retry' ? 'Retrying...' : t('retryStep')}</span>
                      </button>
                      <button
                        onClick={() => handleMissionAction(t('rerunMission'), 'rerun')}
                        disabled={actionLoading === 'rerun'}
                        className="btn btn-secondary"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <RotateCcw size={13} />
                        <span>{actionLoading === 'rerun' ? 'Re-running...' : t('rerunMission')}</span>
                      </button>
                    </>
                  )}

                  {/* CANCELLED STATE */}
                  {selectedMission.status === 'cancelled' && (
                    <button
                      onClick={() => handleMissionAction(t('rerunMission'), 'rerun')}
                      disabled={actionLoading === 'rerun'}
                      className="btn btn-secondary"
                      style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                    >
                      <RotateCcw size={13} />
                      <span>{actionLoading === 'rerun' ? 'Re-running...' : t('rerunMission')}</span>
                    </button>
                  )}

                  {/* Associated Chat Link Button */}
                  {selectedMission.conversation_id && (
                    <button
                      onClick={() => navigate('chat', selectedMission.conversation_id)}
                      className="btn btn-ghost"
                      style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px' }}
                    >
                      <MessageSquare size={13} />
                      <span>{t('openAssociatedChat')}</span>
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Single-Pane Cockpit Body Container (Centered Max-width 920px) */}
            <div style={{
              maxWidth: '920px',
              width: '100%',
              margin: '0 auto',
              padding: '24px 28px',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px'
            }}>
              {/* 1. SIMPLE STATUS BANNER */}
              <div style={{
                padding: '12px 18px',
                borderRadius: '10px',
                border: selectedMission.status === 'running'
                  ? '1px solid hsl(var(--primary) / 0.4)'
                  : selectedMission.status === 'awaiting_approval'
                  ? '1px solid #f59e0b'
                  : selectedMission.status === 'completed'
                  ? '1px solid #10b98133'
                  : '1px solid hsl(var(--border))',
                backgroundColor: selectedMission.status === 'running'
                  ? 'hsl(var(--primary) / 0.08)'
                  : selectedMission.status === 'awaiting_approval'
                  ? 'rgba(245, 158, 11, 0.08)'
                  : selectedMission.status === 'completed'
                  ? 'rgba(16, 185, 129, 0.06)'
                  : 'hsl(var(--card))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '12px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{
                    width: '9px',
                    height: '9px',
                    borderRadius: '50%',
                    backgroundColor: selectedMission.status === 'running'
                      ? 'hsl(var(--primary))'
                      : selectedMission.status === 'awaiting_approval'
                      ? '#f59e0b'
                      : selectedMission.status === 'completed'
                      ? '#10b981'
                      : 'hsl(var(--muted-fg))'
                  }} />
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
                    {selectedMission.status === 'running' && t('operationalPulseRunning')}
                    {selectedMission.status === 'draft' && t('operationalPulseIdle')}
                    {selectedMission.status === 'interrupted' && t('operationalPulsePaused')}
                    {selectedMission.status === 'awaiting_approval' && t('operationalPulseApproval')}
                    {selectedMission.status === 'completed' && t('operationalPulseCompleted')}
                    {selectedMission.status === 'failed' && t('operationalPulseFailed')}
                    {selectedMission.status === 'cancelled' && t('operationalPulseCancelled')}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                  <Clock size={13} />
                  <span>
                    {new Date(selectedMission.updated_at || selectedMission.created_at).toLocaleDateString([], {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </span>
                </div>
              </div>

              {/* APPROVAL GATE BANNER (When Awaiting Signoff) */}
              {selectedMission.status === 'awaiting_approval' && (
                <div style={{
                  padding: '16px 20px',
                  borderRadius: '12px',
                  border: '1px solid #f59e0b',
                  backgroundColor: 'rgba(245, 158, 11, 0.08)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <ShieldAlert size={18} className="text-amber-500" />
                      <span style={{ fontSize: '13px', fontWeight: 700, color: '#f59e0b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        {t('gateApprovalRequired')}
                      </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <button
                        onClick={() => handleMissionAction(t('approveMission'), 'approve')}
                        disabled={actionLoading === 'approve'}
                        className="btn btn-sm btn-primary"
                        style={{ display: 'flex', alignItems: 'center', gap: '5px', backgroundColor: '#10b981', borderColor: '#10b981' }}
                      >
                        <Check size={14} />
                        <span>{actionLoading === 'approve' ? 'Approving...' : t('approveAndProceed')}</span>
                      </button>
                      <button
                        onClick={() => handleMissionAction(t('rejectMission'), 'reject')}
                        disabled={actionLoading === 'reject'}
                        className="btn btn-sm btn-ghost text-rose-500 hover:bg-rose-500/10"
                        style={{ display: 'flex', alignItems: 'center', gap: '5px' }}
                      >
                        <X size={14} />
                        <span>{actionLoading === 'reject' ? 'Rejecting...' : t('rejectChanges')}</span>
                      </button>
                    </div>
                  </div>
                  <p style={{ margin: 0, fontSize: '13px', color: 'hsl(var(--fg))', lineHeight: 1.5 }}>
                    {executions.find(e => e.id === selectedExecutionId)?.pending_approval?.prompt || t('operationalPulseApproval')}
                  </p>
                </div>
              )}

              {/* 2. OBIETTIVO (Objective) */}
              <div style={{
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                  <Target size={16} className="text-primary" />
                  <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                    {t('outcomeCharter')}
                  </h3>
                </div>
                <p style={{
                  fontSize: '14px',
                  color: 'hsl(var(--fg))',
                  lineHeight: 1.6,
                  margin: 0,
                  whiteSpace: 'pre-wrap'
                }}>
                  {selectedMission.objective}
                </p>
              </div>

              {/* 3. WORKFORCE */}
              <div style={{
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))',
                display: 'flex',
                flexDirection: 'column',
                gap: '14px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Users size={16} className="text-primary" />
                    <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                      {t('assignedWorkforceLabel')}
                    </h3>
                    {selectedMission.team_name && (
                      <span style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
                        ({selectedMission.team_name})
                      </span>
                    )}
                  </div>

                  {currentTeam && (
                    <span style={{
                      fontSize: '11px',
                      padding: '3px 10px',
                      borderRadius: '12px',
                      backgroundColor: workforceStatus.bg,
                      color: workforceStatus.color,
                      fontWeight: 600
                    }}>
                      {workforceStatus.label}
                    </span>
                  )}
                </div>

                {currentTeam ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {/* Responsabile (Lead) */}
                    {missionLead && (
                      <div style={{
                        padding: '12px 14px',
                        borderRadius: '8px',
                        backgroundColor: 'hsl(var(--bg))',
                        border: '1px solid hsl(var(--border))',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '12px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <div style={{
                            width: '32px',
                            height: '32px',
                            borderRadius: '8px',
                            backgroundColor: 'hsl(var(--primary) / 0.15)',
                            color: 'hsl(var(--primary))',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 700,
                            fontSize: '13px'
                          }}>
                            {missionLead.name.slice(0, 1).toUpperCase()}
                          </div>
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
                                {missionLead.name}
                              </span>
                              <span style={{
                                fontSize: '10px',
                                textTransform: 'uppercase',
                                fontWeight: 700,
                                padding: '1px 6px',
                                borderRadius: '4px',
                                backgroundColor: 'hsl(var(--primary) / 0.2)',
                                color: 'hsl(var(--primary))'
                              }}>
                                {t('workforceOwner')}
                              </span>
                            </div>
                            <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                              {missionLead.role}
                            </div>
                          </div>
                        </div>

                        <button
                          onClick={() => setSelectedSpecialistForPopover(missionLead)}
                          className="btn btn-ghost"
                          style={{ fontSize: '12px', padding: '4px 10px' }}
                        >
                          {t('viewDetails')}
                        </button>
                      </div>
                    )}

                    {/* Specialisti (Specialists) */}
                    {assignedSpecialists.length > 0 && (
                      <div>
                        <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                          {t('workforceSpecialists')} ({assignedSpecialists.length})
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                          {assignedSpecialists.map((agent, idx) => (
                            <div
                              key={idx}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '10px',
                                padding: '8px 12px',
                                borderRadius: '8px',
                                backgroundColor: 'hsl(var(--bg))',
                                border: '1px solid hsl(var(--border))',
                                flex: '1 1 calc(50% - 8px)',
                                minWidth: '220px',
                                justifyContent: 'space-between'
                              }}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                                <div style={{
                                  width: '24px',
                                  height: '24px',
                                  borderRadius: '50%',
                                  backgroundColor: 'hsl(var(--muted))',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  fontSize: '11px',
                                  fontWeight: 600,
                                  color: 'hsl(var(--fg))',
                                  flexShrink: 0
                                }}>
                                  {agent.name.slice(0, 1).toUpperCase()}
                                </div>
                                <div style={{ minWidth: 0 }}>
                                  <div style={{ fontSize: '12.5px', fontWeight: 600, color: 'hsl(var(--fg))', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {agent.name}
                                  </div>
                                  <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {agent.role}
                                  </div>
                                </div>
                              </div>
                              <button
                                onClick={() => setSelectedSpecialistForPopover(agent)}
                                className="btn btn-ghost"
                                style={{ fontSize: '11px', padding: '2px 8px', flexShrink: 0 }}
                              >
                                {t('viewDetails')}
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{
                    padding: '16px',
                    borderRadius: '8px',
                    backgroundColor: 'hsl(var(--bg))',
                    border: '1px dashed hsl(var(--border))',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '12px'
                  }}>
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 500, color: 'hsl(var(--fg))' }}>
                        {t('noWorkforceAssigned')}
                      </div>
                      <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                        {t('noWorkforceDesc')}
                      </div>
                    </div>

                    {availableTeams.length > 0 && (
                      <select
                        value=""
                        onChange={(e) => { if (e.target.value) handleUpdateTeam(e.target.value); }}
                        className="form-input"
                        style={{ fontSize: '12px', padding: '4px 8px', maxWidth: '220px' }}
                      >
                        <option value="" disabled>Assign workforce team...</option>
                        {availableTeams.map(tm => (
                          <option key={tm} value={tm}>{tm}</option>
                        ))}
                      </select>
                    )}
                  </div>
                )}
              </div>

              {/* 3. OUTCOME STAGE PIPELINE (Slice 2C) */}
              <div style={{
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Workflow size={16} className="text-primary" />
                      <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                        {t('stagePipeline')}
                      </h3>
                    </div>
                    <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px', display: 'block' }}>
                      {pipelineStats.completed} {t('ofMilestones')} {selectedMission.milestones.length} {t('completedCount')}
                    </span>
                  </div>

                  {/* Pipeline Overview Status Bar */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '12px', backgroundColor: 'rgba(16, 185, 129, 0.12)', color: '#10b981', fontWeight: 600 }}>
                      {pipelineStats.completed} {t('pipelineCompleted')}
                    </span>
                    {pipelineStats.running > 0 && (
                      <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '12px', backgroundColor: 'hsl(var(--primary) / 0.15)', color: 'hsl(var(--primary))', fontWeight: 600 }}>
                        {pipelineStats.running} {t('pipelineRunning')}
                      </span>
                    )}
                    {pipelineStats.blocked > 0 && (
                      <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '12px', backgroundColor: 'rgba(239, 68, 68, 0.12)', color: '#ef4444', fontWeight: 600 }}>
                        {pipelineStats.blocked} {t('pipelineBlocked')}
                      </span>
                    )}
                    <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '12px', backgroundColor: 'hsl(var(--muted))', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>
                      {pipelineStats.pending} {t('pipelinePending')}
                    </span>

                    <button
                      onClick={() => setIsAddingMilestone(!isAddingMilestone)}
                      className="btn btn-ghost"
                      style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '5px', padding: '4px 10px', marginLeft: '4px' }}
                    >
                      <Plus size={14} />
                      <span>{t('addStep')}</span>
                    </button>
                  </div>
                </div>

                {/* Inline Milestone Creation Form */}
                {isAddingMilestone && (
                  <form
                    onSubmit={handleAddMilestone}
                    style={{
                      padding: '14px',
                      backgroundColor: 'hsl(var(--bg))',
                      borderRadius: '8px',
                      border: '1px solid hsl(var(--border))',
                      marginBottom: '16px'
                    }}
                  >
                    <div style={{ marginBottom: '8px' }}>
                      <input
                        type="text"
                        placeholder={t('milestoneTitle')}
                        value={newMTitle}
                        onChange={(e) => setNewMTitle(e.target.value)}
                        className="form-input"
                        style={{ width: '100%', fontSize: '13px' }}
                        autoFocus
                      />
                    </div>
                    <div style={{ marginBottom: '10px' }}>
                      <input
                        type="text"
                        placeholder={t('milestoneDescription')}
                        value={newMDesc}
                        onChange={(e) => setNewMDesc(e.target.value)}
                        className="form-input"
                        style={{ width: '100%', fontSize: '12px' }}
                      />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                      <button
                        type="button"
                        onClick={() => setIsAddingMilestone(false)}
                        className="btn btn-ghost"
                        style={{ fontSize: '12px', padding: '4px 10px' }}
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="btn btn-primary"
                        style={{ fontSize: '12px', padding: '4px 12px' }}
                      >
                        Add
                      </button>
                    </div>
                  </form>
                )}

                {/* Stage Sequence */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {selectedMission.milestones.length === 0 ? (
                    <div style={{
                      padding: '24px',
                      textAlign: 'center',
                      color: 'hsl(var(--muted-fg))',
                      fontSize: '13px',
                      border: '1px dashed hsl(var(--border))',
                      borderRadius: '8px'
                    }}>
                      No stages defined yet. Add steps to establish verifiable execution boundaries.
                    </div>
                  ) : (
                    (() => {
                      const activeExec = executions.find(e => e.id === selectedExecutionId) || (executions.length > 0 ? executions[executions.length - 1] : null);
                      const execMilestoneMap = new Map((activeExec?.milestone_states || []).map(s => [s.milestone_id, s]));

                      return selectedMission.milestones.map((m, idx) => {
                        const execState = execMilestoneMap.get(m.id);
                        const effectiveStatus = execState ? execState.status : m.status;
                        const isDone = effectiveStatus === 'completed';
                        const isRunning = effectiveStatus === 'running';
                        const isFailed = effectiveStatus === 'failed';
                        const isExpanded = expandedStageIds.has(m.id);
                        const hasDetails = Boolean(execState?.output || execState?.error_message);

                        return (
                          <div
                            key={m.id}
                            className="group"
                            onMouseEnter={() => setHoveredMilestoneId(m.id)}
                            onMouseLeave={() => setHoveredMilestoneId(null)}
                            style={{
                              display: 'flex',
                              flexDirection: 'column',
                              padding: '12px 14px',
                              borderRadius: '8px',
                              backgroundColor: isDone
                                ? 'hsl(var(--card) / 0.5)'
                                : isRunning
                                ? 'hsl(var(--primary) / 0.04)'
                                : isFailed
                                ? 'rgba(239, 68, 68, 0.04)'
                                : 'hsl(var(--card))',
                              border: isRunning
                                ? '1px solid hsl(var(--primary) / 0.4)'
                                : isFailed
                                ? '1px solid rgba(239, 68, 68, 0.4)'
                                : '1px solid hsl(var(--border))',
                              transition: 'all 0.15s ease'
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                              {/* Status Clickable Checkbox/Action */}
                              <button
                                onClick={() => handleToggleMilestone(m)}
                                title="Toggle stage state"
                                style={{
                                  background: 'none',
                                  border: 'none',
                                  padding: 0,
                                  cursor: 'pointer',
                                  color: isDone ? '#10b981' : isRunning ? 'hsl(var(--primary))' : isFailed ? '#ef4444' : 'hsl(var(--muted-fg))',
                                  marginTop: '2px'
                                }}
                              >
                                {isDone ? (
                                  <CheckCircle size={18} />
                                ) : isRunning ? (
                                  <Play size={16} fill="currentColor" />
                                ) : isFailed ? (
                                  <AlertCircle size={18} />
                                ) : (
                                  <Circle size={18} />
                                )}
                              </button>

                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                                  <div style={{
                                    fontSize: '13.5px',
                                    fontWeight: isRunning ? 600 : 500,
                                    color: isDone ? 'hsl(var(--muted-fg))' : 'hsl(var(--fg))',
                                    textDecoration: isDone ? 'line-through' : 'none'
                                  }}>
                                    <span style={{
                                      fontSize: '10px',
                                      textTransform: 'uppercase',
                                      fontWeight: 700,
                                      padding: '1px 5px',
                                      borderRadius: '4px',
                                      backgroundColor: 'hsl(var(--muted))',
                                      color: 'hsl(var(--muted-fg))',
                                      marginRight: '8px'
                                    }}>
                                      {t('stage')} {idx + 1}
                                    </span>
                                    {m.title}
                                  </div>

                                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    {isDone && (
                                      <span style={{ fontSize: '11px', color: '#10b981', fontWeight: 500 }}>
                                        {t('completedAt')} {execState?.completed_at ? new Date(execState.completed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : (m.completed_at ? new Date(m.completed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '')}
                                      </span>
                                    )}
                                    {isRunning && (
                                      <span style={{ fontSize: '11px', color: 'hsl(var(--primary))', fontWeight: 600 }}>
                                        {t('statusExecuting')}
                                      </span>
                                    )}
                                    {isFailed && (
                                      <span style={{ fontSize: '11px', color: '#ef4444', fontWeight: 600 }}>
                                        {t('pipelineBlocked')}
                                      </span>
                                    )}

                                    {/* Show/Hide Details Toggle */}
                                    {hasDetails && (
                                      <button
                                        type="button"
                                        onClick={() => toggleStageExpanded(m.id)}
                                        className="btn btn-ghost"
                                        style={{
                                          fontSize: '11px',
                                          display: 'flex',
                                          alignItems: 'center',
                                          gap: '4px',
                                          padding: '2px 6px',
                                          color: 'hsl(var(--muted-fg))'
                                        }}
                                      >
                                        {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                                        <span>{isExpanded ? t('hideDetails') : t('showDetails')}</span>
                                      </button>
                                    )}

                                    {/* Hover-activated deletion */}
                                    {hoveredMilestoneId === m.id && (
                                      <button
                                        onClick={() => setMilestoneToDelete(m.id)}
                                        className="btn btn-ghost text-muted-fg hover:text-rose-500"
                                        style={{ padding: '2px 4px', borderRadius: '4px' }}
                                        title="Delete milestone"
                                      >
                                        <Trash2 size={13} />
                                      </button>
                                    )}
                                  </div>
                                </div>

                                {m.description && (
                                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '4px', lineHeight: 1.4 }}>
                                    {m.description}
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Progressive Disclosure: Formatted Output When Expanded */}
                            {isExpanded && (
                              <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid hsl(var(--border))' }}>
                                {execState?.output && (
                                  <div style={{
                                    fontSize: '12.5px',
                                    color: 'hsl(var(--fg))',
                                    lineHeight: 1.6,
                                    padding: '12px 14px',
                                    borderRadius: '6px',
                                    backgroundColor: 'hsl(var(--bg))',
                                    border: '1px solid hsl(var(--border))'
                                  }}>
                                    <MarkdownRenderer content={execState.output} />
                                  </div>
                                )}

                                {execState?.error_message && (
                                  <div style={{
                                    fontSize: '12px',
                                    color: '#ef4444',
                                    marginTop: execState?.output ? '8px' : '0',
                                    padding: '8px 12px',
                                    borderRadius: '6px',
                                    backgroundColor: 'rgba(239, 68, 68, 0.08)',
                                    border: '1px solid rgba(239, 68, 68, 0.2)'
                                  }}>
                                    {execState.error_message}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      });
                    })()
                  )}
                </div>
              </div>

              {/* 5. RISULTATI (Results) */}
              <div style={{
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <FileText size={16} className="text-primary" />
                    <h3 style={{ fontSize: '14px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                      {t('deliverablesDossier')}
                    </h3>
                    <span style={{
                      fontSize: '11px',
                      padding: '1px 6px',
                      borderRadius: '10px',
                      backgroundColor: 'hsl(var(--muted))',
                      color: 'hsl(var(--muted-fg))',
                      fontWeight: 600
                    }}>
                      {deliverables.length}
                    </span>
                  </div>
                </div>

                {loadingDeliverables ? (
                  <div style={{ padding: '24px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '12px' }}>
                    <RefreshCw size={16} className="animate-spin" style={{ margin: '0 auto 8px' }} />
                    Loading...
                  </div>
                ) : deliverables.length === 0 ? (
                  <div style={{
                    padding: '24px 16px',
                    borderRadius: '8px',
                    border: '1px dashed hsl(var(--border))',
                    textAlign: 'center',
                    color: 'hsl(var(--muted-fg))'
                  }}>
                    <FileText size={26} style={{ margin: '0 auto 10px', opacity: 0.3 }} />
                    <div style={{ fontSize: '13px', fontWeight: 500, color: 'hsl(var(--fg))' }}>
                      {t('deliverablesEmptyTitle')}
                    </div>
                    <div style={{ fontSize: '12px', marginTop: '4px', maxWidth: '440px', marginInline: 'auto' }}>
                      {t('deliverablesEmptyDesc')}
                    </div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {deliverables.map((del) => {
                      const renderTypeIcon = () => {
                        switch (del.type) {
                          case 'code': return <FileCode size={16} className="text-sky-500" />;
                          case 'data': return <Table size={16} className="text-amber-500" />;
                          case 'archive': return <FolderArchive size={16} className="text-purple-500" />;
                          default: return <FileText size={16} className="text-primary" />;
                        }
                      };

                      return (
                        <div
                          key={del.id}
                          style={{
                            padding: '10px 14px',
                            borderRadius: '8px',
                            backgroundColor: 'hsl(var(--bg))',
                            border: '1px solid hsl(var(--border))',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: '12px'
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, flex: 1 }}>
                            <div style={{
                              width: '32px',
                              height: '32px',
                              borderRadius: '8px',
                              backgroundColor: 'hsl(var(--card))',
                              border: '1px solid hsl(var(--border))',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0
                            }}>
                              {renderTypeIcon()}
                            </div>
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span
                                  onClick={() => handleOpenDeliverable(del.id, false)}
                                  style={{
                                    fontSize: '13px',
                                    fontWeight: 600,
                                    color: 'hsl(var(--fg))',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                    cursor: 'pointer'
                                  }}
                                  className="hover:underline"
                                  title={t('deliverableActionOpenTooltip')}
                                >
                                  {del.name}
                                </span>
                                {del.status === 'verified' && (
                                  <span style={{
                                    fontSize: '10px',
                                    padding: '1px 6px',
                                    borderRadius: '4px',
                                    backgroundColor: 'rgba(16, 185, 129, 0.15)',
                                    color: '#10b981',
                                    fontWeight: 600,
                                    textTransform: 'uppercase'
                                  }}>
                                    {del.status}
                                  </span>
                                )}
                              </div>
                              <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                                {formatBytes(del.size_bytes)}
                              </div>
                            </div>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }}>
                            {/* Open */}
                            <button
                              onClick={() => handleOpenDeliverable(del.id, false)}
                              className="btn btn-ghost"
                              style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', padding: '4px 8px' }}
                              title={t('deliverableActionOpenTooltip')}
                            >
                              <ExternalLink size={13} className="text-primary" />
                              <span>{t('deliverableActionOpen')}</span>
                            </button>

                            {/* Reveal in Finder / File Explorer */}
                            <button
                              onClick={() => handleOpenDeliverable(del.id, true)}
                              className="btn btn-ghost"
                              style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', padding: '4px 8px' }}
                              title={t('deliverableActionRevealTooltip')}
                            >
                              <FolderOpen size={13} />
                              <span className="hidden sm:inline">{t('deliverableActionReveal')}</span>
                            </button>

                            {/* Download */}
                            <button
                              onClick={() => handleDownloadDeliverable(del.id, del.name)}
                              className="btn btn-ghost"
                              style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', padding: '4px 8px' }}
                              title={t('deliverableActionDownloadTooltip')}
                            >
                              <Download size={13} />
                              <span>{t('deliverableActionDownload')}</span>
                            </button>

                            {/* Copy Path */}
                            <button
                              onClick={() => handleCopyPath(del.id, del.path)}
                              className="btn btn-ghost"
                              style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', padding: '4px 8px' }}
                              title={t('deliverableActionCopyPath')}
                            >
                              {copiedPath === del.id ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
                              <span>{copiedPath === del.id ? t('copied') : t('deliverableActionCopyPath')}</span>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* 6. PROGRESSIVE DISCLOSURE INSPECTOR GATEWAY */}
              <div style={{
                padding: '14px 18px',
                borderRadius: '10px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '16px'
              }}>
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
                    {t('inspectExecution')}
                  </div>
                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                    {t('inspectExecutionDesc')}
                  </div>
                </div>

                <button
                  onClick={() => {
                    setIsInspectorOpen(true);
                    if (selectedMission) fetchActivities(selectedMission.id);
                  }}
                  className="btn btn-secondary"
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', padding: '6px 12px' }}
                >
                  <Layers size={14} />
                  <span>{t('inspectExecution')}</span>
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {/* Slide-over Advanced Inspector Sheet (Slice 2E) */}
      {isInspectorOpen && selectedMission && (
        <div style={{
          position: 'fixed',
          inset: 0,
          zIndex: 60,
          display: 'flex',
          justifyContent: 'flex-end',
          backgroundColor: 'rgba(0,0,0,0.5)',
          backdropFilter: 'blur(2px)'
        }}>
          <div style={{
            width: '100%',
            maxWidth: '640px',
            height: '100%',
            backgroundColor: 'hsl(var(--card))',
            borderLeft: '1px solid hsl(var(--border))',
            boxShadow: '-8px 0 25px -5px rgba(0,0,0,0.3)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden'
          }}>
            {/* Header */}
            <div style={{ padding: '16px 20px', borderBottom: '1px solid hsl(var(--border))', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Layers size={18} className="text-primary" />
                <div>
                  <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                    {t('inspectorSlideOverTitle')}
                  </h3>
                  <p style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', margin: '2px 0 0', maxWidth: '380px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {selectedMission.title}
                  </p>
                </div>
              </div>
              <button onClick={() => setIsInspectorOpen(false)} className="btn btn-ghost" style={{ padding: '4px' }}>
                <X size={18} />
              </button>
            </div>

            {/* Tab Navigation */}
            <div style={{
              display: 'flex',
              borderBottom: '1px solid hsl(var(--border))',
              backgroundColor: 'hsl(var(--bg))',
              padding: '0 16px'
            }}>
              <button
                onClick={() => setActiveInspectorTab('graph')}
                style={{
                  padding: '10px 14px',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: activeInspectorTab === 'graph' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
                  borderBottom: activeInspectorTab === 'graph' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
                  background: 'none',
                  border: 'none',
                  borderBottomWidth: '2px',
                  borderBottomStyle: 'solid',
                  borderBottomColor: activeInspectorTab === 'graph' ? 'hsl(var(--primary))' : 'transparent',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <Workflow size={14} />
                <span>{t('tabGraph')}</span>
                {graphData?.nodes && (
                  <span style={{ fontSize: '10px', padding: '1px 5px', borderRadius: '10px', backgroundColor: 'hsl(var(--muted))' }}>
                    {graphData.nodes.length}
                  </span>
                )}
              </button>

              <button
                onClick={() => {
                  setActiveInspectorTab('trace');
                  if (selectedMission) fetchActivities(selectedMission.id);
                }}
                style={{
                  padding: '10px 14px',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: activeInspectorTab === 'trace' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
                  background: 'none',
                  border: 'none',
                  borderBottomWidth: '2px',
                  borderBottomStyle: 'solid',
                  borderBottomColor: activeInspectorTab === 'trace' ? 'hsl(var(--primary))' : 'transparent',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <Activity size={14} />
                <span>{t('tabTrace')}</span>
                {activities.length > 0 && (
                  <span style={{ fontSize: '10px', padding: '1px 5px', borderRadius: '10px', backgroundColor: 'hsl(var(--muted))' }}>
                    {activities.length}
                  </span>
                )}
              </button>

              <button
                onClick={() => setActiveInspectorTab('telemetry')}
                style={{
                  padding: '10px 14px',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: activeInspectorTab === 'telemetry' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
                  background: 'none',
                  border: 'none',
                  borderBottomWidth: '2px',
                  borderBottomStyle: 'solid',
                  borderBottomColor: activeInspectorTab === 'telemetry' ? 'hsl(var(--primary))' : 'transparent',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <Terminal size={14} />
                <span>{t('tabTelemetry')}</span>
              </button>
            </div>

            {/* Tab Body */}
            <div style={{ padding: '20px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Tab 1: Execution Graph */}
              {activeInspectorTab === 'graph' && (
                <>
                  <div style={{
                    padding: '10px 14px',
                    borderRadius: '6px',
                    backgroundColor: 'hsl(var(--muted))',
                    fontSize: '12px',
                    color: 'hsl(var(--muted-fg))'
                  }}>
                    {t('inspectPlaceholderNotice')}
                  </div>

                  {loadingGraph ? (
                    <div style={{ padding: '32px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
                      <RefreshCw size={20} className="animate-spin" style={{ margin: '0 auto 8px' }} />
                      Compiling node graph...
                    </div>
                  ) : !graphData || graphData.nodes.length === 0 ? (
                    <div style={{ padding: '32px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '12px' }}>
                      No execution nodes registered yet.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', color: 'hsl(var(--muted-fg))', padding: '0 4px' }}>
                        <span>Topology: {graphData.nodes.length} {t('graphNodesCount')} · {graphData.edges.length} {t('graphEdgesCount')}</span>
                        {selectedGraphNode && (
                          <button onClick={() => setSelectedGraphNode(null)} className="btn btn-ghost" style={{ padding: '1px 6px', fontSize: '10px' }}>
                            Clear selection
                          </button>
                        )}
                      </div>

                      {graphData.nodes.map(node => {
                        const isSelected = selectedGraphNode?.id === node.id;
                        return (
                          <div
                            key={node.id}
                            onClick={() => setSelectedGraphNode(isSelected ? null : node)}
                            style={{
                              padding: '12px 14px',
                              borderRadius: '8px',
                              backgroundColor: isSelected
                                ? 'hsl(var(--primary) / 0.1)'
                                : node.type === 'mission'
                                ? 'hsl(var(--primary) / 0.05)'
                                : 'hsl(var(--bg))',
                              border: isSelected
                                ? '1px solid hsl(var(--primary))'
                                : '1px solid hsl(var(--border))',
                              cursor: 'pointer',
                              transition: 'all 0.15s ease'
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                <span style={{
                                  fontSize: '10px',
                                  textTransform: 'uppercase',
                                  fontWeight: 700,
                                  padding: '2px 6px',
                                  borderRadius: '4px',
                                  backgroundColor: 'hsl(var(--muted))',
                                  color: 'hsl(var(--fg))'
                                }}>
                                  {node.type}
                                </span>
                                <span style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
                                  {node.label}
                                </span>
                              </div>
                              {getStatusBadge(node.status)}
                            </div>

                            {isSelected && (
                              <div style={{
                                marginTop: '10px',
                                paddingTop: '10px',
                                borderTop: '1px solid hsl(var(--border))',
                                fontSize: '11px',
                                color: 'hsl(var(--muted-fg))'
                              }}>
                                <div style={{ fontFamily: 'monospace', marginBottom: '4px' }}>
                                  ID: {node.id}
                                </div>
                                {node.metadata && Object.keys(node.metadata).length > 0 && (
                                  <pre style={{
                                    backgroundColor: 'hsl(var(--card))',
                                    padding: '8px',
                                    borderRadius: '4px',
                                    fontSize: '10px',
                                    overflowX: 'auto',
                                    margin: 0
                                  }}>
                                    {JSON.stringify(node.metadata, null, 2)}
                                  </pre>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </>
              )}

              {/* Tab 2: Activity Trace */}
              {activeInspectorTab === 'trace' && (
                <>
                  {loadingActivities ? (
                    <div style={{ padding: '32px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
                      <RefreshCw size={20} className="animate-spin" style={{ margin: '0 auto 8px' }} />
                      Loading activity trace...
                    </div>
                  ) : activities.length === 0 ? (
                    <div style={{
                      padding: '32px 16px',
                      borderRadius: '8px',
                      border: '1px dashed hsl(var(--border))',
                      textAlign: 'center',
                      color: 'hsl(var(--muted-fg))'
                    }}>
                      <Activity size={28} style={{ margin: '0 auto 10px', opacity: 0.3 }} />
                      <div style={{ fontSize: '13px', fontWeight: 500, color: 'hsl(var(--fg))' }}>
                        {t('traceEmptyTitle')}
                      </div>
                      <div style={{ fontSize: '12px', marginTop: '4px', maxWidth: '400px', marginInline: 'auto' }}>
                        {t('traceEmptyDesc')}
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {activities.map((act) => (
                        <div
                          key={act.id}
                          style={{
                            padding: '12px 14px',
                            borderRadius: '8px',
                            backgroundColor: 'hsl(var(--bg))',
                            border: '1px solid hsl(var(--border))',
                            fontSize: '12px'
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ fontWeight: 600, color: 'hsl(var(--fg))' }}>
                                {act.agent || 'System'}
                              </span>
                              <span style={{
                                fontSize: '10px',
                                padding: '1px 5px',
                                borderRadius: '4px',
                                backgroundColor: 'hsl(var(--muted))',
                                color: 'hsl(var(--muted-fg))'
                              }}>
                                {act.activity_type}
                              </span>
                            </div>
                            <span style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))' }}>
                              {new Date(act.created_at).toLocaleTimeString()}
                            </span>
                          </div>
                          <div style={{ color: 'hsl(var(--fg))', lineHeight: 1.4 }}>
                            {act.message}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}

              {/* Tab 3: Telemetry & Specs */}
              {activeInspectorTab === 'telemetry' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{
                    padding: '12px',
                    borderRadius: '8px',
                    backgroundColor: 'hsl(var(--bg))',
                    border: '1px solid hsl(var(--border))',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                    fontSize: '12px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'hsl(var(--muted-fg))' }}>{t('telemetryMissionId')}</span>
                      <span style={{ fontFamily: 'monospace', fontWeight: 500 }}>{selectedMission.id}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'hsl(var(--muted-fg))' }}>{t('telemetryWorkspaceId')}</span>
                      <span style={{ fontFamily: 'monospace', fontWeight: 500 }}>{selectedMission.workspace_id}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'hsl(var(--muted-fg))' }}>{t('missionStatus')}</span>
                      <span>{selectedMission.status}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'hsl(var(--muted-fg))' }}>{t('telemetryTeamConfig')}</span>
                      <span style={{ fontWeight: 500 }}>{selectedMission.team_name || 'None'}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'hsl(var(--muted-fg))' }}>{t('telemetryCreated')}</span>
                      <span>{new Date(selectedMission.created_at).toLocaleString()}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'hsl(var(--muted-fg))' }}>{t('telemetryUpdated')}</span>
                      <span>{new Date(selectedMission.updated_at).toLocaleString()}</span>
                    </div>
                  </div>

                  <div style={{
                    padding: '12px',
                    borderRadius: '8px',
                    backgroundColor: 'hsl(var(--muted))',
                    fontSize: '11px',
                    color: 'hsl(var(--muted-fg))',
                    lineHeight: 1.5
                  }}>
                    {t('telemetryRuntimeNotice')}
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{ padding: '12px 20px', borderTop: '1px solid hsl(var(--border))', display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={() => setIsInspectorOpen(false)} className="btn btn-secondary" style={{ fontSize: '12px' }}>
                {t('closeInspector')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Specialist Details Modal (Slice 2B) */}
      {selectedSpecialistForPopover && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 70,
          padding: '16px'
        }}>
          <div style={{
            width: '100%',
            maxWidth: '500px',
            backgroundColor: 'hsl(var(--card))',
            borderRadius: '12px',
            border: '1px solid hsl(var(--border))',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,0.3)',
            overflow: 'hidden'
          }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid hsl(var(--border))', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <User size={18} className="text-primary" />
                <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                  {selectedSpecialistForPopover.name}
                </h3>
                <span style={{
                  fontSize: '11px',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  backgroundColor: workforceStatus.bg,
                  color: workforceStatus.color,
                  fontWeight: 600
                }}>
                  {workforceStatus.label}
                </span>
              </div>
              <button onClick={() => setSelectedSpecialistForPopover(null)} className="btn btn-ghost" style={{ padding: '4px' }}>
                <X size={16} />
              </button>
            </div>

            <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '13px' }}>
              <div>
                <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', marginBottom: '4px' }}>
                  {t('specialistRole')}
                </div>
                <div style={{ color: 'hsl(var(--fg))', fontWeight: 500 }}>
                  {selectedSpecialistForPopover.role}
                </div>
              </div>

              <div>
                <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', marginBottom: '4px' }}>
                  {t('specialistModel')}
                </div>
                <div style={{ color: 'hsl(var(--fg))' }}>
                  {selectedSpecialistForPopover.provider || currentTeam?.default_provider || 'OpenAI'} ({selectedSpecialistForPopover.model || currentTeam?.default_model || 'gpt-4o'})
                </div>
              </div>

              {selectedSpecialistForPopover.instructions && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', marginBottom: '4px' }}>
                    {t('specialistResponsibilities')}
                  </div>
                  <div style={{
                    color: 'hsl(var(--fg))',
                    backgroundColor: 'hsl(var(--bg))',
                    padding: '10px 12px',
                    borderRadius: '6px',
                    border: '1px solid hsl(var(--border))',
                    fontSize: '12px',
                    lineHeight: 1.5,
                    maxHeight: '140px',
                    overflowY: 'auto',
                    whiteSpace: 'pre-wrap'
                  }}>
                    {selectedSpecialistForPopover.instructions}
                  </div>
                </div>
              )}

              {selectedSpecialistForPopover.tools && selectedSpecialistForPopover.tools.length > 0 && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', marginBottom: '6px' }}>
                    {t('specialistCapabilities')}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {selectedSpecialistForPopover.tools.map((tl, i) => (
                      <span
                        key={i}
                        style={{
                          fontSize: '11px',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          backgroundColor: 'hsl(var(--muted))',
                          color: 'hsl(var(--fg))'
                        }}
                      >
                        {tl}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div style={{
                padding: '10px 12px',
                borderRadius: '6px',
                backgroundColor: 'hsl(var(--muted))',
                fontSize: '11px',
                color: 'hsl(var(--muted-fg))'
              }}>
                ℹ️ {workforceStatus.key === 'completed' ? t('workforceStatusCompletedNote') :
                    workforceStatus.key === 'running' ? t('workforceStatusRunningNote') :
                    workforceStatus.key === 'paused' ? t('workforceStatusPausedNote') :
                    workforceStatus.key === 'failed' ? t('workforceStatusFailedNote') :
                    t('workforceStatusReadyNote')}
              </div>
            </div>

            <div style={{ padding: '12px 20px', borderTop: '1px solid hsl(var(--border))', display: 'flex', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setSelectedSpecialistForPopover(null)}
                className="btn btn-secondary"
                style={{ fontSize: '12px' }}
              >
                {t('close')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Mission Confirmation Modal */}
      {missionToDelete && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 70,
          padding: '16px'
        }}>
          <div style={{
            width: '100%',
            maxWidth: '440px',
            backgroundColor: 'hsl(var(--card))',
            borderRadius: '12px',
            border: '1px solid hsl(var(--border))',
            padding: '20px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.3)'
          }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, margin: '0 0 8px', color: 'hsl(var(--fg))' }}>
              {t('confirmDeleteMissionTitle')}
            </h3>
            <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', margin: '0 0 20px', lineHeight: 1.5 }}>
              {t('confirmDeleteMissionDesc')}
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                onClick={() => setMissionToDelete(null)}
                className="btn btn-ghost"
                style={{ fontSize: '13px' }}
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteMission}
                className="btn btn-primary"
                style={{ fontSize: '13px', backgroundColor: '#e11d48' }}
              >
                {t('deleteMission')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Milestone Confirmation Modal */}
      {milestoneToDelete && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 70,
          padding: '16px'
        }}>
          <div style={{
            width: '100%',
            maxWidth: '420px',
            backgroundColor: 'hsl(var(--card))',
            borderRadius: '12px',
            border: '1px solid hsl(var(--border))',
            padding: '20px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.3)'
          }}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, margin: '0 0 8px', color: 'hsl(var(--fg))' }}>
              {t('confirmDeleteMilestoneTitle')}
            </h3>
            <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', margin: '0 0 18px', lineHeight: 1.5 }}>
              {t('confirmDeleteMilestoneDesc')}
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                onClick={() => setMilestoneToDelete(null)}
                className="btn btn-ghost"
                style={{ fontSize: '12px' }}
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteMilestone}
                className="btn btn-primary"
                style={{ fontSize: '12px', backgroundColor: '#e11d48' }}
              >
                Delete Step
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create New Mission Modal */}
      {isCreateOpen && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 50,
          padding: '16px'
        }}>
          <div style={{
            width: '100%',
            maxWidth: '560px',
            backgroundColor: 'hsl(var(--card))',
            borderRadius: '12px',
            border: '1px solid hsl(var(--border))',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.3)',
            overflow: 'hidden'
          }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid hsl(var(--border))', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Target size={18} className="text-primary" />
                <h3 style={{ fontSize: '16px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>{t('createMission')}</h3>
              </div>
              <button onClick={() => setIsCreateOpen(false)} className="btn btn-ghost" style={{ padding: '4px' }}>
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleCreateMission} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '6px', color: 'hsl(var(--fg))' }}>
                  {t('missionTitle')} *
                </label>
                <input
                  type="text"
                  placeholder="e.g., Conduct Competitor Benchmark & Architecture Audit"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="form-input"
                  style={{ width: '100%', fontSize: '13px' }}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '6px', color: 'hsl(var(--fg))' }}>
                  {t('missionObjective')} *
                </label>
                <textarea
                  placeholder="Clearly state what outcome or verified deliverables must be produced..."
                  value={newObjective}
                  onChange={(e) => setNewObjective(e.target.value)}
                  className="form-input"
                  rows={3}
                  style={{ width: '100%', fontSize: '13px', resize: 'vertical' }}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '6px', color: 'hsl(var(--fg))' }}>
                  {t('missionTeam')}
                </label>
                <select
                  value={newTeam}
                  onChange={(e) => setNewTeam(e.target.value)}
                  className="form-input"
                  style={{ width: '100%', fontSize: '13px' }}
                >
                  {availableTeams.length === 0 ? (
                    <option value="">Default Workforce</option>
                  ) : (
                    availableTeams.map(tm => <option key={tm} value={tm}>{tm}</option>)
                  )}
                </select>
              </div>

              {/* Initial Milestones */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <label style={{ fontSize: '12px', fontWeight: 500, color: 'hsl(var(--fg))' }}>
                    Initial Milestones (optional)
                  </label>
                  <button
                    type="button"
                    onClick={() => setNewMilestones([...newMilestones, { title: '', description: '' }])}
                    className="btn btn-ghost"
                    style={{ fontSize: '11px', padding: '2px 6px' }}
                  >
                    + Add Step
                  </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {newMilestones.map((ms, idx) => (
                    <div key={idx} style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', width: '20px' }}>#{idx + 1}</span>
                      <input
                        type="text"
                        placeholder={`Milestone ${idx + 1} title`}
                        value={ms.title}
                        onChange={(e) => {
                          const updated = [...newMilestones];
                          updated[idx].title = e.target.value;
                          setNewMilestones(updated);
                        }}
                        className="form-input"
                        style={{ flex: 1, fontSize: '12px' }}
                      />
                      {newMilestones.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setNewMilestones(newMilestones.filter((_, i) => i !== idx))}
                          className="btn btn-ghost text-muted-fg hover:text-rose-500"
                          style={{ padding: '4px' }}
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '12px', borderTop: '1px solid hsl(var(--border))', paddingTop: '14px' }}>
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="btn btn-ghost"
                  style={{ fontSize: '13px' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="btn btn-primary"
                  style={{ fontSize: '13px' }}
                >
                  {creating ? 'Creating...' : t('createMission')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
