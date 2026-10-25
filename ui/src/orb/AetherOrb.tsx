import { useEffect, useRef, useCallback } from 'react';
import { OrbEngine, type OrbState, type QualityProfileKey } from './OrbEngine';
import { onVoiceLevel } from '../voice/voiceIO';
import './orb.css';

export interface AetherOrbProps {
  state?: OrbState;
  audioLevel?: number;
  quality?: QualityProfileKey;
  reducedMotion?: boolean;
  onClick?: () => void;
  onMetrics?: (metrics: { fps: number; frameTimeMs: string; particleCount: number; quality: string }) => void;
  size?: number;
  className?: string;
  interactive?: boolean;
  /** Use the engine's small-canvas layout (see OrbEngineOptions.compact). */
  compact?: boolean;
  /** Move with the live voice level (your microphone while you talk, Aether's voice while it answers). */
  followVoice?: boolean;
}

export function AetherOrb({
  state = 'idle',
  audioLevel = 0,
  quality = 'auto',
  reducedMotion,
  onClick,
  onMetrics,
  size = 640,
  className = '',
  interactive = true,
  compact = false,
  followVoice = false,
}: AetherOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const engineRef = useRef<OrbEngine | null>(null);
  const rafIdRef = useRef<number | null>(null);
  const isIntersectingRef = useRef<boolean>(true);

  // Initialize Engine
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const engine = new OrbEngine(canvas, {
      initialState: state,
      quality,
      reducedMotion,
      compact,
    });
    engineRef.current = engine;

    let lastMetricsTick = 0;

    const renderLoop = (time: number) => {
      if (isIntersectingRef.current) {
        engine.render(time);

        if (onMetrics && time - lastMetricsTick > 500) {
          lastMetricsTick = time;
          const m = engine.telemetry;
          onMetrics({
            fps: m.fps,
            frameTimeMs: m.frameTimeMs,
            particleCount: engine.particleCount,
            quality,
          });
        }
      }

      rafIdRef.current = requestAnimationFrame(renderLoop);
    };

    rafIdRef.current = requestAnimationFrame(renderLoop);

    // Responsive Canvas Resize Observer
    const ro = new ResizeObserver(() => {
      engine.setupCanvas();
    });
    ro.observe(canvas);

    // IntersectionObserver to pause loop when scrolled offscreen
    let io: IntersectionObserver | null = null;
    if (typeof IntersectionObserver !== 'undefined') {
      io = new IntersectionObserver((entries) => {
        const entry = entries[0];
        isIntersectingRef.current = entry ? entry.isIntersecting : true;
      });
      io.observe(canvas);
    }

    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
      }
      ro.disconnect();
      if (io) io.disconnect();
      engine.destroy();
      engineRef.current = null;
    };
  }, []);

  // Sync state
  useEffect(() => {
    if (engineRef.current) {
      engineRef.current.setState(state);
    }
  }, [state]);

  // Live voice level, straight to the engine (no React render per frame)
  useEffect(() => {
    if (!followVoice) return;
    return onVoiceLevel(level => engineRef.current?.setAudioLevel(level));
  }, [followVoice]);

  // Sync audio level
  useEffect(() => {
    if (engineRef.current) {
      engineRef.current.setAudioLevel(audioLevel);
    }
  }, [audioLevel]);

  // Sync quality
  useEffect(() => {
    if (engineRef.current) {
      engineRef.current.setQuality(quality);
    }
  }, [quality]);

  // Sync reduced motion
  useEffect(() => {
    if (engineRef.current && reducedMotion !== undefined) {
      engineRef.current.setReducedMotion(reducedMotion);
    }
  }, [reducedMotion]);

  const handleClick = useCallback(() => {
    if (engineRef.current) {
      engineRef.current.triggerMicroReaction();
    }
    if (onClick) {
      onClick();
    }
  }, [onClick]);

  return (
    <div
      className={`aether-orb-container ${className}`}
      style={{
        width: size,
        height: size,
        maxWidth: '92vw',
        maxHeight: '92vw',
      }}
    >
      <canvas
        ref={canvasRef}
        width={size}
        height={size}
        className="aether-orb-canvas"
        style={{
          cursor: interactive ? 'pointer' : 'default',
        }}
        onClick={interactive ? handleClick : undefined}
        title="Aether Presence"
      />
    </div>
  );
}
