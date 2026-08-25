import { useState, useContext, useMemo } from 'react';
import {
  Puzzle, Globe, FileText, Database, Terminal, Mail, GitBranch,
  MessageSquare, CheckCircle2, Sliders, Search, X, Sparkles, ArrowRight
} from 'lucide-react';
import { TopHeader } from './TopHeader';
import { useTranslation } from './i18n';
import { ToastContext } from './toast';

interface SkillItem {
  id: string;
  name: string;
  category: 'native' | 'integration' | 'mcp' | 'custom';
  descriptionKey: string;
  descriptionDefault: string;
  icon: any;
  enabled: boolean;
  permissions: string[];
  requiresConfig?: boolean;
  configFields?: Array<{ key: string; label: string; type: string; placeholder: string }>;
  version?: string;
  author?: string;
}

const INITIAL_SKILLS: SkillItem[] = [
  {
    id: 'web_search',
    name: 'Web Search',
    category: 'native',
    descriptionKey: 'skillWebSearchDesc',
    descriptionDefault: 'Search live information across the web using DuckDuckGo to augment model knowledge with real-time data.',
    icon: Globe,
    enabled: true,
    permissions: ['net:http', 'search:duckduckgo'],
    version: '1.5.0',
    author: 'Aether Core',
  },
  {
    id: 'search_knowledge',
    name: 'Knowledge Retrieval',
    category: 'native',
    descriptionKey: 'skillKnowledgeDesc',
    descriptionDefault: 'Perform semantic and lexical search across indexed workspace and system knowledge documents.',
    icon: Database,
    enabled: true,
    permissions: ['kb:read', 'vectors:query'],
    version: '1.5.0',
    author: 'Aether Core',
  },
  {
    id: 'filesystem_tools',
    name: 'Filesystem Tools',
    category: 'native',
    descriptionKey: 'skillFilesystemDesc',
    descriptionDefault: 'Inspect directories, read project files, patch source code, and create workspace deliverables.',
    icon: FileText,
    enabled: true,
    permissions: ['fs:read', 'fs:write', 'fs:patch'],
    version: '1.5.0',
    author: 'Aether Core',
  },
  {
    id: 'terminal_sandbox',
    name: 'Terminal & Command Sandbox',
    category: 'native',
    descriptionKey: 'skillTerminalDesc',
    descriptionDefault: 'Execute shell commands, run tests, compile builds, and verify code execution in a secure sandbox.',
    icon: Terminal,
    enabled: true,
    permissions: ['exec:shell', 'sandbox:isolated'],
    version: '1.5.0',
    author: 'Aether Core',
  },
  {
    id: 'gmail_integration',
    name: 'Google Workspace / Gmail',
    category: 'integration',
    descriptionKey: 'skillGmailDesc',
    descriptionDefault: 'Read, search, draft, and organize emails and thread communications through Google Workspace APIs.',
    icon: Mail,
    enabled: false,
    requiresConfig: true,
    configFields: [
      { key: 'client_id', label: 'OAuth Client ID', type: 'text', placeholder: 'xxxx.apps.googleusercontent.com' },
      { key: 'api_key', label: 'Service Account / API Key', type: 'password', placeholder: 'AIzaSy...' }
    ],
    permissions: ['email:read', 'email:draft', 'email:send'],
    version: '1.0.0',
    author: 'Google Cloud Ecosystem',
  },
  {
    id: 'github_tools',
    name: 'GitHub Repository Manager',
    category: 'integration',
    descriptionKey: 'skillGithubDesc',
    descriptionDefault: 'Connect private repositories, create pull requests, review issues, and synchronize project trees.',
    icon: GitBranch,
    enabled: true,
    requiresConfig: true,
    configFields: [
      { key: 'token', label: 'Personal Access Token', type: 'password', placeholder: 'ghp_xxxxxxxxxxxxxxxxxxxx' }
    ],
    permissions: ['git:clone', 'git:read', 'git:commit'],
    version: '1.2.0',
    author: 'GitHub Connect',
  },
  {
    id: 'slack_notifications',
    name: 'Slack Team Relay',
    category: 'integration',
    descriptionKey: 'skillSlackDesc',
    descriptionDefault: 'Broadcast task updates, human-in-the-loop approvals, and workflow notifications to Slack channels.',
    icon: MessageSquare,
    enabled: false,
    requiresConfig: true,
    configFields: [
      { key: 'webhook_url', label: 'Incoming Webhook URL', type: 'text', placeholder: 'https://hooks.slack.com/services/...' },
      { key: 'bot_token', label: 'Bot User OAuth Token', type: 'password', placeholder: 'xoxb-...' }
    ],
    permissions: ['chat:write', 'channels:read'],
    version: '1.0.0',
    author: 'Slack Ecosystem',
  },
  {
    id: 'mcp_bridge',
    name: 'Model Context Protocol (MCP) Bridge',
    category: 'mcp',
    descriptionKey: 'skillMcpDesc',
    descriptionDefault: 'Connect standard Model Context Protocol servers to dynamically load external developer tools.',
    icon: Sparkles,
    enabled: false,
    requiresConfig: true,
    configFields: [
      { key: 'server_url', label: 'MCP Server Endpoint / Command', type: 'text', placeholder: 'npx -y @modelcontextprotocol/server-...' }
    ],
    permissions: ['mcp:stdio', 'mcp:call'],
    version: '1.0.0',
    author: 'Anthropic MCP Standard',
  },
];

