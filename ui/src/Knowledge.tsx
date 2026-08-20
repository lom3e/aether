import { useState, useEffect, useContext } from 'react';
import { Database, FileText, Upload, Trash2, ShieldCheck, Lock } from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';

export function Knowledge() {
  const [documents, setDocuments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'workspace' | 'system'>('all');
  const showToast = useContext(ToastContext);

  const fetchStatus = () => {
    fetch(apiUrl('/api/knowledge/files'))
      .then(res => res.json())
      .then(data => {
        setDocuments(data.documents || []);
        setLoading(false);
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleFileUpload = async (e: any) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(apiUrl('/api/knowledge/upload'), {
        method: 'POST',
        body: formData
      });
      if (res.ok) {
        showToast('Document uploaded successfully.', 'success');
        fetchStatus();
      } else {
        const error = await apiError(res, 'Unable to upload this document.');
        showToast(error.message, 'error');
      }
    } catch (error) {
      showToast(error instanceof Error ? error.message : 'Unable to upload this document.', 'error');
    } finally {
      setUploading(false);
      e.target.value = ''; // Reset file input
    }
  };

  const handleDelete = async (doc: any) => {
    if (doc.scope === 'system') {
      showToast('System knowledge documents are built-in and read-only.', 'info');
      return;
    }

    try {
      const res = await fetch(apiUrl(`/api/knowledge/files/${encodeURIComponent(doc.id)}`), {
        method: 'DELETE'
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
    if (bytes < 1024) return bytes + ' B';
    else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    else return (bytes / 1048576).toFixed(1) + ' MB';
  };

  const formatDate = (isoStr: string) => {
    return new Date(isoStr).toLocaleDateString() + ' ' + new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const filteredDocs = documents.filter(doc => {
    if (activeTab === 'workspace') return doc.scope !== 'system';
    if (activeTab === 'system') return doc.scope === 'system';
    return true;
  });

  const systemCount = documents.filter(d => d.scope === 'system').length;
  const workspaceCount = documents.filter(d => d.scope !== 'system').length;

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <div className="top-header">
        <div className="top-header-title">
          <Database size={18} className="text-primary" />
          <span>Knowledge Base</span>
        </div>

        <div>
          <input
            type="file"
            id="file-upload"
            style={{ display: 'none' }}
            onChange={handleFileUpload}
            disabled={uploading}
            accept=".txt,.md,.pdf,.csv"
          />
          <label htmlFor="file-upload" className="btn btn-primary" style={{ cursor: 'pointer' }}>
            <Upload size={16} /> {uploading ? 'Uploading...' : 'Upload Document'}
          </label>
        </div>
      </div>

      <div style={{ padding: '32px', maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px', borderBottom: '1px solid hsl(var(--border))', paddingBottom: '8px' }}>
          <button
            className={`btn btn-ghost ${activeTab === 'all' ? 'active' : ''}`}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontWeight: activeTab === 'all' ? 600 : 400,
              color: activeTab === 'all' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              borderBottom: activeTab === 'all' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              borderRadius: 0
            }}
            onClick={() => setActiveTab('all')}
          >
            All ({documents.length})
          </button>
          <button
            className={`btn btn-ghost ${activeTab === 'workspace' ? 'active' : ''}`}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontWeight: activeTab === 'workspace' ? 600 : 400,
              color: activeTab === 'workspace' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              borderBottom: activeTab === 'workspace' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              borderRadius: 0
            }}
            onClick={() => setActiveTab('workspace')}
          >
            Workspace ({workspaceCount})
          </button>
          <button
            className={`btn btn-ghost ${activeTab === 'system' ? 'active' : ''}`}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontWeight: activeTab === 'system' ? 600 : 400,
              color: activeTab === 'system' ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
              borderBottom: activeTab === 'system' ? '2px solid hsl(var(--primary))' : '2px solid transparent',
              borderRadius: 0
            }}
            onClick={() => setActiveTab('system')}
          >
            System / Official ({systemCount})
          </button>
        </div>
        {filteredDocs.length > 0 ? (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Scope</th>
                  <th>Size</th>
                  <th>Chunks</th>
                  <th>Indexed</th>
                  <th>Status</th>
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
                          <ShieldCheck size={12} /> System
                        </span>
                      ) : (
                        <span className="badge" style={{ background: 'hsl(var(--muted))' }}>
                          Workspace
                        </span>
                      )}
                    </td>
                    <td className="text-muted">{formatSize(doc.size_bytes)}</td>
                    <td>{doc.chunk_count}</td>
                    <td className="text-muted">{formatDate(doc.uploaded_at)}</td>
                    <td>
                      <span className={`badge ${doc.status === 'Ready' ? 'badge-success' : (doc.status.startsWith('Error') ? 'badge-error' : 'badge-warning')}`}>
                        {doc.status}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {doc.scope === 'system' ? (
                        <span title="Built-in System Knowledge (Read-only)" style={{ padding: '4px', color: 'hsl(var(--muted-foreground))', display: 'inline-block' }}>
                          <Lock size={15} />
                        </span>
                      ) : (
                        <button className="btn btn-ghost" style={{ padding: '4px' }} onClick={() => handleDelete(doc)}>
                          <Trash2 size={16} className="text-muted" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !loading && (
          <div className="empty-state">
            <Database className="empty-icon" />
            <div className="empty-title">No Documents in this Scope</div>
            <p className="text-muted" style={{ maxWidth: '400px' }}>Upload documents (PDF, TXT, MD, CSV) to provide contextual knowledge for your workforce.</p>
            <label htmlFor="file-upload" className="btn btn-primary mt-4" style={{ cursor: 'pointer' }}>
              <Upload size={16} /> Upload your first document
            </label>
          </div>
        )}
      </div>
    </div>
  );
}
