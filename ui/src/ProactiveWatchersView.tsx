import React, { useState, useEffect, useCallback } from 'react';
import {
  Sparkles, Eye, CheckCircle2, Plus, RefreshCw,
  ArrowUpRight, Zap, Trash2
} from 'lucide-react';

import { apiUrl } from './api';

export interface ProactiveSuggestionItem {
  id: string;
  category: string;
  title: string;
  description: string;
  proposed_action_id: string;
  proposed_action_args: Record<string, any>;
  evidence: Record<string, any>;
  priority: 'low' | 'medium' | 'high' | 'critical';
  status: 'pending' | 'accepted' | 'dismissed' | 'applied';
  created_at: string;
}

export interface AmbientWatcherItem {
  id: string;
  name: string;
  description: string;
  watcher_type: string;
  target: string;
  condition_expression: string;
  action_id: string;
  action_args: Record<string, any>;
  auto_trigger: boolean;
  interval_seconds: number;
  status: 'active' | 'paused' | 'triggered' | 'disabled';
  last_checked_at: string;
  last_triggered_at: string | null;
  created_at: string;
}

export const ProactiveWatchersView: React.FC = () => {
  const [suggestions, setSuggestions] = useState<ProactiveSuggestionItem[]>([]);
  const [watchers, setWatchers] = useState<AmbientWatcherItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [checkingWatchers, setCheckingWatchers] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  // New Watcher Form State
  const [newWatcherName, setNewWatcherName] = useState('');
  const [newWatcherType, setNewWatcherType] = useState('file_change');
  const [newWatcherTarget, setNewWatcherTarget] = useState('docs/architecture.md');
  const [newWatcherAction, setNewWatcherAction] = useState('knowledge.search');
  const [newWatcherAutoTrigger, setNewWatcherAutoTrigger] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [sugRes, watRes] = await Promise.all([
        fetch(apiUrl('/proactive/suggestions?status=pending')),
        fetch(apiUrl('/proactive/watchers')),
      ]);

      if (sugRes.ok) setSuggestions(await sugRes.json());
      if (watRes.ok) setWatchers(await watRes.json());
    } catch (err) {
      console.error('Failed to load proactive data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleScanOpportunities = async () => {
    try {
      setScanning(true);
      setNotification(null);
      const res = await fetch(apiUrl('/proactive/suggestions/generate'), { method: 'POST' });
      if (!res.ok) throw new Error('Scan failed');
      const data = await res.json();
      setNotification({
        type: 'success',
        message: `Workspace analysis complete! Discovered ${data.suggestions.length} proactive opportunities.`,
      });
      await fetchData();
    } catch (err: any) {
      setNotification({ type: 'error', message: err.message || 'Error scanning opportunities' });
    } finally {
      setScanning(false);
    }
  };

  const handleAcceptSuggestion = async (id: string) => {
    try {
      const res = await fetch(apiUrl(`/proactive/suggestions/${id}/accept`), { method: 'POST' });
      if (!res.ok) throw new Error('Failed to accept suggestion');
      setNotification({ type: 'success', message: 'Suggestion accepted and action executed!' });
      await fetchData();
    } catch (err: any) {
      setNotification({ type: 'error', message: err.message || 'Accept failed' });
    }
  };

  const handleDismissSuggestion = async (id: string) => {
    try {
      const res = await fetch(apiUrl(`/proactive/suggestions/${id}/dismiss`), { method: 'POST' });
      if (!res.ok) throw new Error('Failed to dismiss suggestion');
      setNotification({ type: 'success', message: 'Suggestion dismissed.' });
      await fetchData();
    } catch (err: any) {
      setNotification({ type: 'error', message: err.message || 'Dismiss failed' });
    }
  };

  const handleCheckAllWatchers = async () => {
    try {
      setCheckingWatchers(true);
      const res = await fetch(apiUrl('/proactive/watchers/check-all'), { method: 'POST' });
      if (!res.ok) throw new Error('Failed checking watchers');
      const data = await res.json();
      const triggered = data.results.filter((r: any) => r.triggered).length;
      setNotification({
        type: 'success',
        message: `Evaluated ${data.results.length} ambient watchers. (${triggered} conditions triggered)`,
      });
      await fetchData();
    } catch (err: any) {
      setNotification({ type: 'error', message: err.message || 'Error checking watchers' });
    } finally {
      setCheckingWatchers(false);
    }
  };

  const handleCheckSingleWatcher = async (id: string) => {
    try {
      const res = await fetch(apiUrl(`/proactive/watchers/${id}/check`), { method: 'POST' });
      if (!res.ok) throw new Error('Watcher check failed');
      const data = await res.json();
      setNotification({
        type: 'success',
        message: data.triggered ? 'Watcher condition triggered! Event recorded.' : 'Target verified. No state change detected.',
      });
      await fetchData();
    } catch (err: any) {
      setNotification({ type: 'error', message: err.message || 'Watcher check error' });
    }
  };

  const handleDeleteWatcher = async (id: string) => {
    try {
      const res = await fetch(apiUrl(`/proactive/watchers/${id}`), { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed deleting watcher');
      setNotification({ type: 'success', message: 'Watcher deleted.' });
      await fetchData();
    } catch (err: any) {
      setNotification({ type: 'error', message: err.message || 'Delete error' });
    }
  };

  const handleCreateWatcher = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWatcherName || !newWatcherTarget) return;

    try {
      const res = await fetch(apiUrl('/proactive/watchers'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newWatcherName,
          watcher_type: newWatcherType,
          target: newWatcherTarget,
          action_id: newWatcherAction,
          auto_trigger: newWatcherAutoTrigger,
        }),
      });
      if (!res.ok) throw new Error('Failed to create watcher');
      setShowCreateModal(false);
      setNewWatcherName('');
      setNotification({ type: 'success', message: 'Ambient watcher active and registered!' });
      await fetchData();
    } catch (err: any) {
      setNotification({ type: 'error', message: err.message || 'Creation error' });
    }
  };

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* Top Header & Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles className="text-primary" size={24} />
            Proactive Intelligence & Ambient Watchers
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
            Continuous workspace pattern discovery, automated opportunity suggestions, and ambient monitors.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
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
            className="btn btn-secondary"
            onClick={handleCheckAllWatchers}
            disabled={checkingWatchers}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '36px', fontSize: '13px' }}
          >
            <Eye size={14} className={checkingWatchers ? 'animate-pulse' : ''} />
            {checkingWatchers ? 'Checking...' : 'Check All Watchers'}
          </button>

          <button
            className="btn btn-primary"
            onClick={handleScanOpportunities}
            disabled={scanning}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '36px', fontSize: '13px' }}
          >
            <Sparkles size={14} className={scanning ? 'animate-spin' : ''} />
            {scanning ? 'Scanning...' : 'Scan Opportunities'}
          </button>

          <button
            className="btn btn-primary"
            onClick={() => setShowCreateModal(true)}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '36px', fontSize: '13px' }}
          >
            <Plus size={14} />
            New Watcher
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
            <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>ACTIVE WATCHERS</span>
            <Eye size={16} className="text-primary" />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700 }}>{watchers.length}</div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>Monitoring local & API state</div>
        </div>

        <div className="card" style={{ padding: '16px', backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>PENDING SUGGESTIONS</span>
            <Zap size={16} style={{ color: 'hsl(var(--warning))' }} />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: suggestions.length > 0 ? 'hsl(var(--warning))' : 'inherit' }}>
            {suggestions.length}
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>Ready for 1-click execution</div>
        </div>

        <div className="card" style={{ padding: '16px', backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>AUTOMATED TRIGGERS</span>
            <CheckCircle2 size={16} style={{ color: 'hsl(var(--success))' }} />
          </div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: 'hsl(var(--success))' }}>
            {watchers.filter(w => w.auto_trigger).length}
          </div>
          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '4px' }}>Autonomous action runners</div>
        </div>
      </div>

      {/* Proactive Suggestions Section */}
      <div className="card" style={{ backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))', padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={18} className="text-primary" />
            Synthesized Proactive Recommendations
          </h3>
          <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
            {suggestions.length} pending
          </span>
        </div>

        {suggestions.length === 0 ? (
          <div style={{ padding: '32px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
            No pending suggestions. Click "Scan Opportunities" above to discover automation patterns in workspace activity.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '14px' }}>
            {suggestions.map((sug) => (
              <div
                key={sug.id}
                style={{
                  padding: '16px',
                  borderRadius: '6px',
                  border: '1px solid hsl(var(--border))',
                  backgroundColor: 'hsl(var(--card))',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '12px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{
                      textTransform: 'uppercase',
                      fontSize: '10px',
                      fontWeight: 700,
                      padding: '2px 6px',
                      borderRadius: '4px',
                      backgroundColor: sug.priority === 'high' ? 'hsl(var(--destructive)/0.2)' : 'hsl(var(--primary)/0.15)',
                      color: sug.priority === 'high' ? 'hsl(var(--destructive))' : 'hsl(var(--primary))',
                    }}>
                      {sug.category.replace('_', ' ')}
                    </span>
                    <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                      Priority: {sug.priority}
                    </span>
                  </div>

                  <strong style={{ fontSize: '14px', display: 'block', marginBottom: '6px' }}>{sug.title}</strong>
                  <p style={{ margin: 0, fontSize: '12px', color: 'hsl(var(--muted-fg))', lineHeight: '1.4' }}>
                    {sug.description}
                  </p>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '8px', borderTop: '1px solid hsl(var(--border))' }}>
                  <span style={{ fontSize: '11px', fontFamily: 'monospace', color: 'hsl(var(--muted-fg))' }}>
                    Action: {sug.proposed_action_id}
                  </span>

                  <div style={{ display: 'flex', gap: '6px' }}>
                    <button
                      className="btn btn-ghost"
                      onClick={() => handleDismissSuggestion(sug.id)}
                      style={{ fontSize: '11px', padding: '4px 8px', height: '28px' }}
                    >
                      Dismiss
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={() => handleAcceptSuggestion(sug.id)}
                      style={{ fontSize: '11px', padding: '4px 10px', height: '28px', display: 'flex', alignItems: 'center', gap: '4px' }}
                    >
                      <ArrowUpRight size={12} /> Accept & Run
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Ambient Watchers Table */}
      <div className="card" style={{ backgroundColor: 'hsl(var(--card))', borderRadius: '8px', border: '1px solid hsl(var(--border))', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid hsl(var(--border))', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Eye size={18} className="text-primary" />
            Configured Ambient Watchers
          </h3>
          <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>Real-time Background Monitors</span>
        </div>

        {watchers.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
            No watchers configured yet. Click "New Watcher" to monitor files, folders, or metric thresholds.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: 'hsl(var(--muted)/0.3)', borderBottom: '1px solid hsl(var(--border))' }}>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Watcher Name</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Type</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Target</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Trigger Action</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Auto-Exec</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>Status</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {watchers.map((w) => (
                  <tr key={w.id} style={{ borderBottom: '1px solid hsl(var(--border))' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 600 }}>{w.name}</td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        textTransform: 'uppercase',
                        fontSize: '10px',
                        fontWeight: 700,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        backgroundColor: 'hsl(var(--secondary))',
                      }}>
                        {w.watcher_type}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontSize: '12px' }}>{w.target}</td>
                    <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontSize: '12px' }}>{w.action_id || 'Alert Only'}</td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        color: w.auto_trigger ? 'hsl(var(--success))' : 'hsl(var(--muted-fg))',
                      }}>
                        {w.auto_trigger ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        fontSize: '10px',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        backgroundColor: w.status === 'triggered' ? 'hsl(var(--warning)/0.2)' : 'hsl(var(--success)/0.2)',
                        color: w.status === 'triggered' ? 'hsl(var(--warning))' : 'hsl(var(--success))',
                      }}>
                        {w.status}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '6px' }}>
                        <button
                          className="btn btn-ghost"
                          onClick={() => handleCheckSingleWatcher(w.id)}
                          style={{ padding: '4px 8px', fontSize: '12px' }}
                        >
                          Check
                        </button>
                        <button
                          className="btn btn-ghost text-destructive"
                          onClick={() => handleDeleteWatcher(w.id)}
                          style={{ padding: '4px 8px', fontSize: '12px' }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create Watcher Modal */}
      {showCreateModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div style={{
            backgroundColor: 'hsl(var(--card))',
            borderRadius: '8px',
            border: '1px solid hsl(var(--border))',
            padding: '24px',
            width: '100%',
            maxWidth: '500px',
          }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, margin: '0 0 16px' }}>
              Create Ambient Watcher
            </h3>

            <form onSubmit={handleCreateWatcher} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>Watcher Name</label>
                <input
                  className="input"
                  style={{ width: '100%' }}
                  placeholder="e.g. Architecture Docs Monitor"
                  value={newWatcherName}
                  onChange={(e) => setNewWatcherName(e.target.value)}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>Watcher Type</label>
                <select
                  className="input"
                  style={{ width: '100%' }}
                  value={newWatcherType}
                  onChange={(e) => setNewWatcherType(e.target.value)}
                >
                  <option value="file_change">File Change (Hash/Modified)</option>
                  <option value="directory_watch">Directory Watch (File count)</option>
                  <option value="metric_threshold">Metric Threshold (Performance/Error)</option>
                  <option value="activity_pattern">Activity Pattern</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>Target Path or Identifier</label>
                <input
                  className="input"
                  style={{ width: '100%' }}
                  placeholder="e.g. docs/architecture.md or src/"
                  value={newWatcherTarget}
                  onChange={(e) => setNewWatcherTarget(e.target.value)}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>Trigger Action ID</label>
                <input
                  className="input"
                  style={{ width: '100%' }}
                  placeholder="e.g. knowledge.search, content.repurpose, benchmarking.run_suite"
                  value={newWatcherAction}
                  onChange={(e) => setNewWatcherAction(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="checkbox"
                  id="auto_trigger"
                  checked={newWatcherAutoTrigger}
                  onChange={(e) => setNewWatcherAutoTrigger(e.target.checked)}
                />
                <label htmlFor="auto_trigger" style={{ fontSize: '13px' }}>
                  Auto-execute action immediately when condition triggers
                </label>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                >
                  Create Watcher
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
