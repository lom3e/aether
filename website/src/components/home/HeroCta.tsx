"use client";

import { orbHover } from "./HeroOrb";

export function HeroCta({ href, children }: { href: string; children: React.ReactNode }) {
  return <a className="ae-btn" href={href} {...orbHover}>{children}</a>;
}
