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
