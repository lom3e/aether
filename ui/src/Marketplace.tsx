import { useState, useEffect, useCallback, useContext } from 'react';
import {
  ShoppingBag, Users, Puzzle, Wrench, Link2, Workflow as WorkflowIcon,
  ShieldCheck, ShieldAlert, Check, Trash2, Download, Search, Star,
  Info, X
} from 'lucide-react';
import { ToastContext } from './toast';
import { apiError, apiUrl } from './api';
import { TopHeader } from './TopHeader';
import { useTranslation } from './i18n';

export type PackageTypeFilter = 'all' | 'workforce' | 'skill' | 'tool' | 'connector' | 'workflow_template';

export interface PackagePermission {
  name: string;
  description: string;
  level: string;
}

export interface SecuritySummary {
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  permissions: PackagePermission[];
  network_domains: string[];
  filesystem_paths: string[];
  external_tools: string[];
  audit_notes: string[];
}

export interface PackageManifest {
  id: string;
  name: string;
  version: string;
  type: string;
  author: string;
  description: string;
  category: string;
  tags: string[];
  security_summary: SecuritySummary;
  downloads_count: number;
  rating: number;
  verified: boolean;
  is_installed?: boolean;
}

export function Marketplace() {
  const { t } = useTranslation();
  const showToast = useContext(ToastContext);

  const [packages, setPackages] = useState<PackageManifest[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedType, setSelectedType] = useState<PackageTypeFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [inspectingPackage, setInspectingPackage] = useState<PackageManifest | null>(null);

  const fetchPackages = useCallback(async () => {
    setLoading(true);
    try {
      const typeParam = selectedType === 'all' ? '' : `type=${selectedType}`;
      const searchParam = searchQuery.trim() ? `search=${encodeURIComponent(searchQuery.trim())}` : '';
      const params = [typeParam, searchParam].filter(Boolean).join('&');
      const url = apiUrl(`/api/marketplace/packages${params ? `?${params}` : ''}`);

      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setPackages(data);
      }
    } catch (err: any) {
      console.error('Failed to load marketplace packages', err);
    } finally {
      setLoading(false);
    }
  }, [selectedType, searchQuery]);

  useEffect(() => {
    fetchPackages();
  }, [fetchPackages]);

  const handleInstall = async (pkg: PackageManifest) => {
    setActionLoadingId(pkg.id);
    try {
      const res = await fetch(apiUrl(`/api/marketplace/packages/${pkg.id}/install`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        throw await apiError(res, 'Failed to install package.');
      }
      showToast(`Installed ${pkg.name} successfully!`, 'success');
      fetchPackages();
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleUninstall = async (pkg: PackageManifest) => {
    setActionLoadingId(pkg.id);
    try {
      const res = await fetch(apiUrl(`/api/marketplace/packages/${pkg.id}/uninstall`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        throw await apiError(res, 'Failed to uninstall package.');
      }
      showToast(`Uninstalled ${pkg.name}.`, 'info');
      fetchPackages();
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setActionLoadingId(null);
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'workforce': return <Users size={16} className="text-violet-500" />;
      case 'skill': return <Puzzle size={16} className="text-emerald-500" />;
      case 'tool': return <Wrench size={16} className="text-amber-500" />;
      case 'connector': return <Link2 size={16} className="text-sky-500" />;
      case 'workflow_template': return <WorkflowIcon size={16} className="text-pink-500" />;
      default: return <ShoppingBag size={16} className="text-primary" />;
    }
  };

  const getRiskBadge = (risk: string) => {
    switch (risk) {
      case 'low':
        return <span className="badge badge-success" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}><ShieldCheck size={11} /> Low Risk</span>;
      case 'medium':
        return <span className="badge badge-warning" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}><ShieldAlert size={11} /> Medium Risk</span>;
      default:
        return <span className="badge badge-danger" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}><ShieldAlert size={11} /> High Risk</span>;
    }
  };

  return (
    <div style={{ flex: 1, overflowY: 'auto' }}>
      <TopHeader
        title={t('marketplaceTitle') || 'Ecosystem Marketplace'}
        icon={ShoppingBag}
        actions={
          <span className="badge badge-primary" style={{ fontSize: '11px', padding: '4px 10px' }}>
            Verified Ecosystem Catalog
          </span>
        }
      />

      <div style={{ maxWidth: '1100px', margin: '24px auto', padding: '0 24px' }}>
        {/* Controls: Search and Type Filters */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
          {/* Category Tabs */}
          <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', paddingBottom: '4px' }}>
            {(
              [
                { id: 'all', label: 'All Catalog' },
                { id: 'workforce', label: 'Workforces' },
                { id: 'skill', label: 'Skills' },
                { id: 'tool', label: 'Tools' },
                { id: 'connector', label: 'Connectors' },
                { id: 'workflow_template', label: 'Workflow DAGs' },
              ] as const
            ).map(tab => (
              <button
                key={tab.id}
                className={`btn btn-ghost ${selectedType === tab.id ? 'active' : ''}`}
                style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  borderRadius: '20px',
                  padding: '6px 14px',
                  backgroundColor: selectedType === tab.id ? 'hsl(var(--primary)/0.15)' : 'transparent',
                  color: selectedType === tab.id ? 'hsl(var(--primary))' : 'hsl(var(--fg))',
                }}
                onClick={() => setSelectedType(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Search bar */}
          <div style={{ position: 'relative', width: '260px' }}>
            <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'hsl(var(--muted-fg))' }} />
            <input
              type="text"
              className="form-input"
              placeholder="Search packages, tags..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              style={{ paddingLeft: '32px', height: '32px', fontSize: '13px', borderRadius: '8px' }}
            />
          </div>
        </div>

        {/* Package Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px', marginBottom: '40px' }}>
          {packages.map(pkg => (
            <div
              key={pkg.id}
              className="card"
              style={{
                padding: '20px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                borderRadius: '12px',
                border: pkg.is_installed ? '1px solid hsl(var(--primary)/0.4)' : '1px solid hsl(var(--border))',
                boxShadow: pkg.is_installed ? '0 4px 16px hsl(var(--primary)/0.08)' : 'none',
              }}
            >
              <div>
                {/* Header: Icon, Type, Risk Level */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '8px',
                      backgroundColor: 'hsl(var(--secondary))',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}>
                      {getTypeIcon(pkg.type)}
                    </div>
                    <div>
                      <span style={{ fontSize: '10px', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.04em', color: 'hsl(var(--muted-fg))' }}>
                        {pkg.type.replace('_', ' ')}
                      </span>
                      <div style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>v{pkg.version} • {pkg.author}</div>
                    </div>
                  </div>

                  {getRiskBadge(pkg.security_summary.risk_level)}
                </div>

                {/* Title & Description */}
                <h3 style={{ fontSize: '16px', fontWeight: 600, margin: '0 0 6px', color: 'hsl(var(--fg))' }}>
                  {pkg.name}
                </h3>
                <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', lineHeight: 1.45, marginBottom: '14px', minHeight: '38px' }}>
                  {pkg.description}
                </p>

                {/* Tags */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '14px' }}>
                  {pkg.tags.map(tag => (
                    <span
                      key={tag}
                      style={{
                        fontSize: '11px',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        backgroundColor: 'hsl(var(--secondary)/0.5)',
                        color: 'hsl(var(--muted-fg))',
                      }}
                    >
                      #{tag}
                    </span>
                  ))}
                </div>

                {/* Metrics */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', fontSize: '11px', color: 'hsl(var(--muted-fg))', marginBottom: '16px' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                    <Download size={12} /> {pkg.downloads_count.toLocaleString()}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                    <Star size={12} className="text-amber-500 fill-amber-500" /> {pkg.rating.toFixed(1)}
                  </span>
                  <button
                    className="btn btn-ghost"
                    style={{ padding: '2px 4px', fontSize: '11px', textDecoration: 'underline', color: 'hsl(var(--primary))' }}
                    onClick={() => setInspectingPackage(pkg)}
                  >
                    <Info size={11} /> Security details
                  </button>
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', gap: '8px' }}>
                {pkg.is_installed ? (
                  <>
                    <button
                      className="btn btn-ghost"
                      style={{ flex: 1, fontSize: '13px', border: '1px solid hsl(var(--border))', color: 'hsl(var(--success))' }}
                      disabled
                    >
                      <Check size={14} /> Installed
                    </button>
                    <button
                      className="btn btn-ghost"
                      style={{ padding: '8px 12px', color: 'hsl(var(--destructive))' }}
                      onClick={() => handleUninstall(pkg)}
                      disabled={actionLoadingId === pkg.id}
                      title="Uninstall package"
                    >
                      <Trash2 size={14} />
                    </button>
                  </>
                ) : (
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', fontSize: '13px' }}
                    onClick={() => handleInstall(pkg)}
                    disabled={actionLoadingId === pkg.id}
                  >
                    <Download size={14} />
                    {actionLoadingId === pkg.id ? 'Installing...' : 'Install Package'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {packages.length === 0 && !loading && (
          <div style={{ textAlign: 'center', padding: '48px', color: 'hsl(var(--muted-fg))' }}>
            <ShoppingBag size={36} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
            <p>No marketplace packages matching criteria.</p>
          </div>
        )}
      </div>

      {/* Security & Permissions Inspection Modal */}
      {inspectingPackage && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: '16px',
        }}>
          <div style={{
            width: '540px',
            maxHeight: '85vh',
            overflowY: 'auto',
            backgroundColor: 'hsl(var(--card))',
            borderRadius: '12px',
            border: '1px solid hsl(var(--border))',
            boxShadow: '0 16px 36px rgba(0,0,0,0.3)',
            padding: '24px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShieldCheck size={20} className="text-primary" />
                <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 600 }}>
                  Security & Permission Audit
                </h3>
              </div>
              <button
                className="btn btn-ghost"
                style={{ padding: '4px' }}
                onClick={() => setInspectingPackage(null)}
              >
                <X size={16} />
              </button>
            </div>

            <div style={{ marginBottom: '14px', fontSize: '13px' }}>
              <strong>Package:</strong> {inspectingPackage.name} (v{inspectingPackage.version})
            </div>

            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '4px' }}>
                RISK CLASSIFICATION
              </div>
              <div>{getRiskBadge(inspectingPackage.security_summary.risk_level)}</div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '6px' }}>
                REQUESTED PERMISSIONS
              </div>
              {inspectingPackage.security_summary.permissions.length === 0 ? (
                <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>No special permissions required.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {inspectingPackage.security_summary.permissions.map(perm => (
                    <div
                      key={perm.name}
                      style={{
                        padding: '8px 10px',
                        borderRadius: '6px',
                        backgroundColor: 'hsl(var(--secondary)/0.4)',
                        fontSize: '12px',
                      }}
                    >
                      <div style={{ fontWeight: 600, color: 'hsl(var(--fg))' }}>{perm.name} <span style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))' }}>({perm.level})</span></div>
                      <div style={{ color: 'hsl(var(--muted-fg))', fontSize: '11px', marginTop: '2px' }}>{perm.description}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {inspectingPackage.security_summary.network_domains.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '4px' }}>
                  EXTERNAL NETWORK DOMAINS
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                  {inspectingPackage.security_summary.network_domains.map(dom => (
                    <span key={dom} className="badge badge-secondary" style={{ fontSize: '11px' }}>
                      {dom}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {inspectingPackage.security_summary.audit_notes.length > 0 && (
              <div style={{ marginBottom: '20px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'hsl(var(--muted-fg))', marginBottom: '4px' }}>
                  SECURITY AUDIT NOTES
                </div>
                <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                  {inspectingPackage.security_summary.audit_notes.map((note, idx) => (
                    <li key={idx} style={{ marginBottom: '4px' }}>{note}</li>
                  ))}
                </ul>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setInspectingPackage(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
