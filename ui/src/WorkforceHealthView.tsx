import React, { useState, useEffect, useCallback } from 'react';
import {
  HeartPulse, AlertTriangle, CheckCircle2,
  RefreshCw, Sparkles
} from 'lucide-react';
import { useTranslation } from './i18n';
import { apiUrl } from './api';

export interface AgentHealthMetric {
  agent_id: string;
  name: string;
  role: string;
  provider?: string | null;
  model?: string | null;
  status: 'healthy' | 'active' | 'degraded' | 'idle';
  tasks_assigned: number;
  tasks_completed: number;
  tasks_failed: number;
  tools_executed: number;
  tool_failures: number;
  reworks_count: number;
  success_rate: number;
  average_latency_ms?: number | null;
  last_active?: string | null;
}

export interface HealthInsight {
  id: string;
  category: 'reliability' | 'performance' | 'quality' | 'governance';
  level: 'success' | 'info' | 'warning' | 'error';
  title: string;
  detail: string;
  data_points?: Record<string, any>;
}

export interface WorkforceHealthSummary {
  team_name: string;
  scope: string;
  mission_id?: string | null;
  execution_id?: string | null;
  overall_status: 'healthy' | 'active' | 'degraded';
  total_executions: number;
  completed_executions: number;
  failed_executions: number;
  execution_success_rate: number;
  total_milestones: number;
  completed_milestones: number;
  milestone_success_rate: number;
  total_tools_executed: number;
  tool_failures: number;
  tool_error_rate: number;
  rework_count: number;
  rework_rate: number;
  approvals_count: number;
  average_execution_duration_sec: number;
  average_milestone_duration_sec: number;
  agents: AgentHealthMetric[];
  insights: HealthInsight[];
}

interface WorkforceHealthViewProps {
  missionId?: string | null;
  executionId?: string | null;
  teamName?: string | null;
  runNumber?: number | null;
}

