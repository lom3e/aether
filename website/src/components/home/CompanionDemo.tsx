"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { Copy } from "@/content/home";
import { OrbCanvas } from "@/components/orb/OrbCanvas";
import type { OrbState } from "@/components/orb/OrbEngine";
import { Heading, Rise } from "./Rise";

const subscribeMotion = (cb: () => void) => {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};

function Typed({ text }: { text: string }) {
  const reduced = useSyncExternalStore(subscribeMotion, () => window.matchMedia("(prefers-reduced-motion: reduce)").matches, () => false);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const id = window.setInterval(() => setN((v) => (v >= text.length ? v : v + 2)), 22);
    return () => window.clearInterval(id);
  }, [text, reduced]);
  const shown = reduced ? text.length : n;
  return <>{text.slice(0, shown)}<span className="ae-caret" aria-hidden="true" style={{ opacity: shown < text.length ? 1 : 0 }} /></>;
}

type Phase = "idle" | "working" | "needs-you" | "done" | "rejected";

/** The live thing: a scripted Companion scene. The orb really changes state; the answers are written by hand and labelled as a demo. */
export function CompanionDemo({ c }: { c: Copy }) {
  const d = c.demo;
  const [pick, setPick] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const timer = useRef<number | null>(null);

  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  const start = (i: number) => {
    if (timer.current) window.clearTimeout(timer.current);
    setPick(i);
    setPhase("working");
    const sc = d.scenarios[i];
    timer.current = window.setTimeout(() => setPhase(sc.approval ? "needs-you" : "done"), 1700);
  };
  const decide = (ok: boolean) => setPhase(ok ? "done" : "rejected");
  const reset = () => { if (timer.current) window.clearTimeout(timer.current); setPick(null); setPhase("idle"); };

  const orb: OrbState = phase === "working" ? "working" : phase === "needs-you" ? "needs-you" : phase === "done" ? "done" : "idle";
  const label = phase === "rejected" ? d.states.idle : d.states[orb as "idle" | "working" | "needs-you" | "done"];
  const sc = pick !== null ? d.scenarios[pick] : null;

  return (
    <section className="ae-section ae-demo" id="demo">
      <div className="ae-wrap ae-demo-grid">
        <div>
          <Heading>{d.title}</Heading>
          <Rise as="p" i={1} className="ae-lead">{d.sub}</Rise>
          <Rise as="p" i={2} className="ae-demo-note">{d.note}</Rise>
        </div>
        <Rise i={2} className="ae-demo-stage">
          <span className="ae-demo-label">{d.label}</span>
          <div>
            <div className="ae-demo-orb">
              <OrbCanvas state={orb} compact label={label} />
            </div>
            <div className="ae-demo-state" aria-live="polite"><span className="ae-dot" />{label}</div>
          </div>
          <div className="ae-panel" data-ui>
            <div className="ae-panel-title">Aether</div>
            {sc && <div className="ae-msg user ae-pop" key={`u${pick}`}>{sc.ask}</div>}
            {sc && phase === "working" && <div className="ae-msg work">{sc.working}</div>}
            {sc && phase === "needs-you" && sc.approval && (
              <div className="ae-approval ae-pop">
                <b>{sc.approval.title}</b>
                <small>{sc.approval.detail}</small>
                <div className="ae-row">
                  <button className="ae-mini" onClick={() => decide(false)}>{d.reject}</button>
                  <button className="ae-mini go" onClick={() => decide(true)}>{d.approve}</button>
                </div>
              </div>
            )}
            {sc && phase === "done" && <div className="ae-msg bot"><span className="ae-sr">{sc.done}</span><span aria-hidden="true"><Typed key={`t${pick}`} text={sc.done} /></span></div>}
            {sc && phase === "rejected" && <div className="ae-msg bot">{d.rejected}</div>}
            {(phase === "done" || phase === "rejected") && <div className="ae-row"><button className="ae-mini" onClick={reset}>{d.reset}</button></div>}
            {phase === "idle" && (
              <div className="ae-chips" role="group" aria-label={d.placeholder}>
                {d.scenarios.map((s, i) => (
                  <button key={s.id} className="ae-mini go" onClick={() => start(i)}>{s.chip}</button>
                ))}
              </div>
            )}
          </div>
        </Rise>
      </div>
    </section>
  );
}
