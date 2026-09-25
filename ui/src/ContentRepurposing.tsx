import { useState, useEffect } from 'react';
import {
  Share2,
  Sparkles,
  Mail,
  Video,
  Copy,
  Check,
  Calendar,
  Clock,
  Send,
  Plus,
  BarChart2,
  AlertCircle,
  FileText
} from 'lucide-react';
import { apiUrl } from './api';

function LinkedinIcon({ size = 15, color = "#0A66C2" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
      <rect x="2" y="9" width="4" height="12" />
      <circle cx="4" cy="4" r="2" />
    </svg>
  );
}

function TwitterIcon({ size = 15, color = "#1DA1F2" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 4s-.7 2.1-2 3.4c1.6 10-9.4 17.3-18 11.6 2.2.1 4.4-.6 6-2C3 15.5.5 9.6 3 5c2.2 2.6 5.6 4.1 9 4-.9-4.2 4-6.6 7-3.8 1.1 0 3-1.2 3-1.2z" />
    </svg>
  );
}

interface RepurposedVariant {
  id: string;
  item_id: string;
  platform: string;
  title: string;
  body: string;
  thread_tweets: string[];
  hashtags: string[];
  call_to_action: string;
  estimated_read_time_sec: number;
  character_count: number;
  compliance_passed: boolean;
  compliance_notes: string[];
  engagement_score: number;
  status: string;
  scheduled_at?: string | null;
  published_at?: string | null;
  metadata?: any;
}

interface Campaign {
  id: string;
  name: string;
  description: string;
  target_audience: string;
  objectives: string[];
  status: string;
  tags: string[];
}