export const WorkforceHealthView: React.FC<WorkforceHealthViewProps> = ({
  missionId,
  executionId,
  teamName,
  runNumber,
}) => {
  const { t } = useTranslation();
  const [health, setHealth] = useState<WorkforceHealthSummary | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchHealth = useCallback(async () => {
    try {
      setLoading(true);
      let url = '';
      if (missionId) {
        const q = executionId ? `?execution_id=${encodeURIComponent(executionId)}` : '';
        url = apiUrl(`/api/missions/${missionId}/health${q}`);
      } else {
        const q = teamName ? `?team_name=${encodeURIComponent(teamName)}` : '';
        url = apiUrl(`/api/workforce/health${q}`);
      }

      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to load workforce health');
      const data: WorkforceHealthSummary = await res.json();
      setHealth(data);
    } catch (err) {
      console.error(err);
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }, [missionId, executionId, teamName]);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  if (loading) {
    return (
      <div style={{ padding: '48px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
        <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 12px' }} />
        <div style={{ fontSize: '13px' }}>Computing workforce health metrics...</div>
      </div>
    );
  }

  if (!health) {
    return (
      <div
        data-testid="workforce-health-empty"
        style={{
          padding: '48px 24px',
          borderRadius: '12px',
          border: '1px dashed hsl(var(--border))',
          textAlign: 'center',
          color: 'hsl(var(--muted-fg))',
          maxWidth: '480px',
          margin: '32px auto',
        }}
      >
        <HeartPulse size={32} style={{ margin: '0 auto 12px', opacity: 0.35 }} />
        <div style={{ fontSize: '14px', fontWeight: 600, color: 'hsl(var(--foreground))' }}>
          No health telemetry available
        </div>
      </div>
    );
  }

  const isHealthy = health.overall_status === 'healthy';
  const isDegraded = health.overall_status === 'degraded';

  return (
    <div
      className="workforce-health-view-container workforce-health-view"
      data-testid="workforce-health-view"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '24px',
        padding: '24px 32px',
        maxWidth: '1200px',
        margin: '0 auto',
        width: '100%',
        boxSizing: 'border-box',
      }}
    >
      {/* 1. Overall Status Header Card */}
      <div
        style={{
          padding: '16px 20px',
          borderRadius: '12px',
          backgroundColor: 'hsl(var(--card))',
          border: '1px solid hsl(var(--border))',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              padding: '10px',
              borderRadius: '10px',
              backgroundColor: isHealthy ? '#10b98118' : isDegraded ? '#ef444418' : '#3b82f618',
              color: isHealthy ? '#10b981' : isDegraded ? '#ef4444' : '#3b82f6',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <HeartPulse size={22} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '15px', fontWeight: 700, color: 'hsl(var(--foreground))' }}>
                {health.team_name}
              </span>
              <span
                data-testid="workforce-status-pill"
                style={{
                  fontSize: '11px',
                  fontWeight: 600,
                  padding: '2px 8px',
                  borderRadius: '12px',
                  backgroundColor: isHealthy ? '#10b98120' : isDegraded ? '#ef444420' : '#3b82f620',
                  color: isHealthy ? '#10b981' : isDegraded ? '#ef4444' : '#3b82f6',
                  textTransform: 'uppercase',
                }}
              >
                ● {health.overall_status}
              </span>
              {runNumber && (
                <span
                  style={{
                    fontSize: '11px',
                    fontWeight: 600,
                    padding: '2px 8px',
                    borderRadius: '12px',
                    backgroundColor: 'hsl(var(--primary) / 0.1)',
                    color: 'hsl(var(--primary))',
                  }}
                >
                  Run #{runNumber}
                </span>
              )}
            </div>
            <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '3px' }}>
              {t('healthSubtitle')}
            </div>
          </div>
        </div>

        <button
          className="btn btn-ghost"
          onClick={fetchHealth}
          style={{ padding: '6px 12px', fontSize: '12px', gap: '6px' }}
        >
          <RefreshCw size={13} />
          <span>Refresh</span>
        </button>
      </div>

      {/* 2. Primary KPI Metrics Grid */}
      <div
        data-testid="workforce-metrics-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
          gap: '12px',
        }}
      >
        {/* Metric 1: Mission Success Rate */}
        <div
          style={{
            padding: '14px 16px',
            borderRadius: '10px',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
          }}
        >
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase' }}>
            {t('missionSuccessRate')}
          </div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: 'hsl(var(--foreground))', marginTop: '6px' }}>
            {health.execution_success_rate}%
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
            {health.completed_executions} of {health.total_executions} runs passed
          </div>
        </div>

        {/* Metric 2: Milestone Success Rate */}
        <div
          style={{
            padding: '14px 16px',
            borderRadius: '10px',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
          }}
        >
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase' }}>
            {t('milestoneSuccessRate')}
          </div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: 'hsl(var(--foreground))', marginTop: '6px' }}>
            {health.milestone_success_rate}%
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
            {health.completed_milestones} of {health.total_milestones} stages
          </div>
        </div>

        {/* Metric 3: Tool Error Rate */}
        <div
          style={{
            padding: '14px 16px',
            borderRadius: '10px',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
          }}
        >
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase' }}>
            {t('toolErrorRate')}
          </div>
          <div
            style={{
              fontSize: '22px',
              fontWeight: 700,
              color: health.tool_error_rate > 0 ? '#ef4444' : 'hsl(var(--foreground))',
              marginTop: '6px',
            }}
          >
            {health.tool_error_rate}%
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
            {health.tool_failures} failed / {health.total_tools_executed} calls
          </div>
        </div>

        {/* Metric 4: Average Duration */}
        <div
          style={{
            padding: '14px 16px',
            borderRadius: '10px',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
          }}
        >
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase' }}>
            {t('avgExecutionDuration')}
          </div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: 'hsl(var(--foreground))', marginTop: '6px' }}>
            {health.average_execution_duration_sec > 0 ? `${health.average_execution_duration_sec}s` : '--'}
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
            Per-execution runtime
          </div>
        </div>

        {/* Metric 5: Rework Cycles */}
        <div
          style={{
            padding: '14px 16px',
            borderRadius: '10px',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
          }}
        >
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase' }}>
            {t('reworkCycles')}
          </div>
          <div
            style={{
              fontSize: '22px',
              fontWeight: 700,
              color: health.rework_count > 0 ? '#f59e0b' : 'hsl(var(--foreground))',
              marginTop: '6px',
            }}
          >
            {health.rework_count}
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
            Quality gate corrections
          </div>
        </div>

        {/* Metric 6: Approvals */}
        <div
          style={{
            padding: '14px 16px',
            borderRadius: '10px',
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
          }}
        >
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', textTransform: 'uppercase' }}>
            {t('approvalsCount')}
          </div>
          <div style={{ fontSize: '22px', fontWeight: 700, color: 'hsl(var(--foreground))', marginTop: '6px' }}>
            {health.approvals_count}
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
            Human oversight checkpoints
          </div>
        </div>
      </div>

      {/* 3. Per-Agent Health & Telemetry Table */}
      <div
        data-testid="per-agent-health-section"
        style={{
          padding: '16px 20px',
          borderRadius: '12px',
          backgroundColor: 'hsl(var(--card))',
          border: '1px solid hsl(var(--border))',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: '14px', fontWeight: 700, color: 'hsl(var(--foreground))' }}>
            {t('agentHealth')}
          </div>
          <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
            {health.agents.length} active specialists
          </span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table
            data-testid="per-agent-health-table"
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '12.5px',
              textAlign: 'left',
            }}
          >
            <thead>
              <tr style={{ borderBottom: '1.5px solid hsl(var(--border))', color: 'hsl(var(--muted-fg))' }}>
                <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('agentColName')}</th>
                <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('agentColStatus')}</th>
                <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('agentColTasks')}</th>
                <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('agentColTools')}</th>
                <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('agentColSuccess')}</th>
                <th style={{ padding: '8px 12px', fontWeight: 600 }}>Avg Latency</th>
                <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('agentColLastActive')}</th>
              </tr>
            </thead>
            <tbody>
              {health.agents.map((ag) => (
                <tr
                  key={ag.agent_id}
                  data-testid={`agent-row-${ag.name.toLowerCase().replace(/\s+/g, '-')}`}
                  style={{ borderBottom: '1px solid hsl(var(--border) / 0.6)' }}
                >
                  {/* Name & Role */}
                  <td style={{ padding: '10px 12px' }}>
                    <div style={{ fontWeight: 600, color: 'hsl(var(--foreground))' }}>{ag.name}</div>
                    <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                      {ag.role}
                      {ag.model && ` • ${ag.model}`}
                    </div>
                  </td>

                  {/* Status Pill */}
                  <td style={{ padding: '10px 12px' }}>
                    <span
                      style={{
                        fontSize: '10.5px',
                        fontWeight: 600,
                        padding: '2px 7px',
                        borderRadius: '10px',
                        backgroundColor:
                          ag.status === 'healthy'
                            ? '#10b98118'
                            : ag.status === 'degraded'
                            ? '#ef444418'
                            : 'hsl(var(--muted))',
                        color:
                          ag.status === 'healthy'
                            ? '#10b981'
                            : ag.status === 'degraded'
                            ? '#ef4444'
                            : 'hsl(var(--muted-fg))',
                        textTransform: 'capitalize',
                      }}
                    >
                      {ag.status}
                    </span>
                  </td>

                  {/* Tasks Assigned / Completed */}
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{ fontWeight: 600 }}>{ag.tasks_completed}</span>
                    <span style={{ color: 'hsl(var(--muted-fg))' }}> / {ag.tasks_assigned}</span>
                  </td>

                  {/* Tools Invocations */}
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{ fontFamily: 'monospace' }}>{ag.tools_executed}</span>
                    {ag.tool_failures > 0 && (
                      <span style={{ color: '#ef4444', fontSize: '11px', marginLeft: '4px' }}>
                        ({ag.tool_failures} err)
                      </span>
                    )}
                  </td>

                  {/* Success Rate */}
                  <td style={{ padding: '10px 12px' }}>
                    <span
                      style={{
                        fontWeight: 600,
                        color: ag.success_rate >= 90 ? '#10b981' : ag.success_rate < 70 ? '#ef4444' : '#f59e0b',
                      }}
                    >
                      {ag.success_rate}%
                    </span>
                  </td>

                  {/* Latency */}
                  <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: 'hsl(var(--muted-fg))' }}>
                    {ag.average_latency_ms != null ? `${ag.average_latency_ms}ms` : '--'}
                  </td>

                  {/* Last Active */}
                  <td style={{ padding: '10px 12px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                    {ag.last_active
                      ? new Date(ag.last_active).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                      : 'Idle'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 4. Diagnostic Insights Section */}
      {health.insights && health.insights.length > 0 && (
        <div
          data-testid="diagnostic-insights-section"
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
          }}
        >
          <div style={{ fontSize: '13px', fontWeight: 700, color: 'hsl(var(--foreground))', paddingLeft: '4px' }}>
            {t('diagnosticInsights')}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '10px' }}>
            {health.insights.map((ins) => (
              <div
                key={ins.id}
                style={{
                  padding: '14px 16px',
                  borderRadius: '10px',
                  backgroundColor: 'hsl(var(--card))',
                  border:
                    ins.level === 'warning'
                      ? '1px solid #f59e0b40'
                      : ins.level === 'error'
                      ? '1px solid #ef444440'
                      : '1px solid hsl(var(--border))',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                }}
              >
                <div
                  style={{
                    padding: '6px',
                    borderRadius: '6px',
                    backgroundColor:
                      ins.level === 'success'
                        ? '#10b98118'
                        : ins.level === 'warning'
                        ? '#f59e0b18'
                        : '#3b82f618',
                    color:
                      ins.level === 'success'
                        ? '#10b981'
                        : ins.level === 'warning'
                        ? '#f59e0b'
                        : '#3b82f6',
                    marginTop: '2px',
                  }}
                >
                  {ins.level === 'success' ? (
                    <CheckCircle2 size={16} />
                  ) : ins.level === 'warning' ? (
                    <AlertTriangle size={16} />
                  ) : (
                    <Sparkles size={16} />
                  )}
                </div>
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--foreground))' }}>
                    {ins.title}
                  </div>
                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '3px', lineHeight: 1.4 }}>
                    {ins.detail}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
