import { useState, useEffect, useCallback, useContext } from 'react';
import {
  Zap, Plus, Play, Edit2, Trash2, Clock, Folder, Globe,
  CheckCircle2, AlertCircle, RefreshCw, X, ArrowRight,
  Layers, Bell, FileText, Database, ShieldAlert
} from 'lucide-react';
import { TopHeader } from './TopHeader';
import { useTranslation } from './i18n';
import { Tooltip } from './Tooltip';
import { ToastContext } from './toast';
import { apiUrl, apiError } from './api';
import { MagicEnhancePromptButton } from './MagicEnhancePromptButton';

interface TriggerConfig {
  type: string;
  cron?: string;
  interval_seconds?: number;
  watch_path?: string;
  watch_pattern?: string;
  watch_events?: string[];
  webhook_secret?: string;
  webhook_slug?: string;
}

interface PipelineStep {
  id: string;
  name: string;
  agent_name: string;
  prompt_template: string;
  depends_on?: string[];
}

interface OutputDestination {
  type: string;
  target_path?: string;
  project_id?: string;
  notify_title?: string;
}

interface Automation {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  team_name?: string;
  trigger: TriggerConfig;
  steps: PipelineStep[];
  output_destination?: OutputDestination;
  created_at: string;
  updated_at: string;
  last_run_at?: string;
  last_run_status?: string;
  next_run_at?: string;
}

interface AutomationRun {
  run_id: string;
  automation_id: string;
  automation_name: string;
  trigger_type: string;
  status: string;
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
  input_payload?: Record<string, any>;
  output_result?: string;
  error?: string;
  step_runs?: Array<{
    step_id: string;
    step_name: string;
    agent_name: string;
    status: string;
    prompt_used: string;
    output: string;
    error?: string;
    duration_seconds?: number;
  }>;
}