export function Skills({ navigate }: { navigate?: (view: string) => void } = {}) {
  const { t } = useTranslation();
  const showToast = useContext(ToastContext);

  const [skills, setSkills] = useState<SkillItem[]>(INITIAL_SKILLS);
  const [filterCategory, setFilterCategory] = useState<'all' | 'native' | 'integration' | 'mcp'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [configuringSkill, setConfiguringSkill] = useState<SkillItem | null>(null);
  const [configValues, setConfigValues] = useState<Record<string, string>>({});

  const handleToggleSkill = (skill: SkillItem) => {
    const next = !skill.enabled;
    setSkills(prev => prev.map(s => s.id === skill.id ? { ...s, enabled: next } : s));
    showToast(
      next
        ? `${skill.name} ${t('skillEnabled') || 'enabled'}`
        : `${skill.name} ${t('skillDisabled') || 'disabled'}`,
      'info'
    );
  };

  const handleOpenConfig = (skill: SkillItem) => {
    setConfiguringSkill(skill);
  };

  const handleSaveConfig = () => {
    if (!configuringSkill) return;
    showToast(`${configuringSkill.name} ${t('configSaved') || 'configuration saved'}`, 'success');
    setConfiguringSkill(null);
  };

  const filteredSkills = useMemo(() => {
    return skills.filter(s => {
      const matchesCategory = filterCategory === 'all' || s.category === filterCategory;
      const q = searchQuery.toLowerCase().trim();
      const matchesQuery = !q || s.name.toLowerCase().includes(q) || s.descriptionDefault.toLowerCase().includes(q) || s.permissions.some(p => p.toLowerCase().includes(q));
      return matchesCategory && matchesQuery;
    });
  }, [skills, filterCategory, searchQuery]);

  const activeCount = skills.filter(s => s.enabled).length;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto' }}>
      <TopHeader
        title={t('skillsTitle') || 'Skills & Tools Hub'}
        icon={Puzzle}
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="badge badge-primary" style={{ fontSize: '11.5px', padding: '4px 10px' }}>
              {activeCount} / {skills.length} {t('activeSkills') || 'Active'}
            </span>
          </div>
        }
      />

      <div style={{ maxWidth: '1100px', width: '100%', margin: '24px auto', padding: '0 32px' }}>
        <p className="text-muted" style={{ fontSize: '14.5px', marginBottom: '24px', lineHeight: 1.5 }}>
          {t('skillsSubtitle') || 'Showcase, enable, and configure native tools, workspace capabilities, and third-party integrations available to your AI workforce.'}
        </p>

        {/* Filter Bar & Search */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap', marginBottom: '24px' }}>
          <div style={{ display: 'flex', gap: '6px', backgroundColor: 'hsl(var(--card))', padding: '4px', borderRadius: '8px', border: '1px solid hsl(var(--border))' }}>
            {[
              { id: 'all', label: t('allSkills') || 'All Capabilities' },
              { id: 'native', label: t('nativeTools') || 'Native Tools' },
              { id: 'integration', label: t('integrations') || 'Integrations' },
              { id: 'mcp', label: 'MCP Servers' },
            ].map(tab => (
              <button
                key={tab.id}
                className={`btn btn-ghost ${filterCategory === tab.id ? 'active' : ''}`}
                style={{
                  padding: '6px 14px',
                  fontSize: '12.5px',
                  borderRadius: '6px',
                  fontWeight: filterCategory === tab.id ? 600 : 500,
                  backgroundColor: filterCategory === tab.id ? 'hsl(var(--primary)/0.12)' : 'transparent',
                  color: filterCategory === tab.id ? 'hsl(var(--primary))' : 'hsl(var(--fg))',
                }}
                onClick={() => setFilterCategory(tab.id as any)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div style={{ position: 'relative', width: '260px' }}>
            <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'hsl(var(--muted-fg))' }} />
            <input
              className="form-input"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder={t('searchSkills') || 'Search tools & skills...'}
              style={{ paddingLeft: '32px', height: '36px', fontSize: '13px' }}
            />
          </div>
        </div>

        {/* Grid of Skills */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))', gap: '18px', marginBottom: '40px' }}>
          {filteredSkills.map(skill => {
            const IconComp = skill.icon;
            return (
              <div
                key={skill.id}
                className="card"
                style={{
                  padding: '20px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  borderRadius: '12px',
                  border: skill.enabled ? '1px solid hsl(var(--primary)/0.35)' : '1px solid hsl(var(--border))',
                  backgroundColor: skill.enabled ? 'hsl(var(--card))' : 'hsl(var(--muted)/0.15)',
                  transition: 'all 0.15s ease',
                }}
              >
                <div>
                  {/* Card Header */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div
                        style={{
                          width: '40px',
                          height: '40px',
                          borderRadius: '10px',
                          backgroundColor: skill.enabled ? 'hsl(var(--primary)/0.12)' : 'hsl(var(--muted))',
                          color: skill.enabled ? 'hsl(var(--primary))' : 'hsl(var(--muted-fg))',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                        }}
                      >
                        <IconComp size={20} />
                      </div>
                      <div>
                        <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600 }}>{skill.name}</h3>
                        <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                          {skill.author} {skill.version ? `• v${skill.version}` : ''}
                        </span>
                      </div>
                    </div>

                    {/* Toggle Switch */}
                    <button
                      className={`badge ${skill.enabled ? 'badge-success' : ''}`}
                      style={{
                        cursor: 'pointer',
                        padding: '4px 10px',
                        fontSize: '11px',
                        border: '1px solid hsl(var(--border))',
                        backgroundColor: skill.enabled ? 'hsl(var(--success-bg))' : 'hsl(var(--muted))',
                        color: skill.enabled ? 'hsl(var(--success))' : 'hsl(var(--muted-fg))',
                      }}
                      onClick={() => handleToggleSkill(skill)}
                    >
                      {skill.enabled ? (t('statusEnabled') || 'Active') : (t('statusDisabled') || 'Disabled')}
                    </button>
                  </div>

                  <p className="text-muted" style={{ fontSize: '13px', lineHeight: 1.5, marginBottom: '14px' }}>
                    {t(skill.descriptionKey as any) || skill.descriptionDefault}
                  </p>
                </div>

                <div>
                  {/* Permissions & Badges */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '14px' }}>
                    {skill.permissions.map(p => (
                      <span key={p} className="badge" style={{ fontSize: '10px', fontFamily: 'monospace' }}>
                        {p}
                      </span>
                    ))}
                  </div>

                  {/* Card Footer Actions */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '10px', borderTop: '1px solid hsl(var(--border))' }}>
                    <span style={{ fontSize: '11.5px', color: 'hsl(var(--muted-fg))', textTransform: 'capitalize' }}>
                      {skill.category}
                    </span>

                    {skill.requiresConfig ? (
                      <button
                        className="btn btn-ghost"
                        style={{ fontSize: '12px', padding: '4px 8px', gap: '4px' }}
                        onClick={() => handleOpenConfig(skill)}
                      >
                        <Sliders size={13} />
                        <span>{t('configure') || 'Configure'}</span>
                      </button>
                    ) : (
                      <span style={{ fontSize: '11.5px', color: 'hsl(var(--primary))', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <CheckCircle2 size={13} /> {t('readyToUse') || 'Ready'}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Discovery Banner for Marketplace */}
        <div
          className="card"
          style={{
            padding: '20px 24px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, hsl(var(--primary)/0.08) 0%, hsl(var(--card)) 100%)',
            border: '1px solid hsl(var(--primary)/0.25)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '16px',
            flexWrap: 'wrap',
            marginBottom: '32px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div
              style={{
                width: '42px',
                height: '42px',
                borderRadius: '10px',
                backgroundColor: 'hsl(var(--primary)/0.15)',
                color: 'hsl(var(--primary))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Sparkles size={22} />
            </div>
            <div>
              <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600 }}>
                {t('exploreMoreSkillsMarketplace') || 'Discover more Skills & Toolpacks in the Marketplace'}
              </h4>
              <p className="text-muted" style={{ margin: '3px 0 0', fontSize: '13px' }}>
                {t('marketplaceSkillsBannerDesc') || 'Explore community-curated integrations, domain workflows, and official workforce packs.'}
              </p>
            </div>
          </div>

          {navigate && (
            <button
              type="button"
              className="btn btn-primary"
              style={{ padding: '8px 16px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}
              onClick={() => navigate('marketplace')}
            >
              <span>{t('goToMarketplace') || 'Open Marketplace'}</span>
              <ArrowRight size={15} />
            </button>
          )}
        </div>
      </div>

      {/* CONFIGURATION MODAL */}
      {configuringSkill && (
        <div className="modal-overlay" onClick={() => setConfiguringSkill(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '500px', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ width: '32px', height: '32px', borderRadius: '8px', backgroundColor: 'hsl(var(--primary)/0.12)', color: 'hsl(var(--primary))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Sliders size={16} />
                </div>
                <h3 style={{ margin: 0, fontSize: '16px' }}>
                  {configuringSkill.name}
                </h3>
              </div>
              <button className="btn btn-ghost" onClick={() => setConfiguringSkill(null)}>
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', marginBottom: '20px' }}>
              {t('configureSkillDesc') || 'Set connection credentials and environment parameters for this integration.'}
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '20px' }}>
              {(configuringSkill.configFields || []).map(f => (
                <div key={f.key} className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label" style={{ fontSize: '12.5px' }}>{f.label}</label>
                  <input
                    type={f.type}
                    className="form-input"
                    placeholder={f.placeholder}
                    value={configValues[f.key] || ''}
                    onChange={e => setConfigValues({ ...configValues, [f.key]: e.target.value })}
                  />
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="btn btn-secondary" onClick={() => setConfiguringSkill(null)}>
                {t('cancel')}
              </button>
              <button className="btn btn-primary" onClick={handleSaveConfig}>
                {t('saveSettings')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
