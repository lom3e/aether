"use client";

import { useState } from "react";
import type { Copy } from "@/content/home";
import { Rise } from "./Rise";

export function ScreenFlow({ c }: { c: Copy }) {
  const s = c.screen;
  const [tab, setTab] = useState(0);
  const step = s.steps[tab];

  return (
    <section className="ae-section" id="screen">
      <div className="ae-wrap ae-screen-grid">
        <div>
          <Rise as="h2" className="ae-h2">{s.title}</Rise>
          <Rise as="p" i={1} className="ae-lead">{s.sub}</Rise>
          <Rise i={2}>
            <div role="tablist" className="ae-tabs">
              {s.steps.map((st, i) => (
                <button key={st.tab} role="tab" aria-selected={tab === i} className="ae-tab" onClick={() => setTab(i)}>{st.tab}</button>
              ))}
            </div>
          </Rise>
          <div role="tabpanel">
            <h3 className="ae-step-title">{step.title}</h3>
            <p className="ae-p" style={{ marginTop: 16, maxWidth: "46ch" }}>{step.text}</p>
          </div>
          <div className="ae-promises">
            {s.promise.map((p) => (
              <span key={p}><span className="ae-dot" />{p}</span>
            ))}
          </div>
        </div>
        <Rise i={2} className="ae-stage">
          <div className="ae-ui" data-ui>
            {tab === 0 && (
              <>
                <div className="ae-choice sel"><i /><span><b>{s.ui.entire}</b><small>{s.ui.entireHint}</small></span></div>
                <div className="ae-choice"><i style={{ opacity: 0.5 }} /><span><b>{s.ui.area}</b><small>{s.ui.areaHint}</small></span></div>
              </>
            )}
            {tab >= 1 && (
              <>
                <small style={{ color: "var(--ae-mute)", fontWeight: 650 }}>{s.ui.preview}</small>
                <div className="ae-shot">
                  <div className="ae-shot-ui"><i className="a" /><i className="b" /><i /><i /></div>
                  <svg className="ae-arrow" viewBox="0 0 100 100" aria-label={s.ui.marks} role="img">
                    <path d="M8 92 L82 20 M82 20 L58 22 M82 20 L80 44" fill="none" stroke="#ff3b6b" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <div className="ae-field">{s.ui.ask}</div>
                {tab === 1 && <small style={{ color: "var(--ae-mute)" }}>{s.ui.sendTo}</small>}
                {tab === 1 && (
                  <div className="ae-row">
                    <span className="ae-mini">{s.ui.discard}</span>
                    <span className="ae-mini go">{s.ui.send}</span>
                  </div>
                )}
                {tab === 2 && <div className="ae-answer">{s.ui.answer}</div>}
              </>
            )}
          </div>
        </Rise>
      </div>
    </section>
  );
}
