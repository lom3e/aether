import { useState, useEffect, useContext, useMemo } from 'react';
import {
  Brain, Search, Plus, Archive, ArchiveRestore, Trash2,
  ShieldCheck, Tag, Bot, X, RefreshCw
} from 'lucide-react';
import { ToastContext } from './toast';
import { apiUrl, apiError } from './api';
import { TopHeader } from './TopHeader';
import { useTranslation } from './i18n';
import { Tooltip } from './Tooltip';

export interface MemoryProvenance {
  source_entity: string;
  source_id?: string | null;
  source_mission_id?: string | null;
  source_execution_id?: string | null;
  author_agent?: string | null;
  verification_status: string;
  verified_at?: string | null;
  evidence_excerpt?: string | null;
}

export interface WorkforceMemory {
  id: string;
  workspace_id: string;
  team_name?: string | null;
  agent_name?: string | null;
  mission_id?: string | null;
  execution_id?: string | null;
  category: string;
  summary: string;
  content: string;
  provenance: MemoryProvenance;
  confidence: number;
  tags: string[];
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

interface CategoryDef {
  key: string;
  label: string;
  color: string;
}

const CATEGORIES: CategoryDef[] = [
  { key: 'all', label: 'All Categories', color: '#64748b' },
  { key: 'fact', label: 'Fact', color: '#3b82f6' },
  { key: 'preference', label: 'Preference', color: '#a855f7' },
  { key: 'decision', label: 'Decision', color: '#10b981' },
  { key: 'process', label: 'Process', color: '#f59e0b' },
  { key: 'person', label: 'Person', color: '#6366f1' },
  { key: 'project', label: 'Project', color: '#06b6d4' },
  { key: 'outcome', label: 'Outcome', color: '#22c55e' },
  { key: 'lesson', label: 'Lesson', color: '#f43f5e' },
];

export function Memory() {
  const { t } = useTranslation();
  const showToast = useContext(ToastContext);

  const [memories, setMemories] = useState<WorkforceMemory[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<'active' | 'archived' | 'all'>('active');
  const [activeMemory, setActiveMemory] = useState<WorkforceMemory | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // New Memory form state
  const [newCategory, setNewCategory] = useState<string>('fact');
  const [newSummary, setNewSummary] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newTags, setNewTags] = useState('');
  const [newConfidence, setNewConfidence] = useState(0.9);
  const [submitting, setSubmitting] = useState(false);

  const fetchMemories = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedCategory !== 'all') {
        params.set('category', selectedCategory);
      }
      if (statusFilter !== 'all') {
        params.set('status', statusFilter);
      }
      if (searchQuery.trim()) {
        params.set('search', searchQuery.trim());
      }
      params.set('limit', '100');

