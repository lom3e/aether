import type { Copy } from "@/content/home";
import { Rise } from "./Rise";

export function Teams({ c }: { c: Copy }) {
  const t = c.teams;
  return (
    <section className="ae-section" id="teams" style={{ paddingTop: 0 }}>
      <div className="ae-wrap">
        <Rise as="h2" className="ae-h2" style={{ maxWidth: "20ch" }}>{t.title}</Rise>
        <Rise as="p" i={1} className="ae-lead">{t.sub}</Rise>
        <div className="ae-teams-grid">
          {t.presets.map((p, i) => (
            <Rise key={p.name} className="ae-team" i={i}>
              <span className="nodes" aria-hidden="true"><i /><i /><i /><i /></span>
              <div>
                <h3>{p.name}</h3>
                <p className="ae-p" style={{ marginTop: 8 }}>{p.line}</p>
              </div>
            </Rise>
          ))}
          <Rise className="ae-teams-wide" i={0}>
            <h3 style={{ fontSize: 28, letterSpacing: "-0.03em" }}>{t.architect.title}</h3>
            <p className="ae-p" style={{ marginTop: 10, maxWidth: "46ch" }}>{t.architect.text}</p>
          </Rise>
          <Rise className="ae-teams-wide" i={1}>
            <span className="ae-badge">{t.community.badge}</span>
            <h3 style={{ fontSize: 28, letterSpacing: "-0.03em" }}>{t.community.title}</h3>
            <p className="ae-p" style={{ marginTop: 10, maxWidth: "46ch" }}>{t.community.text}</p>
          </Rise>
        </div>
      </div>
    </section>
  );
}
