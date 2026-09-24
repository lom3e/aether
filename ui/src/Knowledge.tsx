import { useState, useEffect, useContext, useRef } from 'react';
import { Database, FileText, Upload, Trash2, ShieldCheck, Lock, FolderGit2, CheckCircle2, AlertCircle, FileUp, Network, Globe, Link2, X } from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';
import { TopHeader } from './TopHeader';
import { useTranslation } from './i18n';
import { Tooltip } from './Tooltip';
import { KnowledgeGraph } from './KnowledgeGraph';

interface IngestionProgress {
  active: boolean;
  totalFiles: number;
  currentFileName: string;
  statusText: string;
  percent: number;
}

export function Knowledge() {
  const { t } = useTranslation();
  const [viewMode, setViewMode] = useState<'documents' | 'graph'>('documents');
  const [documents, setDocuments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'all' | 'workspace' | 'project' | 'system'>('all');
  const [uploadScope, setUploadScope] = useState<'workspace' | 'project'>('workspace');
  const [projectInfo, setProjectInfo] = useState<any>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUrlModalOpen, setIsUrlModalOpen] = useState(false);
  const [ingestUrlInput, setIngestUrlInput] = useState('');
  const [ingestUrlTitle, setIngestUrlTitle] = useState('');
  const [ingestingUrl, setIngestingUrl] = useState(false);
  const [progress, setProgress] = useState<IngestionProgress>({
    active: false,
    totalFiles: 0,
    currentFileName: '',
    statusText: '',
    percent: 0,
  });

  const showToast = useContext(ToastContext);
  const dragCounter = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchStatus = () => {
    fetch(apiUrl('/api/knowledge/files'))
      .then(res => res.json())
      .then(data => {
        setDocuments(data.documents || []);
        setLoading(false);
      })
      .catch(console.error);

    fetch(apiUrl('/api/workspace/project'))
      .then(res => res.json())
      .then(data => {
        if (data && data.project) {
          setProjectInfo(data.project);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const executeUpload = async (files: FileList | File[]) => {
    if (!files || files.length === 0) return;

    const fileArray = Array.from(files);
    const total = fileArray.length;
    const firstFileName = fileArray[0]?.name || 'Document';

    setProgress({
      active: true,
      totalFiles: total,
      currentFileName: firstFileName,
      statusText: t('processingKnowledgeFiles'),
      percent: 30,
    });

    const formData = new FormData();
    for (let i = 0; i < fileArray.length; i++) {
      formData.append('files', fileArray[i]);
    }
    formData.append('scope', uploadScope);
    if (uploadScope === 'project' && projectInfo) {
      formData.append('project_id', projectInfo.id || projectInfo.name);
    }

    const progressTimer = setTimeout(() => {
      setProgress(prev => ({
        ...prev,
        statusText: t('ingestionProgress'),
        percent: 75,
      }));
    }, 400);

    try {
      const res = await fetch(apiUrl('/api/knowledge'), {
        method: 'POST',
        body: formData,
      });

      clearTimeout(progressTimer);

      if (res.ok) {
        const data = await res.json();
        setProgress(prev => ({
          ...prev,
          percent: 100,
          statusText: 'Ingestion completed.',
        }));

        if (data.status === 'ok') {
          const totalChunks = (data.documents || []).reduce((acc: number, d: any) => acc + (d.chunks || 0), 0);
          showToast(`Successfully uploaded ${data.succeeded} document(s) (${totalChunks} chunks).`, 'success');
        } else if (data.status === 'partial') {
          showToast(`Uploaded ${data.succeeded} document(s), ${data.failed} failed.`, 'warning');
        } else {
          showToast(`Upload failed: ${data.documents?.[0]?.error || 'Unknown error'}`, 'error');
        }
        fetchStatus();
      } else {
        const error = await apiError(res, 'Unable to upload documents.');
        showToast(error.message, 'error');
      }
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to upload documents.', 'error');
    } finally {
      setTimeout(() => {
        setProgress({
          active: false,
          totalFiles: 0,
          currentFileName: '',
          statusText: '',
          percent: 0,
        });
      }, 500);

      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      executeUpload(e.target.files);
    }
  };

  const handleIngestUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ingestUrlInput.trim()) return;
    setIngestingUrl(true);
    try {
      const res = await fetch(apiUrl('/api/knowledge/url'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: ingestUrlInput.trim(),
          title: ingestUrlTitle.trim() || undefined,
          scope: uploadScope,
          project_id: uploadScope === 'project' ? (projectInfo?.id || projectInfo?.name) : undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to ingest URL');
      }
      showToast(`Indexed ${data.document.chunks} chunks from ${data.document.filename}`, 'success');
      setIsUrlModalOpen(false);
      setIngestUrlInput('');
      setIngestUrlTitle('');
      fetchStatus();
    } catch (err: any) {
      showToast(err.message || 'Could not ingest URL', 'error');
    } finally {
      setIngestingUrl(false);
    }
  };

  // Drag and drop event handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current += 1;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current <= 0) {
      setIsDragging(false);
      dragCounter.current = 0;
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounter.current = 0;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      executeUpload(e.dataTransfer.files);
    }
  };

  const handleDelete = async (doc: any) => {
    if (doc.scope === 'system') {
      showToast('System knowledge documents are built-in and read-only.', 'info');
      return;
    }

    try {
      const res = await fetch(apiUrl(`/api/knowledge/${encodeURIComponent(doc.id)}`), {
        method: 'DELETE',
      });
      if (res.ok) {
        showToast('Document deleted.', 'success');
        fetchStatus();
      } else {
        throw await apiError(res, 'Unable to delete this document.');
      }
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to delete this document.', 'error');
    }
  };

  const formatSize = (bytes: number) => {
    if (!bytes || bytes < 1024) return (bytes || 0) + ' B';
    else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    else return (bytes / 1048576).toFixed(1) + ' MB';
  };

  const formatDate = (isoStr: string) => {
    if (!isoStr) return '-';
    return new Date(isoStr).toLocaleDateString() + ' ' + new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const filteredDocs = documents.filter(doc => {
    if (activeTab === 'workspace') return doc.scope === 'workspace';
    if (activeTab === 'project') return doc.scope === 'project';
    if (activeTab === 'system') return doc.scope === 'system';
    return true;
  });

  const systemCount = documents.filter(d => d.scope === 'system').length;
  const projectCount = documents.filter(d => d.scope === 'project').length;
  const workspaceCount = documents.filter(d => d.scope === 'workspace' || (!d.scope && d.scope !== 'system')).length;

  return (
    <div
      style={{ flex: 1, overflowY: 'auto', position: 'relative' }}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Full-view Drag & Drop Overlay */}
      {isDragging && (
        <div className="knowledge-drag-overlay">
          <div
            style={{
              background: 'hsl(var(--card))',
              border: '1px solid hsl(var(--primary)/0.4)',
              borderRadius: 'var(--radius)',
              padding: '36px 48px',
              textAlign: 'center',
              boxShadow: '0 12px 36px rgba(0,0,0,0.18)',
              maxWidth: '520px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '14px',
            }}
          >
            <div
              className="pulse-icon"
              style={{
                width: 64,
                height: 64,
                borderRadius: '50%',
                background: 'hsl(var(--primary)/0.15)',
                color: 'hsl(var(--primary))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <FileUp size={32} />
            </div>

            <div style={{ fontSize: '18px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
              {t('dropFilesHere')}
            </div>

            <div style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', maxWidth: '380px' }}>
              {t('dropFilesDesc')}
            </div>

            {/* Scope destination indicator */}
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                padding: '6px 14px',
                background: 'hsl(var(--muted))',
                borderRadius: '999px',
                fontSize: '12px',
                fontWeight: 500,
                color: 'hsl(var(--fg))',
                marginTop: '4px',
              }}
            >
              <span style={{ color: 'hsl(var(--muted-fg))' }}>{t('dropDestination')}:</span>
              <strong style={{ color: 'hsl(var(--primary))' }}>
                {uploadScope === 'project' && projectInfo ? `${t('projectScope')} (${projectInfo.name})` : t('workspaceScope')}
              </strong>
            </div>
          </div>
        </div>
      )}

      {/* Top Header with Upload Actions */}
      <TopHeader
        title={t('knowledgeTitle')}
        icon={Database}
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {projectInfo && (
              <select
                className="input"
                style={{ padding: '6px 10px', fontSize: '13px', width: 'auto' }}
                value={uploadScope}
                onChange={e => setUploadScope(e.target.value as 'workspace' | 'project')}
              >
                <option value="workspace">{t('workspaceScope')}</option>
                <option value="project">{t('projectScope')} ({projectInfo.name})</option>
              </select>
            )}
            <button
              className="btn btn-secondary"
              onClick={() => setIsUrlModalOpen(true)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
            >
              <Globe size={15} /> Ingest URL
            </button>
            <input
              type="file"
              ref={fileInputRef}
              id="file-upload"
              multiple
              style={{ display: 'none' }}
              onChange={handleFileInputChange}
              disabled={progress.active}
              accept=".txt,.md,.markdown,.pdf,.csv,.tsv,.docx,.py,.ts,.tsx,.js,.jsx,.json,.yaml,.yml,.toml,.rst,.html,.htm,.sql,.sh"
            />
            <label htmlFor="file-upload" className="btn btn-primary" style={{ cursor: 'pointer' }}>
              <Upload size={16} /> {progress.active ? t('uploading') : t('uploadDocument')}
            </label>
          </div>
        }
      />

      <div style={{ padding: '32px', maxWidth: '1200px', margin: '0 auto' }}>
        {/* Main Knowledge View Mode Switcher */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', background: 'hsl(var(--card))', padding: '4px', borderRadius: '10px', width: 'fit-content', border: '1px solid hsl(var(--border))' }}>
          <button
            data-testid="knowledge-documents-tab"
            className={`btn btn-sm ${viewMode === 'documents' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: '8px', fontSize: '13px' }}
            onClick={() => setViewMode('documents')}
          >
            <FileText size={15} /> {t('knowledgeDocumentsTab')}
          </button>
          <button
            data-testid="knowledge-graph-tab"
            className={`btn btn-sm ${viewMode === 'graph' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: '8px', fontSize: '13px' }}
            onClick={() => setViewMode('graph')}
          >
            <Network size={15} /> {t('knowledgeGraphTab')}
          </button>
        </div>

        {viewMode === 'graph' ? (
          <KnowledgeGraph />
        ) : (
          <>
            {/* Real-time Ingestion Progress Card */}
            {progress.active && (
          <div
            className="card fade-in"
            style={{
              marginBottom: '24px',
              border: '1px solid hsl(var(--primary)/0.3)',
              backgroundColor: 'hsl(var(--card))',
              boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div
                  className="pulse-icon"
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: '50%',
                    background: 'hsl(var(--primary)/0.15)',
                    color: 'hsl(var(--primary))',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Upload size={15} />
                </div>
                <div>
                  <div style={{ fontSize: '13.5px', fontWeight: 600, color: 'hsl(var(--fg))' }}>
                    {progress.statusText}
                  </div>
                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                    {progress.currentFileName} ({progress.totalFiles} {progress.totalFiles === 1 ? 'file' : 'files'})
                  </div>
                </div>
              </div>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'hsl(var(--primary))' }}>
                {progress.percent}%
              </div>
            </div>

            <div className="progress-bar-container">
              <div className="progress-bar-fill" style={{ width: `${progress.percent}%` }} />
            </div>
          </div>
        )}

        {/* Scope Filter Tabs */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', borderBottom: '1px solid hsl(var(--border))', paddingBottom: '8px' }}>
          <button
            className={`btn btn-ghost ${activeTab === 'all' ? 'active' : ''}`}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontWeight: activeTab === 'all' ? 600 : 400,
              color: activeTab === 'all' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              borderBottom: activeTab === 'all' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              borderRadius: 0,
            }}
            onClick={() => setActiveTab('all')}
          >
            {t('allScopes')} ({documents.length})
          </button>
          <button
            className={`btn btn-ghost ${activeTab === 'workspace' ? 'active' : ''}`}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontWeight: activeTab === 'workspace' ? 600 : 400,
              color: activeTab === 'workspace' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              borderBottom: activeTab === 'workspace' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              borderRadius: 0,
            }}
            onClick={() => setActiveTab('workspace')}
          >
            {t('workspaceScope')} ({workspaceCount})
          </button>
          <button
            className={`btn btn-ghost ${activeTab === 'project' ? 'active' : ''}`}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontWeight: activeTab === 'project' ? 600 : 400,
              color: activeTab === 'project' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              borderBottom: activeTab === 'project' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              borderRadius: 0,
            }}
            onClick={() => setActiveTab('project')}
          >
            {t('projectScope')} ({projectCount})
          </button>
          <button
            className={`btn btn-ghost ${activeTab === 'system' ? 'active' : ''}`}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontWeight: activeTab === 'system' ? 600 : 400,
              color: activeTab === 'system' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              borderBottom: activeTab === 'system' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              borderRadius: 0,
            }}
            onClick={() => setActiveTab('system')}
          >
            {t('systemScope')} ({systemCount})
          </button>
        </div>

        {/* Documents Table */}
        {filteredDocs.length > 0 ? (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t('filename')}</th>
                  <th>{t('scope')}</th>
                  <th>{t('size')}</th>
                  <th>{t('chunks')}</th>
                  <th>{t('indexedAt')}</th>
                  <th>{t('status')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredDocs.map((doc, i) => (
                  <tr key={i}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 500 }}>
                        <FileText size={16} className="text-primary" />
                        {doc.filename}
                      </div>
                    </td>
                    <td>
                      {doc.scope === 'system' ? (
                        <span className="badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'hsl(var(--primary)/0.1)', color: 'hsl(var(--primary))' }}>
                          <ShieldCheck size={12} /> {t('systemKnowledge')}
                        </span>
                      ) : doc.scope === 'project' ? (
                        <span className="badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'hsl(var(--secondary)/0.15)', color: 'hsl(var(--primary))' }}>
                          <FolderGit2 size={12} /> {doc.project_id || t('projectKnowledge')}
                        </span>
                      ) : (
                        <span className="badge" style={{ background: 'hsl(var(--muted))' }}>
                          {t('workspaceKnowledge')}
                        </span>
                      )}
                    </td>
                    <td className="text-muted">{formatSize(doc.size_bytes)}</td>
                    <td>{doc.chunk_count}</td>
                    <td className="text-muted">{formatDate(doc.uploaded_at)}</td>
                    <td>
                      <span className={`badge ${doc.status === 'Ready' ? 'badge-success' : (doc.status?.startsWith('Error') ? 'badge-error' : 'badge-warning')}`}>
                        {doc.status === 'Ready' && <CheckCircle2 size={11} style={{ marginRight: 2 }} />}
                        {doc.status?.startsWith('Error') && <AlertCircle size={11} style={{ marginRight: 2 }} />}
                        {doc.status}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {doc.scope === 'system' ? (
                        <Tooltip content={t('readOnlyProtected')} position="left">
                          <span style={{ padding: '4px', color: 'hsl(var(--muted-foreground))', display: 'inline-block' }}>
                            <Lock size={15} />
                          </span>
                        </Tooltip>
                      ) : (
                        <Tooltip content={t('deleteDocument')} position="left">
                          <button className="btn btn-ghost" style={{ padding: '4px' }} onClick={() => handleDelete(doc)}>
                            <Trash2 size={16} className="text-muted" />
                          </button>
                        </Tooltip>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !loading && (
          <div
            className="knowledge-dropzone-box"
            onClick={() => fileInputRef.current?.click()}
          >
            <div
              style={{
                width: 52,
                height: 52,
                borderRadius: '50%',
                background: 'hsl(var(--primary)/0.1)',
                color: 'hsl(var(--primary))',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: '14px',
              }}
            >
              <Upload size={24} />
            </div>
            <div style={{ fontSize: '16px', fontWeight: 600, color: 'hsl(var(--fg))', marginBottom: '6px' }}>
              {t('dragDropDropzone')}
            </div>
            <p className="text-muted" style={{ maxWidth: '420px', margin: '0 auto 16px', fontSize: '13px' }}>
              {t('noDocumentsDesc')}
            </p>
            <div style={{ display: 'inline-flex', gap: '8px', alignItems: 'center' }}>
              <span className="badge" style={{ fontSize: '11.5px', background: 'hsl(var(--muted))' }}>
                {t('supportedFormats')}
              </span>
            </div>
          </div>
        )}
          </>
        )}
      </div>

      {/* Ingest URL Modal */}
      {isUrlModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.65)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '20px',
          }}
          onClick={() => !ingestingUrl && setIsUrlModalOpen(false)}
        >
          <div
            style={{
              background: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: '16px',
              maxWidth: '520px',
              width: '100%',
              padding: '24px',
              boxShadow: '0 20px 50px rgba(0,0,0,0.3)',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ width: 36, height: 36, borderRadius: '8px', background: 'hsl(var(--primary)/0.15)', color: 'hsl(var(--primary))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Globe size={18} />
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>Ingest Web Documentation</h3>
                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>Extract and index web articles, API docs, or specs</div>
                </div>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setIsUrlModalOpen(false)}
                disabled={ingestingUrl}
                style={{ padding: '6px' }}
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleIngestUrl}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>
                    Web URL <span style={{ color: 'hsl(var(--destructive))' }}>*</span>
                  </label>
                  <input
                    type="url"
                    className="input"
                    required
                    placeholder="https://docs.example.com/api-reference"
                    value={ingestUrlInput}
                    onChange={e => setIngestUrlInput(e.target.value)}
                    style={{ width: '100%' }}
                    autoFocus
                  />
                </div>

                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>
                    Document Label (Optional)
                  </label>
                  <input
                    type="text"
                    className="input"
                    placeholder="e.g. Acme API Documentation"
                    value={ingestUrlTitle}
                    onChange={e => setIngestUrlTitle(e.target.value)}
                    style={{ width: '100%' }}
                  />
                </div>

                {projectInfo && (
                  <div>
                    <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>
                      Scope Destination
                    </label>
                    <select
                      className="input"
                      value={uploadScope}
                      onChange={e => setUploadScope(e.target.value as 'workspace' | 'project')}
                      style={{ width: '100%' }}
                    >
                      <option value="workspace">Workspace Knowledge (Global)</option>
                      <option value="project">Project Knowledge ({projectInfo.name})</option>
                    </select>
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setIsUrlModalOpen(false)}
                    disabled={ingestingUrl}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={ingestingUrl || !ingestUrlInput.trim()}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                  >
                    {ingestingUrl ? (
                      <>Fetching & Indexing...</>
                    ) : (
                      <>
                        <Link2 size={15} /> Ingest Web Page
                      </>
                    )}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

