import { useState, useEffect, useContext, useMemo } from 'react';
import {
  FileText,
  FileCode,
  Table,
  FolderArchive,
  Download,
  FolderOpen,
  Eye,
  RefreshCw,
  Sparkles,
  FileCheck
} from 'lucide-react';
import { apiUrl } from './api';
import { ToastContext } from './toast';
import {
  PageContainer,
  Section,
  Stack,
  Grid,
  Panel,
  Heading,
  Button,
  SegmentedControl,
  StatusBadge,
  AetherInput,
  EmptyState,
  LoadingSpinner,
  Modal,
} from './design-system';
import { useTranslation } from './i18n';

// What the badge says must be what the backend knows: only a verified deliverable is "Verified"; a record whose file
// is empty or missing is never shown as ready.
function resultBadge(item: { status?: string; size_bytes: number; mission_id?: string; file_available?: boolean }, t: (key: any) => string): { status: string; label: string } {
  const st = (item.status || '').toLowerCase();
  if (item.file_available === false) return { status: 'error', label: t('syFileUnavailable') };
  if (st === 'verified') return { status: 'verified', label: t('syVerified') };
  if (st === 'needs_revision') return { status: 'configured', label: t('syToReview') };
  if (item.mission_id && !item.size_bytes) return { status: 'error', label: t('syFileUnavailable') };
  if (st === 'draft') return { status: 'connecting', label: t('syDraft') };
  return { status: 'connected', label: t('syReady') };   // a file Aether produced outside a mission
}

export interface ResultItem {
  id: string;
  mission_id?: string;
  name: string;
  path: string;
  type: string;
  size_bytes: number;
  status?: string;
  created_at?: string;
  mission_title?: string;
  preview_content?: string;
  file_available?: boolean;
}

interface ResultsViewProps {
  navigate?: (view: string, params?: any) => void;
}

