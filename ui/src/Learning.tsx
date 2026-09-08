import { useState, useEffect, useContext, useMemo } from 'react';
import {
  GraduationCap, Search, ShieldCheck, AlertTriangle, CheckCircle2, XCircle,
  RefreshCw, X, Brain, Database
} from 'lucide-react';
import { ToastContext } from './toast';
import { apiUrl, apiError } from './api';
import { TopHeader } from './TopHeader';
import { useTranslation } from './i18n';

export interface DistilledLesson {
  id: string;
  workspace_id: string;
  title: string;
  lesson_text: string;
  scope: string;
  target_identifier?: string | null;
  source_mission_id?: string | null;
  source_execution_id?: string | null;
  source_correction_id?: string | null;
  quality_gate_rule?: string | null;
  verification_status: string;
  memory_id?: string | null;
  node_id?: string | null;
  is_regression: boolean;
  regression_count: number;
  created_at: string;
  metadata?: Record<string, any>;
}

export interface Correction {
  id: string;
  workspace_id: string;
  target_scope?: string | null;
  target_identifier?: string | null;
  problem?: string | null;
  correction?: string | null;
  rationale?: string | null;
  evidence: Record<string, any>;
  source_mission_id?: string | null;
  source_execution_id?: string | null;
  verification_status: string;
  verified_at?: string | null;
  is_regression?: boolean;
  rework_count?: number;
  created_at: string;
}

export interface LearningEvent {
  id: string;
  workspace_id: string;
  event_type: string;
  observed_behavior: string;
  expected_behavior?: string | null;
  correction?: string | null;
  evidence: Record<string, any>;
  verification_status: string;
  mission_id?: string | null;
  execution_id?: string | null;
  milestone_id?: string | null;
  agent_name?: string | null;
  team_name?: string | null;
  scope?: string | null;
  created_at: string;
}

