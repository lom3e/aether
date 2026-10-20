/**
 * Screen Shield on the page side: the local OCR words of a capture -> regions with sensitive data (the local server, no
 * network) -> those regions pixelated in the image that is actually sent. Used by the manual capture review and by the
 * summon flow (hold the key and ask).
 */
import { apiUrl } from '../../api';
import { flattenToDataUrl, stripDataUrl, type Shape } from './annotations';
import type { OcrWord } from './captureBridge';

export interface ShieldRegion { x: number; y: number; w: number; h: number; kind: string }
export interface ShieldResult { regions: ShieldRegion[]; counts: Record<string, number> }

export async function fetchShieldRegions(words: OcrWord[]): Promise<ShieldResult> {
  const res = await fetch(apiUrl('/api/privacy/screen-shield'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ words }) });
  if (!res.ok) throw new Error(`shield ${res.status}`);
  const d = await res.json();
  return { regions: d.regions || [], counts: d.counts || {} };
}

export const regionShapes = (regions: ShieldRegion[]): Shape[] =>
  regions.map(g => ({ kind: 'blur' as const, x: g.x, y: g.y, w: g.w, h: g.h, label: g.kind, source: 'auto' as const }));

export interface ShieldedImage {
  url: string;
  base64: string;
  mediaType: string;
  width: number;
  height: number;
  hidden: number;
  kinds: string[];
  /** false when the local OCR was missing or failed: nothing was hidden automatically */
  ran: boolean;
  /** the text the OCR read (for models that cannot see images); empty when unavailable */
  text: string;
}

export async function shieldCapture(c: { imageBase64: string; mediaType: string; width: number; height: number; ocrWords: OcrWord[] | null }): Promise<ShieldedImage> {
  const plainUrl = `data:${c.mediaType};base64,${c.imageBase64}`;
  const base = { url: plainUrl, base64: c.imageBase64, mediaType: c.mediaType, width: c.width, height: c.height };
  if (!c.ocrWords) return { ...base, hidden: 0, kinds: [], ran: false, text: '' };
  const text = c.ocrWords.map(w => w.text).join(' ').slice(0, 6000);
  try {
    const r = await fetchShieldRegions(c.ocrWords);
    if (r.regions.length === 0) return { ...base, hidden: 0, kinds: [], ran: true, text };
    const url = await flattenToDataUrl(plainUrl, regionShapes(r.regions));
    return { ...base, url, base64: stripDataUrl(url), mediaType: 'image/png', hidden: r.regions.length, kinds: Object.keys(r.counts), ran: true, text };
  } catch {
    // Never send an image the shield could not check as if it had been checked.
    return { ...base, hidden: 0, kinds: [], ran: false, text: '' };
  }
}
