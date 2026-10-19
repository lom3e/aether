"use client";

import { useEffect } from "react";

const STORAGE_KEY = "aether_cookie_consent";
const SCRIPTS = [
  "/_vercel/insights/script.js", // Vercel Web Analytics: cookieless, aggregate
  "/_vercel/speed-insights/script.js", // Vercel Speed Insights: performance metrics
];

function analyticsAllowed(): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return !!raw && JSON.parse(raw).analytics === true;
  } catch {
    return false;
  }
}

/** Loads the (cookieless) Vercel measurement scripts only after the visitor accepted the "analytics" category. */
export function ConsentAnalytics() {
  useEffect(() => {
    const load = () => {
      if (!analyticsAllowed()) return;
      for (const src of SCRIPTS) {
        if (document.querySelector(`script[src="${src}"]`)) continue;
        const el = document.createElement("script");
        el.src = src;
        el.defer = true;
        document.head.appendChild(el);
      }
    };
    load();
    window.addEventListener("aether-consent-changed", load);
    return () => window.removeEventListener("aether-consent-changed", load);
  }, []);
  return null;
}
