"use client";

import { usePlatform } from "@/lib/useOs";

export function PlatformText({ mac, pc }: { mac: string; pc: string }) {
  return <>{usePlatform() === "mac" ? mac : pc}</>;
}