export function Automations() {
  const { t } = useTranslation();
  const showToast = useContext(ToastContext);

  const [automations, setAutomations] = useState<Automation[]>([]);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [teams, setTeams] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'workflows' | 'history'>('workflows');
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());

  // Builder Modal State
  const [isBuilderOpen, setIsBuilderOpen] = useState(false);
  const [editingAutomation, setEditingAutomation] = useState<Automation | null>(null);

  // Delete Confirm State
  const [deletingAutomation, setDeletingAutomation] = useState<Automation | null>(null);

  // Run Details Modal
  const [selectedRun, setSelectedRun] = useState<AutomationRun | null>(null);

  const fetchAutomations = useCallback(() => {
    setLoading(true);
    fetch(apiUrl('/api/automations'))
      .then((res) => res.json())
      .then((data) => {
        setAutomations(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load automations', err);
        setLoading(false);
      });
  }, []);

  const fetchRuns = useCallback(() => {
    fetch(apiUrl('/api/automations/history?limit=50'))
      .then((res) => res.json())
      .then((data) => {
        setRuns(Array.isArray(data) ? data : []);
      })
      .catch((err) => {
        console.error('Failed to load runs history', err);
      });
  }, []);

  const fetchTeamsAndAgents = useCallback(() => {
    fetch(apiUrl('/api/teams'))
      .then((res) => res.json())
      .then((data) => setTeams(Array.isArray(data) ? data : []))
      .catch(console.error);

    fetch(apiUrl('/api/agents'))
      .then((res) => res.json())
      .then((data) => setAgents(Array.isArray(data) ? data : []))
      .catch(console.error);
  }, []);

  useEffect(() => {
    fetchAutomations();
    fetchRuns();
    fetchTeamsAndAgents();
  }, [fetchAutomations, fetchRuns, fetchTeamsAndAgents]);

  const handleToggle = async (auto: Automation) => {
    const nextEnabled = !auto.enabled;
    // Optimistic UI update
    setAutomations((prev) =>
      prev.map((a) => (a.id === auto.id ? { ...a, enabled: nextEnabled } : a))
    );

    try {
      const res = await fetch(apiUrl(`/api/automations/${auto.id}/toggle`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      if (!res.ok) throw await apiError(res, 'Failed to toggle automation');
      showToast(
        nextEnabled ? t('statusEnabled') : t('statusDisabled'),
        'success'
      );
    } catch (err: any) {
      // Revert optimistic update
      setAutomations((prev) =>
        prev.map((a) => (a.id === auto.id ? { ...a, enabled: auto.enabled } : a))
      );
      showToast(err.message || 'Failed to toggle automation', 'error');
    }
  };

  const handleRunNow = async (auto: Automation) => {
    setRunningIds((prev) => new Set(prev).add(auto.id));
    showToast(`${t('runNow')}: ${auto.name}`, 'info');

    try {
      const res = await fetch(apiUrl(`/api/automations/${auto.id}/run`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payload: {} }),
      });
      if (!res.ok) throw await apiError(res, 'Failed to run automation');
      const runData = await res.json();
      showToast(
        runData.status === 'completed'
          ? `${t('statusCompleted')}: ${auto.name}`
          : `${t('statusFailed')}: ${auto.name}`,
        runData.status === 'completed' ? 'success' : 'error'
      );
      fetchAutomations();
      fetchRuns();
    } catch (err: any) {
      showToast(err.message || 'Failed to run automation', 'error');
    } finally {
      setRunningIds((prev) => {
        const next = new Set(prev);
        next.delete(auto.id);
        return next;
      });
    }
  };

  const handleDelete = async (auto: Automation) => {
    try {
      const res = await fetch(apiUrl(`/api/automations/${auto.id}`), {
        method: 'DELETE',
      });
      if (!res.ok) throw await apiError(res, 'Failed to delete automation');
      showToast(t('deleteAutomation'), 'success');
      setDeletingAutomation(null);
      fetchAutomations();
      fetchRuns();
    } catch (err: any) {
      showToast(err.message || 'Failed to delete automation', 'error');
    }
  };

  const activeCount = automations.filter((a) => a.enabled).length;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto' }}>
      <TopHeader
        title={t('automationsTitle')}
        icon={Zap}
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Tooltip content="Refresh automations and runs">
              <button
                className="btn btn-ghost"
                onClick={() => {
                  fetchAutomations();
                  fetchRuns();
                }}
              >
                <RefreshCw size={15} />
              </button>
            </Tooltip>
            <button
              className="btn btn-primary"
              onClick={() => {
                setEditingAutomation(null);
                setIsBuilderOpen(true);
              }}
            >
              <Plus size={16} /> {t('createAutomation')}
            </button>
          </div>
        }
      />

      <div style={{ maxWidth: '1100px', width: '100%', margin: '24px auto', padding: '0 32px' }}>
        {/* Metric Cards Banner */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
          <div className="card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{ width: '40px', height: '40px', borderRadius: '10px', backgroundColor: 'hsl(var(--primary)/0.12)', color: 'hsl(var(--primary))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Zap size={20} />
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>{t('activeAutomations')}</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'hsl(var(--fg))' }}>
                {activeCount} <span style={{ fontSize: '13px', fontWeight: 400, color: 'hsl(var(--muted-fg))' }}>/ {automations.length}</span>
              </div>
            </div>
          </div>

          <div className="card" style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{ width: '40px', height: '40px', borderRadius: '10px', backgroundColor: 'hsl(var(--success)/0.12)', color: 'hsl(var(--success))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CheckCircle2 size={20} />
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>{t('totalRuns')}</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'hsl(var(--fg))' }}>
                {runs.length}
              </div>
            </div>
          </div>
        </div>

        {/* View Switcher Tabs */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', borderBottom: '1px solid hsl(var(--border))', paddingBottom: '6px' }}>
          <button
            className={`btn btn-ghost ${activeTab === 'workflows' ? 'active' : ''}`}
            style={{
              padding: '6px 14px',
              fontSize: '13px',
              fontWeight: activeTab === 'workflows' ? 600 : 400,
              color: activeTab === 'workflows' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              borderBottom: activeTab === 'workflows' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              borderRadius: 0,
            }}
            onClick={() => setActiveTab('workflows')}
          >
            {t('workflowTab')} ({automations.length})
          </button>
          <button
            className={`btn btn-ghost ${activeTab === 'history' ? 'active' : ''}`}
            style={{
              padding: '6px 14px',
              fontSize: '13px',
              fontWeight: activeTab === 'history' ? 600 : 400,
              color: activeTab === 'history' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              borderBottom: activeTab === 'history' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              borderRadius: 0,
            }}
            onClick={() => setActiveTab('history')}
          >
            {t('historyTab')} ({runs.length})
          </button>
        </div>

        {/* WORKFLOWS TAB */}
        {activeTab === 'workflows' && (
          <div>
            {automations.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '20px' }}>
                {automations.map((auto) => {
                  const isRunning = runningIds.has(auto.id);
                  return (
                    <div
                      key={auto.id}
                      className="card card-interactive"
                      style={{
                        padding: '20px',
                        display: 'flex',
                        flexDirection: 'column',
                        height: '100%',
                        opacity: auto.enabled ? 1 : 0.72,
                      }}
                    >
                      {/* Top row: Name + Toggle Switch */}
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '10px' }}>
                        <div>
                          <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>{auto.name}</h3>
                          {auto.description && (
                            <p style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', margin: '4px 0 0', lineHeight: 1.4 }}>
                              {auto.description}
                            </p>
                          )}
                        </div>
                        <Tooltip content={auto.enabled ? 'Click to disable' : 'Click to enable'}>
                          <button
                            className={`badge ${auto.enabled ? 'badge-success' : 'badge-default'}`}
                            style={{ cursor: 'pointer', border: 'none', padding: '4px 10px', fontSize: '11px', fontWeight: 600 }}
                            onClick={() => handleToggle(auto)}
                          >
                            {auto.enabled ? t('statusEnabled') : t('statusDisabled')}
                          </button>
                        </Tooltip>
                      </div>

                      {/* Badges Strip: Trigger & Team */}
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '14px' }}>
                        {auto.trigger.type === 'schedule' && (
                          <span className="badge badge-primary" style={{ fontSize: '11px' }}>
                            <Clock size={11} /> {auto.trigger.cron ? `Cron: ${auto.trigger.cron}` : `Interval: ${auto.trigger.interval_seconds}s`}
                          </span>
                        )}
                        {auto.trigger.type === 'file_watcher' && (
                          <span className="badge" style={{ fontSize: '11px', background: 'hsl(var(--secondary)/0.15)', color: 'hsl(var(--primary))' }}>
                            <Folder size={11} /> Watch: {auto.trigger.watch_pattern || '*.*'}
                          </span>
                        )}
                        {auto.trigger.type === 'webhook' && (
                          <span className="badge" style={{ fontSize: '11px', background: 'hsl(var(--muted))' }}>
                            <Globe size={11} /> Webhook
                          </span>
                        )}
                        {auto.trigger.type === 'manual' && (
                          <span className="badge" style={{ fontSize: '11px', background: 'hsl(var(--muted))' }}>
                            <Play size={11} /> Manual
                          </span>
                        )}
                        {auto.team_name && (
                          <span className="badge" style={{ fontSize: '11px' }}>
                            <Layers size={11} /> {auto.team_name}
                          </span>
                        )}
                      </div>

                      {/* Pipeline Steps Sequence */}
                      <div style={{ marginBottom: '16px', background: 'hsl(var(--muted)/0.3)', padding: '10px 12px', borderRadius: '8px', border: '1px solid hsl(var(--border)/0.5)' }}>
                        <div style={{ fontSize: '10px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>
                          Pipeline ({auto.steps.length} {auto.steps.length === 1 ? t('stepSingular') : t('stepPlural')})
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                          {auto.steps.map((step, idx) => (
                            <div key={step.id || idx} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span className="badge" style={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', fontSize: '11px', fontWeight: 500 }}>
                                {step.agent_name || 'Agent'}: {step.name}
                              </span>
                              {idx < auto.steps.length - 1 && <ArrowRight size={10} className="text-muted" />}
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Output Destination Info */}
                      {auto.output_destination && (
                        <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '14px' }}>
                          {auto.output_destination.type === 'file' && (
                            <>
                              <FileText size={12} className="text-primary" />
                              <span>Deliverable: <code>{auto.output_destination.target_path}</code></span>
                            </>
                          )}
                          {auto.output_destination.type === 'knowledge' && (
                            <>
                              <Database size={12} className="text-primary" />
                              <span>Output: Ingest into Knowledge Base</span>
                            </>
                          )}
                          {auto.output_destination.type === 'notification' && (
                            <>
                              <Bell size={12} className="text-primary" />
                              <span>Output: System Notification</span>
                            </>
                          )}
                        </div>
                      )}

                      {/* Last Execution Info */}
                      <div style={{ marginTop: 'auto', paddingTop: '12px', borderTop: '1px solid hsl(var(--border)/0.4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                          {auto.last_run_status ? (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                              {auto.last_run_status === 'completed' ? (
                                <CheckCircle2 size={12} className="text-success" />
                              ) : (
                                <AlertCircle size={12} className="text-error" />
                              )}
                              {t('lastRun')}: {new Date(auto.last_run_at || '').toLocaleTimeString()}
                            </span>
                          ) : (
                            <span>{t('neverRun')}</span>
                          )}
                        </div>

                        {/* Action buttons */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Tooltip content={t('runNow')}>
                            <button
                              className="btn btn-ghost"
                              style={{ padding: '6px' }}
                              disabled={isRunning}
                              onClick={() => handleRunNow(auto)}
                            >
                              <Play size={14} className={isRunning ? 'animate-spin' : 'text-primary'} />
                            </button>
                          </Tooltip>

                          <Tooltip content={t('editAutomation')}>
                            <button
                              className="btn btn-ghost"
                              style={{ padding: '6px' }}
                              onClick={() => {
                                setEditingAutomation(auto);
                                setIsBuilderOpen(true);
                              }}
                            >
                              <Edit2 size={14} />
                            </button>
                          </Tooltip>

                          <Tooltip content={t('deleteAutomation')}>
                            <button
                              className="btn btn-ghost"
                              style={{ padding: '6px' }}
                              onClick={() => setDeletingAutomation(auto)}
                            >
                              <Trash2 size={14} className="text-muted" />
                            </button>
                          </Tooltip>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : !loading && (
              <div className="card" style={{ textAlign: 'center', padding: '56px 24px' }}>
                <Zap size={44} className="text-muted" style={{ margin: '0 auto 16px' }} />
                <h3 style={{ fontSize: '18px', marginBottom: '8px' }}>{t('noAutomationsYet')}</h3>
                <p className="text-muted" style={{ fontSize: '13.5px', maxWidth: '480px', margin: '0 auto 24px', lineHeight: 1.5 }}>
                  {t('noAutomationsDesc')}
                </p>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    setEditingAutomation(null);
                    setIsBuilderOpen(true);
                  }}
                >
                  <Plus size={16} /> {t('createAutomation')}
                </button>
              </div>
            )}
          </div>
        )}

        {/* HISTORY TAB */}
        {activeTab === 'history' && (
          <div>
            {runs.length > 0 ? (
              <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Automation</th>
                      <th>Trigger</th>
                      <th>Status</th>
                      <th>Started At</th>
                      <th>Duration</th>
                      <th>Steps</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((run) => (
                      <tr key={run.run_id}>
                        <td style={{ fontWeight: 600 }}>{run.automation_name}</td>
                        <td>
                          <span className="badge" style={{ textTransform: 'capitalize' }}>
                            {run.trigger_type}
                          </span>
                        </td>
                        <td>
                          <span className={`badge ${run.status === 'completed' ? 'badge-success' : run.status === 'failed' ? 'badge-error' : 'badge-warning'}`}>
                            {run.status === 'completed' && <CheckCircle2 size={11} style={{ marginRight: 3 }} />}
                            {run.status === 'failed' && <AlertCircle size={11} style={{ marginRight: 3 }} />}
                            {run.status}
                          </span>
                        </td>
                        <td className="text-muted" style={{ fontSize: '12px' }}>
                          {new Date(run.started_at).toLocaleString()}
                        </td>
                        <td className="text-muted" style={{ fontSize: '12px' }}>
                          {run.duration_seconds ? `${run.duration_seconds}s` : '—'}
                        </td>
                        <td>
                          <span className="badge">
                            {run.step_runs ? run.step_runs.length : 0} steps
                          </span>
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            className="btn btn-ghost"
                            style={{ fontSize: '12px', padding: '4px 8px' }}
                            onClick={() => setSelectedRun(run)}
                          >
                            Details
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="card" style={{ textAlign: 'center', padding: '40px 20px', color: 'hsl(var(--muted-fg))' }}>
                <Clock size={32} style={{ margin: '0 auto 12px' }} />
                <div>{t('noHistoryYet')}</div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* AUTOMATION BUILDER MODAL / SLIDE-OVER */}
      {isBuilderOpen && (
        <AutomationBuilderModal
          isOpen={isBuilderOpen}
          initialData={editingAutomation}
          teams={teams}
          agents={agents}
          onClose={() => {
            setIsBuilderOpen(false);
            setEditingAutomation(null);
          }}
          onSaved={() => {
            setIsBuilderOpen(false);
            setEditingAutomation(null);
            fetchAutomations();
            fetchRuns();
          }}
        />
      )}

      {/* DELETE CONFIRMATION MODAL */}
      {deletingAutomation && (
        <div className="modal-overlay" onClick={() => setDeletingAutomation(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '420px', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px', color: 'hsl(var(--error))' }}>
              <ShieldAlert size={24} />
              <h3 style={{ margin: 0, fontSize: '16px' }}>{t('deleteAutomation')}</h3>
            </div>
            <p style={{ fontSize: '13.5px', color: 'hsl(var(--muted-fg))', margin: '0 0 20px', lineHeight: 1.5 }}>
              {t('deleteAutomationConfirm')}
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="btn btn-secondary" onClick={() => setDeletingAutomation(null)}>
                {t('cancel')}
              </button>
              <button className="btn btn-primary" style={{ backgroundColor: 'hsl(var(--error))', borderColor: 'hsl(var(--error))' }} onClick={() => handleDelete(deletingAutomation)}>
                {t('delete')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* RUN DETAILS MODAL */}
      {selectedRun && (
        <div className="modal-overlay" onClick={() => setSelectedRun(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '640px', maxHeight: '85vh', overflowY: 'auto', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '16px' }}>Execution Run: {selectedRun.automation_name}</h3>
                <div style={{ fontSize: '11.5px', fontFamily: 'monospace', color: 'hsl(var(--muted-fg))' }}>{selectedRun.run_id}</div>
              </div>
              <button className="btn btn-ghost" onClick={() => setSelectedRun(null)}>
                <X size={16} />
              </button>
            </div>

            <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
              <span className={`badge ${selectedRun.status === 'completed' ? 'badge-success' : 'badge-error'}`}>
                {selectedRun.status}
              </span>
              <span className="badge">Trigger: {selectedRun.trigger_type}</span>
              <span className="badge">Duration: {selectedRun.duration_seconds || 0}s</span>
            </div>

            {selectedRun.error && (
              <div style={{ padding: '12px', borderRadius: '8px', backgroundColor: 'hsl(var(--error)/0.12)', border: '1px solid hsl(var(--error)/0.3)', color: 'hsl(var(--error))', fontSize: '12.5px', marginBottom: '16px' }}>
                <strong>Error:</strong> {selectedRun.error}
              </div>
            )}

            {selectedRun.step_runs && selectedRun.step_runs.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ fontSize: '13px', margin: '0 0 8px', color: 'hsl(var(--fg))' }}>Step Executions</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {selectedRun.step_runs.map((step, idx) => (
                    <div key={idx} style={{ padding: '10px 12px', borderRadius: '8px', backgroundColor: 'hsl(var(--muted)/0.4)', border: '1px solid hsl(var(--border))' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontSize: '12.5px', fontWeight: 600 }}>{step.step_name} ({step.agent_name})</span>
                        <span className={`badge ${step.status === 'completed' ? 'badge-success' : 'badge-error'}`} style={{ fontSize: '10px' }}>
                          {step.status}
                        </span>
                      </div>
                      <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', whiteSpace: 'pre-wrap', maxHeight: '100px', overflowY: 'auto' }}>
                        {step.output}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {selectedRun.output_result && (
              <div>
                <h4 style={{ fontSize: '13px', margin: '0 0 8px', color: 'hsl(var(--fg))' }}>Final Deliverable Output</h4>
                <pre style={{ padding: '12px', borderRadius: '8px', backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', fontSize: '12px', whiteSpace: 'pre-wrap', maxHeight: '200px', overflowY: 'auto' }}>
                  {selectedRun.output_result}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface ModalProps {
  isOpen: boolean;
  initialData?: Automation | null;
  teams: any[];
  agents: any[];
  onClose: () => void;
  onSaved: () => void;
}

function AutomationBuilderModal({ initialData, teams, agents, onClose, onSaved }: ModalProps) {
  const { t } = useTranslation();
  const showToast = useContext(ToastContext);

  const [name, setName] = useState(initialData?.name || '');
  const [description, setDescription] = useState(initialData?.description || '');
  const [teamName, setTeamName] = useState(initialData?.team_name || (teams[0]?.name || ''));
  const [triggerType, setTriggerType] = useState(initialData?.trigger?.type || 'schedule');
  const [cron, setCron] = useState(initialData?.trigger?.cron || '0 9 * * 1');
  const [intervalSec, setIntervalSec] = useState(initialData?.trigger?.interval_seconds || 3600);
  const [watchPath, setWatchPath] = useState(initialData?.trigger?.watch_path || 'input_files');
  const [watchPattern, setWatchPattern] = useState(initialData?.trigger?.watch_pattern || '*.md');

  const [steps, setSteps] = useState<PipelineStep[]>(
    initialData?.steps?.length
      ? initialData.steps
      : [{ id: 'step_1', name: 'Generate Task', agent_name: 'Manager', prompt_template: 'Process and summarize {input}' }]
  );

  const [outputType, setOutputType] = useState(initialData?.output_destination?.type || 'file');
  const [targetPath, setTargetPath] = useState(initialData?.output_destination?.target_path || 'reports/output.md');
  const [saving, setSaving] = useState(false);

  const handleAddStep = () => {
    const nextIdx = steps.length + 1;
    setSteps((prev) => [
      ...prev,
      {
        id: `step_${nextIdx}`,
        name: `Step ${nextIdx}`,
        agent_name: agents[0]?.name || 'Manager',
        prompt_template: `Process input from previous step: {step_${nextIdx - 1}_output}`,
      },
    ]);
  };

  const handleRemoveStep = (idx: number) => {
    setSteps((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleUpdateStep = (idx: number, field: keyof PipelineStep, value: string) => {
    setSteps((prev) =>
      prev.map((s, i) => (i === idx ? { ...s, [field]: value } : s))
    );
  };

  const handleSave = async () => {
    if (!name.trim()) return;
    setSaving(true);

    const triggerData: TriggerConfig = {
      type: triggerType,
      ...(triggerType === 'schedule' ? (cron ? { cron } : { interval_seconds: Number(intervalSec) }) : {}),
      ...(triggerType === 'file_watcher' ? { watch_path: watchPath, watch_pattern: watchPattern, watch_events: ['created', 'modified'] } : {}),
      ...(triggerType === 'webhook' ? { webhook_slug: name.toLowerCase().replace(/\s+/g, '-') } : {}),
    };

    const outputData: OutputDestination = {
      type: outputType,
      ...(outputType === 'file' ? { target_path: targetPath } : {}),
    };

    const payload = {
      name: name.trim(),
      description: description.trim(),
      enabled: true,
      team_name: teamName || undefined,
      trigger: triggerData,
      steps: steps.map((s) => ({ ...s, name: s.name.trim(), prompt_template: s.prompt_template.trim() })),
      output_destination: outputData,
    };

    try {
      const endpoint = initialData
        ? apiUrl(`/api/automations/${initialData.id}`)
        : apiUrl('/api/automations');
      const method = initialData ? 'PUT' : 'POST';

      const res = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw await apiError(res, 'Failed to save automation');
      showToast(initialData ? t('automationUpdatedToast') : t('automationCreatedToast'), 'success');
      onSaved();
    } catch (err: any) {
      showToast(err.message || 'Failed to save automation', 'error');
      setSaving(false);
    }
  };

  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="slide-over slide-over-content" style={{ maxWidth: '720px' }}>
        <div className="slide-over-header" style={{ padding: '20px 24px' }}>
          <div>
            <h2 style={{ fontSize: '17px', fontWeight: 600, margin: 0, color: 'hsl(var(--fg))' }}>
              {initialData ? t('editAutomation') : t('createAutomation')}
            </h2>
            <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
              {t('configureAutomationSubtitle') || 'Configura trigger, passaggi della pipeline e deliverable'}
            </div>
          </div>
          <button className="btn btn-ghost" style={{ padding: '8px' }} onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="slide-over-body" style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* SECTION 1: GENERAL */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <h4 style={{ fontSize: '14px', margin: '0 0 14px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
              Informazioni Flusso
            </h4>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">{t('automationName')}</label>
                <input
                  className="form-input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t('automationNamePlaceholder') || 'e.g. Weekly Market Report'}
                />
              </div>

              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">{t('automationDescription')}</label>
                <input
                  className="form-input"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={t('automationDescPlaceholder') || 'e.g. Ingests competitor prices and produces markdown report'}
                />
              </div>

              {teams.length > 0 && (
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">{t('assignedWorkforceTeam')}</label>
                  <select
                    className="form-select"
                    value={teamName}
                    onChange={(e) => setTeamName(e.target.value)}
                  >
                    {teams.map((tm) => (
                      <option key={tm.name} value={tm.name}>{tm.name}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </div>

          {/* SECTION 2: TRIGGER */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <h4 style={{ fontSize: '14px', margin: '0 0 14px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
              {t('triggerSection')}
            </h4>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px', marginBottom: '16px' }}>
              {[
                { id: 'schedule', label: 'Schedule', icon: Clock },
                { id: 'file_watcher', label: 'File Watch', icon: Folder },
                { id: 'webhook', label: 'Webhook', icon: Globe },
                { id: 'manual', label: 'Manual', icon: Play },
              ].map((item) => {
                const IconComponent = item.icon;
                const isSel = triggerType === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`btn ${isSel ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ flexDirection: 'column', gap: '6px', padding: '10px 4px', fontSize: '12px', borderRadius: '8px' }}
                    onClick={() => setTriggerType(item.id)}
                  >
                    <IconComponent size={16} />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>

            {triggerType === 'schedule' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {[
                    { label: 'Every 15 mins', val: '*/15 * * * *' },
                    { label: 'Every Hour', val: '0 * * * *' },
                    { label: 'Daily at 9 AM', val: '0 9 * * *' },
                    { label: 'Weekly Mon at 9 AM', val: '0 9 * * 1' },
                  ].map((p) => (
                    <button
                      key={p.val}
                      type="button"
                      className="badge"
                      style={{ cursor: 'pointer', border: '1px solid hsl(var(--border))', background: cron === p.val ? 'hsl(var(--primary)/0.15)' : 'hsl(var(--card))', padding: '4px 8px' }}
                      onClick={() => setCron(p.val)}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">{t('cronExpression')}</label>
                    <input
                      className="form-input"
                      value={cron}
                      onChange={(e) => setCron(e.target.value)}
                      placeholder="e.g. 0 9 * * 1"
                      style={{ fontFamily: 'monospace' }}
                    />
                  </div>
                  <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">{t('intervalSeconds')}</label>
                    <input
                      type="number"
                      className="form-input"
                      value={intervalSec}
                      onChange={(e) => setIntervalSec(Number(e.target.value) || 3600)}
                      placeholder="3600"
                    />
                  </div>
                </div>
              </div>
            )}

            {triggerType === 'file_watcher' && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">{t('watchPath')}</label>
                  <input
                    className="form-input"
                    value={watchPath}
                    onChange={(e) => setWatchPath(e.target.value)}
                    placeholder="input_files"
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">{t('watchPattern')}</label>
                  <input
                    className="form-input"
                    value={watchPattern}
                    onChange={(e) => setWatchPattern(e.target.value)}
                    placeholder="*.pdf or *.md"
                  />
                </div>
              </div>
            )}
          </div>

          {/* SECTION 3: WORKFLOW PIPELINE */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
              <h4 style={{ fontSize: '14px', margin: 0, fontWeight: 600, color: 'hsl(var(--fg))' }}>
                {t('pipelineSection')} ({steps.length})
              </h4>
              <button className="btn btn-secondary" style={{ fontSize: '12px', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: '4px' }} onClick={handleAddStep}>
                <Plus size={14} /> {t('addStep')}
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {steps.map((step, idx) => (
                <div key={step.id || idx} className="card" style={{ padding: '14px', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                    <span className="badge badge-primary" style={{ fontSize: '11px' }}>
                      Step {idx + 1}
                    </span>
                    {steps.length > 1 && (
                      <button
                        className="btn btn-ghost"
                        style={{ padding: '2px 6px', color: 'hsl(var(--destructive))' }}
                        onClick={() => handleRemoveStep(idx)}
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '10px' }}>
                    <div>
                      <label className="form-label" style={{ fontSize: '11.5px' }}>{t('stepLabel')} {t('name')}</label>
                      <input
                        className="form-input"
                        value={step.name}
                        onChange={(e) => handleUpdateStep(idx, 'name', e.target.value)}
                        placeholder="e.g. Research data"
                      />
                    </div>
                    <div>
                      <label className="form-label" style={{ fontSize: '11.5px' }}>{t('assignedAgent')}</label>
                      <select
                        className="form-select"
                        value={step.agent_name}
                        onChange={(e) => handleUpdateStep(idx, 'agent_name', e.target.value)}
                      >
                        <option value="Manager">Manager</option>
                        {agents.map((ag) => (
                          <option key={ag.name} value={ag.name}>{ag.name} ({ag.role})</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <label className="form-label" style={{ fontSize: '11.5px', marginBottom: 0 }}>{t('promptTemplate')}</label>
                      <MagicEnhancePromptButton
                        prompt={step.prompt_template}
                        role={step.name}
                        agentName={step.agent_name}
                        teamName={teamName}
                        onEnhanced={(enhanced) => handleUpdateStep(idx, 'prompt_template', enhanced)}
                      />
                    </div>
                    <textarea
                      className="form-textarea"
                      rows={2}
                      value={step.prompt_template}
                      onChange={(e) => handleUpdateStep(idx, 'prompt_template', e.target.value)}
                      placeholder="Prompt instructions for this step..."
                    />
                    <div style={{ display: 'flex', gap: '4px', marginTop: '6px' }}>
                      <span className="text-muted" style={{ fontSize: '11px' }}>{t('insertVariables')}</span>
                      <code
                        style={{ fontSize: '11px', cursor: 'pointer', padding: '1px 5px', background: 'hsl(var(--muted))', borderRadius: '3px' }}
                        onClick={() => handleUpdateStep(idx, 'prompt_template', `${step.prompt_template} {input}`)}
                      >
                        +&#123;input&#125;
                      </code>
                      {idx > 0 && (
                        <code
                          style={{ fontSize: '11px', cursor: 'pointer', padding: '1px 5px', background: 'hsl(var(--muted))', borderRadius: '3px' }}
                          onClick={() => handleUpdateStep(idx, 'prompt_template', `${step.prompt_template} {step_${idx}_output}`)}
                        >
                          +&#123;step_{idx}_output&#125;
                        </code>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 4: DELIVERABLE & OUTPUT */}
          <div className="card" style={{ padding: '20px', borderRadius: '12px', border: '1px solid hsl(var(--border))' }}>
            <h4 style={{ fontSize: '14px', margin: '0 0 14px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
              {t('outputSection')}
            </h4>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginBottom: '14px' }}>
              {[
                { id: 'file', label: t('outputFile'), icon: FileText },
                { id: 'knowledge', label: t('outputKnowledge'), icon: Database },
                { id: 'notification', label: t('outputNotification'), icon: Bell },
              ].map((item) => {
                const IconComponent = item.icon;
                const isSel = outputType === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`btn ${isSel ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ flexDirection: 'column', gap: '6px', padding: '10px 4px', fontSize: '12px', borderRadius: '8px' }}
                    onClick={() => setOutputType(item.id)}
                  >
                    <IconComponent size={16} />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>

            {outputType === 'file' && (
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">{t('targetFilePath')}</label>
                <input
                  className="form-input"
                  value={targetPath}
                  onChange={(e) => setTargetPath(e.target.value)}
                  placeholder="reports/summary.md"
                  style={{ fontFamily: 'monospace' }}
                />
              </div>
            )}
          </div>
        </div>

        <div className="slide-over-footer" style={{ padding: '16px 24px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button className="btn btn-secondary" onClick={onClose} disabled={saving}>
            {t('cancel')}
          </button>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving || !name.trim()} style={{ padding: '8px 20px' }}>
            {saving ? t('saving') : initialData ? t('save') : t('createAutomation')}
          </button>
        </div>
      </div>
    </>
  );
}
