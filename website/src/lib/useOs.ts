"use client";

import { useSyncExternalStore } from "react";

export type Platform = "mac" | "pc";

/** "mac" only for a real Mac (not an iPhone/iPad, which report "Mac OS X" too); everything else is "pc". */
export function detectPlatform(ua: string, platform = "", touchPoints = 0): Platform {
  const u = ua.toLowerCase();
  if (/iphone|ipad|ipod|android|windows|linux|cros/.test(u)) return "pc";
  const isMac = /mac/i.test(platform) || /macintosh|mac os x/.test(u);
  // iPadOS 13+ reports itself as a Mac with a touch screen.
  if (isMac && touchPoints > 1) return "pc";
  return isMac ? "mac" : "pc";
}

const subscribe = () => () => {};
const client = (): Platform => {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } };
  return detectPlatform(nav.userAgent || "", nav.userAgentData?.platform || nav.platform || "", nav.maxTouchPoints || 0);
};

/** Server and first paint say "mac" (the product is macOS first); other systems switch right after hydration. */
export function usePlatform(): Platform {
  return useSyncExternalStore(subscribe, client, () => "mac");
}
