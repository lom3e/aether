import { apiUrl } from './api';

export type NotificationTargetType =
  | 'mission'
  | 'action_execution'
  | 'automation'
  | 'deliverable'
  | 'approval'
  | 'task'
  | 'connection'
  | 'chat'
  | 'settings'
  | 'view';

export interface CanonicalNotificationTarget {
  notification_id?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  view: string;
  id?: string | null;
  deep_link?: string | null;
  created_at?: number;
}

export interface TargetResolutionResult {
  view: string;
  params: any;
  valid: boolean;
  reason?: string;
}

export interface ApprovalDecisionOptions {
  target_type?: string;
  target_id?: string;
  notification_id?: string;
  decision: 'approve' | 'reject';
  reason?: string;
  notes?: string;
  approver?: string;
  workspaceName?: string;
  endpoint?: string;
}

export interface ApprovalDecisionResult {
  success: boolean;
  status: 'approved' | 'rejected' | 'already_completed' | 'expired' | 'unauthorized' | 'failed';
  message: string;
  target_type?: string;
  target_id?: string;
  entity?: any;
}

/**
 * Validates and maps a canonical notification target (or raw notification payload)
 * to an internal application view and parameter payload.
 */
export function resolveCanonicalTarget(raw: any): TargetResolutionResult {
  if (!raw || typeof raw !== 'object') {
    return {
      view: 'home',
      params: null,
      valid: false,
      reason: 'Notification target payload is missing or invalid.',
    };
  }

  // 0. Canonical open_target object resolution (highest priority)
  if (raw.open_target && typeof raw.open_target === 'object' && raw.open_target.view) {
    return {
      view: raw.open_target.view,
      params: raw.open_target.params !== undefined ? raw.open_target.params : (raw.target_id || raw.link_id || null),
      valid: true,
    };
  }

  // 1. Deep Link resolution (e.g. aether://missions/m-123 or /missions/m-123)
  const deepLink = raw.deep_link;
  if (deepLink && typeof deepLink === 'string') {
    try {
      const clean = deepLink.replace(/^[a-z]+:\/\//i, '').replace(/^\//, '');
      const parts = clean.split('/');
      const section = parts[0]?.toLowerCase();
      const entityId = parts[1] || null;

      if (section) {
        switch (section) {
          case 'missions':
          case 'mission':
            return { view: 'missions', params: entityId, valid: true };
          case 'approvals':
          case 'approval':
            return { view: 'missions', params: entityId, valid: true };
          case 'actions':
          case 'action':
          case 'action_executions':
          case 'connections':
          case 'connection':
            return { view: 'connections', params: entityId, valid: true };
          case 'automations':
          case 'automation':
            return { view: 'automations', params: entityId, valid: true };
          case 'deliverables':
          case 'deliverable':
            return { view: 'missions', params: entityId, valid: true };
          case 'chat':
          case 'conversations':
            return { view: 'chat', params: entityId, valid: true };
          case 'settings':
            return { view: 'settings', params: null, valid: true };
          default:
            return { view: section, params: entityId, valid: true };
        }
      }
    } catch {
      // Fall through to target_type
    }
  }

  // 2. Canonical target_type & target_id resolution
  const targetType = (raw.target_type || '').toString().toLowerCase().trim();
  const targetId = raw.target_id || raw.id || raw.link_id || null;

  if (targetType) {
    switch (targetType) {
      case 'mission':
        return { view: 'missions', params: targetId, valid: true };
      case 'approval':
        // Approvals route to missions (which hosts the pending approval modal/card)
        return { view: 'missions', params: targetId, valid: true };
      case 'action_execution':
        // Action executions route to connections/audit feed
        return { view: 'connections', params: targetId, valid: true };
      case 'automation':
        return { view: 'automations', params: targetId, valid: true };
      case 'deliverable':
        return { view: 'missions', params: targetId, valid: true };
      case 'task':
        return { view: 'home', params: targetId, valid: true };
      case 'connection':
        return { view: 'connections', params: targetId, valid: true };
      case 'chat':
        return { view: 'chat', params: targetId, valid: true };
      case 'settings':
        return { view: 'settings', params: null, valid: true };
      case 'view':
        return {
          view: targetId || raw.link_view || 'home',
          params: raw.link_id || null,
          valid: Boolean(targetId || raw.link_view),
        };
      default:
        // Unknown target_type: fallback safely
        return {
          view: raw.link_view || 'home',
          params: targetId,
          valid: false,
          reason: `Unknown target_type: ${targetType}. Navigated to safe fallback.`,
        };
    }
  }

  // 3. Backward compatible link_view & link_id
  if (raw.link_view && typeof raw.link_view === 'string') {
    return {
      view: raw.link_view,
      params: raw.link_id || null,
      valid: true,
    };
  }

  // 4. View property from Tauri CanonicalNotificationTarget
  if (raw.view && typeof raw.view === 'string') {
    return {
      view: raw.view,
      params: raw.id || raw.target_id || null,
      valid: true,
    };
  }

  // 5. Default safe fallback
  return {
    view: 'home',
    params: null,
    valid: false,
    reason: 'Notification target is empty or unspecified. Returned to Home.',
  };
}

/**
 * Sends a delivery receipt status update back to the backend service.
 */
export async function acknowledgeNotificationReceipt(
  notificationId: string,
  status: 'displayed' | 'delivered_to_client' | 'failed' = 'displayed',
  options?: { detail?: string; workspaceName?: string }
): Promise<void> {
  if (!notificationId) return;
  try {
    const token =
      (typeof window !== 'undefined' && (window as any).__AETHER_SESSION_TOKEN__) || '';
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['X-Aether-Session-Token'] = token;
    }

    await fetch(apiUrl(`/api/notifications/${encodeURIComponent(notificationId)}/receipt`), {
      method: 'POST',
      headers,
      body: JSON.stringify({
        workspace_id: options?.workspaceName || undefined,
        channel_type: 'desktop',
        status,
        detail: options?.detail,
      }),
    });
  } catch (err) {
    console.debug('Failed to acknowledge notification receipt:', err);
  }
}

