import React, { useState, useEffect, useCallback } from 'react';
import {
  TrendingUp, AlertTriangle, CheckCircle2, RefreshCw, Zap,
  Play, Award, ArrowUpRight, ShieldCheck, Cpu
} from 'lucide-react';
import { apiUrl } from './api';

export interface LeaderboardEntry {
  target_id: string;
  target_name: string;
  target_type: string;
  overall_score: number;
  completion_rate: number;
  error_rate: number;
  latency_ms: number;
  tokens_used: number;
  safety_compliance: number;
  total_evaluations: number;
  last_evaluated_at: string;
}

export interface RegressionAlertItem {
  id: string;
  benchmark_run_id: string;
  target_id: string;
  metric_name: string;
  baseline_value: number;
  current_value: number;
  delta_percentage: number;
  severity: 'low' | 'medium' | 'high' | 'critical';
  message: string;
  resolved: boolean;
  created_at: string;
}

export interface EvolutionProposalItem {
  id: string;
  target_agent: string;
  benchmark_run_id: string;
  title: string;
  rationale: string;
  suggested_prompt_addition: string;
  suggested_preferred_model: string | null;
  expected_quality_delta: number;
  status: 'pending' | 'applied' | 'rejected';
  applied_at: string | null;
  created_at: string;
}

