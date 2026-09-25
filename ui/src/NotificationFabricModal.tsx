import { useState, useEffect } from 'react';
import {
  X,
  Radio,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  Send,
  Monitor,
  MessageSquare,
  Globe,
  Mail,
  Bell,
  Clock,
  RefreshCw,
  Volume2,
} from 'lucide-react';
import { apiUrl } from './api';

export interface ChannelConfig {
  id: string;
  workspace_id: string;
  channel_type: string;
  name: string;
  enabled: boolean;
  config: Record<string, any>;
  updated_at: string;
}

export interface RoutingRule {
  id: string;
  workspace_id: string;
  name: string;
  enabled: boolean;
  event_types: string[];
  min_priority: string;
  channels: string[];
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
}

export interface DeliveryReceiptItem {
  id: string;
  notification_id: string;
  workspace_id: string;
  channel_type: string;
  status: string;
  detail: string;
  latency_ms: number;
  timestamp: string;
}

interface NotificationFabricModalProps {
  workspaceName: string;
  isOpen: boolean;
  onClose: () => void;
}

export function NotificationFabricModal({
  workspaceName,
  isOpen,
  onClose,
}: NotificationFabricModalProps) {
  const [activeTab, setActiveTab] = useState<'channels' | 'rules' | 'history' | 'briefing'>('channels');
  const [channels, setChannels] = useState<ChannelConfig[]>([]);
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [receipts, setReceipts] = useState<DeliveryReceiptItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [testingChannel, setTestingChannel] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ channel: string; status: string; detail: string } | null>(null);

  // Briefing state
  const [briefingTitle, setBriefingTitle] = useState('Mission & Workforce Executive Update');
  const [briefingSummary, setBriefingSummary] = useState('Autonomous run completed across all agents with zero violations.');
  const [briefingHighlights, setBriefingHighlights] = useState('Milestone execution verified\nAmbient watchers active\nPerformance within SLA');
  const [dispatchingBriefing, setDispatchingBriefing] = useState(false);

  // Edit channel state
  const [editingChannel, setEditingChannel] = useState<string | null>(null);
  const [editUrl, setEditUrl] = useState('');
  const [editSound, setEditSound] = useState(true);

  const fetchChannels = async () => {
    if (!workspaceName) return;
    try {
      const res = await fetch(apiUrl(`/api/notifications/channels?workspace_id=${encodeURIComponent(workspaceName)}`));
      if (res.ok) {
        const data = await res.json();
        setChannels(data);
      }
    } catch (e) {
      console.error('Failed to load notification channels:', e);
    }
  };

  const fetchRules = async () => {
    if (!workspaceName) return;
    try {
      const res = await fetch(apiUrl(`/api/notifications/rules?workspace_id=${encodeURIComponent(workspaceName)}`));
      if (res.ok) {
        const data = await res.json();
        setRules(data);
      }
    } catch (e) {
      console.error('Failed to load notification rules:', e);
    }
  };

  const fetchReceipts = async () => {
    if (!workspaceName) return;
    try {
      const res = await fetch(apiUrl(`/api/notifications/deliveries?workspace_id=${encodeURIComponent(workspaceName)}&limit=30`));
      if (res.ok) {
        const data = await res.json();
        setReceipts(data);
      }
    } catch (e) {
      console.error('Failed to load delivery receipts:', e);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      Promise.all([fetchChannels(), fetchRules(), fetchReceipts()]).finally(() => setLoading(false));
    }
  }, [isOpen, workspaceName]);

  if (!isOpen) return null;

  const handleToggleChannel = async (channel: ChannelConfig) => {
    const updated = !channel.enabled;
    try {
      const res = await fetch(apiUrl('/api/notifications/channels'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceName,
          channel_type: channel.channel_type,
          enabled: updated,
        }),
      });
      if (res.ok) {
        setChannels(prev => prev.map(c => (c.channel_type === channel.channel_type ? { ...c, enabled: updated } : c)));
      }
    } catch (err) {
      console.error('Failed to toggle channel', err);
    }
  };

  const handleTestChannel = async (channelType: string) => {
    setTestingChannel(channelType);
    setTestResult(null);
    try {
      const res = await fetch(
        apiUrl(`/api/notifications/channels/${channelType}/test?workspace_id=${encodeURIComponent(workspaceName)}`),
        { method: 'POST' }
      );
      if (res.ok) {
        const data = await res.json();
        setTestResult({
          channel: channelType,
          status: data.status,
          detail: data.detail || `Test finished with status: ${data.status}`,
        });
        fetchReceipts();
      }
    } catch (err) {
      setTestResult({
        channel: channelType,
        status: 'failed',
        detail: String(err),
      });
    } finally {
      setTestingChannel(null);
    }
  };

  const handleSaveChannelConfig = async (channel: ChannelConfig) => {
    try {
      const newConfig = { ...channel.config };
      if (channel.channel_type === 'webhook') {
        newConfig.url = editUrl;
      } else if (channel.channel_type === 'desktop') {
        newConfig.sound_enabled = editSound;
      }

      const res = await fetch(apiUrl('/api/notifications/channels'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceName,
          channel_type: channel.channel_type,
          config: newConfig,
        }),
      });
      if (res.ok) {
        const saved = await res.json();
        setChannels(prev => prev.map(c => (c.channel_type === channel.channel_type ? saved : c)));
        setEditingChannel(null);
      }
    } catch (err) {
      console.error('Failed to update channel config', err);
    }
  };

  const handleDispatchBriefing = async () => {
    setDispatchingBriefing(true);
    try {
      const highlightsArray = briefingHighlights
        .split('\n')
        .map(h => h.trim())
        .filter(Boolean);

      const res = await fetch(apiUrl('/api/notifications/briefing'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceName,
          title: briefingTitle,
          summary: briefingSummary,
          highlights: highlightsArray,
          metrics: { status: 'success', active_agents: 4, memory_utilization: '42MB' },
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setTestResult({
          channel: 'fabric',
          status: 'sent',
          detail: `Briefing dispatched to: ${data.channels_dispatched?.join(', ') || 'configured channels'}`,
        });
        fetchReceipts();
      }
    } catch (err) {
      setTestResult({
        channel: 'fabric',
        status: 'failed',
        detail: String(err),
      });
    } finally {
      setDispatchingBriefing(false);
    }
  };

  const getChannelIcon = (type: string) => {
    switch (type) {
      case 'desktop':
        return <Monitor size={18} color="#3b82f6" />;
      case 'telegram':
        return <MessageSquare size={18} color="#0284c7" />;
      case 'webhook':
        return <Globe size={18} color="#8b5cf6" />;
      case 'email':
        return <Mail size={18} color="#ec4899" />;
      default:
        return <Bell size={18} color="#10b981" />;
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(6px)',
        zIndex: 2000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
      onClick={onClose}
    >
      <div
        className="card"
        style={{
          width: '740px',
          maxWidth: '95vw',
          maxHeight: '85vh',
          backgroundColor: 'hsl(var(--card))',
          borderRadius: '16px',
          border: '1px solid hsl(var(--border))',
          boxShadow: '0 20px 50px rgba(0, 0, 0, 0.35)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 24px',
            borderBottom: '1px solid hsl(var(--border))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'hsl(var(--muted)/0.25)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                backgroundColor: 'hsl(var(--primary)/0.12)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'hsl(var(--primary))',
              }}
            >
              <Radio size={20} />
            </div>
            <div>
              <h2 style={{ fontSize: '17px', fontWeight: 600, margin: 0 }}>
                Universal Notification Fabric
              </h2>
              <p style={{ fontSize: '12px', color: 'hsl(var(--muted-foreground))', margin: '2px 0 0' }}>
                Multi-channel delivery, automated briefings, and quiet hour routing rules
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'hsl(var(--muted-foreground))',
              padding: '4px',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div
          style={{
            display: 'flex',
            borderBottom: '1px solid hsl(var(--border))',
            padding: '0 24px',
            backgroundColor: 'hsl(var(--muted)/0.1)',
            gap: '8px',
          }}
        >
          {[
            { id: 'channels', label: 'Delivery Channels', icon: Radio },
            { id: 'rules', label: 'Routing & Rules', icon: Sliders },
            { id: 'briefing', label: 'Dispatch Briefing', icon: Send },
            { id: 'history', label: 'Delivery History', icon: Clock },
          ].map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id as any)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '12px 14px',
                  background: 'none',
                  border: 'none',
                  borderBottom: isActive ? '2px solid hsl(var(--primary))' : '2px solid transparent',
                  color: isActive ? 'hsl(var(--primary))' : 'hsl(var(--muted-foreground))',
                  fontWeight: isActive ? 600 : 500,
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Test Result Toast Banner */}
        {testResult && (
          <div
            style={{
              padding: '10px 24px',
              backgroundColor:
                testResult.status === 'sent' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
              borderBottom: '1px solid hsl(var(--border))',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '13px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {testResult.status === 'sent' ? (
                <CheckCircle2 size={16} color="#10b981" />
              ) : (
                <AlertTriangle size={16} color="#ef4444" />
              )}
              <span style={{ fontWeight: 500 }}>
                {testResult.channel.toUpperCase()}: {testResult.detail}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setTestResult(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '11px', color: 'hsl(var(--muted-foreground))' }}
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Body Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'hsl(var(--muted-foreground))' }}>
              <RefreshCw className="spin" size={24} style={{ margin: '0 auto 12px' }} />
              <div>Loading Notification Fabric state...</div>
            </div>
          ) : activeTab === 'channels' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div style={{ fontSize: '13px', color: 'hsl(var(--muted-foreground))', marginBottom: '4px' }}>
                Aether dispatches real system banners, Telegram messages, outgoing HTTP webhooks, and in-app alerts.
              </div>

              {channels.map(channel => {
                const isEditing = editingChannel === channel.channel_type;
                return (
                  <div
                    key={channel.id}
                    style={{
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '12px',
                      padding: '16px',
                      backgroundColor: channel.enabled ? 'hsl(var(--card))' : 'hsl(var(--muted)/0.2)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '12px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div
                          style={{
                            width: '34px',
                            height: '34px',
                            borderRadius: '8px',
                            backgroundColor: 'hsl(var(--muted)/0.6)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                        >
                          {getChannelIcon(channel.channel_type)}
                        </div>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '14px' }}>{channel.name}</div>
                          <div style={{ fontSize: '11px', color: 'hsl(var(--muted-foreground))' }}>
                            Type: <code>{channel.channel_type}</code> • Status: {channel.enabled ? 'Enabled' : 'Disabled'}
                          </div>
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <button
                          type="button"
                          onClick={() => handleTestChannel(channel.channel_type)}
                          disabled={testingChannel === channel.channel_type}
                          style={{
                            padding: '6px 12px',
                            borderRadius: '6px',
                            fontSize: '12px',
                            border: '1px solid hsl(var(--border))',
                            backgroundColor: 'hsl(var(--muted)/0.3)',
                            cursor: 'pointer',
                          }}
                        >
                          {testingChannel === channel.channel_type ? 'Testing...' : 'Test Channel'}
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            if (isEditing) {
                              setEditingChannel(null);
                            } else {
                              setEditingChannel(channel.channel_type);
                              setEditUrl(channel.config?.url || '');
                              setEditSound(channel.config?.sound_enabled ?? true);
                            }
                          }}
                          style={{
                            padding: '6px 10px',
                            borderRadius: '6px',
                            fontSize: '12px',
                            border: '1px solid hsl(var(--border))',
                            backgroundColor: 'transparent',
                            cursor: 'pointer',
                          }}
                        >
                          Configure
                        </button>

                        <button
                          type="button"
                          onClick={() => handleToggleChannel(channel)}
                          style={{
                            padding: '6px 12px',
                            borderRadius: '6px',
                            fontSize: '12px',
                            fontWeight: 500,
                            border: 'none',
                            backgroundColor: channel.enabled ? '#10b981' : 'hsl(var(--muted))',
                            color: channel.enabled ? '#fff' : 'hsl(var(--muted-foreground))',
                            cursor: 'pointer',
                          }}
                        >
                          {channel.enabled ? 'Active' : 'Enable'}
                        </button>
                      </div>
                    </div>

                    {/* Inline Channel Configuration Editor */}
                    {isEditing && (
                      <div
                        style={{
                          marginTop: '8px',
                          padding: '12px',
                          backgroundColor: 'hsl(var(--muted)/0.3)',
                          borderRadius: '8px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '10px',
                        }}
                      >
                        {channel.channel_type === 'webhook' && (
                          <div>
                            <label style={{ fontSize: '12px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
                              Webhook Endpoint URL (Slack / Discord / Custom POST)
                            </label>
                            <input
                              type="text"
                              value={editUrl}
                              onChange={e => setEditUrl(e.target.value)}
                              placeholder="https://hooks.slack.com/services/... or https://api.endpoint.com"
                              style={{
                                width: '100%',
                                padding: '8px 10px',
                                borderRadius: '6px',
                                border: '1px solid hsl(var(--border))',
                                backgroundColor: 'hsl(var(--background))',
                                color: 'hsl(var(--foreground))',
                                fontSize: '13px',
                              }}
                            />
                          </div>
                        )}

                        {channel.channel_type === 'desktop' && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Volume2 size={16} />
                            <label style={{ fontSize: '13px', cursor: 'pointer' }}>
                              <input
                                type="checkbox"
                                checked={editSound}
                                onChange={e => setEditSound(e.target.checked)}
                                style={{ marginRight: '6px' }}
                              />
                              Play system notification sound (macOS "Glass")
                            </label>
                          </div>
                        )}

                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                          <button
                            type="button"
                            onClick={() => setEditingChannel(null)}
                            style={{
                              padding: '5px 12px',
                              borderRadius: '6px',
                              border: '1px solid hsl(var(--border))',
                              background: 'transparent',
                              fontSize: '12px',
                              cursor: 'pointer',
                            }}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => handleSaveChannelConfig(channel)}
                            style={{
                              padding: '5px 14px',
                              borderRadius: '6px',
                              border: 'none',
                              backgroundColor: 'hsl(var(--primary))',
                              color: 'hsl(var(--primary-foreground))',
                              fontSize: '12px',
                              fontWeight: 500,
                              cursor: 'pointer',
                            }}
                          >
                            Save Settings
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : activeTab === 'rules' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div style={{ fontSize: '13px', color: 'hsl(var(--muted-foreground))' }}>
                Routing rules decide which events trigger multi-channel alerts and apply quiet hours filters.
              </div>

              {rules.map(rule => (
                <div
                  key={rule.id}
                  style={{
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '12px',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ fontWeight: 600, fontSize: '14px' }}>{rule.name}</div>
                    <span
                      className="badge"
                      style={{
                        backgroundColor: rule.enabled ? 'rgba(16, 185, 129, 0.15)' : 'rgba(156, 163, 175, 0.15)',
                        color: rule.enabled ? '#10b981' : '#9ca3af',
                      }}
                    >
                      {rule.enabled ? 'Active' : 'Disabled'}
                    </span>
                  </div>

                  <div style={{ fontSize: '12px', color: 'hsl(var(--muted-foreground))' }}>
                    Events: <code>{rule.event_types.join(', ')}</code> • Priority threshold:{' '}
                    <strong>{rule.min_priority}</strong>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '4px' }}>
                    <span style={{ fontSize: '12px', color: 'hsl(var(--muted-foreground))' }}>Target Channels:</span>
                    {rule.channels.map(ch => (
                      <span
                        key={ch}
                        style={{
                          fontSize: '11px',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          backgroundColor: 'hsl(var(--muted)/0.5)',
                        }}
                      >
                        {ch}
                      </span>
                    ))}
                  </div>

                  {rule.quiet_hours_enabled && (
                    <div style={{ fontSize: '11px', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={12} /> Quiet hours applied ({rule.quiet_hours_start} - {rule.quiet_hours_end})
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : activeTab === 'briefing' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div style={{ fontSize: '13px', color: 'hsl(var(--muted-foreground))' }}>
                Executive briefings compile mission outcomes, autonomous metrics, and actionable items into a rich card
                dispatched across enabled channels.
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
                  Briefing Title
                </label>
                <input
                  type="text"
                  value={briefingTitle}
                  onChange={e => setBriefingTitle(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid hsl(var(--border))',
                    backgroundColor: 'hsl(var(--background))',
                    color: 'hsl(var(--foreground))',
                    fontSize: '13px',
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
                  Executive Summary
                </label>
                <textarea
                  rows={3}
                  value={briefingSummary}
                  onChange={e => setBriefingSummary(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid hsl(var(--border))',
                    backgroundColor: 'hsl(var(--background))',
                    color: 'hsl(var(--foreground))',
                    fontSize: '13px',
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>
                  Key Highlights (one per line)
                </label>
                <textarea
                  rows={4}
                  value={briefingHighlights}
                  onChange={e => setBriefingHighlights(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid hsl(var(--border))',
                    backgroundColor: 'hsl(var(--background))',
                    color: 'hsl(var(--foreground))',
                    fontSize: '13px',
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
                <button
                  type="button"
                  onClick={handleDispatchBriefing}
                  disabled={dispatchingBriefing || !briefingTitle || !briefingSummary}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '10px 20px',
                    borderRadius: '8px',
                    border: 'none',
                    backgroundColor: 'hsl(var(--primary))',
                    color: 'hsl(var(--primary-foreground))',
                    fontWeight: 600,
                    fontSize: '13px',
                    cursor: 'pointer',
                  }}
                >
                  <Send size={16} />
                  {dispatchingBriefing ? 'Dispatching...' : 'Dispatch Executive Briefing'}
                </button>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ fontSize: '13px', color: 'hsl(var(--muted-foreground))', marginBottom: '6px' }}>
                Recent delivery receipts recorded by the notification dispatcher.
              </div>

              {receipts.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '30px', color: 'hsl(var(--muted-foreground))' }}>
                  No delivery receipts recorded yet.
                </div>
              ) : (
                <div style={{ border: '1px solid hsl(var(--border))', borderRadius: '10px', overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                    <thead>
                      <tr style={{ backgroundColor: 'hsl(var(--muted)/0.4)', textAlign: 'left' }}>
                        <th style={{ padding: '8px 12px' }}>Channel</th>
                        <th style={{ padding: '8px 12px' }}>Status</th>
                        <th style={{ padding: '8px 12px' }}>Latency</th>
                        <th style={{ padding: '8px 12px' }}>Detail</th>
                        <th style={{ padding: '8px 12px' }}>Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {receipts.map(rcpt => (
                        <tr key={rcpt.id} style={{ borderTop: '1px solid hsl(var(--border))' }}>
                          <td style={{ padding: '8px 12px', fontWeight: 600 }}>{rcpt.channel_type}</td>
                          <td style={{ padding: '8px 12px' }}>
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                                color:
                                  rcpt.status === 'sent'
                                    ? '#10b981'
                                    : rcpt.status === 'skipped'
                                    ? '#f59e0b'
                                    : '#ef4444',
                              }}
                            >
                              {rcpt.status === 'sent' ? (
                                <CheckCircle2 size={12} />
                              ) : (
                                <AlertTriangle size={12} />
                              )}
                              {rcpt.status.toUpperCase()}
                            </span>
                          </td>
                          <td style={{ padding: '8px 12px' }}>{rcpt.latency_ms.toFixed(1)}ms</td>
                          <td style={{ padding: '8px 12px', color: 'hsl(var(--muted-foreground))' }}>
                            {rcpt.detail || '-'}
                          </td>
                          <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                            {new Date(rcpt.timestamp).toLocaleTimeString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
