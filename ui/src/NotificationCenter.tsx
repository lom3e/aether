import { useState, useEffect, useRef } from 'react';
import { Bell, Check, Trash2, Shield, CheckCircle2, AlertTriangle, Sparkles, ExternalLink } from 'lucide-react';
import { apiUrl } from './api';

export interface NotificationItem {
  id: string;
  workspace_id: string;
  type: string;
  title: string;
  message: string;
  priority: string;
  status: string;
  link_view?: string;
  link_id?: string;
  action_required: boolean;
  metadata?: Record<string, any>;
  created_at: string;
}

interface NotificationCenterProps {
  workspaceName: string;
  onNavigate?: (view: string, params?: any) => void;
}

export function NotificationCenter({ workspaceName, onNavigate }: NotificationCenterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = async () => {
    if (!workspaceName) return;
    try {
      const res = await fetch(apiUrl(`/api/notifications/unread-count?workspace_id=${encodeURIComponent(workspaceName)}`));
      if (res.ok) {
        const data = await res.json();
        setUnreadCount(data.unread_count || 0);
      }
    } catch {
      // Ignore background network blips
    }
  };

  const fetchNotifications = async () => {
    if (!workspaceName) return;
    setLoading(true);
    try {
      const res = await fetch(apiUrl(`/api/notifications?workspace_id=${encodeURIComponent(workspaceName)}&limit=30`));
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setNotifications(data);
          const unread = data.filter((n: NotificationItem) => n.status === 'unread').length;
          setUnreadCount(unread);
        }
      }
    } catch (err) {
      console.error('Failed to load notifications', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 10000);
    return () => clearInterval(interval);
  }, [workspaceName]);

  // Handle outside click to close
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const handleToggle = () => {
    if (!isOpen) {
      fetchNotifications();
    }
    setIsOpen(prev => !prev);
  };

  const handleMarkAsRead = async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      const res = await fetch(apiUrl(`/api/notifications/${id}/read?workspace_id=${encodeURIComponent(workspaceName)}`), {
        method: 'POST',
      });
      if (res.ok) {
        setNotifications(prev => prev.map(n => n.id === id ? { ...n, status: 'read' } : n));
        setUnreadCount(prev => Math.max(0, prev - 1));
      }
    } catch (err) {
      console.error('Failed to mark read', err);
    }
  };

  const handleDismiss = async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      const res = await fetch(apiUrl(`/api/notifications/${id}/dismiss?workspace_id=${encodeURIComponent(workspaceName)}`), {
        method: 'POST',
      });
      if (res.ok) {
        const target = notifications.find(n => n.id === id);
        if (target && target.status === 'unread') {
          setUnreadCount(prev => Math.max(0, prev - 1));
        }
        setNotifications(prev => prev.filter(n => n.id !== id));
      }
    } catch (err) {
      console.error('Failed to dismiss', err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      const res = await fetch(apiUrl(`/api/notifications/read-all?workspace_id=${encodeURIComponent(workspaceName)}`), {
        method: 'POST',
      });
      if (res.ok) {
        setNotifications(prev => prev.map(n => ({ ...n, status: 'read' })));
        setUnreadCount(0);
      }
    } catch (err) {
      console.error('Failed to mark all read', err);
    }
  };

  const handleItemClick = (notif: NotificationItem) => {
    if (notif.status === 'unread') {
      handleMarkAsRead(notif.id);
    }
    if (notif.link_view && onNavigate) {
      onNavigate(notif.link_view, notif.link_id);
      setIsOpen(false);
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'approval_required':
        return <Shield size={16} color="#f59e0b" />;
      case 'task_completed':
      case 'action_completed':
        return <CheckCircle2 size={16} color="#10b981" />;
      case 'task_failed':
      case 'action_failed':
        return <AlertTriangle size={16} color="#ef4444" />;
      default:
        return <Sparkles size={16} color="hsl(var(--primary))" />;
    }
  };

  return (
    <div ref={dropdownRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        aria-label="Notifications"
        className="btn btn-ghost"
        onClick={handleToggle}
        data-testid="notification-bell-btn"
        style={{
          position: 'relative',
          padding: '8px',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Bell size={18} />
        {unreadCount > 0 && (
          <span
            data-testid="notification-badge"
            style={{
              position: 'absolute',
              top: '4px',
              right: '4px',
              minWidth: '16px',
              height: '16px',
              borderRadius: '8px',
              backgroundColor: 'hsl(var(--primary))',
              color: '#fff',
              fontSize: '10px',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '0 4px',
            }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          data-testid="notification-drawer"
          className="card"
          style={{
            position: 'absolute',
            right: 0,
            top: 'calc(100% + 8px)',
            width: '380px',
            maxHeight: '480px',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 12px 36px rgba(0,0,0,0.18)',
            borderRadius: '14px',
            zIndex: 1000,
            overflow: 'hidden',
            border: '1px solid hsl(var(--border))',
            backgroundColor: 'hsl(var(--card))',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '14px 18px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid hsl(var(--border))',
              backgroundColor: 'hsl(var(--muted)/0.3)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontWeight: 600, fontSize: '14px' }}>Notifications</span>
              {unreadCount > 0 && (
                <span className="badge badge-primary" style={{ fontSize: '11px', padding: '1px 6px' }}>
                  {unreadCount} new
                </span>
              )}
            </div>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'hsl(var(--primary))',
                  fontSize: '12px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                Mark all read
              </button>
            )}
          </div>

          {/* Body List */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
            {loading && notifications.length === 0 ? (
              <div style={{ padding: '32px', textAlign: 'center', color: 'hsl(var(--muted-fg))', fontSize: '13px' }}>
                Loading notifications...
              </div>
            ) : notifications.length === 0 ? (
              <div style={{ padding: '40px 20px', textAlign: 'center', color: 'hsl(var(--muted-fg))' }}>
                <CheckCircle2 size={32} style={{ margin: '0 auto 8px', opacity: 0.4 }} />
                <div style={{ fontSize: '14px', fontWeight: 500 }}>All caught up!</div>
                <div style={{ fontSize: '12px', marginTop: '4px' }}>No new notifications or pending actions.</div>
              </div>
            ) : (
              notifications.map(item => (
                <div
                  key={item.id}
                  onClick={() => handleItemClick(item)}
                  style={{
                    padding: '12px 16px',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    borderBottom: '1px solid hsl(var(--border)/0.4)',
                    cursor: item.link_view ? 'pointer' : 'default',
                    backgroundColor: item.status === 'unread' ? 'hsl(var(--primary)/0.04)' : 'transparent',
                    transition: 'background 0.15s ease',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.backgroundColor = 'hsl(var(--muted)/0.4)';
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.backgroundColor = item.status === 'unread' ? 'hsl(var(--primary)/0.04)' : 'transparent';
                  }}
                >
                  <div style={{ marginTop: '2px', flexShrink: 0 }}>
                    {getTypeIcon(item.type)}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                      <span style={{ fontSize: '13px', fontWeight: item.status === 'unread' ? 600 : 500, color: 'hsl(var(--fg))' }}>
                        {item.title}
                      </span>
                      <span style={{ fontSize: '10px', color: 'hsl(var(--muted-fg))', whiteSpace: 'nowrap' }}>
                        {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: 'hsl(var(--muted-fg))', marginTop: '2px', lineHeight: 1.4 }}>
                      {item.message}
                    </div>
                    {item.action_required && (
                      <div style={{ marginTop: '6px', display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <span style={{ fontSize: '11px', fontWeight: 600, color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <ExternalLink size={11} /> Requires Review
                        </span>
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flexShrink: 0 }}>
                    {item.status === 'unread' && (
                      <button
                        title="Mark as read"
                        onClick={e => handleMarkAsRead(item.id, e)}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: '4px',
                          cursor: 'pointer',
                          color: 'hsl(var(--muted-fg))',
                        }}
                      >
                        <Check size={13} />
                      </button>
                    )}
                    <button
                      title="Dismiss"
                      onClick={e => handleDismiss(item.id, e)}
                      style={{
                        background: 'none',
                        border: 'none',
                        padding: '4px',
                        cursor: 'pointer',
                        color: 'hsl(var(--muted-fg))',
                      }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
