import React, { useState, useEffect, useContext, useCallback, useMemo, useRef } from 'react';
import {
  Target, Plus, CheckCircle, Circle, Play, AlertCircle, Trash2,
  Users, Layers, Sparkles, X, RefreshCw, Pause,
  Square, RotateCcw, FileText, MessageSquare, Check, ArrowLeft,
  Clock, ShieldAlert, ChevronRight
} from 'lucide-react';
import { apiUrl } from './api';
import { useTranslation } from './i18n';
import { ToastContext } from './toast';
import { Tooltip } from './Tooltip';

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

  // Teams list for selector
  const [availableTeams, setAvailableTeams] = useState<string[]>([]);

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

  useEffect(() => {
    if (selectedMission) {
      loadGraph(selectedMission.id);
    } else {
      setGraphData(null);
    }
  }, [selectedMission?.id, loadGraph]);

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
      showToast?.(err.message || 'Failed to create mission', 'error');
    } finally {
      setCreating(false);
    }
  };

  const handleUpdateStatus = async (status: string) => {
    if (!selectedMission) return;
    try {
      const res = await fetch(apiUrl(`/api/missions/${selectedMission.id}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error('Failed to update mission status');
      const updated = await res.json();
      setSelectedMission(updated);
      setMissions(prev => prev.map(m => m.id === updated.id ? updated : m));
      showToast?.(`Mission status: ${status}`, 'success');
      loadGraph(updated.id);
    } catch (err: any) {
      showToast?.(err.message, 'error');
    }
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

  // Calculate specialists list for human workforce display
  const specialists = useMemo(() => {
    if (!selectedMission?.team_name) {
      return ['Strategic Lead', 'Research Specialist', 'Quality Reviewer'];
    }
    return ['Domain Lead', 'Autonomous Specialist', 'Verification Auditor'];
  }, [selectedMission?.team_name]);

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
                  </div>
                </div>

                {/* Context-Driven Action Buttons (Eliminated Developer Select Dropdown) */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  {/* DRAFT STATE */}
                  {selectedMission.status === 'draft' && (
                    <button
                      onClick={() => handleUpdateStatus('running')}
                      className="btn btn-primary"
                      style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 600 }}
                    >
                      <Play size={14} fill="currentColor" />
                      <span>{t('startMission')}</span>
                    </button>
                  )}

                  {/* RUNNING STATE */}
                  {selectedMission.status === 'running' && (
                    <>
                      <button
                        onClick={() => handleUpdateStatus('interrupted')}
                        className="btn btn-secondary"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <Pause size={14} />
                        <span>{t('pauseMission')}</span>
                      </button>
                      <button
                        onClick={() => handleUpdateStatus('cancelled')}
                        className="btn btn-ghost text-rose-500 hover:bg-rose-500/10"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <Square size={14} />
                        <span>{t('stopMission')}</span>
                      </button>
                    </>
                  )}

                  {/* INTERRUPTED / PAUSED STATE */}
                  {selectedMission.status === 'interrupted' && (
                    <>
                      <button
                        onClick={() => handleUpdateStatus('running')}
                        className="btn btn-primary"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <Play size={14} fill="currentColor" />
                        <span>{t('resumeMission')}</span>
                      </button>
                      <button
                        onClick={() => handleUpdateStatus('cancelled')}
                        className="btn btn-ghost text-rose-500 hover:bg-rose-500/10"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <Square size={14} />
                        <span>{t('cancelMission')}</span>
                      </button>
                    </>
                  )}

                  {/* AWAITING APPROVAL STATE */}
                  {selectedMission.status === 'awaiting_approval' && (
                    <>
                      <button
                        onClick={() => handleUpdateStatus('running')}
                        className="btn btn-primary"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', backgroundColor: '#10b981' }}
                      >
                        <Check size={15} />
                        <span>{t('approveMission')}</span>
                      </button>
                      <button
                        onClick={() => handleUpdateStatus('cancelled')}
                        className="btn btn-ghost text-rose-500 hover:bg-rose-500/10"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <X size={15} />
                        <span>{t('rejectMission')}</span>
                      </button>
                    </>
                  )}

                  {/* COMPLETED STATE */}
                  {selectedMission.status === 'completed' && (
                    <>
                      <button
                        onClick={() => handleUpdateStatus('running')}
                        className="btn btn-secondary"
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                      >
                        <RotateCcw size={13} />
                        <span>{t('rerunMission')}</span>
                      </button>
                    </>
                  )}

                  {/* FAILED STATE */}
                  {selectedMission.status === 'failed' && (
                    <button
                      onClick={() => handleUpdateStatus('running')}
                      className="btn btn-secondary text-rose-500"
                      style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                    >
                      <RotateCcw size={13} />
                      <span>{t('retryStep')}</span>
                    </button>
                  )}

                  {/* CANCELLED STATE */}
                  {selectedMission.status === 'cancelled' && (
                    <button
                      onClick={() => handleUpdateStatus('draft')}
                      className="btn btn-secondary"
                      style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                    >
                      <RotateCcw size={13} />
                      <span>{t('rerunMission')}</span>
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
              {/* 1. OPERATIONAL PULSE BANNER */}
              <div style={{
                padding: '14px 18px',
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
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    backgroundColor: selectedMission.status === 'running'
                      ? 'hsl(var(--primary))'
                      : selectedMission.status === 'awaiting_approval'
                      ? '#f59e0b'
                      : selectedMission.status === 'completed'
                      ? '#10b981'
                      : 'hsl(var(--muted-fg))'
                  }} />
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
                      {selectedMission.status === 'running' && t('operationalPulseRunning')}
                      {selectedMission.status === 'draft' && t('operationalPulseIdle')}
                      {selectedMission.status === 'interrupted' && t('operationalPulsePaused')}
                      {selectedMission.status === 'awaiting_approval' && t('operationalPulseApproval')}
                      {selectedMission.status === 'completed' && t('operationalPulseCompleted')}
                      {selectedMission.status === 'failed' && t('operationalPulseFailed')}
                      {selectedMission.status === 'cancelled' && t('operationalPulseCancelled')}
                    </div>
                    <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '3px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <span>{t('assignedWorkforceLabel')}: {selectedMission.team_name || t('defaultWorkforce')}</span>
                      <span style={{ opacity: 0.4 }}>•</span>
                      <span style={{ fontStyle: 'italic', opacity: 0.85 }}>{t('runtimeExecutionNotice')}</span>
                    </div>
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

              {/* 2. OUTCOME CHARTER CARD */}
              <div style={{
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <Target size={16} className="text-primary" />
                  <span style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'hsl(var(--primary))' }}>
                    {t('outcomeCharter')}
                  </span>
                </div>

                <h3 style={{ fontSize: '16px', fontWeight: 600, margin: '0 0 10px', color: 'hsl(var(--fg))' }}>
                  {t('whatAreWeAchieving')}
                </h3>

                <p style={{
                  fontSize: '14px',
                  color: 'hsl(var(--fg))',
                  lineHeight: 1.6,
                  margin: '0 0 16px',
                  whiteSpace: 'pre-wrap'
                }}>
                  {selectedMission.objective}
                </p>

                {/* Workforce & Specialists Stack */}
                <div style={{
                  borderTop: '1px solid hsl(var(--border))',
                  paddingTop: '14px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '10px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>
                      {t('assignedWorkforceLabel')}: <strong>{selectedMission.team_name || t('defaultWorkforce')}</strong>
                    </span>
                    <span style={{ color: 'hsl(var(--border))' }}>•</span>
                    <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>{t('specialistsMobilized')}:</span>
                    {specialists.map((role, idx) => (
                      <span
                        key={idx}
                        style={{
                          fontSize: '11px',
                          padding: '2px 8px',
                          borderRadius: '12px',
                          backgroundColor: 'hsl(var(--muted))',
                          color: 'hsl(var(--fg))',
                          fontWeight: 500
                        }}
                      >
                        {role}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* 3. MILESTONE PROGRESSION STEPPER (Single unified list, no side-by-side duplicate) */}
              <div style={{
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                  <div>
                    <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                      {t('milestoneProgression')}
                    </h3>
                    <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                      {selectedMission.milestones.filter(m => m.status === 'completed').length} {t('ofMilestones')} {selectedMission.milestones.length} {t('completedCount')}
                    </span>
                  </div>

                  <button
                    onClick={() => setIsAddingMilestone(!isAddingMilestone)}
                    className="btn btn-ghost"
                    style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '5px', padding: '4px 10px' }}
                  >
                    <Plus size={14} />
                    <span>{t('addStep')}</span>
                  </button>
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

                {/* Milestones Stepper Sequence */}
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
                      No milestones created yet. Add steps to track verifiable progression.
                    </div>
                  ) : (
                    selectedMission.milestones.map((m, idx) => {
                      const isDone = m.status === 'completed';
                      const isRunning = m.status === 'running';

                      return (
                        <div
                          key={m.id}
                          className="group"
                          onMouseEnter={() => setHoveredMilestoneId(m.id)}
                          onMouseLeave={() => setHoveredMilestoneId(null)}
                          style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '12px',
                            padding: '12px 14px',
                            borderRadius: '8px',
                            backgroundColor: isDone
                              ? 'hsl(var(--card) / 0.5)'
                              : isRunning
                              ? 'hsl(var(--primary) / 0.04)'
                              : 'hsl(var(--card))',
                            border: isRunning
                              ? '1px solid hsl(var(--primary) / 0.4)'
                              : '1px solid hsl(var(--border))',
                            transition: 'all 0.15s ease'
                          }}
                        >
                          {/* Status Clickable Checkbox/Action */}
                          <button
                            onClick={() => handleToggleMilestone(m)}
                            title="Toggle milestone state"
                            style={{
                              background: 'none',
                              border: 'none',
                              padding: 0,
                              cursor: 'pointer',
                              color: isDone ? '#10b981' : isRunning ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
                              marginTop: '2px'
                            }}
                          >
                            {isDone ? (
                              <CheckCircle size={18} />
                            ) : isRunning ? (
                              <Play size={16} fill="currentColor" />
                            ) : (
                              <Circle size={18} />
                            )}
                          </button>

                          <div style={{ flex: 1 }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                              <div style={{
                                fontSize: '13.5px',
                                fontWeight: isRunning ? 600 : 500,
                                color: isDone ? 'hsl(var(--muted-fg))' : 'hsl(var(--fg))',
                                textDecoration: isDone ? 'line-through' : 'none'
                              }}>
                                <span style={{ color: 'hsl(var(--muted-fg))', marginRight: '6px', fontSize: '12px', fontWeight: 400 }}>
                                  #{idx + 1}
                                </span>
                                {m.title}
                              </div>

                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minHeight: '24px' }}>
                                {isDone && (
                                  <span style={{ fontSize: '11px', color: '#10b981', fontWeight: 500 }}>
                                    {t('completedAt')}
                                  </span>
                                )}
                                {isRunning && (
                                  <span style={{ fontSize: '11px', color: 'hsl(var(--primary))', fontWeight: 600 }}>
                                    {t('statusRunning')}
                                  </span>
                                )}

                                {/* Hover-activated deletion (No persistent trash icons) */}
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

                            {m.completed_at && (
                              <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
                                {t('completedAt')} {new Date(m.completed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* 4. DELIVERABLES DOSSIER PLACEHOLDER (Slice 2D Preparation) */}
              <div style={{
                padding: '20px',
                borderRadius: '12px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <FileText size={16} className="text-primary" />
                  <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                    {t('deliverablesDossier')}
                  </h3>
                </div>

                <div style={{
                  padding: '24px 16px',
                  borderRadius: '8px',
                  border: '1px dashed hsl(var(--border))',
                  textAlign: 'center',
                  color: 'hsl(var(--muted-fg))'
                }}>
                  <FileText size={28} style={{ margin: '0 auto 10px', opacity: 0.3 }} />
                  <div style={{ fontSize: '13px', fontWeight: 500, color: 'hsl(var(--fg))' }}>
                    {t('deliverablesPlaceholderTitle')}
                  </div>
                  <div style={{ fontSize: '12px', marginTop: '4px', maxWidth: '420px', marginInline: 'auto' }}>
                    {t('deliverablesPlaceholderDesc')}
                  </div>
                </div>
              </div>

              {/* 5. PROGRESSIVE DISCLOSURE INSPECTOR GATEWAY */}
              <div style={{
                padding: '16px 20px',
                borderRadius: '10px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '16px'
              }}>
                <div>
                  <div style={{ fontSize: '13.5px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
                    {t('inspectExecution')}
                  </div>
                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                    {t('inspectExecutionDesc')}
                  </div>
                </div>

                <button
                  onClick={() => setIsInspectorOpen(true)}
                  className="btn btn-secondary"
                  style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                >
                  <Layers size={14} />
                  <span>Inspect</span>
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {/* Progressive Disclosure Inspector Modal / Drawer */}
      {isInspectorOpen && selectedMission && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 60,
          padding: '20px'
        }}>
          <div style={{
            width: '100%',
            maxWidth: '680px',
            maxHeight: '85vh',
            backgroundColor: 'hsl(var(--card))',
            borderRadius: '12px',
            border: '1px solid hsl(var(--border))',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.4)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden'
          }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid hsl(var(--border))', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Layers size={18} className="text-primary" />
                <div>
                  <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
                    {t('inspectModalTitle')}
                  </h3>
                  <p style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', margin: '2px 0 0' }}>
                    {t('inspectModalSubtitle')}
                  </p>
                </div>
              </div>
              <button onClick={() => setIsInspectorOpen(false)} className="btn btn-ghost" style={{ padding: '4px' }}>
                <X size={16} />
              </button>
            </div>

            <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
              {/* Notice that full interactive 2D canvas comes in Slice 2E */}
              <div style={{
                padding: '10px 14px',
                borderRadius: '6px',
                backgroundColor: 'hsl(var(--muted))',
                fontSize: '12px',
                color: 'hsl(var(--muted-fg))',
                marginBottom: '16px'
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
                  {graphData.nodes.map(node => (
                    <div
                      key={node.id}
                      style={{
                        padding: '12px 14px',
                        borderRadius: '8px',
                        backgroundColor: node.type === 'mission' ? 'hsl(var(--primary) / 0.08)' : 'hsl(var(--bg))',
                        border: '1px solid hsl(var(--border))',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between'
                      }}
                    >
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
                  ))}
                </div>
              )}
            </div>

            <div style={{ padding: '12px 20px', borderTop: '1px solid hsl(var(--border))', display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={() => setIsInspectorOpen(false)} className="btn btn-secondary" style={{ fontSize: '12px' }}>
                {t('closeInspector')}
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