      const res = await fetch(apiUrl(`/api/memories?${params.toString()}`));
      if (!res.ok) {
        throw await apiError(res, 'Failed to fetch workforce memories');
      }
      const data = await res.json();
      setMemories(Array.isArray(data) ? data : []);
    } catch (err: any) {
      console.error('Failed to fetch workforce memories:', err);
      showToast(err.message || 'Failed to load workforce memories', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const handler = setTimeout(() => {
      fetchMemories();
    }, 200);
    return () => clearTimeout(handler);
  }, [selectedCategory, statusFilter, searchQuery]);

  const handleCreateMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSummary.trim() || !newContent.trim()) {
      showToast('Summary and content are required', 'warning');
      return;
    }

    setSubmitting(true);
    try {
      const tagsList = newTags
        .split(',')
        .map(t => t.trim())
        .filter(Boolean);

      const res = await fetch(apiUrl('/api/memories'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category: newCategory,
          summary: newSummary.trim(),
          content: newContent.trim(),
          tags: tagsList,
          confidence: newConfidence,
          source_entity: 'manual',
          author_agent: 'User',
        }),
      });

      if (!res.ok) {
        throw await apiError(res, 'Failed to record memory');
      }

      const created = await res.json();
      showToast('Memory successfully recorded', 'success');
      setIsCreating(false);
      setNewSummary('');
      setNewContent('');
      setNewTags('');
      setNewConfidence(0.9);
      setMemories(prev => [created, ...prev]);
    } catch (err: any) {
      showToast(err.message || 'Failed to record memory', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleArchive = async (mem: WorkforceMemory) => {
    try {
      const newArchived = !mem.is_archived;
      const res = await fetch(apiUrl(`/api/memories/${mem.id}/archive?archived=${newArchived}`), {
        method: 'POST',
      });
      if (!res.ok) throw await apiError(res, 'Failed to update archive state');
      const updated = await res.json();
      showToast(newArchived ? 'Memory archived' : 'Memory unarchived', 'info');
      setMemories(prev => prev.map(m => (m.id === mem.id ? updated : m)));
      if (activeMemory?.id === mem.id) {
        setActiveMemory(updated);
      }
    } catch (err: any) {
      showToast(err.message || 'Archive toggle failed', 'error');
    }
  };

  const handleDeleteMemory = async (mem: WorkforceMemory) => {
    if (!confirm(`Are you sure you want to delete memory: "${mem.summary}"?`)) return;
    try {
      const res = await fetch(apiUrl(`/api/memories/${mem.id}`), {
        method: 'DELETE',
      });
      if (!res.ok) throw await apiError(res, 'Failed to delete memory');
      showToast('Memory record deleted', 'info');
      setMemories(prev => prev.filter(m => m.id !== mem.id));
      if (activeMemory?.id === mem.id) {
        setActiveMemory(null);
      }
    } catch (err: any) {
      showToast(err.message || 'Delete failed', 'error');
    }
  };

  const getCategoryColor = (cat: string) => {
    const found = CATEGORIES.find(c => c.key === cat.toLowerCase());
    return found?.color || '#3b82f6';
  };

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { all: memories.length };
    for (const m of memories) {
      const k = m.category.toLowerCase();
      counts[k] = (counts[k] || 0) + 1;
    }
    return counts;
  }, [memories]);

  return (
    <div
      data-testid="memory-view"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: 'hsl(var(--bg))',
        color: 'hsl(var(--fg))',
        overflow: 'hidden',
      }}
    >
      <TopHeader title={t('memoryTitle')} icon={Brain} />

      {/* Main Content Area */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' }}>
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflowY: 'auto',
            padding: '24px 32px',
            maxWidth: '1200px',
            margin: '0 auto',
            width: '100%',
          }}
        >
          {/* Executive Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '36px',
                    height: '36px',
                    borderRadius: '8px',
                    backgroundColor: 'rgba(59, 130, 246, 0.12)',
                    color: '#3b82f6',
                  }}
                >
                  <Brain size={22} />
                </div>
                <div>
                  <h1 style={{ fontSize: '20px', fontWeight: 600, margin: 0, letterSpacing: '-0.02em' }}>
                    {t('memoryTitle')}
                  </h1>
                  <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', margin: '2px 0 0 0' }}>
                    {t('memorySubtitle')}
                  </p>
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Tooltip content="Refresh memories">
                <button
                  className="btn btn-ghost"
                  onClick={fetchMemories}
                  style={{ padding: '8px', borderRadius: '6px' }}
                >
                  <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
                </button>
              </Tooltip>

              <button
                data-testid="btn-add-memory"
                className="btn btn-primary"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 14px',
                  fontSize: '13px',
                  fontWeight: 500,
                  borderRadius: '6px',
                }}
                onClick={() => setIsCreating(true)}
              >
                <Plus size={15} />
                <span>{t('addMemory')}</span>
              </button>
            </div>
          </div>

          {/* Controls Bar: Search & Status Toggle */}
          <div
            style={{
              display: 'flex',
              gap: '12px',
              alignItems: 'center',
              marginBottom: '16px',
              flexWrap: 'wrap',
            }}
          >
            {/* Search Input */}
            <div style={{ position: 'relative', flex: 1, minWidth: '260px' }}>
              <Search
                size={15}
                style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'hsl(var(--muted-fg))',
                }}
              />
              <input
                data-testid="memory-search-input"
                type="text"
                placeholder={t('memorySearchPlaceholder')}
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px 8px 36px',
                  fontSize: '13px',
                  borderRadius: '8px',
                  border: '1px solid hsl(var(--border))',
                  backgroundColor: 'hsl(var(--card))',
                  color: 'hsl(var(--fg))',
                  outline: 'none',
                }}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    color: 'hsl(var(--muted-fg))',
                    cursor: 'pointer',
                  }}
                >
                  <X size={14} />
                </button>
              )}
            </div>

            {/* Status Filter Toggle */}
            <div
              style={{
                display: 'flex',
                borderRadius: '8px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))',
                padding: '2px',
              }}
            >
              <button
                className={`btn btn-ghost ${statusFilter === 'active' ? 'active' : ''}`}
                style={{
                  padding: '5px 12px',
                  fontSize: '12px',
                  borderRadius: '6px',
                  backgroundColor: statusFilter === 'active' ? 'hsl(var(--accent))' : 'transparent',
                  color: statusFilter === 'active' ? 'hsl(var(--accent-fg))' : 'hsl(var(--muted-fg))',
                }}
                onClick={() => setStatusFilter('active')}
              >
                {t('memoryActive')}
              </button>
              <button
                className={`btn btn-ghost ${statusFilter === 'archived' ? 'active' : ''}`}
                style={{
                  padding: '5px 12px',
                  fontSize: '12px',
                  borderRadius: '6px',
                  backgroundColor: statusFilter === 'archived' ? 'hsl(var(--accent))' : 'transparent',
                  color: statusFilter === 'archived' ? 'hsl(var(--accent-fg))' : 'hsl(var(--muted-fg))',
                }}
                onClick={() => setStatusFilter('archived')}
              >
                {t('memoryArchived')}
              </button>
              <button
                className={`btn btn-ghost ${statusFilter === 'all' ? 'active' : ''}`}
                style={{
                  padding: '5px 12px',
                  fontSize: '12px',
                  borderRadius: '6px',
                  backgroundColor: statusFilter === 'all' ? 'hsl(var(--accent))' : 'transparent',
                  color: statusFilter === 'all' ? 'hsl(var(--accent-fg))' : 'hsl(var(--muted-fg))',
                }}
                onClick={() => setStatusFilter('all')}
              >
                All
              </button>
            </div>
          </div>

          {/* 8-Category Filter Pills */}
          <div
            style={{
              display: 'flex',
              gap: '6px',
              overflowX: 'auto',
              paddingBottom: '8px',
              marginBottom: '20px',
            }}
          >
            {CATEGORIES.map(cat => {
              const isSelected = selectedCategory === cat.key;
              const count = categoryCounts[cat.key] ?? 0;
              return (
                <button
                  key={cat.key}
                  data-testid={`category-filter-${cat.key}`}
                  onClick={() => setSelectedCategory(cat.key)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '5px 12px',
                    borderRadius: '20px',
                    fontSize: '12px',
                    fontWeight: isSelected ? 600 : 500,
                    border: isSelected ? `1px solid ${cat.color}` : '1px solid hsl(var(--border))',
                    backgroundColor: isSelected
                      ? `${cat.color}1a`
                      : 'hsl(var(--card))',
                    color: isSelected ? cat.color : 'hsl(var(--muted-fg))',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <span
                    style={{
                      width: '7px',
                      height: '7px',
                      borderRadius: '50%',
                      backgroundColor: cat.color,
                    }}
                  />
                  <span>{cat.label}</span>
                  <span
                    style={{
                      fontSize: '11px',
                      opacity: 0.7,
                      padding: '1px 5px',
                      borderRadius: '10px',
                      backgroundColor: isSelected ? `${cat.color}26` : 'hsl(var(--muted)/0.3)',
                    }}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Memories Stream */}
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '60px', color: 'hsl(var(--muted-fg))' }}>
              <RefreshCw size={24} className="animate-spin" />
            </div>
          ) : memories.length === 0 ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '60px 20px',
                textAlign: 'center',
                backgroundColor: 'hsl(var(--card))',
                borderRadius: '12px',
                border: '1px dashed hsl(var(--border))',
                marginTop: '12px',
              }}
            >
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '12px',
                  backgroundColor: 'rgba(59, 130, 246, 0.08)',
                  color: '#3b82f6',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '16px',
                }}
              >
                <Brain size={26} />
              </div>
              <h3 style={{ fontSize: '15px', fontWeight: 600, margin: '0 0 6px 0' }}>
                {t('noMemoriesYet')}
              </h3>
              <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', maxWidth: '440px', margin: 0, lineHeight: 1.5 }}>
                {t('noMemoriesDesc')}
              </p>
              <button
                className="btn btn-primary"
                onClick={() => setIsCreating(true)}
                style={{ marginTop: '20px', padding: '8px 16px', fontSize: '13px', borderRadius: '6px' }}
              >
                <Plus size={14} style={{ marginRight: '6px' }} />
                {t('addMemory')}
              </button>
            </div>
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
                gap: '16px',
              }}
            >
              {memories.map(mem => {
                const catColor = getCategoryColor(mem.category);
                const isSelected = activeMemory?.id === mem.id;

                return (
                  <div
                    key={mem.id}
                    data-testid="memory-card"
                    onClick={() => setActiveMemory(mem)}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      backgroundColor: 'hsl(var(--card))',
                      borderRadius: '10px',
                      border: isSelected ? `2px solid ${catColor}` : '1px solid hsl(var(--border))',
                      padding: '16px',
                      cursor: 'pointer',
                      transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
                      boxShadow: isSelected ? '0 4px 12px rgba(0,0,0,0.08)' : 'none',
                    }}
                  >
                    <div>
                      {/* Card Top: Category + Confidence + Time */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: '12px',
                              fontSize: '11px',
                              fontWeight: 600,
                              textTransform: 'uppercase',
                              letterSpacing: '0.04em',
                              backgroundColor: `${catColor}1a`,
                              color: catColor,
                              border: `1px solid ${catColor}33`,
                            }}
                          >
                            {mem.category}
                          </span>
                          {mem.is_archived && (
                            <span
                              style={{
                                padding: '2px 6px',
                                borderRadius: '10px',
                                fontSize: '10px',
                                backgroundColor: 'hsl(var(--muted)/0.3)',
                                color: 'hsl(var(--muted-fg))',
                              }}
                            >
                              Archived
                            </span>
                          )}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                          <span title={`Confidence score: ${Math.round(mem.confidence * 100)}%`}>
                            {Math.round(mem.confidence * 100)}%
                          </span>
                          <span>•</span>
                          <span>{new Date(mem.created_at).toLocaleDateString()}</span>
                        </div>
                      </div>

                      {/* Summary */}
                      <h4
                        style={{
                          fontSize: '14px',
                          fontWeight: 600,
                          margin: '0 0 8px 0',
                          lineHeight: 1.4,
                          color: 'hsl(var(--fg))',
                        }}
                      >
                        {mem.summary}
                      </h4>

                      {/* Content excerpt */}
                      <p
                        style={{
                          fontSize: '12.5px',
                          color: 'hsl(var(--muted-fg))',
                          margin: '0 0 12px 0',
                          lineHeight: 1.5,
                          display: '-webkit-box',
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                      >
                        {mem.content}
                      </p>
                    </div>

                    {/* Card Bottom: Provenance Attribution & Tags */}
                    <div>
                      {/* Provenance Pill */}
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '6px 8px',
                          backgroundColor: 'hsl(var(--bg))',
                          borderRadius: '6px',
                          fontSize: '11px',
                          color: 'hsl(var(--muted-fg))',
                          marginBottom: '10px',
                          border: '1px solid hsl(var(--border)/0.5)',
                        }}
                      >
                        <ShieldCheck size={13} style={{ color: '#10b981', flexShrink: 0 }} />
                        <span style={{ fontWeight: 500, color: 'hsl(var(--fg))' }}>
                          {mem.provenance.source_entity}
                        </span>
                        {mem.provenance.author_agent && (
                          <>
                            <span>•</span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                              <Bot size={11} />
                              {mem.provenance.author_agent}
                            </span>
                          </>
                        )}
                        {mem.provenance.source_mission_id && (
                          <>
                            <span>•</span>
                            <span style={{ opacity: 0.8, fontFamily: 'monospace' }}>
                              {mem.provenance.source_mission_id.slice(0, 8)}
                            </span>
                          </>
                        )}
                      </div>

                      {/* Tags & Quick Actions */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                          {mem.tags.slice(0, 3).map((tag, idx) => (
                            <span
                              key={idx}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '3px',
                                fontSize: '10.5px',
                                padding: '1px 6px',
                                borderRadius: '4px',
                                backgroundColor: 'hsl(var(--muted)/0.2)',
                                color: 'hsl(var(--muted-fg))',
                              }}
                            >
                              <Tag size={9} />
                              {tag}
                            </span>
                          ))}
                          {mem.tags.length > 3 && (
                            <span style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))', alignSelf: 'center' }}>
                              +{mem.tags.length - 3}
                            </span>
                          )}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }} onClick={e => e.stopPropagation()}>
                          <Tooltip content={mem.is_archived ? 'Restore' : 'Archive'}>
                            <button
                              data-testid="btn-archive-memory"
                              className="btn btn-ghost"
                              onClick={() => handleToggleArchive(mem)}
                              style={{ padding: '4px', color: 'hsl(var(--muted-fg))' }}
                            >
                              {mem.is_archived ? <ArchiveRestore size={13} /> : <Archive size={13} />}
                            </button>
                          </Tooltip>
                          <Tooltip content="Delete">
                            <button
                              data-testid="btn-delete-memory"
                              className="btn btn-ghost"
                              onClick={() => handleDeleteMemory(mem)}
                              style={{ padding: '4px', color: '#f43f5e' }}
                            >
                              <Trash2 size={13} />
                            </button>
                          </Tooltip>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Slide-in Detail Drawer */}
        {activeMemory && (
          <div
            data-testid="memory-drawer"
            style={{
              width: '420px',
              borderLeft: '1px solid hsl(var(--border))',
              backgroundColor: 'hsl(var(--card))',
              display: 'flex',
              flexDirection: 'column',
              height: '100%',
              boxShadow: '-4px 0 20px rgba(0,0,0,0.06)',
              overflowY: 'auto',
              zIndex: 10,
            }}
          >
            {/* Drawer Header */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '16px 20px',
                borderBottom: '1px solid hsl(var(--border))',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span
                  style={{
                    padding: '3px 8px',
                    borderRadius: '12px',
                    fontSize: '11px',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    backgroundColor: `${getCategoryColor(activeMemory.category)}1a`,
                    color: getCategoryColor(activeMemory.category),
                  }}
                >
                  {activeMemory.category}
                </span>
                <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                  {activeMemory.id.slice(0, 12)}
                </span>
              </div>
              <button
                className="btn btn-ghost"
                onClick={() => setActiveMemory(null)}
                style={{ padding: '4px', borderRadius: '4px' }}
              >
                <X size={16} />
              </button>
            </div>

            {/* Drawer Content */}
            <div style={{ padding: '20px', flex: 1 }}>
              <h3 style={{ fontSize: '16px', fontWeight: 600, margin: '0 0 12px 0', lineHeight: 1.4 }}>
                {activeMemory.summary}
              </h3>

              <div
                style={{
                  fontSize: '13px',
                  lineHeight: 1.6,
                  color: 'hsl(var(--fg))',
                  padding: '14px',
                  backgroundColor: 'hsl(var(--bg))',
                  borderRadius: '8px',
                  border: '1px solid hsl(var(--border))',
                  whiteSpace: 'pre-wrap',
                  marginBottom: '20px',
                }}
              >
                {activeMemory.content}
              </div>

              {/* Provenance Audit Section */}
              <div style={{ marginBottom: '24px' }}>
                <h4
                  style={{
                    fontSize: '12px',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    color: 'hsl(var(--muted-fg))',
                    margin: '0 0 10px 0',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <ShieldCheck size={14} style={{ color: '#10b981' }} />
                  Provenance & Attribution
                </h4>

                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                    padding: '12px',
                    backgroundColor: 'hsl(var(--bg))',
                    borderRadius: '8px',
                    border: '1px solid hsl(var(--border))',
                    fontSize: '12px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--muted-fg))' }}>Source Entity:</span>
                    <span style={{ fontWeight: 500 }}>{activeMemory.provenance.source_entity}</span>
                  </div>

                  {activeMemory.provenance.author_agent && (
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'hsl(var(--muted-fg))' }}>Author Agent:</span>
                      <span style={{ fontWeight: 500, display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Bot size={12} />
                        {activeMemory.provenance.author_agent}
                      </span>
                    </div>
                  )}

                  {activeMemory.provenance.source_mission_id && (
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'hsl(var(--muted-fg))' }}>Mission ID:</span>
                      <span style={{ fontFamily: 'monospace', fontSize: '11px' }}>
                        {activeMemory.provenance.source_mission_id}
                      </span>
                    </div>
                  )}

                  {activeMemory.provenance.source_execution_id && (
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'hsl(var(--muted-fg))' }}>Execution ID:</span>
                      <span style={{ fontFamily: 'monospace', fontSize: '11px' }}>
                        {activeMemory.provenance.source_execution_id}
                      </span>
                    </div>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--muted-fg))' }}>Verification:</span>
                    <span
                      style={{
                        padding: '1px 6px',
                        borderRadius: '4px',
                        fontSize: '10.5px',
                        fontWeight: 600,
                        backgroundColor: 'rgba(16, 185, 129, 0.15)',
                        color: '#10b981',
                      }}
                    >
                      {activeMemory.provenance.verification_status.toUpperCase()}
                    </span>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--muted-fg))' }}>Confidence:</span>
                    <span style={{ fontWeight: 500 }}>{Math.round(activeMemory.confidence * 100)}%</span>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'hsl(var(--muted-fg))' }}>Recorded At:</span>
                    <span>{new Date(activeMemory.created_at).toLocaleString()}</span>
                  </div>
                </div>
              </div>

              {/* Tags Section */}
              <div style={{ marginBottom: '24px' }}>
                <h4
                  style={{
                    fontSize: '12px',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    color: 'hsl(var(--muted-fg))',
                    margin: '0 0 10px 0',
                  }}
                >
                  Tags
                </h4>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  {activeMemory.tags.map((tag, idx) => (
                    <span
                      key={idx}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontSize: '11px',
                        padding: '3px 8px',
                        borderRadius: '6px',
                        backgroundColor: 'hsl(var(--muted)/0.25)',
                        color: 'hsl(var(--fg))',
                      }}
                    >
                      <Tag size={11} />
                      {tag}
                    </span>
                  ))}
                  {activeMemory.tags.length === 0 && (
                    <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', fontStyle: 'italic' }}>
                      No tags assigned
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Drawer Footer Actions */}
            <div
              style={{
                padding: '16px 20px',
                borderTop: '1px solid hsl(var(--border))',
                display: 'flex',
                justifyContent: 'space-between',
                gap: '8px',
              }}
            >
              <button
                className="btn btn-ghost"
                onClick={() => handleToggleArchive(activeMemory)}
                style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                {activeMemory.is_archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}
                {activeMemory.is_archived ? 'Restore' : 'Archive'}
              </button>

              <button
                className="btn btn-ghost"
                onClick={() => handleDeleteMemory(activeMemory)}
                style={{ fontSize: '12px', color: '#f43f5e', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Trash2 size={14} />
                Delete
              </button>
            </div>
          </div>
        )}

        {/* Record Memory Modal */}
        {isCreating && (
          <div
            style={{
              position: 'fixed',
              inset: 0,
              backgroundColor: 'rgba(0, 0, 0, 0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 50,
              padding: '20px',
            }}
          >
            <div
              style={{
                backgroundColor: 'hsl(var(--card))',
                borderRadius: '12px',
                border: '1px solid hsl(var(--border))',
                width: '100%',
                maxWidth: '540px',
                boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '16px 20px',
                  borderBottom: '1px solid hsl(var(--border))',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Brain size={18} style={{ color: '#3b82f6' }} />
                  <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0 }}>
                    {t('newMemoryTitle')}
                  </h3>
                </div>
                <button
                  className="btn btn-ghost"
                  onClick={() => setIsCreating(false)}
                  style={{ padding: '4px' }}
                >
                  <X size={16} />
                </button>
              </div>

              <form onSubmit={handleCreateMemory} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '6px' }}>
                    {t('memoryCategory')}
                  </label>
                  <select
                    className="form-input"
                    value={newCategory}
                    onChange={e => setNewCategory(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      fontSize: '13px',
                      borderRadius: '6px',
                      border: '1px solid hsl(var(--border))',
                      backgroundColor: 'hsl(var(--bg))',
                      color: 'hsl(var(--fg))',
                    }}
                  >
                    {CATEGORIES.filter(c => c.key !== 'all').map(c => (
                      <option key={c.key} value={c.key}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '6px' }}>
                    {t('memorySummary')} *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="Brief statement or finding..."
                    value={newSummary}
                    onChange={e => setNewSummary(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: '13px',
                      borderRadius: '6px',
                      border: '1px solid hsl(var(--border))',
                      backgroundColor: 'hsl(var(--bg))',
                      color: 'hsl(var(--fg))',
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '6px' }}>
                    {t('memoryContent')} *
                  </label>
                  <textarea
                    required
                    rows={4}
                    placeholder="Detailed explanation, constraints, decisions, or verified facts..."
                    value={newContent}
                    onChange={e => setNewContent(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: '13px',
                      borderRadius: '6px',
                      border: '1px solid hsl(var(--border))',
                      backgroundColor: 'hsl(var(--bg))',
                      color: 'hsl(var(--fg))',
                      resize: 'vertical',
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '6px' }}>
                    {t('memoryTags')}
                  </label>
                  <input
                    type="text"
                    placeholder="frontend, architecture, auth, latency..."
                    value={newTags}
                    onChange={e => setNewTags(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: '13px',
                      borderRadius: '6px',
                      border: '1px solid hsl(var(--border))',
                      backgroundColor: 'hsl(var(--bg))',
                      color: 'hsl(var(--fg))',
                    }}
                  />
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 500 }}>
                      {t('memoryConfidence')}
                    </label>
                    <span style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                      {Math.round(newConfidence * 100)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0.1"
                    max="1.0"
                    step="0.05"
                    value={newConfidence}
                    onChange={e => setNewConfidence(parseFloat(e.target.value))}
                    style={{ width: '100%' }}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '10px' }}>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setIsCreating(false)}
                    style={{ padding: '8px 14px', fontSize: '13px', borderRadius: '6px' }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={submitting}
                    style={{ padding: '8px 16px', fontSize: '13px', borderRadius: '6px' }}
                  >
                    {submitting ? 'Recording...' : 'Save Memory'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
