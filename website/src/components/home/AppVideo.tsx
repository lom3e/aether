"use client";

import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";

interface Props {
  src: string;
  poster: string;
  label: string;
  caption: string;
  play: string;
  pause: string;
}

/** A real recording of the app, played muted on a loop while it is on screen (not at all with reduced motion; always pausable). */
export function AppVideo({ src, poster, label, caption, play, pause }: Props) {
  const ref = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const userPaused = useRef(false);

  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        const on = entries.some((e) => e.isIntersecting);
        if (on && !userPaused.current) v.play().catch(() => {});
        else if (!on) v.pause();
      },
      { threshold: 0.45 },
    );
    io.observe(v);
    return () => io.disconnect();
  }, []);

  const toggle = () => {
    const v = ref.current;
    if (!v) return;
    if (v.paused) {
      userPaused.current = false;
      v.play().catch(() => {});
    } else {
      userPaused.current = true;
      v.pause();
    }
  };

  return (
    <figure className="ae-video">
      <div className="ae-video-frame">
        <video
          ref={ref}
          src={src}
          poster={poster}
          muted
          loop
          playsInline
          preload="none"
          aria-label={label}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
        />
        <button className="ae-video-btn" onClick={toggle} aria-label={playing ? pause : play}>
          {playing ? <Pause size={20} /> : <Play size={20} />}
        </button>
      </div>
      <figcaption className="ae-p">{caption}</figcaption>
    </figure>
  );
}