export function ContentRepurposing({ navigate }: { navigate: (view: string) => void }) {
  // Input State
  const [title, setTitle] = useState('Autonomous Agent Workforces in Production');
  const [sourceText, setSourceText] = useState(
    `Autonomous multi-agent systems are revolutionizing modern engineering workflows. However, running agents at scale reveals critical architectural challenges.

Key takeaways and lessons learned:
* True leverage comes from deterministic state machines combined with adaptive model routing.
* Resilient fallback chains prevent cascading failures when upstream LLM providers suffer degradation.
* Deep knowledge ingestion with SQLite FTS5 BM25 search outperforms brittle naive vector lookups.
* Continuous workforce memory injection prevents knowledge regression across distributed teams.
* Every mission deliverable must produce verifiable, replayable flight recorder lineage.

By standardizing on self-healing execution and strict safety policies, engineering velocity increased by 400% while reducing manual triage time to near zero.`
  );
  const [tone, setTone] = useState('thought_leadership');
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([
    'linkedin',
    'twitter_thread',
    'newsletter',
    'video_script',
  ]);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string>('');

  // Results State
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [variants, setVariants] = useState<RepurposedVariant[]>([]);
  const [activePlatformTab, setActivePlatformTab] = useState<string>('linkedin');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Campaigns State
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [showCampaignModal, setShowCampaignModal] = useState(false);
  const [newCampName, setNewCampName] = useState('');
  const [newCampDesc, setNewCampDesc] = useState('');
  const [newCampAudience, setNewCampAudience] = useState('Engineering Leaders & Developers');
  const [newCampObjectives, setNewCampObjectives] = useState('Publish weekly thought leadership');
  const [newCampTags, setNewCampTags] = useState('ai, workforce, launch');

  // Schedule modal state
  const [scheduleVariantId, setScheduleVariantId] = useState<string | null>(null);
  const [scheduleDateTime, setScheduleDateTime] = useState('');

  // Fetch campaigns
  useEffect(() => {
    fetchCampaigns();
  }, []);

  const fetchCampaigns = async () => {
    try {
      const res = await fetch(apiUrl('/content/campaigns'));
      if (res.ok) {
        const data = await res.json();
        setCampaigns(data);
      }
    } catch (err) {
      console.error('Failed to load campaigns:', err);
    }
  };

  const handleRepurpose = async () => {
    if (!sourceText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(apiUrl('/content/repurpose'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_text: sourceText,
          title: title || 'Repurposed Asset',
          target_platforms: selectedPlatforms,
          tone,
          target_audience: 'Professionals & Developers',
          campaign_id: selectedCampaignId || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Repurposing failed');
      }
      const data = await res.json();
      setVariants(data.variants || []);
      if (data.variants && data.variants.length > 0) {
        setActivePlatformTab(data.variants[0].platform);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to repurpose content');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleScheduleSubmit = async () => {
    if (!scheduleVariantId) return;
    try {
      const res = await fetch(apiUrl(`/content/variants/${scheduleVariantId}/schedule`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scheduled_at: scheduleDateTime || new Date().toISOString() }),
      });
      if (res.ok) {
        const updated = await res.json();
        setVariants((prev) => prev.map((v) => (v.id === updated.id ? updated : v)));
        setScheduleVariantId(null);
      }
    } catch (err) {
      console.error('Failed to schedule:', err);
    }
  };

  const handlePublish = async (variantId: string) => {
    try {
      const res = await fetch(apiUrl(`/content/variants/${variantId}/publish`), {
        method: 'POST',
      });
      if (res.ok) {
        const updated = await res.json();
        setVariants((prev) => prev.map((v) => (v.id === updated.id ? updated : v)));
      }
    } catch (err) {
      console.error('Failed to publish:', err);
    }
  };

  const handleCreateCampaign = async () => {
    if (!newCampName.trim()) return;
    try {
      const res = await fetch(apiUrl('/content/campaigns'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newCampName,
          description: newCampDesc,
          target_audience: newCampAudience,
          objectives: newCampObjectives.split(',').map((s) => s.trim()).filter(Boolean),
          tags: newCampTags.split(',').map((s) => s.trim()).filter(Boolean),
        }),
      });
      if (res.ok) {
        const created = await res.json();
        setCampaigns((prev) => [created, ...prev]);
        setSelectedCampaignId(created.id);
        setShowCampaignModal(false);
        setNewCampName('');
        setNewCampDesc('');
      }
    } catch (err) {
      console.error('Failed to create campaign:', err);
    }
  };

  const togglePlatform = (p: string) => {
    setSelectedPlatforms((prev) =>
      prev.includes(p) ? prev.filter((item) => item !== p) : [...prev, p]
    );
  };

  const currentVariant = variants.find((v) => v.platform === activePlatformTab);

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <Share2 size={24} style={{ color: 'hsl(var(--primary))' }} />
            <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0 }}>Social Media & Content Engine</h1>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '12px',
                backgroundColor: 'hsl(var(--primary)/0.15)',
                color: 'hsl(var(--primary))',
              }}
            >
              Social Workforce
            </span>
          </div>
          <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', margin: 0 }}>
            Repurpose deep technical deliverables and knowledge artifacts into high-conversion multi-platform formats.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className="btn btn-ghost"
            onClick={() => navigate('missions')}
            style={{ fontSize: '13px' }}
          >
            Missions
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => setShowCampaignModal(true)}
            style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
          >
            <Plus size={15} />
            New Campaign
          </button>
        </div>
      </div>

      {/* Main Grid: Input Column & Preview Column */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: '24px' }}>
        {/* Left Column: Source Material & Configuration */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Card: Source Material */}
          <div
            style={{
              padding: '18px',
              borderRadius: '8px',
              border: '1px solid hsl(var(--border))',
              backgroundColor: 'hsl(var(--card))',
            }}
          >
            <h2 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <FileText size={16} />
              Source Material
            </h2>

            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, color: 'hsl(var(--muted-fg))', display: 'block', marginBottom: '4px' }}>
                Asset Title
              </label>
              <input
                type="text"
                className="input"
                style={{ width: '100%', fontSize: '13px' }}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Scaling Autonomous Agent Workforces"
              />
            </div>

            <div style={{ marginBottom: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <label style={{ fontSize: '12px', fontWeight: 500, color: 'hsl(var(--muted-fg))' }}>
                  Raw Content / Deliverable Markdown
                </label>
                <span style={{ fontSize: '11px', color: 'hsl(var(--muted-fg))' }}>
                  {sourceText.length} characters
                </span>
              </div>
              <textarea
                className="input"
                rows={9}
                style={{ width: '100%', fontSize: '13px', lineHeight: 1.5, resize: 'vertical' }}
                value={sourceText}
                onChange={(e) => setSourceText(e.target.value)}
                placeholder="Paste blog post, mission deliverable, architecture spec, or release notes..."
              />
            </div>

            {/* Campaign Selection */}
            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, color: 'hsl(var(--muted-fg))', display: 'block', marginBottom: '4px' }}>
                Associate with Campaign (Optional)
              </label>
              <select
                className="input"
                style={{ width: '100%', fontSize: '13px' }}
                value={selectedCampaignId}
                onChange={(e) => setSelectedCampaignId(e.target.value)}
              >
                <option value="">No Campaign (Ad-hoc Asset)</option>
                {campaigns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.status})
                  </option>
                ))}
              </select>
            </div>

            {/* Tone Selector */}
            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, color: 'hsl(var(--muted-fg))', display: 'block', marginBottom: '4px' }}>
                Tone of Voice
              </label>
              <select
                className="input"
                style={{ width: '100%', fontSize: '13px' }}
                value={tone}
                onChange={(e) => setTone(e.target.value)}
              >
                <option value="thought_leadership">Thought Leadership (Executive & Authoritative)</option>
                <option value="punchy_viral">Punchy & Viral (High-Contrast & Hook-Driven)</option>
                <option value="educational">Educational (Actionable Breakdown & Steps)</option>
                <option value="storytelling">Storytelling (Behind-The-Scenes Narrative)</option>
                <option value="conversational">Conversational (Direct & Community-Oriented)</option>
              </select>
            </div>

            {/* Target Platforms Checkboxes */}
            <div style={{ marginBottom: '18px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, color: 'hsl(var(--muted-fg))', display: 'block', marginBottom: '6px' }}>
                Target Platforms
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
                {[
                  { id: 'linkedin', label: 'LinkedIn Post', icon: <LinkedinIcon size={14} color="#0A66C2" /> },
                  { id: 'twitter_thread', label: 'Twitter / X Thread', icon: <TwitterIcon size={14} color="#1DA1F2" /> },
                  { id: 'newsletter', label: 'Newsletter Digest', icon: <Mail size={14} color="#FF6600" /> },
                  { id: 'video_script', label: 'Short-Form Script', icon: <Video size={14} color="#E1306C" /> },
                ].map((p) => (
                  <label
                    key={p.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      border: selectedPlatforms.includes(p.id)
                        ? '1px solid hsl(var(--primary))'
                        : '1px solid hsl(var(--border))',
                      backgroundColor: selectedPlatforms.includes(p.id)
                        ? 'hsl(var(--primary)/0.08)'
                        : 'transparent',
                      cursor: 'pointer',
                      fontSize: '12px',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedPlatforms.includes(p.id)}
                      onChange={() => togglePlatform(p.id)}
                    />
                    {p.icon}
                    <span>{p.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Repurpose Button */}
            <button
              className="btn btn-primary"
              style={{ width: '100%', padding: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
              onClick={handleRepurpose}
              disabled={loading || selectedPlatforms.length === 0}
            >
              <Sparkles size={16} />
              {loading ? 'Repurposing Content...' : 'Repurpose with Social Workforce'}
            </button>

            {error && (
              <div
                style={{
                  marginTop: '12px',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  backgroundColor: 'hsl(var(--destructive)/0.15)',
                  color: 'hsl(var(--destructive))',
                  fontSize: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <AlertCircle size={14} />
                {error}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Multi-Platform Previews */}
        <div>
          {variants.length === 0 ? (
            <div
              style={{
                height: '100%',
                minHeight: '400px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px dashed hsl(var(--border))',
                borderRadius: '8px',
                padding: '40px',
                textAlign: 'center',
              }}
            >
              <Share2 size={36} style={{ color: 'hsl(var(--muted-fg))', marginBottom: '12px', opacity: 0.6 }} />
              <h3 style={{ fontSize: '16px', fontWeight: 600, margin: '0 0 6px 0' }}>No Repurposed Variants Yet</h3>
              <p style={{ fontSize: '13px', color: 'hsl(var(--muted-fg))', maxWidth: '360px', margin: 0 }}>
                Configure your source text on the left and click "Repurpose with Social Workforce" to generate multi-channel adaptations.
              </p>
            </div>
          ) : (
            <div
              style={{
                borderRadius: '8px',
                border: '1px solid hsl(var(--border))',
                backgroundColor: 'hsl(var(--card))',
                overflow: 'hidden',
              }}
            >
              {/* Platform Navigation Tabs */}
              <div
                style={{
                  display: 'flex',
                  borderBottom: '1px solid hsl(var(--border))',
                  backgroundColor: 'hsl(var(--secondary)/0.3)',
                  overflowX: 'auto',
                }}
              >
                {variants.map((v) => (
                  <button
                    key={v.platform}
                    onClick={() => setActivePlatformTab(v.platform)}
                    style={{
                      padding: '12px 16px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      fontSize: '13px',
                      fontWeight: activePlatformTab === v.platform ? 600 : 400,
                      color: activePlatformTab === v.platform ? 'hsl(var(--foreground))' : 'hsl(var(--muted-fg))',
                      borderBottom: activePlatformTab === v.platform ? '2px solid hsl(var(--primary))' : '2px solid transparent',
                      background: 'none',
                      borderTop: 'none',
                      borderLeft: 'none',
                      borderRight: 'none',
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {v.platform === 'linkedin' && <LinkedinIcon size={15} color="#0A66C2" />}
                    {v.platform === 'twitter_thread' && <TwitterIcon size={15} color="#1DA1F2" />}
                    {v.platform === 'newsletter' && <Mail size={15} color="#FF6600" />}
                    {v.platform === 'video_script' && <Video size={15} color="#E1306C" />}
                    <span>
                      {v.platform === 'linkedin' && 'LinkedIn'}
                      {v.platform === 'twitter_thread' && `Twitter Thread (${v.thread_tweets.length})`}
                      {v.platform === 'newsletter' && 'Newsletter'}
                      {v.platform === 'video_script' && 'Video Script'}
                    </span>
                  </button>
                ))}
              </div>

              {/* Active Tab Preview Body */}
              {currentVariant && (
                <div style={{ padding: '20px' }}>
                  {/* Meta Bar */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: '16px',
                      paddingBottom: '12px',
                      borderBottom: '1px solid hsl(var(--border)/0.6)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          padding: '2px 8px',
                          borderRadius: '10px',
                          backgroundColor:
                            currentVariant.status === 'published'
                              ? 'hsl(142 76% 36% / 0.15)'
                              : currentVariant.status === 'scheduled'
                              ? 'hsl(217 91% 60% / 0.15)'
                              : 'hsl(var(--muted)/0.4)',
                          color:
                            currentVariant.status === 'published'
                              ? '#16a34a'
                              : currentVariant.status === 'scheduled'
                              ? '#2563eb'
                              : 'hsl(var(--muted-fg))',
                        }}
                      >
                        {currentVariant.status.toUpperCase()}
                      </span>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                        <BarChart2 size={14} />
                        Score: <strong>{currentVariant.engagement_score.toFixed(0)}/100</strong>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: 'hsl(var(--muted-fg))' }}>
                        <Clock size={14} />
                        {currentVariant.platform === 'video_script'
                          ? `~${currentVariant.estimated_read_time_sec}s speech`
                          : `~${currentVariant.estimated_read_time_sec}s read`}
                      </div>

                      {currentVariant.compliance_passed ? (
                        <span style={{ fontSize: '11px', color: '#16a34a', display: 'flex', alignItems: 'center', gap: '3px' }}>
                          <Check size={12} /> Compliant
                        </span>
                      ) : (
                        <span style={{ fontSize: '11px', color: '#ef4444', display: 'flex', alignItems: 'center', gap: '3px' }}>
                          <AlertCircle size={12} /> Limit exceeded
                        </span>
                      )}
                    </div>

                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        className="btn btn-secondary"
                        style={{ fontSize: '12px', padding: '6px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                        onClick={() => handleCopy(currentVariant.body, currentVariant.id)}
                      >
                        {copiedId === currentVariant.id ? <Check size={13} color="#16a34a" /> : <Copy size={13} />}
                        {copiedId === currentVariant.id ? 'Copied' : 'Copy'}
                      </button>

                      {currentVariant.status !== 'published' && (
                        <>
                          <button
                            className="btn btn-secondary"
                            style={{ fontSize: '12px', padding: '6px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                            onClick={() => {
                              setScheduleVariantId(currentVariant.id);
                              setScheduleDateTime(new Date(Date.now() + 86400000).toISOString().slice(0, 16));
                            }}
                          >
                            <Calendar size={13} />
                            Schedule
                          </button>

                          <button
                            className="btn btn-primary"
                            style={{ fontSize: '12px', padding: '6px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                            onClick={() => handlePublish(currentVariant.id)}
                          >
                            <Send size={13} />
                            Mark Published
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Twitter Thread View: Render Individual Tweet Cards */}
                  {currentVariant.platform === 'twitter_thread' ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {currentVariant.thread_tweets.map((tweet, idx) => (
                        <div
                          key={idx}
                          style={{
                            padding: '14px',
                            borderRadius: '6px',
                            border: '1px solid hsl(var(--border))',
                            backgroundColor: 'hsl(var(--background))',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                            <span style={{ fontSize: '12px', fontWeight: 600, color: '#1DA1F2' }}>
                              Tweet {idx + 1} of {currentVariant.thread_tweets.length}
                            </span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span
                                style={{
                                  fontSize: '11px',
                                  color: tweet.length <= 280 ? 'hsl(var(--muted-fg))' : '#ef4444',
                                  fontWeight: 500,
                                }}
                              >
                                {tweet.length}/280 chars
                              </span>
                              <button
                                className="btn btn-ghost"
                                style={{ padding: '2px 6px', fontSize: '11px' }}
                                onClick={() => handleCopy(tweet, `tweet-${idx}`)}
                              >
                                {copiedId === `tweet-${idx}` ? <Check size={11} color="#16a34a" /> : <Copy size={11} />}
                              </button>
                            </div>
                          </div>
                          <div style={{ fontSize: '13px', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{tweet}</div>
                        </div>
                      ))}
                    </div>
                  ) : currentVariant.platform === 'video_script' ? (
                    /* Video Script Teleprompter View */
                    <div
                      style={{
                        padding: '16px',
                        borderRadius: '6px',
                        backgroundColor: 'hsl(var(--background))',
                        border: '1px solid hsl(var(--border))',
                        fontFamily: 'monospace',
                        fontSize: '13px',
                        lineHeight: 1.6,
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {currentVariant.body}
                    </div>
                  ) : (
                    /* LinkedIn or Newsletter Markdown View */
                    <div
                      style={{
                        padding: '16px',
                        borderRadius: '6px',
                        backgroundColor: 'hsl(var(--background))',
                        border: '1px solid hsl(var(--border))',
                        fontSize: '13px',
                        lineHeight: 1.6,
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {currentVariant.body}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Modal: Create Campaign */}
      {showCampaignModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: 'hsl(var(--card))',
              borderRadius: '8px',
              border: '1px solid hsl(var(--border))',
              padding: '24px',
              width: '460px',
              maxWidth: '90%',
            }}
          >
            <h3 style={{ fontSize: '16px', fontWeight: 600, margin: '0 0 16px 0' }}>Create Content Campaign</h3>

            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Campaign Name</label>
              <input
                type="text"
                className="input"
                style={{ width: '100%', fontSize: '13px' }}
                value={newCampName}
                onChange={(e) => setNewCampName(e.target.value)}
                placeholder="e.g. Q4 Autonomous Workforce Launch"
              />
            </div>

            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Description</label>
              <textarea
                className="input"
                rows={2}
                style={{ width: '100%', fontSize: '13px' }}
                value={newCampDesc}
                onChange={(e) => setNewCampDesc(e.target.value)}
                placeholder="Target goals, cross-channel reach..."
              />
            </div>

            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Target Audience</label>
              <input
                type="text"
                className="input"
                style={{ width: '100%', fontSize: '13px' }}
                value={newCampAudience}
                onChange={(e) => setNewCampAudience(e.target.value)}
              />
            </div>

            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Objectives (comma separated)</label>
              <input
                type="text"
                className="input"
                style={{ width: '100%', fontSize: '13px' }}
                value={newCampObjectives}
                onChange={(e) => setNewCampObjectives(e.target.value)}
              />
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ fontSize: '12px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>Tags (comma separated)</label>
              <input
                type="text"
                className="input"
                style={{ width: '100%', fontSize: '13px' }}
                value={newCampTags}
                onChange={(e) => setNewCampTags(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="btn btn-secondary" onClick={() => setShowCampaignModal(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleCreateCampaign} disabled={!newCampName.trim()}>
                Create Campaign
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Schedule Post */}
      {scheduleVariantId && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: 'hsl(var(--card))',
              borderRadius: '8px',
              border: '1px solid hsl(var(--border))',
              padding: '20px',
              width: '380px',
            }}
          >
            <h3 style={{ fontSize: '15px', fontWeight: 600, margin: '0 0 12px 0' }}>Schedule Publication</h3>
            <p style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', margin: '0 0 14px 0' }}>
              Select target publication date and time:
            </p>
            <input
              type="datetime-local"
              className="input"
              style={{ width: '100%', fontSize: '13px', marginBottom: '16px' }}
              value={scheduleDateTime}
              onChange={(e) => setScheduleDateTime(e.target.value)}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="btn btn-secondary" onClick={() => setScheduleVariantId(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleScheduleSubmit}>
                Confirm Schedule
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
