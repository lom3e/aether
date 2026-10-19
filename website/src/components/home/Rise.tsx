"use client";

import { Fragment, useEffect, useRef, type CSSProperties, type ElementType, type ReactNode } from "react";

function useInView<T extends HTMLElement>(threshold = 0.12) {
  const ref = useRef<T | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      el.classList.add("in");
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          el.classList.add("in");
          io.disconnect();
        }
      },
      { threshold, rootMargin: "0px 0px -6% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return ref;
}

/** Entrance for the parts of a section: rises once when it enters the viewport. Content is visible without script. */
export function Rise({
  children, i = 0, as: Tag = "div", className = "", style, variant = "rise", id,
}: { children: ReactNode; i?: number; as?: ElementType; className?: string; style?: CSSProperties; variant?: "rise" | "wipe"; id?: string }) {
  const ref = useInView<HTMLElement>(variant === "wipe" ? 0.05 : 0.12);
  return (
    <Tag ref={ref} id={id} className={`ae-${variant} ${className}`} style={{ ["--i" as string]: i, ...style }}>
      {children}
    </Tag>
  );
}

/** A heading whose words slide up one after the other when it enters the viewport. */
export function Heading({ children, className = "ae-h2", style }: { children: string; className?: string; style?: CSSProperties }) {
  const ref = useInView<HTMLHeadingElement>(0.3);
  const words = children.split(" ");
  return (
    <h2 ref={ref} className={`${className} ae-words`} style={style} aria-label={children}>
      {words.map((w, k) => (
        <Fragment key={k}>
          <span className="ae-w" aria-hidden="true" style={{ ["--k" as string]: k }}>
            <span>{w}</span>
          </span>
          {k < words.length - 1 ? " " : ""}
        </Fragment>
      ))}
    </h2>
  );
}
