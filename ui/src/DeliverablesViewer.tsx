import React, { useState, useEffect } from 'react';
import {
  X,
  FileText,
  FileCode,
  Table,
  FolderArchive,
  Download,
  ExternalLink,
  FolderOpen,
  Copy,
  Check,
  CheckCircle2,
  XCircle,
  Clock,
  Sparkles,
  Info,
  ShieldCheck,
  Users,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { useTranslation } from './i18n';

export interface DeliverableItem {
  id: string;
  mission_id: string;
  execution_id?: string | null;
  milestone_id?: string | null;
  name: string;
  path: string;
  type: string;
  size_bytes: number;
  status: string;
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface DeliverablePreviewData {
  deliverable_id: string;
  mission_id: string;
  execution_id: string | null;
  name: string;
  path: string;
  type: string;
  format: 'markdown' | 'json' | 'csv' | 'code' | 'text' | 'binary' | string;
  size_bytes: number;
  content: string | null;
  preview_available: boolean;
  truncated: boolean;
  message: string | null;
}

export interface VerificationCheck {
  id: string;
  name: string;
  passed: boolean;
  reason: string;
  score: number | null;
}

export interface Contributor {
  name: string;
  role: string;
  contribution_type: string;
}

export interface EvidenceItem {
  category: string;
  title: string;
  detail: string;
  timestamp: string | null;
}

export interface VerificationSummary {
  status: string;
  reviewer_agent: string | null;
  quality_score: number | null;
  verified_at: string | null;
  checks: VerificationCheck[];
  redlines: string[];
}

export interface ExplainCardData {
  deliverable_id: string;
  deliverable_name: string;
  mission_id: string;
  execution_id: string | null;
  run_number: number | null;
  result: string;
  evidence: EvidenceItem[];
  contributors: Contributor[];
  verification: VerificationSummary;
  decision: string;
  limitations: string[];
}

export interface MissionExplainSummaryData {
  mission_id: string;
  mission_title: string;
  mission_objective: string;
  execution_id: string | null;
  run_number: number | null;
  status: string;
  result: string;
  evidence: EvidenceItem[];
  contributors: Contributor[];
  verification: VerificationSummary;
  decision: string;
  limitations: string[];
}

interface DeliverablesViewerProps {
  deliverable: DeliverableItem | null;
  missionId: string;
  apiUrl: (path: string) => string;
  initialTab?: 'preview' | 'explain';
  onClose: () => void;
  onOpen: (deliverableId: string, reveal?: boolean) => void;
  onDownload: (deliverableId: string, filename: string) => void;
  onCopyPath: (deliverableId: string, path: string) => void;
  copiedPathId: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export const DeliverableDossierViewerModal: React.FC<DeliverablesViewerProps> = ({
  deliverable,
  missionId,
  apiUrl,
  initialTab = 'preview',
  onClose,
  onOpen,
  onDownload,
  onCopyPath,
  copiedPathId,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'preview' | 'explain'>(initialTab);
  const [previewData, setPreviewData] = useState<DeliverablePreviewData | null>(null);
  const [explainData, setExplainData] = useState<ExplainCardData | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [loadingExplain, setLoadingExplain] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [explainError, setExplainError] = useState<string | null>(null);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  // Load Preview Data
  useEffect(() => {
    if (!deliverable) return;
    let isMounted = true;
    setLoadingPreview(true);
    setPreviewError(null);

    fetch(apiUrl(`/api/missions/${missionId}/deliverables/${deliverable.id}/preview`))
      .then(async res => {
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.detail || `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((data: DeliverablePreviewData) => {
        if (isMounted) {
          setPreviewData(data);
          setLoadingPreview(false);
        }
      })
      .catch(err => {
        if (isMounted) {
          setPreviewError(err.message || 'Failed to load preview');
          setLoadingPreview(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [deliverable?.id, missionId, apiUrl]);

  // Load Explain Data
  useEffect(() => {
    if (!deliverable) return;
    let isMounted = true;
    setLoadingExplain(true);
    setExplainError(null);

    fetch(apiUrl(`/api/missions/${missionId}/deliverables/${deliverable.id}/explain`))
      .then(async res => {
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.detail || `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((data: ExplainCardData) => {
        if (isMounted) {
          setExplainData(data);
          setLoadingExplain(false);
        }
      })
      .catch(err => {
        if (isMounted) {
          setExplainError(err.message || 'Failed to load explanation');
          setLoadingExplain(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [deliverable?.id, missionId, apiUrl]);

  if (!deliverable) return null;

  const renderTypeIcon = () => {
    switch (deliverable.type) {
      case 'code':
        return <FileCode size={20} className="text-sky-500" />;
      case 'data':
        return <Table size={20} className="text-amber-500" />;
      case 'archive':
        return <FolderArchive size={20} className="text-purple-500" />;
      default:
        return <FileText size={20} className="text-primary" />;
    }
  };

  const renderStatusBadge = () => {
    switch (deliverable.status) {
      case 'verified':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '6px',
              fontSize: '11px',
              fontWeight: 700,
              backgroundColor: 'rgba(16, 185, 129, 0.15)',
              color: '#10b981',
              textTransform: 'uppercase',
            }}
          >
            <CheckCircle2 size={12} />
            {t('deliverableStatusVerified')}
          </span>
        );
      case 'needs_revision':
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '6px',
              fontSize: '11px',
              fontWeight: 700,
              backgroundColor: 'rgba(239, 68, 68, 0.15)',
              color: '#ef4444',
              textTransform: 'uppercase',
            }}
          >
            <XCircle size={12} />
            {t('deliverableStatusNeedsRevision')}
          </span>
        );
      default:
        return (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              borderRadius: '6px',
              fontSize: '11px',
              fontWeight: 700,
              backgroundColor: 'hsl(var(--muted))',
              color: 'hsl(var(--muted-fg))',
              textTransform: 'uppercase',
            }}
          >
            <Clock size={12} />
            {t('deliverableStatusDraft')}
          </span>
        );
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(4px)',
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
      onClick={onClose}
    >
      <div
        className="deliverable-viewer-modal"
        style={{
          width: '100%',
          maxWidth: '940px',
          maxHeight: '90vh',
          backgroundColor: 'hsl(var(--card))',
          borderRadius: '12px',
          border: '1px solid hsl(var(--border))',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.25)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid hsl(var(--border))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'hsl(var(--bg))',
            gap: '16px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '8px',
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              {renderTypeIcon()}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <h3
                  style={{
                    fontSize: '15px',
                    fontWeight: 700,
                    color: 'hsl(var(--fg))',
                    margin: 0,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={deliverable.name}
                >
                  {deliverable.name}
                </h3>
                {renderStatusBadge()}
                {explainData?.run_number && (
                  <span
                    style={{
                      fontSize: '10px',
                      padding: '1px 6px',
                      borderRadius: '4px',
                      backgroundColor: 'rgba(168, 85, 247, 0.15)',
                      color: '#c084fc',
                      fontWeight: 600,
                    }}
                  >
                    Run #{explainData.run_number}
                  </span>
                )}
              </div>
              <div
                style={{
                  fontSize: '12px',
                  color: 'hsl(var(--muted-fg))',
                  marginTop: '2px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <span>{formatBytes(previewData?.size_bytes || deliverable.size_bytes)}</span>
                <span>•</span>
                <span style={{ textTransform: 'capitalize' }}>{deliverable.type}</span>
                {previewData?.format && previewData.format !== deliverable.type && (
                  <>
                    <span>•</span>
                    <span style={{ textTransform: 'uppercase', fontSize: '10px', opacity: 0.8 }}>
                      {previewData.format}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              onClick={() => onOpen(deliverable.id, false)}
              className="btn btn-ghost"
              style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', padding: '6px 10px' }}
              title={t('deliverableActionOpenTooltip')}
            >
              <ExternalLink size={14} className="text-primary" />
              <span className="hidden sm:inline">{t('deliverableActionOpen')}</span>
            </button>

            <button
              onClick={() => onOpen(deliverable.id, true)}
              className="btn btn-ghost"
              style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', padding: '6px 10px' }}
              title={t('deliverableActionRevealTooltip')}
            >
              <FolderOpen size={14} />
              <span className="hidden sm:inline">{t('deliverableActionReveal')}</span>
            </button>

            <button
              onClick={() => onDownload(deliverable.id, deliverable.name)}
              className="btn btn-ghost"
              style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', padding: '6px 10px' }}
              title={t('deliverableActionDownloadTooltip')}
            >
              <Download size={14} />
              <span className="hidden sm:inline">{t('deliverableActionDownload')}</span>
            </button>

            <button
              onClick={() => onCopyPath(deliverable.id, deliverable.path)}
              className="btn btn-ghost"
              style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', padding: '6px 10px' }}
              title={t('deliverableActionCopyPath')}
            >
              {copiedPathId === deliverable.id ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
            </button>

            <div style={{ width: '1px', height: '18px', backgroundColor: 'hsl(var(--border))', margin: '0 4px' }} />

            <button
              onClick={onClose}
              className="btn btn-ghost"
              aria-label="Close Preview"
              data-testid="close-preview-modal-btn"
              style={{ padding: '6px' }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div
          style={{
            display: 'flex',
            borderBottom: '1px solid hsl(var(--border))',
            backgroundColor: 'hsl(var(--bg))',
            padding: '0 20px',
            gap: '8px',
          }}
        >
          <button
            onClick={() => setActiveTab('preview')}
            data-testid="tab-preview"
            style={{
              padding: '10px 16px',
              fontSize: '12px',
              fontWeight: 600,
              color: activeTab === 'preview' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              border: 'none',
              background: 'none',
              borderBottom: activeTab === 'preview' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <FileText size={14} />
            <span>{t('tabPreview')}</span>
          </button>

          <button
            onClick={() => setActiveTab('explain')}
            data-testid="tab-explain"
            style={{
              padding: '10px 16px',
              fontSize: '12px',
              fontWeight: 600,
              color: activeTab === 'explain' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              border: 'none',
              background: 'none',
              borderBottom: activeTab === 'explain' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Sparkles size={14} className="text-primary" />
            <span>{t('tabExplain')}</span>
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column' }}>
          {activeTab === 'preview' && (
            <DeliverableContentPreview
              data={previewData}
              loading={loadingPreview}
              error={previewError}
              deliverable={deliverable}
              onOpen={() => onOpen(deliverable.id, false)}
              onDownload={() => onDownload(deliverable.id, deliverable.name)}
            />
          )}

          {activeTab === 'explain' && (
            <DeliverableExplainCardView
              data={explainData}
              loading={loadingExplain}
              error={explainError}
              deliverable={deliverable}
            />
          )}
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 1. Deliverable Content Preview Renderer
// ---------------------------------------------------------------------------

interface ContentPreviewProps {
  data: DeliverablePreviewData | null;
  loading: boolean;
  error: string | null;
  deliverable: DeliverableItem;
  onOpen: () => void;
  onDownload: () => void;
}

const DeliverableContentPreview: React.FC<ContentPreviewProps> = ({
  data,
  loading,
  error,
  deliverable,
  onOpen,
  onDownload,
}) => {
  const { t } = useTranslation();

  if (loading) {
    return (
      <div style={{ padding: '60px 20px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
        <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 12px' }} />
        <div style={{ fontSize: '13px' }}>{t('previewLoading')}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          padding: '24px',
          borderRadius: '8px',
          backgroundColor: 'rgba(239, 68, 68, 0.08)',
          border: '1px solid rgba(239, 68, 68, 0.25)',
          color: '#ef4444',
          textAlign: 'center',
        }}
      >
        <AlertTriangle size={24} style={{ margin: '0 auto 8px' }} />
        <div style={{ fontWeight: 600, fontSize: '14px' }}>{error}</div>
        <div style={{ marginTop: '14px', display: 'flex', gap: '8px', justifyContent: 'center' }}>
          <button onClick={onOpen} className="btn btn-outline" style={{ fontSize: '12px', padding: '6px 14px' }}>
            {t('deliverableActionOpen')}
          </button>
          <button onClick={onDownload} className="btn btn-primary" style={{ fontSize: '12px', padding: '6px 14px' }}>
            {t('deliverableActionDownload')}
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  // Unsupported or Binary
  if (!data.preview_available || data.format === 'binary') {
    return (
      <div
        style={{
          padding: '40px 20px',
          borderRadius: '10px',
          border: '1px dashed hsl(var(--border))',
          backgroundColor: 'hsl(var(--bg))',
          textAlign: 'center',
          color: 'hsl(var(--muted-fg))',
        }}
      >
        <FolderArchive size={36} style={{ margin: '0 auto 14px', opacity: 0.4 }} />
        <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'hsl(var(--fg))', margin: 0 }}>
          {data.message || t('previewUnavailable')}
        </h4>
        <p style={{ fontSize: '12px', maxWidth: '440px', margin: '8px auto 20px' }}>
          {data.truncated ? t('previewTruncatedNotice') : t('deliverablesPlaceholderDesc')}
        </p>
        <div style={{ display: 'flex', gap: '10px', justifyContent: 'center' }}>
          <button onClick={onOpen} className="btn btn-outline" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <ExternalLink size={14} />
            <span>{t('deliverableActionOpen')}</span>
          </button>
          <button onClick={onDownload} className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Download size={14} />
            <span>{t('deliverableActionDownload')}</span>
          </button>
        </div>
      </div>
    );
  }

  const content = data.content || '';

  // Render by format
  if (data.format === 'markdown') {
    return <MarkdownViewer content={content} />;
  }

  if (data.format === 'json') {
    return <JsonViewer content={content} />;
  }

  if (data.format === 'csv') {
    return <CsvViewer content={content} />;
  }

  if (data.format === 'code') {
    return <CodeViewer content={content} filename={deliverable.name} />;
  }

  // Plain text fallback
  return (
    <pre
      style={{
        margin: 0,
        padding: '16px',
        borderRadius: '8px',
        backgroundColor: 'hsl(var(--bg))',
        border: '1px solid hsl(var(--border))',
        fontFamily: 'monospace',
        fontSize: '12px',
        lineHeight: 1.6,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        color: 'hsl(var(--fg))',
      }}
    >
      {content}
    </pre>
  );
};

// ---------------------------------------------------------------------------
// Format Viewers: Markdown, JSON, CSV, Code
// ---------------------------------------------------------------------------

const MarkdownViewer: React.FC<{ content: string }> = ({ content }) => {
  // Simple, safe Markdown tokenizer & renderer
  const lines = content.split('\n');

  return (
    <div
      className="markdown-rendered-view"
      style={{
        fontSize: '13px',
        lineHeight: 1.7,
        color: 'hsl(var(--fg))',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
      }}
    >
      {lines.map((line, idx) => {
        const trimmed = line.trim();

        if (trimmed.startsWith('# ')) {
          return (
            <h1 key={idx} style={{ fontSize: '20px', fontWeight: 800, margin: '14px 0 6px', color: 'hsl(var(--fg))' }}>
              {trimmed.substring(2)}
            </h1>
          );
        }
        if (trimmed.startsWith('## ')) {
          return (
            <h2 key={idx} style={{ fontSize: '16px', fontWeight: 700, margin: '12px 0 4px', color: 'hsl(var(--fg))' }}>
              {trimmed.substring(3)}
            </h2>
          );
        }
        if (trimmed.startsWith('### ')) {
          return (
            <h3 key={idx} style={{ fontSize: '14px', fontWeight: 600, margin: '10px 0 4px', color: 'hsl(var(--fg))' }}>
              {trimmed.substring(4)}
            </h3>
          );
        }
        if (trimmed.startsWith('> ')) {
          return (
            <blockquote
              key={idx}
              style={{
                margin: '4px 0',
                padding: '6px 12px',
                borderLeft: '3px solid hsl(var(--primary))',
                backgroundColor: 'hsl(var(--primary) / 0.05)',
                borderRadius: '0 4px 4px 0',
                color: 'hsl(var(--muted-fg))',
                fontStyle: 'italic',
              }}
            >
              {trimmed.substring(2)}
            </blockquote>
          );
        }
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
          return (
            <div key={idx} style={{ display: 'flex', gap: '8px', paddingLeft: '8px' }}>
              <span style={{ color: 'hsl(var(--primary))' }}>•</span>
              <span>{renderInlineMarkdown(trimmed.substring(2))}</span>
            </div>
          );
        }
        if (/^\d+\.\s/.test(trimmed)) {
          const numMatch = trimmed.match(/^(\d+)\.\s(.*)$/);
          return (
            <div key={idx} style={{ display: 'flex', gap: '8px', paddingLeft: '8px' }}>
              <span style={{ color: 'hsl(var(--muted-fg))', fontWeight: 600 }}>{numMatch?.[1]}.</span>
              <span>{renderInlineMarkdown(numMatch?.[2] || '')}</span>
            </div>
          );
        }
        if (trimmed.startsWith('```')) {
          return null; // code blocks can be rendered by pre
        }
        if (trimmed === '') {
          return <div key={idx} style={{ height: '4px' }} />;
        }

        return <p key={idx} style={{ margin: 0 }}>{renderInlineMarkdown(trimmed)}</p>;
      })}
    </div>
  );
};

function renderInlineMarkdown(text: string): React.ReactNode {
  // Matches **bold**, *italic*, `code`
  const parts = text.split(/(\*\*.*?\*\*|\*.*?\*|`.*?`)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} style={{ fontWeight: 700 }}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('*') && part.endsWith('*')) {
      return <em key={i} style={{ fontStyle: 'italic' }}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={i}
          style={{
            fontFamily: 'monospace',
            fontSize: '11px',
            padding: '1px 5px',
            borderRadius: '4px',
            backgroundColor: 'hsl(var(--muted))',
            color: 'hsl(var(--fg))',
          }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

const JsonViewer: React.FC<{ content: string }> = ({ content }) => {
  let parsed: any = null;
  let error = false;
  try {
    parsed = JSON.parse(content);
  } catch {
    error = true;
  }

  if (error || !parsed) {
    return (
      <pre
        style={{
          margin: 0,
          padding: '16px',
          borderRadius: '8px',
          backgroundColor: 'hsl(var(--bg))',
          fontFamily: 'monospace',
          fontSize: '12px',
          color: 'hsl(var(--fg))',
        }}
      >
        {content}
      </pre>
    );
  }

  const formatted = JSON.stringify(parsed, null, 2);

  return (
    <pre
      style={{
        margin: 0,
        padding: '16px',
        borderRadius: '8px',
        backgroundColor: 'hsl(var(--bg))',
        border: '1px solid hsl(var(--border))',
        fontFamily: 'monospace',
        fontSize: '12px',
        lineHeight: 1.6,
        overflowX: 'auto',
        color: 'hsl(var(--fg))',
      }}
    >
      <code>{formatted}</code>
    </pre>
  );
};

const CsvViewer: React.FC<{ content: string }> = ({ content }) => {
  const lines = content.trim().split('\n').filter(l => l.trim().length > 0);
  if (lines.length === 0) {
    return <div style={{ color: 'hsl(var(--muted-fg))', fontSize: '12px' }}>Empty CSV file.</div>;
  }

  const parseRow = (line: string) => {
    // Simple CSV parser supporting quotes
    const regex = /(?:,|\n|^)("(?:(?:"")*[^"]*)*"|[^",\n]*|(?:\n|$))/g;
    const matches: string[] = [];
    let match;
    while ((match = regex.exec(line)) !== null) {
      if (match.index === regex.lastIndex) regex.lastIndex++;
      let val = match[1] ?? '';
      if (val.startsWith('"') && val.endsWith('"')) {
        val = val.slice(1, -1).replace(/""/g, '"');
      }
      matches.push(val);
      if (regex.lastIndex >= line.length) break;
    }
    return matches;
  };

  const headers = parseRow(lines[0]);
  const rows = lines.slice(1).map(parseRow);

  return (
    <div
      style={{
        overflowX: 'auto',
        borderRadius: '8px',
        border: '1px solid hsl(var(--border))',
        backgroundColor: 'hsl(var(--bg))',
      }}
    >
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
        <thead>
          <tr style={{ backgroundColor: 'hsl(var(--card))', borderBottom: '2px solid hsl(var(--border))' }}>
            {headers.map((h, i) => (
              <th
                key={i}
                style={{
                  padding: '10px 14px',
                  fontWeight: 600,
                  color: 'hsl(var(--fg))',
                  whiteSpace: 'nowrap',
                }}
              >
                {h || `Col ${i + 1}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rIdx) => (
            <tr
              key={rIdx}
              style={{
                borderBottom: '1px solid hsl(var(--border))',
                backgroundColor: rIdx % 2 === 0 ? 'transparent' : 'hsl(var(--card) / 0.5)',
              }}
            >
              {row.map((cell, cIdx) => (
                <td
                  key={cIdx}
                  style={{
                    padding: '8px 14px',
                    color: 'hsl(var(--fg))',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const CodeViewer: React.FC<{ content: string; filename: string }> = ({ content, filename }) => {
  const lines = content.split('\n');

  return (
    <div
      style={{
        borderRadius: '8px',
        border: '1px solid hsl(var(--border))',
        backgroundColor: 'hsl(var(--bg))',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          padding: '8px 14px',
          borderBottom: '1px solid hsl(var(--border))',
          backgroundColor: 'hsl(var(--card))',
          fontSize: '11px',
          fontWeight: 600,
          color: 'hsl(var(--muted-fg))',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>{filename}</span>
        <span>{lines.length} lines</span>
      </div>
      <div style={{ overflowX: 'auto', display: 'flex', padding: '12px 0' }}>
        <div
          style={{
            userSelect: 'none',
            padding: '0 12px',
            textAlign: 'right',
            color: 'hsl(var(--muted-fg))',
            opacity: 0.5,
            fontFamily: 'monospace',
            fontSize: '12px',
            lineHeight: 1.6,
            borderRight: '1px solid hsl(var(--border))',
          }}
        >
          {lines.map((_, i) => (
            <div key={i}>{i + 1}</div>
          ))}
        </div>
        <pre
          style={{
            margin: 0,
            padding: '0 16px',
            fontFamily: 'monospace',
            fontSize: '12px',
            lineHeight: 1.6,
            color: 'hsl(var(--fg))',
          }}
        >
          <code>{content}</code>
        </pre>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 2. Aether Explain Card View (Deliverable Level)
// ---------------------------------------------------------------------------

interface ExplainCardProps {
  data: ExplainCardData | null;
  loading: boolean;
  error: string | null;
  deliverable: DeliverableItem;
}

const DeliverableExplainCardView: React.FC<ExplainCardProps> = ({
  data,
  loading,
  error,
}) => {
  const { t } = useTranslation();

  if (loading) {
    return (
      <div style={{ padding: '60px 20px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
        <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 12px' }} />
        <div style={{ fontSize: '13px' }}>{t('explainLoading')}</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div
        style={{
          padding: '24px',
          borderRadius: '8px',
          backgroundColor: 'rgba(239, 68, 68, 0.08)',
          border: '1px solid rgba(239, 68, 68, 0.25)',
          color: '#ef4444',
          textAlign: 'center',
        }}
      >
        <AlertTriangle size={24} style={{ margin: '0 auto 8px' }} />
        <div style={{ fontWeight: 600, fontSize: '14px' }}>{error || 'Explanation unavailable'}</div>
      </div>
    );
  }

  return (
    <div className="aether-explain-card" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* 1. Result Statement */}
      <div
        style={{
          padding: '16px 18px',
          borderRadius: '10px',
          backgroundColor: 'hsl(var(--primary) / 0.08)',
          border: '1px solid hsl(var(--primary) / 0.25)',
          display: 'flex',
          gap: '12px',
          alignItems: 'flex-start',
        }}
      >
        <Sparkles size={20} className="text-primary" style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: 'hsl(var(--primary))' }}>
            {t('explainResultHeader')}
          </div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'hsl(var(--fg))', marginTop: '3px' }}>
            {data.result}
          </div>
        </div>
      </div>

      {/* 2. Verification & Quality Gate */}
      <div
        style={{
          padding: '16px 18px',
          borderRadius: '10px',
          backgroundColor: 'hsl(var(--bg))',
          border: '1px solid hsl(var(--border))',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldCheck size={18} className="text-emerald-500" />
            <h4 style={{ fontSize: '13px', fontWeight: 700, color: 'hsl(var(--fg))', margin: 0 }}>
              {t('explainVerificationHeader')}
            </h4>
          </div>

          {data.verification.quality_score !== null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>{t('explainQualityScore')}:</span>
              <span
                style={{
                  fontSize: '13px',
                  fontWeight: 800,
                  padding: '2px 8px',
                  borderRadius: '6px',
                  backgroundColor: data.verification.quality_score >= 80 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                  color: data.verification.quality_score >= 80 ? '#10b981' : '#f59e0b',
                }}
              >
                {data.verification.quality_score}/100
              </span>
            </div>
          )}
        </div>

        {data.verification.reviewer_agent && (
          <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
            {t('qualityGateReviewer')}: <strong style={{ color: 'hsl(var(--fg))' }}>{data.verification.reviewer_agent}</strong>
          </div>
        )}

        {/* Checks Checklist */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px' }}>
          {data.verification.checks.map(check => (
            <div
              key={check.id}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '10px',
                padding: '8px 12px',
                borderRadius: '6px',
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                fontSize: '12px',
              }}
            >
              {check.passed ? (
                <CheckCircle2 size={16} className="text-emerald-500" style={{ flexShrink: 0, marginTop: '1px' }} />
              ) : (
                <XCircle size={16} className="text-rose-500" style={{ flexShrink: 0, marginTop: '1px' }} />
              )}
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, color: 'hsl(var(--fg))' }}>{check.name}</div>
                <div style={{ color: 'hsl(var(--muted-fg))', marginTop: '2px', fontSize: '11px' }}>{check.reason}</div>
              </div>
              {check.score !== null && (
                <span style={{ fontSize: '11px', fontWeight: 600, color: 'hsl(var(--muted-fg))' }}>
                  {check.score}%
                </span>
              )}
            </div>
          ))}
        </div>

        {/* Redlines if any */}
        {data.verification.redlines.length > 0 && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: '6px',
              backgroundColor: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              fontSize: '12px',
            }}
          >
            <div style={{ fontWeight: 700, color: '#ef4444', marginBottom: '4px' }}>
              {t('qualityGateRedlines')}:
            </div>
            <ul style={{ margin: 0, paddingLeft: '16px', color: 'hsl(var(--fg))' }}>
              {data.verification.redlines.map((rl, i) => (
                <li key={i}>{rl}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* 3. Observable Evidence */}
      <div
        style={{
          padding: '16px 18px',
          borderRadius: '10px',
          backgroundColor: 'hsl(var(--bg))',
          border: '1px solid hsl(var(--border))',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <FileText size={18} className="text-primary" />
          <h4 style={{ fontSize: '13px', fontWeight: 700, color: 'hsl(var(--fg))', margin: 0 }}>
            {t('explainEvidenceHeader')}
          </h4>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {data.evidence.map((ev, i) => (
            <div
              key={i}
              style={{
                padding: '8px 12px',
                borderRadius: '6px',
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                fontSize: '12px',
              }}
            >
              <div style={{ fontWeight: 600, color: 'hsl(var(--fg))' }}>{ev.title}</div>
              <div style={{ color: 'hsl(var(--muted-fg))', marginTop: '2px', fontSize: '11px' }}>{ev.detail}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 4. Contributors */}
      <div
        style={{
          padding: '16px 18px',
          borderRadius: '10px',
          backgroundColor: 'hsl(var(--bg))',
          border: '1px solid hsl(var(--border))',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Users size={18} className="text-sky-500" />
          <h4 style={{ fontSize: '13px', fontWeight: 700, color: 'hsl(var(--fg))', margin: 0 }}>
            {t('explainContributorsHeader')}
          </h4>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {data.contributors.map((c, i) => (
            <div
              key={i}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '12px',
              }}
            >
              <div
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: c.contribution_type === 'reviewer' ? '#10b981' : '#3b82f6',
                }}
              />
              <span style={{ fontWeight: 600, color: 'hsl(var(--fg))' }}>{c.name}</span>
              <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>({c.role})</span>
            </div>
          ))}
        </div>
      </div>

      {/* 5. Conclusion & Decision */}
      <div
        style={{
          padding: '14px 16px',
          borderRadius: '8px',
          backgroundColor: 'hsl(var(--card))',
          border: '1px solid hsl(var(--border))',
          fontSize: '12px',
        }}
      >
        <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: 'hsl(var(--muted-fg))', marginBottom: '4px' }}>
          {t('explainDecisionHeader')}
        </div>
        <div style={{ color: 'hsl(var(--fg))', lineHeight: 1.5 }}>
          {data.decision}
        </div>
      </div>

      {/* 6. Limitations & Transparency */}
      <div
        style={{
          padding: '12px 14px',
          borderRadius: '8px',
          backgroundColor: 'hsl(var(--muted) / 0.3)',
          border: '1px solid hsl(var(--border))',
          fontSize: '11px',
          color: 'hsl(var(--muted-fg))',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, textTransform: 'uppercase' }}>
          <Info size={13} />
          <span>{t('explainLimitationsHeader')}</span>
        </div>
        {data.limitations.map((lim, i) => (
          <div key={i}>• {lim}</div>
        ))}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 3. Mission-Level Explain Modal
// ---------------------------------------------------------------------------

interface MissionExplainModalProps {
  missionId: string;
  executionId?: string | null;
  apiUrl: (path: string) => string;
  onClose: () => void;
}

export const MissionExplainModal: React.FC<MissionExplainModalProps> = ({
  missionId,
  executionId,
  apiUrl,
  onClose,
}) => {
  const { t } = useTranslation();
  const [data, setData] = useState<MissionExplainSummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    const q = executionId ? `?execution_id=${encodeURIComponent(executionId)}` : '';
    fetch(apiUrl(`/api/missions/${missionId}/explain${q}`))
      .then(async res => {
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.detail || `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((resData: MissionExplainSummaryData) => {
        if (isMounted) {
          setData(resData);
          setLoading(false);
        }
      })
      .catch(err => {
        if (isMounted) {
          setError(err.message || 'Failed to load mission explanation');
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [missionId, executionId, apiUrl]);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(4px)',
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
      onClick={onClose}
    >
      <div
        className="mission-explain-modal"
        style={{
          width: '100%',
          maxWidth: '840px',
          maxHeight: '90vh',
          backgroundColor: 'hsl(var(--card))',
          borderRadius: '12px',
          border: '1px solid hsl(var(--border))',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.25)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid hsl(var(--border))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'hsl(var(--bg))',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Sparkles size={20} className="text-primary" />
            <div>
              <h3 style={{ fontSize: '15px', fontWeight: 700, color: 'hsl(var(--fg))', margin: 0 }}>
                {t('explainMissionOutcome')}
              </h3>
              <p style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', margin: '2px 0 0' }}>
                {t('explainMissionSubtitle')}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="btn btn-ghost"
            aria-label="Close Preview"
            data-testid="close-mission-explain-btn"
            style={{ padding: '6px' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
          {loading ? (
            <div style={{ padding: '60px 20px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
              <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 12px' }} />
              <div style={{ fontSize: '13px' }}>{t('explainLoading')}</div>
            </div>
          ) : error || !data ? (
            <div
              style={{
                padding: '24px',
                borderRadius: '8px',
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                color: '#ef4444',
                textAlign: 'center',
              }}
            >
              <AlertTriangle size={24} style={{ margin: '0 auto 8px' }} />
              <div style={{ fontWeight: 600, fontSize: '14px' }}>{error || 'Explanation unavailable'}</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {/* Outcome Result Banner */}
              <div
                style={{
                  padding: '16px 18px',
                  borderRadius: '10px',
                  backgroundColor: 'hsl(var(--primary) / 0.08)',
                  border: '1px solid hsl(var(--primary) / 0.25)',
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: 'hsl(var(--primary))' }}>
                  {t('explainResultHeader')}
                </div>
                <div style={{ fontSize: '14px', fontWeight: 600, color: 'hsl(var(--fg))', marginTop: '4px', lineHeight: 1.5 }}>
                  {data.result}
                </div>
              </div>

              {/* Verification & Quality Gate */}
              <div
                style={{
                  padding: '16px 18px',
                  borderRadius: '10px',
                  backgroundColor: 'hsl(var(--bg))',
                  border: '1px solid hsl(var(--border))',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <ShieldCheck size={18} className="text-emerald-500" />
                    <h4 style={{ fontSize: '13px', fontWeight: 700, color: 'hsl(var(--fg))', margin: 0 }}>
                      {t('explainVerificationHeader')}
                    </h4>
                  </div>
                  {data.verification.quality_score !== null && (
                    <span
                      style={{
                        fontSize: '13px',
                        fontWeight: 800,
                        padding: '2px 8px',
                        borderRadius: '6px',
                        backgroundColor: 'rgba(16, 185, 129, 0.15)',
                        color: '#10b981',
                      }}
                    >
                      {data.verification.quality_score}/100
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {data.verification.checks.map(check => (
                    <div
                      key={check.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 12px',
                        borderRadius: '6px',
                        backgroundColor: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        fontSize: '12px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {check.passed ? (
                          <CheckCircle2 size={15} className="text-emerald-500" />
                        ) : (
                          <XCircle size={15} className="text-rose-500" />
                        )}
                        <span style={{ fontWeight: 600, color: 'hsl(var(--fg))' }}>{check.name}</span>
                        <span style={{ color: 'hsl(var(--muted-fg))', fontSize: '11px' }}>({check.reason})</span>
                      </div>
                      {check.score !== null && (
                        <span style={{ fontWeight: 600, color: 'hsl(var(--muted-fg))', fontSize: '11px' }}>
                          {check.score}%
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Observable Evidence */}
              <div
                style={{
                  padding: '16px 18px',
                  borderRadius: '10px',
                  backgroundColor: 'hsl(var(--bg))',
                  border: '1px solid hsl(var(--border))',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <FileText size={18} className="text-primary" />
                  <h4 style={{ fontSize: '13px', fontWeight: 700, color: 'hsl(var(--fg))', margin: 0 }}>
                    {t('explainEvidenceHeader')}
                  </h4>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {data.evidence.map((ev, i) => (
                    <div
                      key={i}
                      style={{
                        padding: '8px 12px',
                        borderRadius: '6px',
                        backgroundColor: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        fontSize: '12px',
                      }}
                    >
                      <span style={{ fontWeight: 600, color: 'hsl(var(--fg))' }}>{ev.title}: </span>
                      <span style={{ color: 'hsl(var(--muted-fg))' }}>{ev.detail}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Contributors */}
              <div
                style={{
                  padding: '16px 18px',
                  borderRadius: '10px',
                  backgroundColor: 'hsl(var(--bg))',
                  border: '1px solid hsl(var(--border))',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Users size={18} className="text-sky-500" />
                  <h4 style={{ fontSize: '13px', fontWeight: 700, color: 'hsl(var(--fg))', margin: 0 }}>
                    {t('explainContributorsHeader')}
                  </h4>
                </div>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {data.contributors.map((c, i) => (
                    <div
                      key={i}
                      style={{
                        padding: '6px 12px',
                        borderRadius: '6px',
                        backgroundColor: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        fontSize: '12px',
                      }}
                    >
                      <strong style={{ color: 'hsl(var(--fg))' }}>{c.name}</strong>{' '}
                      <span style={{ color: 'hsl(var(--muted-fg))', fontSize: '11px' }}>({c.role})</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Decision */}
              <div
                style={{
                  padding: '14px 16px',
                  borderRadius: '8px',
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  fontSize: '12px',
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', color: 'hsl(var(--muted-fg))', marginBottom: '4px' }}>
                  {t('explainDecisionHeader')}
                </div>
                <div style={{ color: 'hsl(var(--fg))', lineHeight: 1.5 }}>{data.decision}</div>
              </div>

              {/* Limitations */}
              <div
                style={{
                  padding: '12px 14px',
                  borderRadius: '8px',
                  backgroundColor: 'hsl(var(--muted) / 0.3)',
                  border: '1px solid hsl(var(--border))',
                  fontSize: '11px',
                  color: 'hsl(var(--muted-fg))',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, textTransform: 'uppercase' }}>
                  <Info size={13} />
                  <span>{t('explainLimitationsHeader')}</span>
                </div>
                {data.limitations.map((lim, i) => (
                  <div key={i}>• {lim}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
