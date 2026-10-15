/**
 * Bridge to the native Companion window (src-tauri/src/companion.rs). In a plain browser (tests, dev server)
 * every call is a safe no-op, so the same UI runs without Tauri.
 */
import { invoke } from '@tauri-apps/api/core';
import { isTauri } from '../desktop';

export type CompanionMode = 'orb' | 'panel';

export interface NativeCompanionInfo {
  mode: CompanionMode;
  follow: boolean;
  visible: boolean;
  platform: 'macos' | 'windows' | 'other';
}

export async function getNativeState(): Promise<NativeCompanionInfo | null> {
  if (!isTauri()) return null;
  try {
    return await invoke<NativeCompanionInfo>('companion_get_state');
  } catch (e) {
    console.warn('companion_get_state failed:', e);
    return null;
  }
}

export async function setNativeMode(mode: CompanionMode): Promise<void> {
  if (!isTauri()) return;
  try {
    await invoke('companion_set_mode', { mode });
  } catch (e) {
    console.warn('companion_set_mode failed:', e);
  }
}

export async function startNativeDrag(): Promise<void> {
  if (!isTauri()) return;
  try {
    await invoke('companion_start_drag');
  } catch (e) {
    console.warn('companion_start_drag failed:', e);
  }
}

export async function setNativeFollow(enabled: boolean): Promise<void> {
  if (!isTauri()) return;
  try {
    await invoke('companion_set_follow', { enabled });
  } catch (e) {
    console.warn('companion_set_follow failed:', e);
  }
}

/** The native side announces mode changes with a DOM event (no event-plugin permission needed). */
export function onNativeModeChange(handler: (mode: CompanionMode) => void): () => void {
  const listener = (e: Event) => {
    const mode = (e as CustomEvent<{ mode: CompanionMode }>).detail?.mode;
    if (mode === 'orb' || mode === 'panel') handler(mode);
  };
  window.addEventListener('aether-companion-mode', listener);
  return () => window.removeEventListener('aether-companion-mode', listener);
}