export const BenchmarkingView: React.FC = () => {
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [alerts, setAlerts] = useState<RegressionAlertItem[]>([]);
  const [proposals, setProposals] = useState<EvolutionProposalItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [selectedType, setSelectedType] = useState<string>('all');
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const q = selectedType !== 'all' ? `?target_type=${encodeURIComponent(selectedType)}` : '';
      const [lbRes, alertsRes, propsRes] = await Promise.all([
        fetch(apiUrl(`/benchmarking/leaderboard${q}`)),
        fetch(apiUrl(`/benchmarking/alerts?unresolved_only=false`)),
        fetch(apiUrl(`/benchmarking/proposals`)),
      ]);

      if (lbRes.ok) setLeaderboard(await lbRes.json());
      if (alertsRes.ok) setAlerts(await alertsRes.json());
      if (propsRes.ok) setProposals(await propsRes.json());
    } catch (err) {
      console.error('Failed to load benchmarking data:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedType]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRunBenchmark = async (targetId: string = 'researcher', targetType: string = 'agent') => {
    try {
      setEvaluating(true);
      setNotification(null);
      const res = await fetch(apiUrl('/benchmarking/run'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_type: targetType,
          target_id: targetId,
          suite_name: 'automated_workforce_eval',
        }),
      });
      if (!res.ok) throw new Error('Benchmark run failed');
      const data = await res.json();
      setNotification({
        type: 'success',
        message: `Evaluation completed for ${targetId}! Score: ${(data.benchmark_run.overall_score * 100).toFixed(1)}%`,
      });
      await fetchData();
    } catch (err: any) {
      setNotification({ type: 'error', message: err.message || 'Evaluation error' });
    } finally {
      setEvaluating(false);
    }
  };

  const handleApplyProposal = async (proposalId: string) => {
    try {
      const res = await fetch(apiUrl(`/benchmarking/proposals/${proposalId}/apply`), {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed to apply evolution proposal');
      setNotification({ type: 'success', message: 'Evolution proposal applied to agent configuration!' });
      await fetchData();
    } catch (err: any) {
      setNotification({ type: 'error', message: err.message || 'Apply error' });
    }
  };

  const handleResolveAlert = async (alertId: string) => {
    try {
      const res = await fetch(apiUrl(`/benchmarking/alerts/${alertId}/resolve`), {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Failed to resolve alert');
      setNotification({ type: 'success', message: 'Regression alert resolved.' });
      await fetchData();
    } catch (err: any) {
      setNotification({ type: 'error', message: err.message || 'Resolve error' });
    }
  };

  const unresolvedAlertsCount = alerts.filter(a => !a.resolved).length;
  const pendingProposalsCount = proposals.filter(p => p.status === 'pending').length;

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* Top Header & Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Award className="text-primary" size={24} />
            Workforce Benchmarking & Evolution
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
            Continuous regression tracking, multi-dimensional scoring, and autonomous prompt & routing optimization.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <select
            className="input"
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            style={{ fontSize: '12px', padding: '6px 12px', height: '36px' }}
          >
            <option value="all">All Targets</option>
            <option value="agent">Agents Only</option>
            <option value="workforce">Workforces Only</option>
          </select>

          <button
            className="btn btn-secondary"
            onClick={fetchData}
            disabled={loading}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '36px', fontSize: '13px' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>

          <button
            className="btn btn-primary"
            onClick={() => handleRunBenchmark('researcher', 'agent')}
            disabled={evaluating}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '36px', fontSize: '13px' }}
          >
            <Play size={14} className={evaluating ? 'animate-pulse' : ''} />
            {evaluating ? 'Evaluating...' : 'Run Benchmark'}
          </button>
        </div>
      </div>

      {notification && (
        <div style={{
          padding: '12px 16px',
          borderRadius: '8px',
          fontSize: '13px',
          backgroundColor: notification.type === 'success' ? 'hsl(var(--success)/0.15)' : 'hsl(var(--destructive)/0.15)',
          color: notification.type === 'success' ? 'hsl(var(--success))' : 'hsl(var(--destructive))',
          border: `1px solid ${notification.type === 'success' ? 'hsl(var(--success)/0.3)' : 'hsl(var(--destructive)/0.3)'}`,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span>{notification.message}</span>
          <button
            onClick={() => setNotification(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', fontWeight: 'bold' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
        <div className="card" style={{ padding: '16px', backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>EVALUATED TARGETS</span>
            <Cpu size={16} className="text-primary" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700 }}>{leaderboard.length}</div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>Active in performance tracker</div>
        </div>

        <div className="card" style={{ padding: '16px', backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>TOP SCORE</span>
            <TrendingUp size={16} style={{ color: 'hsl(var(--success))' }} />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: 'hsl(var(--success))' }}>
            {leaderboard.length > 0 ? `${(Math.max(...leaderboard.map(e => e.overall_score)) * 100).toFixed(1)}%` : 'N/A'}
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>Benchmark composite index</div>
        </div>

        <div className="card" style={{ padding: '16px', backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>REGRESSION ALERTS</span>
            <AlertTriangle size={16} style={{ color: unresolvedAlertsCount > 0 ? 'hsl(var(--warning))' : 'hsl(var(--muted-fg))' }} />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: unresolvedAlertsCount > 0 ? 'hsl(var(--warning))' : 'inherit' }}>
            {unresolvedAlertsCount}
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>
            {unresolvedAlertsCount > 0 ? 'Performance regressions detected' : 'Zero performance degradations'}
          </div>
        </div>

        <div className="card" style={{ padding: '16px', backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>EVOLUTION PROPOSALS</span>
            <Zap size={16} className="text-primary" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: pendingProposalsCount > 0 ? 'hsl(var(--primary))' : 'inherit' }}>
            {pendingProposalsCount}
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>Ready for autonomous apply</div>
        </div>
      </div>

      {/* Main Leaderboard Table */}
      <div className="card" style={{ backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid hsl(var(--border))', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Award size={18} className="text-primary" />
            Performance Leaderboard
          </h3>
          <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>Weighted Composite Score</span>
        </div>

        {leaderboard.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
            No evaluations recorded yet. Click "Run Benchmark" above to test workforce performance.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: 'hsl(var(--muted)/0.3)', borderBottom: '1px solid hsl(var(--border))' }}>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Target</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Type</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Overall Score</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Completion</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Error Rate</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Latency</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Safety</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((item, index) => (
                  <tr key={item.target_id} style={{ borderBottom: '1px solid hsl(var(--border))' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: '20px',
                        height: '20px',
                        borderRadius: '50%',
                        fontSize: '11px',
                        backgroundColor: index === 0 ? 'hsl(var(--warning)/0.2)' : 'hsl(var(--muted))',
                        color: index === 0 ? 'hsl(var(--warning))' : 'inherit',
                      }}>
                        {index + 1}
                      </span>
                      {item.target_name || item.target_id}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        textTransform: 'uppercase',
                        fontSize: '10px',
                        fontWeight: 700,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        backgroundColor: item.target_type === 'workforce' ? 'hsl(var(--primary)/0.15)' : 'hsl(var(--secondary))',
                        color: item.target_type === 'workforce' ? 'hsl(var(--primary))' : 'inherit',
                      }}>
                        {item.target_type}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 700, color: item.overall_score >= 0.8 ? 'hsl(var(--success))' : 'hsl(var(--warning))' }}>
                      {(item.overall_score * 100).toFixed(1)}%
                    </td>
                    <td style={{ padding: '12px 16px' }}>{(item.completion_rate * 100).toFixed(1)}%</td>
                    <td style={{ padding: '12px 16px', color: item.error_rate > 0.05 ? 'hsl(var(--destructive))' : 'inherit' }}>
                      {(item.error_rate * 100).toFixed(1)}%
                    </td>
                    <td style={{ padding: '12px 16px' }}>{item.latency_ms.toFixed(0)} ms</td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'hsl(var(--success))' }}>
                        <ShieldCheck size={14} />
                        {(item.safety_compliance * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <button
                        className="btn btn-ghost"
                        onClick={() => handleRunBenchmark(item.target_id, item.target_type)}
                        style={{ padding: '4px 8px', fontSize: '12px' }}
                      >
                        Re-evaluate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Grid: Regression Alerts & Evolution Proposals */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '20px' }}>
        {/* Regression Alerts Guardrail */}
        <div className="card" style={{ backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))', padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertTriangle size={18} style={{ color: 'hsl(var(--warning))' }} />
              Regression Guardrail Alerts
            </h3>
            <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
              {unresolvedAlertsCount} active
            </span>
          </div>

          {alerts.length === 0 ? (
            <div style={{ padding: '32px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
              No regression alerts detected. Performance is strictly within baseline limits.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '420px', overflowY: 'auto' }}>
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  style={{
                    padding: '12px',
                    borderRadius: '6px',
                    border: '1px solid hsl(var(--border))',
                    backgroundColor: alert.resolved ? 'hsl(var(--muted)/0.1)' : 'hsl(var(--card))',
                    opacity: alert.resolved ? 0.7 : 1,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{
                        fontSize: '10px',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        backgroundColor: alert.severity === 'critical' ? 'hsl(var(--destructive)/0.2)' : 'hsl(var(--warning)/0.2)',
                        color: alert.severity === 'critical' ? 'hsl(var(--destructive))' : 'hsl(var(--warning))',
                      }}>
                        {alert.severity}
                      </span>
                      <strong style={{ fontSize: '13px' }}>{alert.target_id}</strong>
                      <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>({alert.metric_name})</span>
                    </div>

                    {!alert.resolved ? (
                      <button
                        className="btn btn-ghost"
                        onClick={() => handleResolveAlert(alert.id)}
                        style={{ fontSize: '11px', padding: '2px 8px', height: '24px' }}
                      >
                        Resolve
                      </button>
                    ) : (
                      <span style={{ fontSize: '11px', color: 'hsl(var(--success))', display: 'flex', alignItems: 'center', gap: '3px' }}>
                        <CheckCircle2 size={12} /> Resolved
                      </span>
                    )}
                  </div>

                  <p style={{ margin: '4px 0 6px', fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                    {alert.message}
                  </p>

                  <div style={{ display: 'flex', gap: '12px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                    <span>Baseline: {alert.baseline_value.toFixed(2)}</span>
                    <span>Current: {alert.current_value.toFixed(2)}</span>
                    <span style={{ color: alert.delta_percentage > 0 ? 'hsl(var(--destructive))' : 'hsl(var(--success))' }}>
                      Delta: {alert.delta_percentage > 0 ? '+' : ''}{alert.delta_percentage.toFixed(1)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Autonomous Evolution Proposals */}
        <div className="card" style={{ backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))', padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={18} className="text-primary" />
              Autonomous Evolution Proposals
            </h3>
            <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
              {pendingProposalsCount} pending
            </span>
          </div>

          {proposals.length === 0 ? (
            <div style={{ padding: '32px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
              No evolution proposals generated yet. Benchmarking engine suggests enhancements automatically when errors or degradations are detected.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '420px', overflowY: 'auto' }}>
              {proposals.map((prop) => (
                <div
                  key={prop.id}
                  style={{
                    padding: '12px',
                    borderRadius: '6px',
                    border: '1px solid hsl(var(--border))',
                    backgroundColor: prop.status === 'applied' ? 'hsl(var(--muted)/0.1)' : 'hsl(var(--card))',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '6px' }}>
                    <div>
                      <strong style={{ fontSize: '13px', display: 'block' }}>{prop.title}</strong>
                      <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                        Target: {prop.target_agent} {prop.suggested_preferred_model ? `• Model: ${prop.suggested_preferred_model}` : ''}
                      </span>
                    </div>

                    {prop.status === 'pending' ? (
                      <button
                        className="btn btn-primary"
                        onClick={() => handleApplyProposal(prop.id)}
                        style={{ fontSize: '11px', padding: '4px 10px', height: '26px', display: 'flex', alignItems: 'center', gap: '4px' }}
                      >
                        <ArrowUpRight size={12} /> Apply
                      </button>
                    ) : (
                      <span style={{
                        fontSize: '11px',
                        color: prop.status === 'applied' ? 'hsl(var(--success))' : 'hsl(var(--muted-fg))',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '3px',
                      }}>
                        <CheckCircle2 size={12} /> {prop.status}
                      </span>
                    )}
                  </div>

                  <p style={{ margin: '4px 0 8px', fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                    {prop.rationale}
                  </p>

                  {prop.suggested_prompt_addition && (
                    <div style={{
                      padding: '8px',
                      borderRadius: '4px',
                      backgroundColor: 'hsl(var(--muted)/0.2)',
                      fontSize: '11px',
                      fontFamily: 'monospace',
                      marginBottom: '6px',
                      whiteSpace: 'pre-wrap',
                    }}>
                      {prop.suggested_prompt_addition}
                    </div>
                  )}

                  <div style={{ fontSize: '11px', color: 'hsl(var(--success))', fontWeight: 600 }}>
                    Expected Quality Delta: +{(prop.expected_quality_delta * 100).toFixed(1)}%
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
