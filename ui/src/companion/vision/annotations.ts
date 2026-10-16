/**
 * Annotation geometry for screen understanding. All coordinates are NORMALIZED to the captured image (0..1 of its
 * width/height, origin top-left), so they mean the same thing at any display size. Pure functions: no DOM except
 * `flattenToDataUrl`, which draws on a canvas.
 */
export type ShapeKind = 'box' | 'highlight' | 'arrow' | 'point';
export type Tool = 'box' | 'highlight' | 'arrow';

export interface Shape {
  kind: ShapeKind;
  x: number;
  y: number;
  /** box/highlight: size. arrow: unused. */
  w: number;
  h: number;
  /** arrow: the tip. */
  x2?: number;
  y2?: number;
  label?: string;
  source: 'user' | 'model';
}

export interface Pt {
  x: number;
  y: number;
}

export const MIN_SIDE = 0.01;
export const MAX_MODEL_SHAPES = 8;
const TOL = 0.005;

export const clamp01 = (n: number): number => (Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0);

/** A pointer position inside an element -> normalized point (clamped to the image). */
export function toNormalized(clientX: number, clientY: number, rect: { left: number; top: number; width: number; height: number }): Pt {
  if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 };
  return { x: clamp01((clientX - rect.left) / rect.width), y: clamp01((clientY - rect.top) / rect.height) };
}

/** The shape a drag from `a` to `b` draws with `tool`; null when it is too small to be intentional. */
export function shapeFromDrag(tool: Tool, a: Pt, b: Pt): Shape | null {
  if (tool === 'arrow') {
    if (Math.hypot(b.x - a.x, b.y - a.y) < 0.03) return null;
    return { kind: 'arrow', x: a.x, y: a.y, w: 0, h: 0, x2: b.x, y2: b.y, source: 'user' };
  }
  const x = Math.min(a.x, b.x);
  const y = Math.min(a.y, b.y);
  const w = Math.abs(b.x - a.x);
  const h = Math.abs(b.y - a.y);
  if (w < MIN_SIDE || h < MIN_SIDE) return null;
  return { kind: tool, x, y, w, h, source: 'user' };
}

/**
 * Annotations returned by the backend are already validated there; this is a second, cheap guard so a malformed one
 * can never be drawn somewhere arbitrary. Out-of-range entries are dropped, never clamped into place.
 */
export function sanitizeModelShapes(raw: unknown): Shape[] {
  if (!Array.isArray(raw)) return [];
  const out: Shape[] = [];
  for (const r of raw) {
    if (out.length >= MAX_MODEL_SHAPES) break;
    if (!r || typeof r !== 'object') continue;
    const a = r as Record<string, unknown>;
    const nums = (...ks: string[]) => ks.map(k => a[k]);
    const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
    const label = typeof a.label === 'string' ? a.label.slice(0, 140) : '';
    if (a.kind === 'point') {
      const [x, y] = nums('x', 'y');
      if (finite(x) && finite(y) && x >= 0 && x <= 1 && y >= 0 && y <= 1) out.push({ kind: 'point', x, y, w: 0, h: 0, label, source: 'model' });
    } else if (a.kind === 'box') {
      const [x, y, w, h] = nums('x', 'y', 'w', 'h');
      if (finite(x) && finite(y) && finite(w) && finite(h) && x >= 0 && y >= 0 && w >= MIN_SIDE && h >= MIN_SIDE && x + w <= 1 + TOL && y + h <= 1 + TOL) {
        out.push({ kind: 'box', x, y, w: Math.min(w, 1 - x), h: Math.min(h, 1 - y), label, source: 'model' });
      }
    }
  }
  return out;
}

/** Normalized rect -> screen rect, given where the capture sat on the desktop (points). Null when it would leave the image. */
export function toScreenRect(
  s: Pick<Shape, 'x' | 'y' | 'w' | 'h'>,
  screen: { x: number; y: number; width: number; height: number },
): { x: number; y: number; width: number; height: number } | null {
  if (!(screen.width > 0 && screen.height > 0)) return null;
  if (s.x < 0 || s.y < 0 || s.x + s.w > 1 + TOL || s.y + s.h > 1 + TOL) return null;
  return { x: screen.x + s.x * screen.width, y: screen.y + s.y * screen.height, width: s.w * screen.width, height: s.h * screen.height };
}

const USER_COLOR = '#ff3b6b';
const HIGHLIGHT = 'rgba(255, 214, 10, 0.38)';

/** Draws the user's own marks onto the image so the model sees what they pointed at. Returns a PNG data URL. */
export async function flattenToDataUrl(imageUrl: string, shapes: Shape[]): Promise<string> {
  const img = await new Promise<HTMLImageElement>((resolve, reject) => {
    const el = new Image();
    el.onload = () => resolve(el);
    el.onerror = () => reject(new Error('image_load_failed'));
    el.src = imageUrl;
  });
  const W = img.naturalWidth;
  const H = img.naturalHeight;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('canvas_unavailable');
  ctx.drawImage(img, 0, 0, W, H);
  const lw = Math.max(3, Math.round(Math.min(W, H) / 220));
  ctx.lineWidth = lw;
  ctx.strokeStyle = USER_COLOR;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  for (const s of shapes) {
    if (s.source !== 'user') continue;
    if (s.kind === 'highlight') {
      ctx.fillStyle = HIGHLIGHT;
      ctx.fillRect(s.x * W, s.y * H, s.w * W, s.h * H);
    } else if (s.kind === 'box') {
      ctx.strokeRect(s.x * W, s.y * H, s.w * W, s.h * H);
    } else if (s.kind === 'arrow' && s.x2 !== undefined && s.y2 !== undefined) {
      const x1 = s.x * W, y1 = s.y * H, x2 = s.x2 * W, y2 = s.y2 * H;
      const ang = Math.atan2(y2 - y1, x2 - x1);
      const head = lw * 5;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.moveTo(x2, y2);
      ctx.lineTo(x2 - head * Math.cos(ang - Math.PI / 6), y2 - head * Math.sin(ang - Math.PI / 6));
      ctx.moveTo(x2, y2);
      ctx.lineTo(x2 - head * Math.cos(ang + Math.PI / 6), y2 - head * Math.sin(ang + Math.PI / 6));
      ctx.stroke();
    }
  }
  return canvas.toDataURL('image/png');
}

/** "data:image/png;base64,AAAA" -> "AAAA" */
export function stripDataUrl(dataUrl: string): string {
  const i = dataUrl.indexOf(',');
  return i >= 0 ? dataUrl.slice(i + 1) : dataUrl;
}
