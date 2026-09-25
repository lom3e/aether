/**
 * Desktop Tauri IPC Bridge & Surface Negotiation for Aether.
 * Coordinates multi-surface communication between Full Workspace and Ambient Companion.
 */
import { invoke } from '@tauri-apps/api/core';

declare global {
  interface Window {
    __AETHER_SURFACE__?: 'workspace' | 'companion' | string;
    __TAURI_INTERNALS__?: any;
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
  metadata?: Record<string, any>;
  onClick?: () => void;
}

export async function consumeNotificationTarget(): Promise<{ view: string; id: string | null } | null> {
  if (isTauri()) {
    try {
      const res = await invoke<[string, string | null] | null>('consume_notification_target');
      if (res && res[0]) {
        return { view: res[0], id: res[1] || null };
      }
    } catch (e) {
      console.debug('Error consuming notification target:', e);
    }
  }
  return null;
}

export async function notifyDesktop(
  title: string,
  options?: AetherNotificationOptions
): Promise<void> {
  if (typeof window === 'undefined') return;

  // 1. Primary path: Native Tauri notification with official app bundle icon and click routing
  if (isTauri()) {
    try {
      await invoke('send_desktop_notification', {
        payload: {
          id: options?.id || null,
          title,
          body: options?.body || null,
          sound: options?.sound || 'Glass',
          link_view: options?.link_view || null,
          link_id: options?.link_id || null,
        },
      });
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
        notif.onclick = () => {
          window.focus();
          if (options?.onClick) {
            options.onClick();
          } else if (options?.link_view) {
            window.dispatchEvent(
              new CustomEvent('aether:navigate', {
                detail: { view: options.link_view, id: options.link_id },
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