export function ResultsView({ navigate }: ResultsViewProps) {
  const { t } = useTranslation();
  const [results, setResults] = useState<ResultItem[]>([]);
  // Records of attempts that left no file: kept as history, never offered as results.
  const [attempts, setAttempts] = useState<ResultItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<'all' | 'documents' | 'code' | 'data' | 'other'>('all');
  
  // Preview modal state
  const [previewItem, setPreviewItem] = useState<ResultItem | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<{ content?: string; format?: string; message?: string } | null>(null);
  const [openingId, setOpeningId] = useState<string | null>(null);

  const showToast = useContext(ToastContext);

  const fetchResults = async () => {
    setLoading(true);
    try {
      // 1. Deliverables of missions: the only source with status, preview, download and "open" support.
      const items: ResultItem[] = [];
      const seenPaths = new Set<string>();
      const missionsRes = await fetch(apiUrl('/api/missions'));
      if (missionsRes.ok) {
        const missions = await missionsRes.json();
        if (Array.isArray(missions)) {
          const gathered = await Promise.all(missions.slice(0, 30).map(async (m: any) => {
            try {
              const delivRes = await fetch(apiUrl(`/api/missions/${m.id}/deliverables`));
              if (!delivRes.ok) return [];
              const delivs = await delivRes.json();
              return (Array.isArray(delivs) ? delivs : []).map((d: any) => ({
                ...d,
                mission_id: m.id,
                mission_title: m.title,
              }));
            } catch {
              return [];
            }
          }));
          for (const d of gathered.flat() as ResultItem[]) {
            items.push(d);
            if (d.path) seenPaths.add(d.path);
          }
        }
      }

      // 2. Files Aether produced outside a mission (documents created from chat, inbox, ...). The companion
      //    endpoint uses its own field names, so they are mapped to the shape of a result here.
      const res = await fetch(apiUrl('/api/personal/companion/deliverables?limit=60'));
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          for (const c of data) {
            if (!c.file_path || seenPaths.has(c.file_path)) continue;
            seenPaths.add(c.file_path);
            items.push({
              id: c.id,
              name: c.title || String(c.file_path).split('/').pop() || 'File',
              path: c.file_path,
              type: c.file_type || 'file',
              size_bytes: c.file_size_bytes || 0,
              created_at: c.created_at,
              mission_title: c.source === 'task' ? c.title : undefined,
            });
          }
        }
      }

      items.sort((x, y) => String(y.created_at || '').localeCompare(String(x.created_at || '')));
      setResults(items.filter((i) => i.file_available !== false));
      setAttempts(items.filter((i) => i.file_available === false));
    } catch (err) {
      console.error('Failed to load results', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchResults();
  }, []);

  const handleOpenPreview = async (item: ResultItem) => {
    setPreviewItem(item);
    setPreviewLoading(true);
    setPreviewData(null);
    try {
      if (item.mission_id) {
        const res = await fetch(apiUrl(`/api/missions/${item.mission_id}/deliverables/${item.id}/preview`));
        if (res.ok) {
          const data = await res.json();
          setPreviewData(data);
        } else {
          setPreviewData({ message: t('syPreviewNotAvailableForThisFile') });
        }
      } else if (item.path) {
        const res = await fetch(apiUrl(`/api/personal/companion/file/preview?path=${encodeURIComponent(item.path)}`));
        setPreviewData(res.ok ? await res.json() : { message: t('syPreviewNotAvailableForThisFile2') });
      } else {
        setPreviewData({ message: t('syPreviewNotAvailableForThisFile2') });
      }
    } catch {
      setPreviewData({ message: t('syCouldNotLoadThePreview') });
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleOpenFile = async (item: ResultItem) => {
    if (!item.mission_id) return;
    setOpeningId(item.id);
    try {
      const res = await fetch(apiUrl(`/api/missions/${item.mission_id}/deliverables/${item.id}/open`), {
        method: 'POST',
      });
      if (res.ok) {
        showToast?.(t('syFileOpenedOnYourSystem'), 'success');
      } else {
        showToast?.(t('syCouldNotOpenTheFileWith'), 'warning');
      }
    } catch {
      showToast?.(t('syErrorWhileOpeningTheFile'), 'error');
    } finally {
      setOpeningId(null);
    }
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const formatDate = (isoString?: string) => {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('it-IT', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  const getFileIcon = (type?: string, name?: string) => {
    const t = (type || '').toLowerCase();
    const n = (name || '').toLowerCase();
    if (t.includes('code') || n.endsWith('.py') || n.endsWith('.ts') || n.endsWith('.js') || n.endsWith('.json')) {
      return <FileCode size={20} color="hsl(var(--primary))" />;
    }
    if (t.includes('data') || t.includes('table') || n.endsWith('.csv') || n.endsWith('.xlsx')) {
      return <Table size={20} color="#10b981" />;
    }
    if (t.includes('archive') || n.endsWith('.zip') || n.endsWith('.tar.gz')) {
      return <FolderArchive size={20} color="#f59e0b" />;
    }
    return <FileText size={20} color="hsl(var(--fg))" />;
  };

  const filteredResults = useMemo(() => {
    return results.filter((item) => {
      const matchesSearch =
        !searchQuery.trim() ||
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (item.mission_title && item.mission_title.toLowerCase().includes(searchQuery.toLowerCase()));

      if (!matchesSearch) return false;

      const t = (item.type || '').toLowerCase();
      const n = (item.name || '').toLowerCase();

      if (categoryFilter === 'documents') {
        return t.includes('document') || n.endsWith('.md') || n.endsWith('.txt') || n.endsWith('.pdf');
      }
      if (categoryFilter === 'code') {
        return t.includes('code') || n.endsWith('.py') || n.endsWith('.ts') || n.endsWith('.js') || n.endsWith('.sh');
      }
      if (categoryFilter === 'data') {
        return t.includes('data') || t.includes('table') || n.endsWith('.csv') || n.endsWith('.json');
      }
      if (categoryFilter === 'other') {
        return !t.includes('document') && !t.includes('code') && !t.includes('data');
      }

      return true;
    });
  }, [results, searchQuery, categoryFilter]);

  return (
    <PageContainer size="xl">
      {/* Header */}
      <Section
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <FileCheck size={26} color="hsl(var(--primary))" />
            <Heading level={1}>{t('syResultsDocuments')}</Heading>
          </div>
        }
        description={t('syEverythingAetherProducedForYouDocuments')}
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchResults}
            disabled={loading}
            leftIcon={<RefreshCw size={14} className={loading ? 'animate-spin' : ''} />}
          >
            {t('resultsRefresh')}
          </Button>
        }
      />

      {/* Filter and Search Bar */}
      <Panel variant="default" style={{ padding: '14px 18px', marginBottom: '24px' }}>
        <Stack direction="row" gap="md" align="center" justify="between" wrap>
          <SegmentedControl
            value={categoryFilter}
            onChange={(val) => setCategoryFilter(val as any)}
            options={[
              { value: 'all', label: t('syAllResults') },
              { value: 'documents', label: t('syDocumentsReports') },
              { value: 'code', label: t('syCodeScripts') },
              { value: 'data', label: t('syTablesData') },
            ]}
          />

          <div style={{ minWidth: '240px', flex: '1', maxWidth: '340px' }}>
            <AetherInput
              placeholder={t('sySearchByNameOrJob')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </Stack>
      </Panel>

      {/* Main Content Area */}
      {loading ? (
        <Panel variant="default" style={{ padding: '48px', textAlign: 'center' }}>
          <Stack align="center" justify="center" gap="sm">
            <LoadingSpinner size="lg" />
            <span style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>{t('syLoadingResults')}</span>
          </Stack>
        </Panel>
      ) : filteredResults.length === 0 ? (
        <EmptyState
          icon={<FileText size={36} />}
          title={searchQuery ? t('syNoResultsFound') : t('syNoDocumentsProducedYet')}
          description={
            searchQuery
              ? t('syTryAnotherSearchTermOrPick')
              : t('syWhenAetherCompletesAJobAn')
          }
          action={
            navigate ? (
              <Button variant="primary" onClick={() => navigate('home')}>
                {t('syAskAetherToPrepareADocument')}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Grid minItemWidth={310} gap="md">
          {filteredResults.map((item) => (
            <Panel
              key={item.id}
              variant="default"
              style={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                padding: '18px 20px',
                height: '100%',
                transition: 'border-color 0.15s ease, transform 0.15s ease',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div
                      style={{
                        width: '38px',
                        height: '38px',
                        borderRadius: '8px',
                        backgroundColor: 'hsl(var(--primary)/0.08)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                      }}
                    >
                      {getFileIcon(item.type, item.name)}
                    </div>
                    <div>
                      <div
                        style={{
                          fontSize: '14px',
                          fontWeight: 600,
                          color: 'hsl(var(--fg))',
                          lineHeight: 1.3,
                          wordBreak: 'break-word',
                        }}
                      >
                        {item.name}
                      </div>
                      <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))', marginTop: '2px' }}>
                        {formatFileSize(item.size_bytes)} • {formatDate(item.created_at)}
                      </div>
                    </div>
                  </div>
                  <StatusBadge {...resultBadge(item, t)} />
                </div>

                {item.mission_title && (
                  <div
                    style={{
                      fontSize: '12px',
                      color: 'hsl(var(--muted-fg))',
                      backgroundColor: 'hsl(var(--card)/0.6)',
                      padding: '6px 10px',
                      borderRadius: '6px',
                      marginBottom: '14px',
                      border: '1px solid hsl(var(--border)/0.5)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <Sparkles size={12} color="hsl(var(--primary))" />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {t('syGeneratedFor')} <strong>{item.mission_title}</strong>
                    </span>
                  </div>
                )}
              </div>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '8px',
                  paddingTop: '12px',
                  borderTop: '1px solid hsl(var(--border)/0.5)',
                  marginTop: '12px',
                }}
              >
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleOpenPreview(item)}
                  leftIcon={<Eye size={13} />}
                  style={{ flex: 1 }}
                >
                  {t('syPreview')}
                </Button>

                {!item.mission_id && item.path && (
                  <a
                    href={apiUrl(`/api/personal/companion/file/download?path=${encodeURIComponent(item.path)}`)}
                    download={item.name}
                    style={{ textDecoration: 'none' }}
                    title={t('syDownloadTheFileToYourComputer')}
                  >
                    <Button variant="ghost" size="sm" leftIcon={<Download size={13} />}>
                      {t('syDownload')}
                    </Button>
                  </a>
                )}
                {item.mission_id && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleOpenFile(item)}
                      disabled={openingId === item.id}
                      title={t('syOpenInTheOperatingSystem')}
                      leftIcon={<FolderOpen size={13} />}
                    >
                      {t('syOpen')}
                    </Button>
                    <a
                      href={apiUrl(`/api/missions/${item.mission_id}/deliverables/${item.id}/download`)}
                      download={item.name}
                      style={{ textDecoration: 'none' }}
                      title={t('syDownloadTheFileToYourComputer')}
                    >
                      <Button variant="ghost" size="sm" leftIcon={<Download size={13} />}>
                        {t('syDownload')}
                      </Button>
                    </a>
                  </>
                )}
              </div>
            </Panel>
          ))}
        </Grid>
      )}

      {attempts.length > 0 && (
        <details data-testid="result-attempts" style={{ marginTop: '20px', fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>
          <summary style={{ cursor: 'pointer' }}>{t('resultsAttemptsSummary', { count: attempts.length })}</summary>
          <ul style={{ margin: '8px 0 0 18px' }}>
            {attempts.map((a) => (
              <li key={a.id}>
                {a.name || a.path} · {resultBadge(a, t).label}{a.mission_title ? ` · ${a.mission_title}` : ''}{a.created_at ? ` · ${formatDate(a.created_at)}` : ''}
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Preview Modal */}
      {previewItem && (
        <Modal
          isOpen={Boolean(previewItem)}
          onClose={() => setPreviewItem(null)}
          title={previewItem.name}
          description={
            previewItem.mission_title
              ? `Generato da Aether per: ${previewItem.mission_title}`
              : t('syPreviewOfTheProducedContent')
          }
          size="lg"
          footer={
            <Stack direction="row" gap="sm">
              {previewItem.mission_id && (
                <a
                  href={apiUrl(`/api/missions/${previewItem.mission_id}/deliverables/${previewItem.id}/download`)}
                  download={previewItem.name}
                  style={{ textDecoration: 'none' }}
                >
                  <Button variant="secondary" size="sm" leftIcon={<Download size={14} />}>
                    {t('syDownloadFile')}
                  </Button>
                </a>
              )}
              <Button variant="primary" size="sm" onClick={() => setPreviewItem(null)}>
                {t('syClose')}
              </Button>
            </Stack>
          }
        >
          {previewLoading ? (
            <div style={{ padding: '36px', textAlign: 'center' }}>
              <Stack align="center" justify="center" gap="sm">
                <LoadingSpinner size="md" />
                <span style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))' }}>{t('syLoadingThePreview')}</span>
              </Stack>
            </div>
          ) : previewData?.content ? (
            <div
              style={{
                backgroundColor: 'hsl(var(--bg))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
                padding: '16px 20px',
                maxHeight: '480px',
                overflowY: 'auto',
                fontFamily: previewData.format === 'code' ? 'var(--font-mono)' : 'inherit',
                fontSize: '13px',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {previewData.content}
            </div>
          ) : (
            <div style={{ padding: '24px 0', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
              {previewData?.message || t('syNoPreviewCanBeShownIn')}
            </div>
          )}
        </Modal>
      )}
    </PageContainer>
  );
}