/**
 * Submits an approval decision (approve/reject) to the canonical backend approval router,
 * handling idempotency, error feedback, notification state, and optimistic status updates.
 */
export async function submitApprovalDecision(
  options: ApprovalDecisionOptions
): Promise<ApprovalDecisionResult> {
  const {
    target_type,
    target_id,
    notification_id,
    decision,
    reason,
    notes,
    approver = 'user',
    workspaceName,
    endpoint: customEndpoint,
  } = options;

  const tid = (target_id || notification_id || '').trim();
  if (!tid) {
    return {
      success: false,
      status: 'failed',
      message: 'Missing target ID for approval action.',
    };
  }

  // Determine endpoint
  let endpoint = customEndpoint;
  if (!endpoint) {
    if (target_type === 'mission' && target_id) {
      endpoint = `/api/missions/${encodeURIComponent(target_id)}/${decision}`;
    } else if (target_type === 'action_execution' && target_id) {
      endpoint = `/api/actions/executions/${encodeURIComponent(target_id)}/${decision}`;
    } else {
      endpoint = `/api/approvals/${encodeURIComponent(tid)}/${decision}`;
    }
  }

  try {
    const token =
      (typeof window !== 'undefined' && (window as any).__AETHER_SESSION_TOKEN__) || '';
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['X-Aether-Session-Token'] = token;
    }

    const bodyPayload: Record<string, any> = {
      target_type: target_type || undefined,
      approver,
      reason: reason || undefined,
      notes: notes || reason || undefined,
      workspace_id: workspaceName || undefined,
    };

    const res = await fetch(apiUrl(endpoint), {
      method: 'POST',
      headers,
      body: JSON.stringify(bodyPayload),
    });

    if (res.status === 401 || res.status === 403) {
      return {
        success: false,
        status: 'unauthorized',
        target_type,
        target_id: tid,
        message: 'You are not authorized to decide on this review.',
      };
    }

    if (res.status === 404) {
      const errData = await res.json().catch(() => ({}));
      return {
        success: false,
        status: 'failed',
        target_type,
        target_id: tid,
        message: errData.detail || `Review target '${tid}' was not found.`,
      };
    }

    if (res.status === 409) {
      const errData = await res.json().catch(() => ({}));
      return {
        success: true,
        status: 'already_completed',
        target_type,
        target_id: tid,
        message: errData.detail || 'This action has already been reviewed.',
      };
    }

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      return {
        success: false,
        status: 'failed',
        target_type,
        target_id: tid,
        message: errData.detail || `Approval decision failed (${res.status}).`,
      };
    }

    const data = await res.json().catch(() => ({}));
    const status = (data.status || (decision === 'approve' ? 'approved' : 'rejected')) as any;
    const defaultMsg =
      status === 'already_completed'
        ? 'This review was already completed.'
        : decision === 'approve'
        ? 'Review approved and executed.'
        : 'Review declined.';

    // If an associated notification ID is present, acknowledge it as displayed/read
    if (notification_id) {
      acknowledgeNotificationReceipt(notification_id, 'displayed', { workspaceName });
    }

    return {
      success: true,
      status,
      target_type: data.target_type || target_type,
      target_id: data.target_id || tid,
      message: data.message || defaultMsg,
      entity: data.entity || data.execution || data.mission,
    };
  } catch (err: any) {
    return {
      success: false,
      status: 'failed',
      target_type,
      target_id: tid,
      message: err.message || 'Network error while submitting approval decision.',
    };
  }
}
