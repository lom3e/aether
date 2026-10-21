"use client";

import { useEffect, useRef, useState } from "react";
import { OrbCanvas } from "@/components/orb/OrbCanvas";
import type { OrbState } from "@/components/orb/OrbEngine";

/**
 * The giant hero orb. It drifts and grows a little as you scroll, and answers the page: hovering or focusing the
 * download button makes it "listen" (the orb's own state, as in the app). Transform only, off when reduced motion.
 */
export function HeroOrb({ label }: { label: string }) {
  const wrap = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<OrbState>("idle");

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    const apply = () => {
      raf = 0;
      const y = Math.min(window.scrollY, 1400);
      if (wrap.current) wrap.current.style.transform = `translate3d(0, ${y * 0.18}px, 0) scale(${1 + y / 5200})`;
    };
    const on = () => { if (!raf) raf = requestAnimationFrame(apply); };
    window.addEventListener("scroll", on, { passive: true });
    return () => { window.removeEventListener("scroll", on); if (raf) cancelAnimationFrame(raf); };
  }, []);

  useEffect(() => {
    const on = (e: Event) => setState(((e as CustomEvent<OrbState>).detail || "idle") as OrbState);
    window.addEventListener("ae-orb", on);
    return () => window.removeEventListener("ae-orb", on);
  }, []);

  return (
    <div ref={wrap} className="ae-hero-orb-move">
      <OrbCanvas scale label={label} state={state} />
    </div>
  );
}

/** Props that make an element drive the hero orb while hovered or focused. */
export const orbHover = {
  onPointerEnter: () => window.dispatchEvent(new CustomEvent("ae-orb", { detail: "listening" })),
  onPointerLeave: () => window.dispatchEvent(new CustomEvent("ae-orb", { detail: "idle" })),
  onFocus: () => window.dispatchEvent(new CustomEvent("ae-orb", { detail: "listening" })),
  onBlur: () => window.dispatchEvent(new CustomEvent("ae-orb", { detail: "idle" })),
};
