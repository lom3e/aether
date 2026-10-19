"use client";

import { useEffect, useRef } from "react";
import { OrbEngine, type OrbState } from "./OrbEngine";

interface Props {
  state?: OrbState;
  /** The orb fills its parent; the parent decides the size. */
  className?: string;
  /** Small canvases use the engine's compact layout. */
  compact?: boolean;
  /** Let the sphere grow with its container (hero). */
  scale?: boolean;
  label?: string;
}

/**
 * The real Aether orb (same engine as the desktop Companion), as a client-only canvas. It draws nothing until it is
 * on screen, stops when scrolled away or when the tab is hidden, and honours prefers-reduced-motion. If a canvas
 * cannot be created the surrounding element keeps its static look (see .ae-orb-fallback).
 */
export function OrbCanvas({ state = "idle", className = "", compact = false, scale = false, label = "Aether orb" }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const engineRef = useRef<OrbEngine | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let engine: OrbEngine;
    try {
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      engine = new OrbEngine(canvas, { initialState: state, quality: "auto", reducedMotion: reduced, compact, scale });
    } catch {
      canvas.style.display = "none";
      return;
    }
    engineRef.current = engine;
    let raf = 0;
    let visible = true;
    // Phones: the big hero/footer orbs draw at ~30 fps so the main thread stays free for the page.
    const slow = scale && window.matchMedia("(max-width: 760px)").matches;
    let last = 0;
    let tabVisible = !document.hidden;
    const loop = (t: number) => {
      if (visible && tabVisible && (!slow || t - last > 33)) {
        last = t;
        engine.render(t);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    const ro = new ResizeObserver(() => engine.setupCanvas());
    ro.observe(canvas);
    const io = new IntersectionObserver((e) => {
      visible = e[0]?.isIntersecting ?? true;
    });
    io.observe(canvas);
    const onVis = () => {
      tabVisible = !document.hidden;
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
      engine.destroy();
      engineRef.current = null;
    };
    // The engine is created once; state changes are pushed by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    engineRef.current?.setState(state);
  }, [state]);

  return (
    <div className={`ae-orb ${className}`} role="img" aria-label={label}>
      <canvas ref={canvasRef} className="ae-orb-canvas" width={640} height={640} />
    </div>
  );
}
