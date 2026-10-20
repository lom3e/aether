/**
 * Bridge to the native screen capture (src-tauri/src/screen_capture.rs). Capture happens only when one of these calls
 * is made from an explicit user action; outside Tauri (tests, dev server) the platform simply reports "unsupported".
 */
import { invoke } from '@tauri-apps/api/core';
import { isTauri } from '../../desktop';

export type CapturePermission = 'granted' | 'denied' | 'unsupported';
export type CaptureMode = 'screen' | 'region';

export interface CaptureStatus {
  platform: 'macos' | 'windows' | 'other';
  supported: boolean;
  permission: CapturePermission;
}

export interface ScreenRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type CaptureErrorCode = 'permission_denied' | 'cancelled' | 'capture_failed' | 'unsupported' | 'too_large';

export interface OcrWord {
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export type CaptureResult =
  | { ok: true; imageBase64: string; mediaType: string; width: number; height: number; mode: CaptureMode; screen: ScreenRect | null; /** null: the local OCR was not available */ ocrWords: OcrWord[] | null }
  | { ok: false; error: CaptureErrorCode; detail: string };

const UNSUPPORTED: CaptureStatus = { platform: 'other', supported: false, permission: 'unsupported' };

export async function getCaptureStatus(): Promise<CaptureStatus> {
  if (!isTauri()) return UNSUPPORTED;
  try {
    return await invoke<CaptureStatus>('screen_capture_status');
  } catch {
    return UNSUPPORTED;
  }
}

export async function requestCapturePermission(): Promise<CaptureStatus> {
  if (!isTauri()) return UNSUPPORTED;
  try {
    return await invoke<CaptureStatus>('screen_capture_request_permission');
  } catch {
    return UNSUPPORTED;
  }
}

export async function openCaptureSettings(): Promise<void> {
  if (!isTauri()) return;
  try {
    await invoke('screen_capture_open_settings');
  } catch (e) {
    console.warn('screen_capture_open_settings failed:', e);
  }
}

export async function takeCapture(mode: CaptureMode): Promise<CaptureResult> {
  if (!isTauri()) return { ok: false, error: 'unsupported', detail: 'not running in the desktop app' };
  try {
    const r = await invoke<any>('screen_capture_take', { mode });
    if (r?.ok && r.image_base64 && r.width > 0 && r.height > 0) {
      return { ok: true, imageBase64: r.image_base64, mediaType: r.media_type || 'image/png', width: r.width, height: r.height, mode, screen: r.screen ?? null, ocrWords: Array.isArray(r.ocr?.words) ? r.ocr.words : null };
    }
    const code = (r?.error as CaptureErrorCode) || 'capture_failed';
    return { ok: false, error: code, detail: String(r?.detail ?? '') };
  } catch (e: any) {
    return { ok: false, error: 'capture_failed', detail: String(e?.message ?? e) };
  }
}

/** The screen read when the Companion was summoned with the hotkey (held once by the native side, in memory only). */
export async function takeSummonCapture(): Promise<Extract<CaptureResult, { ok: true }> | null> {
  if (!isTauri()) return null;
  try {
    const r = await invoke<any>('companion_take_context');
    if (r?.ok && r.image_base64 && r.width > 0 && r.height > 0) {
      return { ok: true, imageBase64: r.image_base64, mediaType: r.media_type || 'image/png', width: r.width, height: r.height, mode: 'screen', screen: r.screen ?? null, ocrWords: Array.isArray(r.ocr?.words) ? r.ocr.words : null };
    }
  } catch (e) {
    console.warn('companion_take_context failed:', e);
  }
  return null;
}