export function Learning() {
  const { t } = useTranslation();
  const showToast = useContext(ToastContext);

  const [lessons, setLessons] = useState<DistilledLesson[]>([]);
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [events, setEvents] = useState<LearningEvent[]>([]);
  const [loading, setLoading] = useState(true);

  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'lessons' | 'corrections' | 'regressions' | 'events'>('all');
  const [scopeFilter, setScopeFilter] = useState<string>('all');

  // Evidence modal state
  const [selectedEvidence, setSelectedEvidence] = useState<{
    title: string;
    type: 'lesson' | 'correction' | 'event';
    item: any;
  } | null>(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [lessonsRes, correctionsRes, eventsRes] = await Promise.all([
        fetch(apiUrl('/api/learning/lessons?limit=100')),
        fetch(apiUrl('/api/learning/corrections?limit=100')),
        fetch(apiUrl('/api/learning/events?limit=100')),
      ]);

      if (lessonsRes.ok) {
        const data = await lessonsRes.json();
        setLessons(Array.isArray(data) ? data : []);
      }
      if (correctionsRes.ok) {
        const data = await correctionsRes.json();
        setCorrections(Array.isArray(data) ? data : []);
      }
      if (eventsRes.ok) {
        const data = await eventsRes.json();
        setEvents(Array.isArray(data) ? data : []);
      }
    } catch (err: any) {
      console.error('Failed to fetch learning records:', err);
      showToast(err.message || 'Failed to fetch learning loop records', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleVerifyCorrection = async (corrId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/learning/corrections/${corrId}/verify`), {
        method: 'POST',
      });
      if (!res.ok) {
        throw await apiError(res, 'Failed to verify correction');
      }
      showToast('Correction verified and distilled into persistent lesson', 'success');
      fetchData();
    } catch (err: any) {
      showToast(err.message || 'Verification failed', 'error');
    }
  };

  const handleRejectCorrection = async (corrId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/learning/corrections/${corrId}/reject`), {
        method: 'POST',
      });
      if (!res.ok) {
        throw await apiError(res, 'Failed to reject correction');
      }
      showToast('Correction rejected', 'success');
      fetchData();
    } catch (err: any) {
      showToast(err.message || 'Rejection failed', 'error');
    }
  };

  // Metrics summary
  const metrics = useMemo(() => {
    const verifiedCount = lessons.filter(l => l.verification_status === 'verified').length;
    const proposedCount = corrections.filter(c => c.verification_status === 'proposed').length;
    const regressionsCount = lessons.filter(l => l.is_regression || l.regression_count > 0).length +
      corrections.filter(c => c.is_regression).length;
    const eventsCount = events.length;
    return { verifiedCount, proposedCount, regressionsCount, eventsCount };
  }, [lessons, corrections, events]);

  // Filtered items
  const filteredLessons = useMemo(() => {
    return lessons.filter(l => {
      if (scopeFilter !== 'all' && l.scope !== scopeFilter) return false;
      if (activeTab === 'regressions' && !l.is_regression && l.regression_count === 0) return false;
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        l.title.toLowerCase().includes(q) ||
        l.lesson_text.toLowerCase().includes(q) ||
        (l.quality_gate_rule && l.quality_gate_rule.toLowerCase().includes(q)) ||
        (l.target_identifier && l.target_identifier.toLowerCase().includes(q))
      );
    });
  }, [lessons, scopeFilter, activeTab, searchQuery]);

  const filteredCorrections = useMemo(() => {
    return corrections.filter(c => {
      const cScope = c.target_scope || 'workspace';
      if (scopeFilter !== 'all' && cScope !== scopeFilter) return false;
      if (activeTab === 'regressions' && !c.is_regression) return false;
      if (activeTab === 'lessons') return false;
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      const problemText = c.problem || '';
      const correctionText = c.correction || '';
      const rationaleText = c.rationale || '';
      const targetId = c.target_identifier || '';
      return (
        problemText.toLowerCase().includes(q) ||
        correctionText.toLowerCase().includes(q) ||
        rationaleText.toLowerCase().includes(q) ||
        targetId.toLowerCase().includes(q)
      );
    });
  }, [corrections, scopeFilter, activeTab, searchQuery]);

  const filteredEvents = useMemo(() => {
    if (activeTab !== 'all' && activeTab !== 'events') return [];
    return events.filter(e => {
      const eScope = e.scope || 'workspace';
      if (scopeFilter !== 'all' && eScope !== scopeFilter) return false;
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        e.observed_behavior.toLowerCase().includes(q) ||
        (e.correction && e.correction.toLowerCase().includes(q)) ||
        (e.agent_name && e.agent_name.toLowerCase().includes(q)) ||
        (e.team_name && e.team_name.toLowerCase().includes(q))
      );
    });
  }, [events, scopeFilter, activeTab, searchQuery]);

  const totalFilteredCount = (activeTab === 'corrections' ? filteredCorrections.length :
    activeTab === 'lessons' ? filteredLessons.length :
    activeTab === 'events' ? filteredEvents.length :
    filteredLessons.length + filteredCorrections.length + filteredEvents.length);

  return (
    <div className="view-container" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <TopHeader
        title={t('learningTitle')}
        subtitle={t('learningSubtitle')}
      >
        <button
          className="btn btn-ghost"
          style={{ padding: '6px 12px', fontSize: '12px' }}
          onClick={fetchData}
          disabled={loading}
          data-testid="refresh-learning-btn"
        >
          <RefreshCw size={14} className={loading ? 'spin' : ''} style={{ marginRight: '6px' }} />
          Refresh
        </button>
      </TopHeader>

      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px' }}>
        {/* Metric Summary Cards */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '16px',
          marginBottom: '24px'
        }} data-testid="learning-summary-banner">
          <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{
              width: '40px', height: '40px', borderRadius: '8px',
              backgroundColor: 'rgba(16, 185, 129, 0.12)', color: '#10b981',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <GraduationCap size={22} />
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>
                {t('learningTotalLessons')}
              </div>
              <div style={{ fontSize: '22px', fontWeight: 700, color: 'hsl(var(--fg))' }} data-testid="metric-verified-lessons">
                {metrics.verifiedCount}
              </div>
            </div>
          </div>

          <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{
              width: '40px', height: '40px', borderRadius: '8px',
              backgroundColor: 'rgba(59, 130, 246, 0.12)', color: '#3b82f6',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <AlertTriangle size={22} />
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>
                {t('learningProposedCorrections')}
              </div>
              <div style={{ fontSize: '22px', fontWeight: 700, color: 'hsl(var(--fg))' }} data-testid="metric-proposed-corrections">
                {metrics.proposedCount}
              </div>
            </div>
          </div>

          <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{
              width: '40px', height: '40px', borderRadius: '8px',
              backgroundColor: metrics.regressionsCount > 0 ? 'rgba(244, 63, 94, 0.12)' : 'rgba(148, 163, 184, 0.12)',
              color: metrics.regressionsCount > 0 ? '#f43f5e' : '#94a3b8',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <AlertTriangle size={22} />
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>
                {t('learningRegressionsCount')}
              </div>
              <div style={{
                fontSize: '22px', fontWeight: 700,
                color: metrics.regressionsCount > 0 ? '#f43f5e' : 'hsl(var(--fg))'
              }} data-testid="metric-regressions-count">
                {metrics.regressionsCount}
              </div>
            </div>
          </div>

          <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{
              width: '40px', height: '40px', borderRadius: '8px',
              backgroundColor: 'rgba(168, 85, 247, 0.12)', color: '#a855f7',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <Brain size={22} />
            </div>
            <div>
              <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontWeight: 500 }}>
                {t('learningTotalEvents')}
              </div>
              <div style={{ fontSize: '22px', fontWeight: 700, color: 'hsl(var(--fg))' }} data-testid="metric-total-events">
                {metrics.eventsCount}
              </div>
            </div>
          </div>
        </div>

        {/* Filter Controls */}
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '12px',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '20px'
        }}>
          {/* Navigation Tabs */}
          <div style={{ display: 'flex', gap: '6px', backgroundColor: 'hsl(var(--muted))', padding: '4px', borderRadius: '8px' }}>
            <button
              className={`btn btn-ghost ${activeTab === 'all' ? 'active' : ''}`}
              style={{ padding: '6px 14px', fontSize: '13px', borderRadius: '6px' }}
              onClick={() => setActiveTab('all')}
              data-testid="tab-learning-all"
            >
              {t('learningTabAll')}
            </button>
            <button
              className={`btn btn-ghost ${activeTab === 'lessons' ? 'active' : ''}`}
              style={{ padding: '6px 14px', fontSize: '13px', borderRadius: '6px' }}
              onClick={() => setActiveTab('lessons')}
              data-testid="tab-learning-lessons"
            >
              {t('learningTabLessons')} ({metrics.verifiedCount})
            </button>
            <button
              className={`btn btn-ghost ${activeTab === 'corrections' ? 'active' : ''}`}
              style={{ padding: '6px 14px', fontSize: '13px', borderRadius: '6px' }}
              onClick={() => setActiveTab('corrections')}
              data-testid="tab-learning-corrections"
            >
              {t('learningTabCorrections')} ({corrections.length})
            </button>
            <button
              className={`btn btn-ghost ${activeTab === 'regressions' ? 'active' : ''}`}
              style={{
                padding: '6px 14px', fontSize: '13px', borderRadius: '6px',
                color: metrics.regressionsCount > 0 ? '#f43f5e' : undefined
              }}
              onClick={() => setActiveTab('regressions')}
              data-testid="tab-learning-regressions"
            >
              {t('learningTabRegressions')} ({metrics.regressionsCount})
            </button>
            <button
              className={`btn btn-ghost ${activeTab === 'events' ? 'active' : ''}`}
              style={{ padding: '6px 14px', fontSize: '13px', borderRadius: '6px' }}
              onClick={() => setActiveTab('events')}
              data-testid="tab-learning-events"
            >
              {t('learningTabEvents')}
            </button>
          </div>

          {/* Search & Scope Filters */}
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <div style={{ position: 'relative', width: '280px' }}>
              <Search size={15} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'hsl(var(--muted-fg))' }} />
              <input
                type="text"
                placeholder={t('learningSearchPlaceholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="input"
                style={{ paddingLeft: '32px', height: '36px', fontSize: '13px', width: '100%' }}
                data-testid="learning-search-input"
              />
              {searchQuery && (
                <button
                  className="btn btn-ghost"
                  style={{ position: 'absolute', right: '4px', top: '50%', transform: 'translateY(-50%)', padding: '2px' }}
                  onClick={() => setSearchQuery('')}
                >
                  <X size={14} />
                </button>
              )}
            </div>

            <select
              value={scopeFilter}
              onChange={(e) => setScopeFilter(e.target.value)}
              className="input"
              style={{ height: '36px', fontSize: '13px', padding: '0 8px' }}
              data-testid="learning-scope-filter"
            >
              <option value="all">All Scopes</option>
              <option value="agent">{t('learningScopeAgent')}</option>
              <option value="team">{t('learningScopeTeam')}</option>
              <option value="project">{t('learningScopeProject')}</option>
              <option value="process">{t('learningScopeProcess')}</option>
              <option value="workspace">{t('learningScopeWorkspace')}</option>
            </select>
          </div>
        </div>

        {/* Content Lists */}
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0', color: 'hsl(var(--muted-fg))' }}>
            <RefreshCw size={24} className="spin" />
          </div>
        ) : totalFilteredCount === 0 ? (
          <div className="card" style={{ padding: '48px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }} data-testid="learning-empty-state">
            <GraduationCap size={44} style={{ margin: '0 auto 16px', opacity: 0.4 }} />
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'hsl(var(--fg))', marginBottom: '8px' }}>
              {t('learningEmptyTitle')}
            </h3>
            <p style={{ fontSize: '13px', maxWidth: '440px', margin: '0 auto' }}>
              {t('learningEmptyDesc')}
            </p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }} data-testid="learning-items-container">
            {/* Distilled Lessons */}
            {(activeTab === 'all' || activeTab === 'lessons' || activeTab === 'regressions') && filteredLessons.map((lesson) => (
              <div
                key={lesson.id}
                className="card"
                style={{
                  padding: '20px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  borderLeft: lesson.is_regression ? '4px solid #f43f5e' : '4px solid #10b981',
                }}
                data-testid={`lesson-card-${lesson.id}`}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <div style={{
                      backgroundColor: 'rgba(16, 185, 129, 0.12)', color: '#10b981',
                      padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600,
                      display: 'flex', alignItems: 'center', gap: '4px'
                    }}>
                      <ShieldCheck size={12} />
                      Verified Lesson
                    </div>

                    <div style={{
                      backgroundColor: 'hsl(var(--muted))', color: 'hsl(var(--muted-fg))',
                      padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 500,
                    }}>
                      Scope: {lesson.scope} {lesson.target_identifier ? `(${lesson.target_identifier})` : ''}
                    </div>

                    {lesson.quality_gate_rule && (
                      <div style={{
                        backgroundColor: 'rgba(59, 130, 246, 0.1)', color: '#3b82f6',
                        padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 500,
                      }}>
                        Rule: {lesson.quality_gate_rule}
                      </div>
                    )}

                    {lesson.is_regression && (
                      <div style={{
                        backgroundColor: 'rgba(244, 63, 94, 0.12)', color: '#f43f5e',
                        padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600,
                        display: 'flex', alignItems: 'center', gap: '4px'
                      }}>
                        <AlertTriangle size={12} />
                        Regression Detected ({lesson.regression_count}x)
                      </div>
                    )}
                  </div>

                  <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', whiteSpace: 'nowrap' }}>
                    {new Date(lesson.created_at).toLocaleString()}
                  </span>
                </div>

                <div>
                  <h4 style={{ fontSize: '15px', fontWeight: 600, color: 'hsl(var(--fg))', marginBottom: '6px' }}>
                    {lesson.title}
                  </h4>
                  <p style={{ fontSize: '13px', color: 'hsl(var(--fg))', lineHeight: '1.5', whiteSpace: 'pre-wrap' }}>
                    {lesson.lesson_text}
                  </p>
                </div>

                {/* Relational Provenance Footer */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  paddingTop: '8px',
                  borderTop: '1px solid hsl(var(--border))',
                  fontSize: '12px',
                  color: 'hsl(var(--muted-fg))',
                  flexWrap: 'wrap',
                  gap: '8px'
                }}>
                  <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                    {lesson.source_mission_id && (
                      <span>Mission: <strong style={{ color: 'hsl(var(--fg))' }}>{lesson.source_mission_id}</strong></span>
                    )}
                    {lesson.memory_id && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#10b981' }}>
                        <Brain size={13} /> Linked in Memory
                      </span>
                    )}
                    {lesson.node_id && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#6366f1' }}>
                        <Database size={13} /> Linked in Graph
                      </span>
                    )}
                  </div>

                  <button
                    className="btn btn-ghost"
                    style={{ padding: '4px 10px', fontSize: '12px', color: 'hsl(var(--primary))' }}
                    onClick={() => setSelectedEvidence({ title: lesson.title, type: 'lesson', item: lesson })}
                    data-testid={`view-evidence-lesson-${lesson.id}`}
                  >
                    View Evidence
                  </button>
                </div>
              </div>
            ))}

            {/* Corrections */}
            {(activeTab === 'all' || activeTab === 'corrections' || activeTab === 'regressions') && filteredCorrections.map((corr) => {
              const problemText = corr.problem || 'Observed failure under evaluation';
              const fixText = corr.correction || 'Proposed correction fix';
              const targetScope = corr.target_scope || 'workspace';
              const targetId = corr.target_identifier || 'workspace';
              const missionId = corr.source_mission_id;

              return (
                <div
                  key={corr.id}
                  className="card"
                  style={{
                    padding: '20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    borderLeft: corr.verification_status === 'verified' ? '4px solid #10b981' :
                      corr.verification_status === 'rejected' ? '4px solid #94a3b8' : '4px solid #f59e0b',
                  }}
                  data-testid={`correction-card-${corr.id}`}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <div style={{
                        backgroundColor: corr.verification_status === 'verified' ? 'rgba(16, 185, 129, 0.12)' :
                          corr.verification_status === 'rejected' ? 'rgba(148, 163, 184, 0.15)' : 'rgba(245, 158, 11, 0.12)',
                        color: corr.verification_status === 'verified' ? '#10b981' :
                          corr.verification_status === 'rejected' ? '#64748b' : '#f59e0b',
                        padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600,
                        textTransform: 'capitalize'
                      }}>
                        Correction: {corr.verification_status}
                      </div>

                      <div style={{
                        backgroundColor: 'hsl(var(--muted))', color: 'hsl(var(--muted-fg))',
                        padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 500,
                      }}>
                        Scope: {targetScope} ({targetId})
                      </div>
                    </div>

                    <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', whiteSpace: 'nowrap' }}>
                      {new Date(corr.created_at).toLocaleString()}
                    </span>
                  </div>

                  {/* Failure vs Proposed Fix comparison */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '4px' }}>
                    <div style={{ backgroundColor: 'rgba(244, 63, 94, 0.05)', padding: '10px 12px', borderRadius: '6px', border: '1px solid rgba(244, 63, 94, 0.15)' }}>
                      <div style={{ fontSize: '11px', fontWeight: 600, color: '#f43f5e', marginBottom: '4px' }}>
                        Observed Problem
                      </div>
                      <div style={{ fontSize: '12px', color: 'hsl(var(--fg))' }}>
                        {problemText}
                      </div>
                    </div>

                    <div style={{ backgroundColor: 'rgba(16, 185, 129, 0.05)', padding: '10px 12px', borderRadius: '6px', border: '1px solid rgba(16, 185, 129, 0.15)' }}>
                      <div style={{ fontSize: '11px', fontWeight: 600, color: '#10b981', marginBottom: '4px' }}>
                        Proposed Correction
                      </div>
                      <div style={{ fontSize: '12px', color: 'hsl(var(--fg))' }}>
                        {fixText}
                      </div>
                    </div>
                  </div>

                  {/* Actions & Provenance */}
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    paddingTop: '8px',
                    borderTop: '1px solid hsl(var(--border))',
                    fontSize: '12px',
                    color: 'hsl(var(--muted-fg))',
                    flexWrap: 'wrap',
                    gap: '8px'
                  }}>
                    <div>
                      {missionId && (
                        <span>Mission: <strong style={{ color: 'hsl(var(--fg))' }}>{missionId}</strong></span>
                      )}
                    </div>

                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: '4px 10px', fontSize: '12px' }}
                        onClick={() => setSelectedEvidence({ title: `Correction ${corr.id}`, type: 'correction', item: corr })}
                        data-testid={`view-evidence-correction-${corr.id}`}
                      >
                        View Evidence
                      </button>

                      {corr.verification_status === 'proposed' && (
                        <>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '4px 10px', fontSize: '12px', color: '#10b981' }}
                            onClick={() => handleVerifyCorrection(corr.id)}
                            data-testid={`verify-correction-${corr.id}`}
                          >
                            <CheckCircle2 size={13} style={{ marginRight: '4px' }} />
                            Verify
                          </button>
                          <button
                            className="btn btn-ghost"
                            style={{ padding: '4px 10px', fontSize: '12px', color: '#f43f5e' }}
                            onClick={() => handleRejectCorrection(corr.id)}
                            data-testid={`reject-correction-${corr.id}`}
                          >
                            <XCircle size={13} style={{ marginRight: '4px' }} />
                            Reject
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Learning Events */}
            {(activeTab === 'all' || activeTab === 'events') && filteredEvents.map((evt) => (
              <div
                key={evt.id}
                className="card"
                style={{
                  padding: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  opacity: 0.9,
                }}
                data-testid={`event-card-${evt.id}`}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <div style={{
                      backgroundColor: 'hsl(var(--muted))',
                      color: 'hsl(var(--fg))',
                      padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600,
                      textTransform: 'uppercase'
                    }}>
                      Event: {evt.event_type}
                    </div>
                    {evt.agent_name && (
                      <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                        Agent: <strong style={{ color: 'hsl(var(--fg))' }}>{evt.agent_name}</strong>
                      </span>
                    )}
                  </div>
                  <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                    {new Date(evt.created_at).toLocaleString()}
                  </span>
                </div>

                <div style={{ fontSize: '13px', color: 'hsl(var(--fg))' }}>
                  {evt.observed_behavior}
                </div>

                {evt.correction && (
                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                    Correction: {evt.correction}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Evidence Inspection Modal */}
      {selectedEvidence && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(3px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px'
        }} data-testid="learning-evidence-modal">
          <div className="card" style={{
            width: '100%',
            maxWidth: '650px',
            maxHeight: '85vh',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)'
          }}>
            {/* Modal Header */}
            <div style={{
              padding: '16px 20px',
              borderBottom: '1px solid hsl(var(--border))',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShieldCheck size={18} color="#10b981" />
                <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0 }}>
                  Evidence & Provenance: {selectedEvidence.title}
                </h3>
              </div>
              <button
                className="btn btn-ghost"
                style={{ padding: '4px' }}
                onClick={() => setSelectedEvidence(null)}
                data-testid="close-evidence-modal"
              >
                <X size={16} />
              </button>
            </div>

            {/* Modal Content */}
            <div style={{ padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '4px', textTransform: 'uppercase' }}>
                  Entity Identifiers
                </div>
                <div style={{
                  backgroundColor: 'hsl(var(--muted))',
                  padding: '10px 12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontFamily: 'var(--font-mono, monospace)',
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '6px'
                }}>
                  <div>ID: {selectedEvidence.item.id}</div>
                  <div>Workspace: {selectedEvidence.item.workspace_id}</div>
                  {(selectedEvidence.item.source_mission_id || selectedEvidence.item.mission_id) && (
                    <div>Mission: {selectedEvidence.item.source_mission_id || selectedEvidence.item.mission_id}</div>
                  )}
                  {selectedEvidence.item.quality_gate_rule && <div>Rule: {selectedEvidence.item.quality_gate_rule}</div>}
                  {selectedEvidence.item.memory_id && <div>Memory ID: {selectedEvidence.item.memory_id}</div>}
                  {selectedEvidence.item.node_id && <div>Node ID: {selectedEvidence.item.node_id}</div>}
                </div>
              </div>

              {(selectedEvidence.item.problem || selectedEvidence.item.observed_behavior) && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: '#f43f5e', marginBottom: '4px', textTransform: 'uppercase' }}>
                    Observed Problem / Failure
                  </div>
                  <div style={{ backgroundColor: 'rgba(244, 63, 94, 0.05)', padding: '10px', borderRadius: '6px', fontSize: '13px' }}>
                    {selectedEvidence.item.problem || selectedEvidence.item.observed_behavior}
                  </div>
                </div>
              )}

              {(selectedEvidence.item.correction || selectedEvidence.item.rationale) && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: '#10b981', marginBottom: '4px', textTransform: 'uppercase' }}>
                    Proposed Correction / Rationale
                  </div>
                  <div style={{ backgroundColor: 'rgba(16, 185, 129, 0.05)', padding: '10px', borderRadius: '6px', fontSize: '13px' }}>
                    {selectedEvidence.item.correction || selectedEvidence.item.rationale}
                  </div>
                </div>
              )}

              {selectedEvidence.item.lesson_text && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: '#3b82f6', marginBottom: '4px', textTransform: 'uppercase' }}>
                    Verified Lesson Knowledge
                  </div>
                  <div style={{ backgroundColor: 'rgba(59, 130, 246, 0.05)', padding: '10px', borderRadius: '6px', fontSize: '13px' }}>
                    {selectedEvidence.item.lesson_text}
                  </div>
                </div>
              )}

              {selectedEvidence.item.evidence && Object.keys(selectedEvidence.item.evidence).length > 0 && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '4px', textTransform: 'uppercase' }}>
                    Raw Evidence Data
                  </div>
                  <pre style={{
                    backgroundColor: 'hsl(var(--muted))',
                    padding: '10px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    overflowX: 'auto',
                    margin: 0
                  }}>
                    {JSON.stringify(selectedEvidence.item.evidence, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div style={{
              padding: '12px 20px',
              borderTop: '1px solid hsl(var(--border))',
              display: 'flex',
              justifyContent: 'flex-end',
              backgroundColor: 'hsl(var(--muted))'
            }}>
              <button
                className="btn btn-primary"
                style={{ padding: '6px 16px', fontSize: '13px' }}
                onClick={() => setSelectedEvidence(null)}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
