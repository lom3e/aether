import { useRef, useState } from 'react';
import { shapeFromDrag, toNormalized, type Pt, type Shape, type Tool } from './annotations';

interface OverlayProps {
  shapes: Shape[];
  width: number;
  height: number;
}

/** Draws shapes on top of an image. Coordinates are normalized to the image, so this works at any display size. */
export function ShapesOverlay({ shapes, width, height }: OverlayProps) {
  return (
    <>
      <svg className="cmp-shapes" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
        {shapes.map((s, i) => {
          const cls = `cmp-shape ${s.source}`;
          if (s.kind === 'box') return <rect key={i} className={cls} x={s.x} y={s.y} width={s.w} height={s.h} vectorEffect="non-scaling-stroke" />;
          if (s.kind === 'highlight') return <rect key={i} className={`${cls} fill`} x={s.x} y={s.y} width={s.w} height={s.h} vectorEffect="non-scaling-stroke" />;
          if (s.kind === 'arrow' && s.x2 !== undefined && s.y2 !== undefined) {
            // The head is built in pixel space so it keeps its shape whatever the image's aspect ratio.
            const x1 = s.x * width, y1 = s.y * height, x2 = s.x2 * width, y2 = s.y2 * height;
            const a = Math.atan2(y2 - y1, x2 - x1);
            const head = Math.min(width, height) * 0.05;
            const hx = (ang: number) => (x2 - head * Math.cos(a + ang)) / width;
            const hy = (ang: number) => (y2 - head * Math.sin(a + ang)) / height;
            const d = `M ${s.x} ${s.y} L ${s.x2} ${s.y2} M ${hx(-0.5)} ${hy(-0.5)} L ${s.x2} ${s.y2} L ${hx(0.5)} ${hy(0.5)}`;
            return <path key={i} className={cls} d={d} fill="none" vectorEffect="non-scaling-stroke" />;
          }
          return null;
        })}
      </svg>
      {shapes.map((s, i) =>
        s.kind === 'point' ? (
          <span key={`p${i}`} className="cmp-point" style={{ left: `${s.x * 100}%`, top: `${s.y * 100}%` }} data-testid="vision-shape-point" />
        ) : null,
      )}
      {shapes.map((s, i) =>
        s.label ? (
          <span
            key={`l${i}`}
            className={`cmp-shape-label ${s.source}`}
            style={{ left: `${Math.min(s.x, 0.7) * 100}%`, top: `${(s.y < 0.1 ? s.y + (s.h || 0.02) : s.y) * 100}%`, transform: s.y < 0.1 ? 'none' : 'translateY(-100%)' }}
            data-testid="vision-shape-label"
          >
            {s.label}
          </span>
        ) : null,
      )}
    </>
  );
}

interface ViewProps extends OverlayProps {
  imageUrl: string;
  alt: string;
  className?: string;
  testId?: string;
}

export function AnnotatedImage({ imageUrl, alt, shapes, width, height, className, testId }: ViewProps) {
  return (
    <div className={`cmp-annotated ${className || ''}`} style={{ aspectRatio: `${width} / ${height}`, ['--ar' as any]: width / height }} data-testid={testId}>
      <img src={imageUrl} alt={alt} draggable={false} />
      <ShapesOverlay shapes={shapes} width={width} height={height} />
    </div>
  );
}

interface EditorProps {
  imageUrl: string;
  alt: string;
  width: number;
  height: number;
  tool: Tool;
  shapes: Shape[];
  onAdd: (s: Shape) => void;
}

/** The captured image with a drawing surface: drag to draw a box, highlight or arrow with the active tool. */
export function AnnotationEditor({ imageUrl, alt, width, height, tool, shapes, onAdd }: EditorProps) {
  const ref = useRef<HTMLDivElement>(null);
  const start = useRef<Pt | null>(null);
  const [draft, setDraft] = useState<Shape | null>(null);

  const point = (e: React.PointerEvent) => toNormalized(e.clientX, e.clientY, ref.current!.getBoundingClientRect());

  return (
    <div
      ref={ref}
      className="cmp-annotated editing"
      style={{ aspectRatio: `${width} / ${height}`, ['--ar' as any]: width / height, touchAction: 'none' }}
      data-testid="vision-preview"
      onPointerDown={e => {
        if (e.button !== 0) return;
        e.currentTarget.setPointerCapture(e.pointerId);
        start.current = point(e);
      }}
      onPointerMove={e => {
        if (!start.current) return;
        setDraft(shapeFromDrag(tool, start.current, point(e)));
      }}
      onPointerUp={e => {
        if (!start.current) return;
        const s = shapeFromDrag(tool, start.current, point(e));
        start.current = null;
        setDraft(null);
        if (s) onAdd(s);
      }}
      onPointerCancel={() => {
        start.current = null;
        setDraft(null);
      }}
    >
      <img src={imageUrl} alt={alt} draggable={false} />
      <ShapesOverlay shapes={draft ? [...shapes, draft] : shapes} width={width} height={height} />
    </div>
  );
}
