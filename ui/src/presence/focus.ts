import { useCallback, useEffect, useRef, useState } from 'react';
import { apiUrl } from '../api';

export interface FocusState { active: boolean; started_at: number | null; until: number | null; remaining_s: number; minutes?: number; held: number }

/**
 * Concentrazione: while it is on, Aether keeps its nudges to itself (the server holds notifications, the orb asks nothing).
 * When the time is up the app ends it and `onEnded` receives what arrived meanwhile, to say it under the orb.
 */
export function useFocus(language: string, onEnded: (text: string) => void) {
  const [focus, setFocus] = useState<FocusState | null>(null);
  const endedRef = useRef(onEnded);
  endedRef.current = onEnded;
  const ending = useRef(false);

  const refresh = useCallback(async () => {
    const d = await fetch(apiUrl('/api/focus')).then(r => (r.ok ? r.json() : null)).catch(() => null);
    if (d) setFocus(d);
    return d as FocusState | null;
  }, []);

  const stop = useCallback(async () => {
    if (ending.current) return;
    ending.current = true;
    try {
      const d = await fetch(apiUrl(`/api/focus?language=${encodeURIComponent(language)}`), { method: 'DELETE' }).then(r => (r.ok ? r.json() : null)).catch(() => null);
      setFocus(f => (f ? { ...f, active: false, remaining_s: 0 } : f));
      if (d?.text) endedRef.current(d.text);
    } finally { ending.current = false; }
  }, [language]);

  const start = useCallback(async (minutes: number) => {
    const d = await fetch(apiUrl('/api/focus'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ minutes }) })
      .then(r => (r.ok ? r.json() : null)).catch(() => null);
    if (d) setFocus(d);
  }, []);

  useEffect(() => {
    void refresh().then(d => { if (d && !d.active && (d as any).ended) void stop(); }); // the time ran out while Aether was closed
    const id = window.setInterval(() => void refresh(), 60 * 1000);
    return () => window.clearInterval(id);
  }, [refresh, stop]);

  // the countdown: a tick every second while on, the end when the time is up
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!focus?.active) return;
    const id = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(id);
  }, [focus?.active]);
  const remaining = focus?.active && focus.until ? Math.max(0, focus.until - now) : 0;
  useEffect(() => {
    if (focus?.active && focus.until && now >= focus.until) void stop();
  }, [focus?.active, focus?.until, now, stop]);

  const total = focus?.active && focus.until && focus.started_at ? focus.until - focus.started_at : 0;
  return { focus: focus?.active ? focus : null, remaining, progress: total ? 1 - remaining / total : 0, start, stop, refresh };
}
