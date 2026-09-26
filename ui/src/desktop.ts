/**
 * Desktop Tauri IPC Bridge & Surface Negotiation for Aether.
 * Coordinates multi-surface communication between Full Workspace and Ambient Companion.
 */
import { invoke } from '@tauri-apps/api/core';
import {
  acknowledgeNotificationReceipt,
  resolveCanonicalTarget,
} from './canonicalNotification';

declare global {
  interface Window {
    __AETHER_SURFACE__?: 'workspace' | 'companion' | string;
    __TAURI_INTERNALS__?: any;
    __AETHER_RECENT_NOTIFICATIONS__?: Map<string, number>;
  }
}

export function isTauri(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    '__TAURI_INTERNALS__' in window ||
    window.location.protocol === 'tauri:' ||
    window.location.hostname === 'tauri.localhost'
  );
}

export function isCompanionSurface(): boolean {
  if (typeof window === 'undefined') return false;
  if (window.__AETHER_SURFACE__ === 'companion') return true;
  const params = new URLSearchParams(window.location.search);
  if (params.get('surface') === 'companion') return true;
  if (window.sessionStorage.getItem('aether_surface') === 'companion') return true;
  return false;
}

export async function hideCompanion(): Promise<void> {
  if (isTauri()) {
    try {
      await invoke('hide_companion');
    } catch (e) {
      console.warn('Could not hide companion via Tauri IPC:', e);
    }
  }
}

export async function showMainWindow(): Promise<void> {
  if (isTauri()) {
    try {
      await invoke('show_main_window');
    } catch (e) {
      console.warn('Could not show main window via Tauri IPC:', e);
    }
  }
}

export async function minimizeToCompanion(): Promise<void> {
  if (isTauri()) {
    try {
      await invoke('minimize_to_companion');
    } catch (e) {
      console.warn('Could not minimize to companion via Tauri IPC:', e);
    }
  }
}

export async function toggleCompanion(): Promise<void> {
  if (isTauri()) {
    try {
      await invoke('toggle_companion');
    } catch (e) {
      console.warn('Could not toggle companion via Tauri IPC:', e);
    }
  }
}

export async function quitAether(): Promise<void> {
  if (isTauri()) {
    try {
      await invoke('quit_aether');
    } catch (e) {
      console.warn('Could not quit Aether via Tauri IPC:', e);
    }
  }
}

export interface AetherNotificationOptions {
  id?: string;
  body?: string;
  sound?: string;
  link_view?: string;
  link_id?: string;
  target_type?: string;
  target_id?: string;
  deep_link?: string;
  source?: string;
  workspaceName?: string;
  metadata?: Record<string, any>;
  onClick?: () => void;
}

export interface ConsumedTarget {
  view: string;
  id: string | null;
  target_type?: string | null;
  target_id?: string | null;
  deep_link?: string | null;
  notification_id?: string | null;
}

export async function consumeNotificationTarget(): Promise<ConsumedTarget | null> {
  if (isTauri()) {
    try {
      const res = await invoke<any>('consume_notification_target');
      if (res) {
        // Handle CanonicalNotificationTarget struct
        if (typeof res === 'object' && !Array.isArray(res) && res.view) {
          return {
            view: res.view,
            id: res.id || res.target_id || null,
            target_type: res.target_type || null,
            target_id: res.target_id || null,
            deep_link: res.deep_link || null,
            notification_id: res.notification_id || null,
          };
        }
        // Handle legacy tuple [view, id]
        if (Array.isArray(res) && res[0]) {
          return {
            view: res[0],
            id: res[1] || null,
          };
        }
      }
    } catch (e) {
      console.debug('Error consuming notification target:', e);
    }
  }
  return null;
}

// In-memory deduplication map with 60-second TTL
const recentClientNotifications = new Map<string, number>();

function isClientDuplicate(key: string): boolean {
  const now = Date.now();
  for (const [k, time] of recentClientNotifications.entries()) {
    if (now - time > 60000) {
      recentClientNotifications.delete(k);
    }
  }
  const lastTime = recentClientNotifications.get(key);
  if (lastTime && now - lastTime < 30000) {
    return true;
  }
  recentClientNotifications.set(key, now);
  return false;
}

export async function notifyDesktop(
  title: string,
  options?: AetherNotificationOptions
): Promise<void> {
  if (typeof window === 'undefined') return;

  // Single Delivery Owner enforcement: Ambient Companion NEVER dispatches native OS notifications.
  if (isCompanionSurface()) {
    return;
  }

  // Deduplication check
  const dedupKey = options?.id || `${title}:${options?.body || ''}:${options?.target_type || ''}:${options?.target_id || ''}`;
  if (isClientDuplicate(dedupKey)) {
    return;
  }

  // 1. Primary path: Native Tauri notification with official com.aether.desktop bundle
  if (isTauri()) {
    try {
      const displayed = await invoke<boolean>('send_desktop_notification', {
        payload: {
          id: options?.id || null,
          title,
          body: options?.body || null,
          sound: options?.sound || 'Glass',
          link_view: options?.link_view || null,
          link_id: options?.link_id || null,
          target_type: options?.target_type || null,
          target_id: options?.target_id || null,
          deep_link: options?.deep_link || null,
          source: options?.source || 'workspace',
        },
      });

      if (displayed && options?.id) {
        acknowledgeNotificationReceipt(options.id, 'displayed', {
          workspaceName: options.workspaceName,
        });
      }
      return;
    } catch (e) {
      console.warn('Native desktop notification via Tauri IPC failed, falling back:', e);
    }
  }

  // 2. Web browser fallback: Web Notification API
  try {
    if ('Notification' in window) {
      const showWebNotif = () => {
        const notif = new Notification(title, {
          body: options?.body,
          icon: '/logo.png',
        });

        if (options?.id) {
          acknowledgeNotificationReceipt(options.id, 'displayed', {
            workspaceName: options.workspaceName,
          });
        }

        notif.onclick = () => {
          window.focus();
          if (options?.onClick) {
            options.onClick();
          } else {
            const resolved = resolveCanonicalTarget(options);
            window.dispatchEvent(
              new CustomEvent('aether:navigate', {
                detail: {
                  view: resolved.view,
                  id: resolved.params,
                  target_type: options?.target_type,
                  target_id: options?.target_id,
                },
              })
            );
          }
        };
      };

      if (Notification.permission === 'granted') {
        showWebNotif();
      } else if (Notification.permission !== 'denied') {
        const permission = await Notification.requestPermission();
        if (permission === 'granted') {
          showWebNotif();
        }
      }
    }
  } catch (e) {
    console.debug('Web desktop notification error:', e);
  }
}
